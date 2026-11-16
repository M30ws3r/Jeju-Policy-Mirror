"""실행 진입점 v3: v2(사례 API) + 실데이터 문장 질문 API.

새 파일로 만든 이유: v2 의 사례 조회와 그 테스트를 그대로 두고, 실데이터로 '문장 질문 → 분석'을 하는
라우트만 덧붙이기 위해서다. 실행: uvicorn app.main_v3:app

추가 라우트 (DB 에 아무것도 저장하지 않는다. 결과에는 노선 단위 집계만 있다)
- POST /api/ask      {question, routes?, policy_month?} → 분석 결과
- POST /api/ask/pdf  같은 입력 → 노선용 정책 검토 PDF
"""
from __future__ import annotations

import re

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import main_v2
from .agent import parser_bus, pipeline_bus_v2, report_bus
from .main_v2 import app
from .security import RateLimiter, sanitize_text

_limiter = RateLimiter(limit=30, window_seconds=60)
_YM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
EXAMPLES = [
    "2024년 8월 감차 이후 311번 이용객은 얼마나 변했나요?",
    "2024년 8월 326번을 폐지하고 325번으로 합친 뒤 이용객은 유지됐나요?",
    "2024년 8월 개편 후 201번 이용객이 줄었나요?",
]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=2, max_length=300)
    routes: list[str] | None = Field(default=None, max_length=parser_bus.MAX_ROUTES)
    policy_month: str | None = Field(default=None, max_length=7)

    @field_validator("question")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = sanitize_text(v)
        if not v:
            raise ValueError("내용이 비어 있습니다")
        return v

    @field_validator("routes")
    @classmethod
    def _routes(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not all(re.fullmatch(r"\d{3}", r) for r in v):
            raise ValueError("노선 번호는 숫자 3자리여야 합니다")
        return v

    @field_validator("policy_month")
    @classmethod
    def _ym(cls, v: str | None) -> str | None:
        if not v:
            return None
        if not _YM.match(v):
            raise ValueError("YYYY-MM 형식이어야 합니다")
        return v


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _analyze(body: AskRequest, request: Request) -> dict:
    key = request.client.host if request.client else "unknown"
    if not _limiter.allow("ask:" + key):
        raise _fail(429, "too_many", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    panel = main_v2._panel()
    if panel is None:
        raise _fail(409, "no_real_data", "버스 실데이터가 아직 준비되지 않았습니다. 실행 매뉴얼의 수집 절차를 확인해 주세요.")
    weighted, weekday = panel
    months = list(weighted.index)
    known = set(weighted.columns)
    spec = parser_bus.parse(body.question, known, months[0], months[-1], body.routes, body.policy_month)

    options = {"first_month": months[1], "last_month": months[-1], "examples": EXAMPLES}
    if spec.missing:
        parts = []
        if "routes" in spec.missing:
            parts.append("분석할 노선 번호(예: 311번)를 찾지 못했습니다"
                         + (f" (데이터에 없는 번호: {', '.join(spec.unknown_routes)})" if spec.unknown_routes else ""))
        if "policy_month" in spec.missing:
            parts.append("정책 시행 연월(예: 2024년 8월)을 찾지 못했습니다")
        if "policy_month_range" in spec.missing:
            parts.append(f"시행 연월은 {months[1]} ~ {months[-1]} 사이여야 합니다")
        return {"status": "needs_input", "message": ". ".join(parts) + ".",
                "spec": {"routes": spec.routes, "policy_month": spec.policy_month, "missing": spec.missing}, "options": options}

    cases = main_v2._cases()
    label = "·".join(spec.routes) + "번" + (" 합산" if len(spec.routes) > 1 else "")
    adhoc = {**cases, "cases": {"ask": {"label": label, "policy": spec.policy_label, "policy_month": spec.policy_month,
                                        "routes": spec.routes, "question": body.question}}}
    result = pipeline_bus_v2.run_case("ask", adhoc, weighted, weekday, main_v2._cache.get("card"))
    result["steps"][0] = {"name": "질문 해석",
                          "summary": f"노선={', '.join(spec.routes)}, 시행월={spec.policy_month}, 정책={spec.policy_label} (규칙 해석)"
                                     + (f" / 데이터에 없어 제외한 번호: {', '.join(spec.unknown_routes)}" if spec.unknown_routes else "")}
    result["spec"]["parsed_by"] = "rule"
    result["options"] = options
    return result


@app.post("/api/ask")
def ask(body: AskRequest, request: Request):
    return _analyze(body, request)


@app.post("/api/ask/pdf")
def ask_pdf(body: AskRequest, request: Request):
    result = _analyze(body, request)
    if result["status"] != "done":
        raise _fail(422, "needs_input", result["message"])
    return Response(content=report_bus.build_pdf(result), media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="policy-review-ask.pdf"'})


__all__ = ["app"]
