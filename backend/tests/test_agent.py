"""에이전트 통계·게이트 검증 (합성 샘플에 심어 둔 정답과 비교)."""
import numpy as np

from app.agent import llm, pipeline, stats
from app.agent.data import load_bundle
from app.config import get_settings

S = get_settings()
B = load_bundle("sample", str(S.data_dir))


def test_did_recovers_known_effect():
    rng = np.random.default_rng(1)
    post = np.arange(48) >= 30
    gap = 0.02 + 0.05 * post + rng.normal(0, 0.01, 48)
    est = stats.did(gap, post)
    assert abs(est.coef - 0.05) < 0.01 and est.excludes_zero


def test_pretrend_detects_diverging_trend():
    rng = np.random.default_rng(2)
    flat = rng.normal(0, 0.01, 30)
    assert stats.pretrend(flat).p > 0.05
    assert stats.pretrend(flat + 0.006 * np.arange(30)).p < 0.01


def test_valid_design_reports_effect_near_truth():
    r = pipeline.run("2024년 7월 함덕 버스 노선을 조정한 뒤 지역 소비가 늘었나요?", B, S)
    assert r["status"] == "done"
    assert r["verdict"]["level"] in {"A", "B"}
    did = r["estimates"]["did"]
    # 심어 둔 효과: 숙박(비중 16%)을 뺀 업종 +6% → 전체 업종 기준 약 +5.0%
    assert did["ci_low"] < 5.0 < did["ci_high"] and did["ci_low"] > 0
    assert "조천" in r["excluded_neighbors"] and "조천" not in [c["area"] for c in r["controls"]]
    assert r["estimates"]["mechanism_bus"]["ci_low"] > 0                    # 버스 이용 +15% 확인


def test_broken_design_is_downgraded_to_association_only():
    r = pipeline.run("2024년 7월 성산 버스 노선 조정으로 소비가 늘었나요?", B, S)
    assert r["verdict"]["level"] == "C"
    assert r["estimates"] == {}                                             # 인과 추정치 제거
    assert r["verdict"]["causal_language_allowed"] is False
    assert "추정하지 않았습니다" in r["verdict"]["statement"]
    assert any(c["id"] in {"pretrend", "placebo_time"} and c["status"] == "fail" for c in r["checks"])


def test_short_post_period_fails_span_gate():
    r = pipeline.run("2025년 11월 애월 버스 노선 조정 효과", B, S)
    assert r["verdict"]["level"] == "C"
    assert next(c for c in r["checks"] if c["id"] == "span")["status"] == "fail"


def test_question_without_area_asks_for_input():
    r = pipeline.run("버스 노선을 바꾸면 소비가 늘어?", B, S)
    assert r["status"] == "needs_input" and set(r["spec"]["missing"]) == {"area", "policy_month"}


def test_number_lock_rejects_invented_figures():
    src = "소비는 +6.2% (95% 신뢰구간 +3.1% ~ +9.4%) 변한 것으로 추정됩니다."
    assert llm.numbers_locked("소비가 6.2% 정도 늘었습니다 (3.1~9.4%).", src)
    assert not llm.numbers_locked("소비가 12% 늘었습니다.", src)


def test_untreated_area_shows_no_clear_effect():
    r = pipeline.run("2024년 7월 애월 버스 노선 조정 효과", B, S)   # 애월에는 아무 효과도 심지 않았다
    did = r["estimates"]["did"]
    assert did["ci_low"] < 0 < did["ci_high"]
    assert "말하기 어렵습니다" in r["verdict"]["statement"]
