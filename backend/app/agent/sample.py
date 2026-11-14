"""합성 샘플 데이터 생성기.

실제 제주데이터허브 데이터가 아니다. 지명은 화면 이해를 돕기 위한 예시이며 수치는 전부 난수로 만든 값이다.
카드 데이터는 센터 밖 반출이 제한될 수 있어, 센터 밖에서는 이 샘플로 기능을 재현하고
센터 PC 에서는 DATA_MODE=real 로 실제 데이터를 읽도록 분리했다.

심어 둔 시나리오 (검증 로직 시연용)
- 함덕: 2024-07 '버스 노선 조정' → 버스 이용 +15%, 카드 소비 +6% (비교 조건 충족 → 효과 추정 가능)
- 성산: 2024-07 '버스 노선 조정' → 실제 효과 0. 다만 2023년부터 관광객 증가로 자체 상승 추세
        (사전 추세 불일치 → 인과효과 대신 연관성만 보고해야 하는 사례)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

AREAS = ["함덕", "성산", "애월", "한림", "중문", "표선", "대정", "구좌", "조천", "남원", "연동", "칠성로"]
INDUSTRIES = ["식음료", "소매", "쇼핑", "숙박", "문화/레져", "교통", "유흥"]
INDUSTRY_SHARE = {"식음료": 0.30, "소매": 0.22, "쇼핑": 0.14, "숙박": 0.16, "문화/레져": 0.08, "교통": 0.06, "유흥": 0.04}
LOCAL_INDUSTRIES = {"식음료", "소매", "쇼핑", "문화/레져", "교통", "유흥"}  # 숙박은 노선 조정 영향권 밖으로 가정
NEIGHBORS = {"함덕": ["조천"], "조천": ["함덕"], "성산": ["구좌"], "구좌": ["성산"]}
POLICY_MONTH = "2024-07"


def generate(seed: int = 20261112) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2022-01", "2025-12", freq="M")
    t = np.arange(len(months))
    moy = np.array([m.month for m in months])
    season = 0.18 * np.sin((moy - 4) / 12 * 2 * np.pi) + 0.06 * (moy == 8)   # 여름 성수기
    tourism = 0.05 * np.sin(t / 9.0) + 0.002 * t + rng.normal(0, 0.015, len(t)).cumsum() * 0.3  # 도 전체 관광 흐름
    post = np.array([str(m) >= POLICY_MONTH for m in months])

    card_rows, bus_rows, map_rows = [], [], []
    for i, area in enumerate(AREAS):
        base_card = rng.uniform(21.5, 23.5)          # log(월 카드 이용금액, 원)
        base_bus = rng.uniform(9.2, 10.4)            # log(월 버스 이용자 수)
        season_amp = rng.uniform(0.85, 1.15)
        tour_beta = rng.uniform(0.8, 1.2)
        own = rng.normal(0, 0.012, len(t))
        log_card = base_card + season_amp * season + tour_beta * tourism + own
        log_bus = base_bus + 0.5 * season_amp * season + 0.4 * tour_beta * tourism + rng.normal(0, 0.02, len(t))
        local_effect = np.zeros(len(t))
        if area == "함덕":
            local_effect = np.log(1.06) * post
            log_bus = log_bus + np.log(1.15) * post
        if area == "성산":
            log_card = log_card + 0.006 * np.clip(t - 12, 0, None)   # 2023-01 이후 자체 상승 추세
            log_bus = log_bus + np.log(1.12) * post

        for k, m in enumerate(months):
            for ind in INDUSTRIES:
                bump = local_effect[k] if ind in LOCAL_INDUSTRIES else 0.0
                amount = np.exp(log_card[k] + bump + rng.normal(0, 0.02)) * INDUSTRY_SHARE[ind]
                card_rows.append((area, str(m), ind, round(float(amount)), round(float(amount) / rng.uniform(18_000, 26_000))))

        routes = [f"{700 + i * 10 + r}" for r in range(2)]
        for r, route in enumerate(routes):
            map_rows.append((route, area))
            share = 0.6 if r == 0 else 0.4
            for k, m in enumerate(months):
                days = m.days_in_month
                monthly = np.exp(log_bus[k]) * share
                weights = rng.dirichlet(np.full(days, 60.0))
                for d in range(days):
                    bus_rows.append((route, f"{m}-{d + 1:02d}", int(round(monthly * weights[d]))))

    area_rows = [(a, ";".join(NEIGHBORS.get(a, []))) for a in AREAS]
    return {
        "card": pd.DataFrame(card_rows, columns=["area", "ym", "industry", "amount", "count"]),
        "bus": pd.DataFrame(bus_rows, columns=["route_no", "date", "riders"]),
        "route_map": pd.DataFrame(map_rows, columns=["route_no", "area"]),
        "areas": pd.DataFrame(area_rows, columns=["area", "neighbors"]),
    }
