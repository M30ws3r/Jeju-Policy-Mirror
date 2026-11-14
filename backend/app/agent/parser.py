"""자연어 질문 → 분석 조건(PolicySpec). 규칙 기반이 1차, LLM 은 선택적 보조."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from ..config import Settings
from . import llm
from .data import ALL_INDUSTRY, DataBundle

_DATE = re.compile(r"(20\d{2})\s*(?:년|[.\-/])\s*(1[0-2]|0?[1-9])\s*월?")
_INDUSTRY_HINTS = {
    "식음료": ["식음료", "음식", "식당", "카페", "외식"],
    "소매": ["소매", "마트", "편의점"],
    "쇼핑": ["쇼핑"],
    "숙박": ["숙박", "호텔", "펜션"],
    "문화/레져": ["문화", "레져", "레저", "여가"],
    "교통": ["교통비", "주유", "렌터카"],
    "유흥": ["유흥"],
}


@dataclass
class PolicySpec:
    area: str | None = None
    policy_month: str | None = None
    industry: str = ALL_INDUSTRY
    policy_label: str = "정책 시행"
    missing: list[str] = field(default_factory=list)
    parsed_by: str = "rule"

    def as_dict(self) -> dict:
        return asdict(self)


def parse_question(question: str, bundle: DataBundle, settings: Settings, overrides: dict | None = None) -> PolicySpec:
    spec = PolicySpec()
    for area in sorted(bundle.areas, key=len, reverse=True):
        if area in question:
            spec.area = area
            break
    match = _DATE.search(question)
    if match:
        spec.policy_month = f"{match.group(1)}-{int(match.group(2)):02d}"
    for industry, hints in _INDUSTRY_HINTS.items():
        if industry in bundle.industries and any(h in question for h in hints):
            spec.industry = industry
            break
    if re.search(r"버스|노선|배차", question):
        spec.policy_label = "버스 노선 조정"

    if (spec.area is None or spec.policy_month is None) and llm.enabled(settings):
        extra = llm.extract_spec(settings, question, bundle.areas, bundle.industries)
        spec.area = spec.area or extra.get("area")
        spec.policy_month = spec.policy_month or extra.get("policy_month")
        if extra:
            spec.parsed_by = "rule+llm"

    # 사용자가 화면에서 직접 고친 값이 최우선 (허용 목록 검증은 스키마에서 끝남)
    for key in ("area", "policy_month", "industry"):
        value = (overrides or {}).get(key)
        if value:
            setattr(spec, key, value)

    if spec.area not in bundle.areas:
        spec.area = None
    if spec.industry != ALL_INDUSTRY and spec.industry not in bundle.industries:
        spec.industry = ALL_INDUSTRY
    if spec.area is None:
        spec.missing.append("area")
    if spec.policy_month is None:
        spec.missing.append("policy_month")
    return spec
