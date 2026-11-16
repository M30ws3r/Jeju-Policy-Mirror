"""Vercel Python Function 진입점: backend 의 FastAPI 앱을 그대로 노출한다 (/api/* → 이 함수)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main_v3 import app  # noqa: E402,F401  (v3: 실데이터 사례 + 실데이터 문장 질문 API)
