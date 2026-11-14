"""v2 지역 소비 수요 점검: 도민·관광객 소비 변화 차이가 크면 주의, A 등급은 B 로만 낮춘다."""
import pandas as pd

from app.agent import pipeline_bus_v2 as v2
from tests.test_pipeline_bus import _panel


def _card(res_drop: float, tour_drop: float) -> pd.DataFrame:
    months = [str(p) for p in pd.period_range("2022-12", "2025-07", freq="M")]
    rows = {"도민": [], "내국인 관광객": []}
    for m in months:
        post = m >= "2024-08"
        rows["도민"].append(100 * (1 + res_drop if post else 1))
        rows["내국인 관광객"].append(100 * (1 + tour_drop if post else 1))
    return pd.DataFrame(rows, index=months)


def test_similar_demand_keeps_grade():
    wide, cases = _panel(effect=-0.20)
    r = v2.run_case("c", cases, wide, wide, _card(-0.05, -0.06))
    assert r["verdict"]["level"] == "A"
    assert next(c for c in r["checks"] if c["id"] == "demand")["status"] == "pass"


def test_diverging_demand_downgrades_a_to_b_without_touching_estimate():
    wide, cases = _panel(effect=-0.20)
    base = v2.pipeline_bus.run_case("c", cases, wide, wide)
    r = v2.run_case("c", cases, wide, wide, _card(-0.02, -0.12))
    assert r["verdict"]["level"] == "B"
    assert r["estimates"]["did"] == base["estimates"]["did"]


def test_missing_card_returns_v1_result():
    wide, cases = _panel(effect=-0.20)
    r = v2.run_case("c", cases, wide, wide, None)
    assert all(c["id"] != "demand" for c in r["checks"])
