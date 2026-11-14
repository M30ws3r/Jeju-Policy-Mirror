"""노선 단위 흐름 검증 — 실데이터가 아니라 정답을 심은 작은 합성 노선 표로 확인한다."""
import numpy as np
import pandas as pd

from app.agent import pipeline_bus as pb


def _panel(effect: float, trend: float = 0.0, seed: int = 7):
    rng = np.random.default_rng(seed)
    months = [str(p) for p in pd.period_range("2022-12", "2025-05", freq="M")]
    t = np.arange(len(months))
    post = np.array([m >= "2024-08" for m in months])
    season = 0.08 * np.sin(t / 12 * 2 * np.pi)
    data = {}
    for i in range(40):
        data[str(400 + i)] = np.exp(6 + rng.uniform(-1, 1) + season + rng.normal(0, 0.03, len(t)))
    data["311"] = np.exp(7 + season + trend * t + np.log(1 + effect) * post + rng.normal(0, 0.03, len(t)))
    wide = pd.DataFrame(data, index=months)
    cases = {"affected_list_complete": True, "known_affected": ["311"],
             "cases": {"c": {"label": "311번", "policy": "감차", "policy_month": "2024-08", "routes": ["311"]}}}
    return wide, cases


def test_planted_route_effect_is_recovered():
    wide, cases = _panel(effect=-0.20)
    r = pb.run_case("c", cases, wide, wide)
    did = r["estimates"]["did"]
    assert r["verdict"]["level"] == "A"
    assert did["ci_low"] < -20.0 < did["ci_high"] and did["ci_high"] < 0


def test_diverging_route_is_downgraded():
    wide, cases = _panel(effect=0.0, trend=-0.02)
    r = pb.run_case("c", cases, wide, wide)
    assert r["verdict"]["level"] == "C" and r["estimates"] == {}


def test_incomplete_case_table_caps_grade_at_b():
    wide, cases = _panel(effect=-0.20)
    cases["affected_list_complete"] = False
    r = pb.run_case("c", cases, wide, wide)
    assert r["verdict"]["level"] == "B"
    assert next(c for c in r["checks"] if c["id"] == "purity")["status"] == "warn"
