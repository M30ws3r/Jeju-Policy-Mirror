"""실행 진입점 v2: 기존 앱(main.py) + 버스 실데이터 정책 사례 API.

새 파일로 만든 이유: main.py 의 기존 흐름(합성 샘플 질문 분석, 로그인, 결과 저장)과 그 보안 테스트를 건드리지 않고,
노선 단위 실데이터 사례 조회만 덧붙이기 위해서다. 실행: uvicorn app.main_v2:app

추가 라우트 (모두 GET, 사용자 입력은 허용 목록에 있는 사례 ID 뿐이며 DB 에 아무것도 저장하지 않는다)
- GET /api/cases             : 사례 목록과 실데이터 사용 가능 여부
- GET /api/cases/{case_id}     : 사례 분석 결과
- GET /api/cases/{case_id}/pdf : 노선용 정책 검토 PDF
"""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from fastapi import HTTPException, Request, Response

from .agent import pipeline_bus, pipeline_bus_v2, report_bus
from .config import get_settings
from .main import app
from .security import RateLimiter

log = logging.getLogger("jpm.cases")
_CASE_ID = re.compile(r"^[a-z0-9_]{1,40}$")
_settings = get_settings()
_CASES_PATH = _settings.data_dir / "policy_cases.json"
_PANEL_PATH = _settings.data_dir / "real" / "bus_monthly.csv"
_CARD_PATH = _settings.data_dir / "real" / pipeline_bus_v2.CARD_FILE  # 없으면 카드 점검 생략
_limiter = RateLimiter(limit=60, window_seconds=60)
_lock = threading.Lock()
_cache: dict = {"mtime": None, "panel": None, "results": {}}


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "not_found", "message": "사례를 찾을 수 없습니다."})


def _panel():
    """bus_monthly.csv 가 바뀌면(수집이 더 되면) 다시 읽고 결과 캐시를 비운다."""
    if not _PANEL_PATH.is_file():
        return None
    mtime = _PANEL_PATH.stat().st_mtime
    with _lock:
        if _cache["mtime"] != mtime:
            _cache["panel"] = pipeline_bus.load_panel(_PANEL_PATH)
            _cache["card"] = pipeline_bus_v2.load_card(_CARD_PATH)
            _cache["results"] = {}
            _cache["mtime"] = mtime
        return _cache["panel"]


def _cases() -> dict:
    return pipeline_bus.load_cases(_CASES_PATH)


def _result(case_id: str) -> dict:
    if not _CASE_ID.match(case_id):
        raise _not_found()
    cases = _cases()
    if case_id not in cases["cases"]:
        raise _not_found()
    panel = _panel()
    if panel is None:
        raise HTTPException(status_code=409, detail={"code": "no_real_data",
                                                     "message": "버스 실데이터가 아직 준비되지 않았습니다. 실행 매뉴얼의 수집 절차를 확인해 주세요."})
    with _lock:
        cached = _cache["results"].get(case_id)
    if cached is None:
        cached = pipeline_bus_v2.run_case(case_id, cases, *panel, _cache.get("card"))
        with _lock:
            _cache["results"][case_id] = cached
    return cached


def _guard(request: Request) -> None:
    key = request.client.host if request.client else "unknown"
    if not _limiter.allow("cases:" + key):
        raise HTTPException(status_code=429, detail={"code": "too_many", "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."})


@app.get("/api/cases")
def list_cases(request: Request):
    _guard(request)
    cases = _cases()
    items = [{"id": cid, "label": c["label"], "question": c.get("question", c["label"]),
              "policy": c["policy"], "policy_month": c["policy_month"]} for cid, c in cases["cases"].items()]
    return {"available": _PANEL_PATH.is_file(), "items": items}


@app.get("/api/cases/{case_id}")
def get_case(case_id: str, request: Request):
    _guard(request)
    return _result(case_id)


@app.get("/api/cases/{case_id}/pdf")
def get_case_pdf(case_id: str, request: Request):
    _guard(request)
    data = report_bus.build_pdf(_result(case_id))
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="policy-review-{case_id}.pdf"'})


__all__ = ["app"]
