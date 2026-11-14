"""FastAPI 앱. 실행: uvicorn app.main:app (HTTPS 설정은 docs/DEPLOY.md)"""
from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import pipeline, report
from .agent.data import ALL_INDUSTRY, DataError, load_bundle
from .config import Settings, get_settings
from .db import Analysis, AuditEvent, User, make_session_factory
from .schemas import AnalyzeRequest, Credentials
from .security import (TOKEN_TTL_MINUTES, FieldCipher, RateLimiter, blind_index, burn_password_check,
                       create_session_token, csrf_matches, hash_password, new_csrf_token,
                       read_session_token, verify_password)

log = logging.getLogger("jpm")
SESSION_COOKIE, CSRF_COOKIE = "jpm_session", "jpm_csrf"
_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_BODY_BYTES = 16 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    prod = settings.is_production
    app = FastAPI(title="Jeju Policy Mirror", docs_url=None if prod else "/docs", redoc_url=None,
                  openapi_url=None if prod else "/openapi.json")
    session_factory = make_session_factory(settings.database_url)
    app.state.session_factory = session_factory
    cipher = FieldCipher(settings.data_keys, settings.active_key_id)
    login_limiter = RateLimiter(limit=8, window_seconds=300)
    analyze_limiter = RateLimiter(limit=30, window_seconds=60)

    # ---------- 미들웨어 ----------
    if settings.trusted_hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],          # '*' 금지, 단일 출처
        allow_credentials=True,                        # 인증 쿠키 허용
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )

    @app.middleware("http")
    async def security_layer(request: Request, call_next):
        request.state.request_id = uuid.uuid4().hex
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if prod and proto != "https":                   # 평문 HTTP 는 처리하지 않는다
            return JSONResponse({"error": {"code": "https_required", "message": "HTTPS 로 접속해 주세요."}}, status_code=400)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"error": {"code": "too_large", "message": "요청이 너무 큽니다."}}, status_code=413)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        if not request.url.path.startswith(("/docs", "/openapi.json")):
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        if proto == "https":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    # ---------- 오류 응답: 내부 기술 정보는 숨기고 요청 ID 만 돌려준다 ----------
    def _error(request: Request, status: int, code: str, message: str, **extra) -> JSONResponse:
        body = {"error": {"code": code, "message": message, "request_id": getattr(request.state, "request_id", ""), **extra}}
        return JSONResponse(body, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        return _error(request, 422, "invalid_input", "입력값을 확인해 주세요.", fields=fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": "요청을 처리할 수 없습니다."}
        return _error(request, exc.status_code, detail["code"], detail["message"])

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", ""))
        return _error(request, 500, "server_error", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    def fail(status: int, code: str, message: str) -> HTTPException:
        return HTTPException(status_code=status, detail={"code": code, "message": message})

    # ---------- 의존성 ----------
    def db():
        with session_factory() as session:
            yield session

    def client_key(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for", "")
        return (fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else "unknown")

    def current_user(request: Request, session=Depends(db)) -> User | None:
        token = request.cookies.get(SESSION_COOKIE)
        user_id = read_session_token(settings, token) if token else None
        return session.get(User, user_id) if user_id else None

    def csrf_guard(request: Request) -> None:
        """쿠키 인증 요청의 상태 변경은 CSRF 토큰(쿠키=헤더)이 맞아야 한다."""
        if request.cookies.get(SESSION_COOKIE) and not csrf_matches(
                request.cookies.get(CSRF_COOKIE), request.headers.get("x-csrf-token")):
            raise fail(403, "csrf", "요청을 확인할 수 없습니다. 새로고침 후 다시 시도해 주세요.")

    def set_session(response: Response, user_id: str) -> str:
        csrf = new_csrf_token()
        common = {"secure": settings.cookie_secure, "samesite": settings.cookie_samesite,
                  "max_age": TOKEN_TTL_MINUTES * 60, "path": "/"}
        response.set_cookie(SESSION_COOKIE, create_session_token(settings, user_id), httponly=True, **common)
        response.set_cookie(CSRF_COOKIE, csrf, httponly=True, **common)
        return csrf

    def audit(session, request: Request, kind: str, user_id: str | None = None) -> None:
        session.add(AuditEvent(kind=kind, user_id=user_id, request_id=request.state.request_id))

    def bundle():
        return load_bundle(settings.data_mode, str(settings.data_dir))

    # ---------- 라우트 ----------
    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/meta")
    def meta(user: User | None = Depends(current_user)):
        b = bundle()
        return {"data_mode": b.mode, "data_label": b.label, "auth_required": settings.auth_required,
                "areas": b.areas, "industries": [ALL_INDUSTRY, *b.industries],
                "first_month": b.months[0], "last_month": b.months[-1], "signed_in": user is not None}

    @app.post("/api/auth/register", status_code=201)
    def register(body: Credentials, request: Request, response: Response, session=Depends(db)):
        if not login_limiter.allow("reg:" + client_key(request)):
            raise fail(429, "too_many", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        user = User(id=uuid.uuid4().hex, email_bidx=blind_index(settings.index_key, body.email),
                    password_hash=hash_password(body.password), email_enc="")
        user.email_enc = cipher.encrypt(body.email, aad=f"users.email:{user.id}")
        session.add(user)
        audit(session, request, "register", user.id)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # 가입 여부를 알려주지 않는 동일 응답 (계정 열거 방지)
            raise fail(400, "register_failed", "가입을 완료할 수 없습니다. 입력값을 확인하거나 로그인해 주세요.") from None
        return {"csrf_token": set_session(response, user.id)}

    @app.post("/api/auth/login")
    def login(body: Credentials, request: Request, response: Response, session=Depends(db)):
        bidx = blind_index(settings.index_key, body.email)
        if not (login_limiter.allow("ip:" + client_key(request)) and login_limiter.allow("acct:" + bidx)):
            raise fail(429, "too_many", "로그인 시도가 너무 많습니다. 5분 후 다시 시도해 주세요.")
        user = session.scalar(select(User).where(User.email_bidx == bidx))
        if user is None:
            burn_password_check(body.password)
            ok = False
        else:
            ok = verify_password(body.password, user.password_hash)
        audit(session, request, "login_ok" if ok else "login_fail", user.id if user else None)
        session.commit()
        if not ok:
            raise fail(401, "bad_credentials", "이메일 또는 비밀번호가 올바르지 않습니다.")
        return {"csrf_token": set_session(response, user.id)}

    @app.post("/api/auth/logout", dependencies=[Depends(csrf_guard)])
    def logout(response: Response):
        for name in (SESSION_COOKIE, CSRF_COOKIE):
            response.delete_cookie(name, path="/", secure=settings.cookie_secure, samesite=settings.cookie_samesite)
        return {"ok": True}

    @app.get("/api/auth/me")
    def me(response: Response, user: User | None = Depends(current_user)):
        if user is None:
            raise fail(401, "auth_required", "로그인이 필요합니다.")
        email = cipher.decrypt(user.email_enc, aad=f"users.email:{user.id}")
        name, _, domain = email.partition("@")
        return {"email_masked": f"{name[:2]}***@{domain}", "csrf_token": set_session(response, user.id)}

    @app.post("/api/analyze", dependencies=[Depends(csrf_guard)])
    def analyze(body: AnalyzeRequest, request: Request, user: User | None = Depends(current_user), session=Depends(db)):
        if settings.auth_required and user is None:
            raise fail(401, "auth_required", "로그인이 필요합니다.")
        if not analyze_limiter.allow("an:" + (user.id if user else client_key(request))):
            raise fail(429, "too_many", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
        b = bundle()
        if body.area is not None and body.area not in b.areas:
            raise fail(422, "invalid_input", "선택할 수 없는 지역입니다.")
        if body.industry is not None and body.industry not in (ALL_INDUSTRY, *b.industries):
            raise fail(422, "invalid_input", "선택할 수 없는 업종입니다.")
        overrides = {"area": body.area, "policy_month": body.policy_month, "industry": body.industry}
        try:
            result = pipeline.run(body.question, b, settings, overrides)
        except DataError as exc:
            raise fail(422, "data_issue", str(exc)) from None
        if result["status"] == "done":
            # 질문 원문은 암호화 컬럼에만 둔다 (result_json 에는 넣지 않는다)
            stored = {k: v for k, v in result.items() if k != "question"}
            record = Analysis(id=uuid.uuid4().hex, user_id=user.id if user else None, question_enc="",
                              result_json=json.dumps(stored, ensure_ascii=False))
            record.question_enc = cipher.encrypt(body.question, aad=f"analyses.question:{record.id}")
            session.add(record)
            audit(session, request, "analyze", user.id if user else None)
            session.commit()
            result["analysis_id"] = record.id
        return result

    def owned_analysis(analysis_id: str, user: User | None, session) -> Analysis:
        if not _ID.match(analysis_id):
            raise fail(404, "not_found", "결과를 찾을 수 없습니다.")
        record = session.get(Analysis, analysis_id)
        # 남의 결과는 '없음'으로 응답 (IDOR 방지). 비로그인 결과는 추측 불가한 ID 를 아는 사람만 접근.
        if record is None or (record.user_id is not None and (user is None or record.user_id != user.id)):
            raise fail(404, "not_found", "결과를 찾을 수 없습니다.")
        return record

    @app.get("/api/analyses")
    def history(user: User | None = Depends(current_user), session=Depends(db)):
        if user is None:
            raise fail(401, "auth_required", "로그인이 필요합니다.")
        rows = session.scalars(select(Analysis).where(Analysis.user_id == user.id)
                               .order_by(Analysis.created_at.desc()).limit(20)).all()
        out = []
        for r in rows:
            v = json.loads(r.result_json)
            out.append({"id": r.id, "created_at": r.created_at.isoformat(),
                        "question": cipher.decrypt(r.question_enc, aad=f"analyses.question:{r.id}"),
                        "level": v["verdict"]["level"]})
        return {"items": out}

    @app.get("/api/analyses/{analysis_id}/pdf")
    def pdf(analysis_id: str, user: User | None = Depends(current_user), session=Depends(db)):
        record = owned_analysis(analysis_id, user, session)
        result = json.loads(record.result_json)
        result["question"] = cipher.decrypt(record.question_enc, aad=f"analyses.question:{record.id}")
        data = report.build_pdf(result)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="policy-review-{analysis_id[:8]}.pdf"'})

    return app


app = create_app()
