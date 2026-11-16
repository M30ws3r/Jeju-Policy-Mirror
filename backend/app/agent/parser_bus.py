"""문장 질문 → 노선 단위 분석 조건 (실데이터용 질문 해석기).

새 파일로 만든 이유: 기존 parser.py 는 '지역·업종' 합성 샘플용이다. 실데이터 질문은 노선 번호와 시행 연월을 읽어야 한다.

읽는 것
- 노선: '326번', '325 번', '211·212번', '251-1번' 처럼 숫자 3자리(+선택 '-숫자'). 연도·월 숫자는 노선으로 보지 않는다.
- 시행 연월: '2024년 8월', '2024.8', '2024-08'
- 정책 종류: 감차·폐지·통합·신설·증차·개편 등 낱말 (판정문에 쓰는 이름표일 뿐, 계산에는 영향 없음)
여러 노선이 나오면 합산해 하나의 대상으로 본다(폐지 노선 + 통합 노선의 총량 비교에 해당).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_YM = re.compile(r"(20\d{2})\s*(?:년|[.\-/])\s*(1[0-2]|0?[1-9])(?:\s*월)?")
_ROUTE = re.compile(r"(?<![\d.\-/])(\d{3})(?:-\d{1,2})?(?=\s*(?:번|[·,/와과및 ]|$))")
_POLICY_WORDS = [("폐지", "노선 폐지"), ("통합", "노선 통합"), ("합치", "노선 통합"), ("합친", "노선 통합"), ("합쳐", "노선 통합"), ("감차", "버스 감차"),
                 ("증차", "버스 증차"), ("신설", "노선 신설"), ("개편", "노선 개편"), ("조정", "노선 조정")]
MAX_ROUTES = 12


@dataclass
class BusSpec:
    routes: list[str] = field(default_factory=list)
    unknown_routes: list[str] = field(default_factory=list)
    policy_month: str | None = None
    policy_label: str = "정책 시행"
    missing: list[str] = field(default_factory=list)


def parse(question: str, known_routes: set[str], first_month: str, last_month: str,
          routes_override: list[str] | None = None, month_override: str | None = None) -> BusSpec:
    spec = BusSpec()
    text = question
    m = _YM.search(text)
    if m:
        spec.policy_month = f"{m.group(1)}-{int(m.group(2)):02d}"
        text = text[:m.start()] + " " + text[m.end():]          # 연월 숫자를 노선으로 오인하지 않게 지운다
    if month_override:
        spec.policy_month = month_override

    found = routes_override if routes_override else [r for r in _ROUTE.findall(text)]
    seen: list[str] = []
    for r in found:
        if r not in seen:
            seen.append(r)
    seen = seen[:MAX_ROUTES]
    spec.routes = [r for r in seen if r in known_routes]
    spec.unknown_routes = [r for r in seen if r not in known_routes]

    labels = [label for word, label in _POLICY_WORDS if word in question]
    if labels:
        spec.policy_label = labels[0] if len(set(labels)) == 1 else "·".join(dict.fromkeys(labels))

    if not spec.routes:
        spec.missing.append("routes")
    if spec.policy_month is None:
        spec.missing.append("policy_month")
    elif not (first_month < spec.policy_month <= last_month):
        spec.missing.append("policy_month_range")
    return spec
