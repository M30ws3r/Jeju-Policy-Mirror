"""노선 단위 정책 검증 v2: v1(pipeline_bus.run_case) 결과에 '지역 소비 수요' 점검을 덧붙인다.

새 파일로 만든 이유: v1 의 통계·판정 로직과 그 테스트는 그대로 두고, 외부 공개 데이터
(제주관광공사 제주관광빅데이터플랫폼 '카드 관광 읍면동 리 월별 통계', 원천 BC카드, 공공누리 제1유형)를
쓰는 점검 한 가지만 추가하기 위해서다. 카드 파일이 없으면 v1 결과를 그대로 돌려준다.

점검 내용
- 시행 이후 12개월(전년 같은 달 대비) 동안 제주 전체 도민 카드 소비와 내국인 관광객 카드 소비가 각각 얼마나 변했는지 본다.
- 두 집단의 변화 폭 차이가 3%p 를 넘으면 '주의': 관광객 의존도가 높은 노선과 도민 의존도가 높은 노선이
  정책과 무관하게 서로 다르게 움직였을 수 있어, 비교 노선 대비 추정치에 관광 수요 변화가 섞였을 수 있다.
- 이 점검은 A 등급만 B 로 낮출 수 있고, 추정치는 바꾸지 않는다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import pipeline_bus

CARD_FILE = "card_emd_monthly_202212_202507.csv"
CARD_SOURCE = ("제주관광공사 제주관광빅데이터플랫폼 · 카드 관광 읍면동 리 월별 통계 (CSV, 원천 BC카드, 공공누리 제1유형) "
               "— 월×이용자 구분×읍면동으로 집계해 사용")
GAP_THRESHOLD = 3.0
RESIDENT, DOMESTIC = "도민", "내국인 관광객"


def load_card(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    df = pd.read_csv(path, dtype={"ym": str, "emd_code": str}, encoding="utf-8-sig")
    df["ym"] = df["ym"].str.slice(0, 4) + "-" + df["ym"].str.slice(4, 6)
    return df.pivot_table(index="ym", columns="user_type", values="amount", aggfunc="sum").sort_index()


def _yoy(series: pd.Series, policy_month: str) -> tuple[float | None, int]:
    post = [m for m in series.index if m >= policy_month][:12]
    pairs = [(m, f"{int(m[:4]) - 1}{m[4:]}") for m in post]
    pairs = [(a, b) for a, b in pairs if b in series.index]
    if not pairs:
        return None, 0
    cur = series[[a for a, _ in pairs]].sum()
    prev = series[[b for _, b in pairs]].sum()
    return (cur / prev - 1) * 100, len(pairs)


def run_case(case_id: str, cases: dict, weighted: pd.DataFrame, weekday: pd.DataFrame, card: pd.DataFrame | None) -> dict:
    result = pipeline_bus.run_case(case_id, cases, weighted, weekday)
    if card is None or RESIDENT not in card.columns or DOMESTIC not in card.columns:
        return result
    policy_month = result["spec"]["policy_month"]
    res, n1 = _yoy(card[RESIDENT], policy_month)
    dom, n2 = _yoy(card[DOMESTIC], policy_month)
    if res is None or dom is None:
        return result
    gap = dom - res
    warn = abs(gap) > GAP_THRESHOLD
    detail = (f"시행 후 {min(n1, n2)}개월간 전년 같은 달 대비 카드 소비: 도민 {res:+.1f}%, 내국인 관광객 {dom:+.1f}% "
              f"(차이 {gap:+.1f}%p)")
    detail += (" → 관광객이 많이 타는 노선과 도민 노선이 정책과 무관하게 다르게 움직였을 수 있음" if warn
               else " → 두 집단의 변화가 비슷해 관광 수요 차이로 인한 왜곡은 작을 것으로 봄")
    result["checks"].append({"id": "demand", "label": "지역 소비 수요 변화(카드 소비)", "status": "warn" if warn else "pass",
                             "detail": detail, "required": False})
    result["observed"]["card_resident_yoy_pct"] = round(res, 1)
    result["observed"]["card_domestic_tourist_yoy_pct"] = round(dom, 1)
    result["data_source"]["datasets"].append(CARD_SOURCE)
    result["limitations"].append("카드 소비 점검은 제주 전체 합계 기준입니다. 노선이 지나는 읍면동별 연결은 아직 반영하지 않았습니다.")

    verdict = result["verdict"]
    verdict["statement"] += (f" 참고로 같은 기간 제주 전체 카드 소비는 도민 {res:+.1f}%, 내국인 관광객 {dom:+.1f}% 변해, "
                             "버스 이용 변화의 일부는 지역 소비 수요 변화와 함께 움직였을 수 있습니다.")
    if verdict["level"] == "A" and warn:
        verdict["level"], verdict["title"] = "B", "잠정 추정 (주의 항목 있음)"
        verdict["statement"] += " 이 때문에 등급을 B로 낮췄습니다."
    result["steps"].insert(-1, {"name": "지역 수요 점검", "summary": f"도민 {res:+.1f}% / 내국인 관광객 {dom:+.1f}% (카드 소비)"})
    if result["steps"][-1]["name"] == "판정":
        result["steps"][-1]["summary"] = f"{verdict['level']} 등급 · {verdict['title']}"
    return result
