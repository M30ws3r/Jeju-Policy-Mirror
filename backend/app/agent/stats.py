"""통계 계산 (numpy 만 사용 — 외부 통계 패키지 의존 없음).

기본 추정량: 이중차분(DiD). 로그 결과변수에서 '대상 지역 − 비교 지역 평균' 격차(gap)를 만들고,
gap_t = a + b·post_t (+ 월 더미) 를 추정한다. b 가 정책 시점 전후 격차의 변화이며 exp(b)−1 이 % 효과다.
표준오차는 Newey–West HAC(자기상관·이분산 보정)로 구한다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Estimate:
    coef: float          # 로그 차이
    se: float
    p: float
    n: int

    @property
    def pct(self) -> float:
        return (math.exp(self.coef) - 1) * 100

    @property
    def ci_pct(self) -> tuple[float, float]:
        lo, hi = self.coef - 1.96 * self.se, self.coef + 1.96 * self.se
        return (math.exp(lo) - 1) * 100, (math.exp(hi) - 1) * 100

    @property
    def excludes_zero(self) -> bool:
        return abs(self.coef) > 1.96 * self.se

    def as_dict(self) -> dict:
        lo, hi = self.ci_pct
        return {"effect_pct": round(self.pct, 2), "ci_low": round(lo, 2), "ci_high": round(hi, 2),
                "p_value": round(self.p, 4), "n_months": self.n}


def _normal_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def ols_hac(X: np.ndarray, y: np.ndarray, col: int) -> Estimate:
    """OLS + Newey–West 표준오차. `col` 번째 계수의 추정치를 돌려준다."""
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    lags = int(math.floor(4 * (n / 100) ** (2 / 9)))
    xu = X * resid[:, None]
    s = xu.T @ xu
    for lag in range(1, lags + 1):
        w = 1 - lag / (lags + 1)
        g = xu[lag:].T @ xu[:-lag]
        s += w * (g + g.T)
    dof = max(n - k, 1)
    cov = xtx_inv @ s @ xtx_inv * (n / dof)
    se = float(math.sqrt(max(cov[col, col], 1e-18)))
    coef = float(beta[col])
    return Estimate(coef=coef, se=se, p=_normal_p(coef / se), n=n)


def _month_dummies(moy: np.ndarray) -> np.ndarray:
    present = sorted(set(moy.tolist()))[1:]            # 기준 월 1개 제외
    return np.column_stack([(moy == m).astype(float) for m in present]) if present else np.empty((len(moy), 0))


def did(gap: np.ndarray, post: np.ndarray, moy: np.ndarray | None = None) -> Estimate:
    """gap: 대상−비교 로그 격차 시계열, post: 정책 이후 여부. moy 를 주면 월(계절) 더미를 넣는다."""
    cols = [np.ones(len(gap)), post.astype(float)]
    X = np.column_stack(cols)
    if moy is not None:
        X = np.column_stack([X, _month_dummies(moy)])
    return ols_hac(X, gap, col=1)


def pretrend(gap_pre: np.ndarray) -> Estimate:
    """정책 이전 격차의 선형 추세(월당 로그 변화). 0 에 가까워야 평행추세 가정과 양립한다."""
    t = np.arange(len(gap_pre), dtype=float)
    X = np.column_stack([np.ones(len(t)), t - t.mean()])
    return ols_hac(X, gap_pre, col=1)


def placebo_in_time(gap_pre: np.ndarray) -> Estimate:
    """정책 이전 기간의 한가운데를 '가짜 시행일'로 두고 같은 추정을 반복한다. 효과가 잡히면 설계가 의심스럽다."""
    half = len(gap_pre) // 2
    fake_post = np.arange(len(gap_pre)) >= half
    return did(gap_pre, fake_post)


def similarity(target_pre: np.ndarray, cand_pre: np.ndarray) -> dict:
    """비교 지역 후보 점수: 정책 이전 기간의 월별 증감 상관(0.5) + 수준 궤적 근접도(0.5)."""
    d_t, d_c = np.diff(target_pre), np.diff(cand_pre)
    corr = float(np.corrcoef(d_t, d_c)[0, 1]) if d_t.std() > 0 and d_c.std() > 0 else 0.0
    dev = (target_pre - target_pre.mean()) - (cand_pre - cand_pre.mean())
    rmse = float(np.sqrt(np.mean(dev ** 2)))
    scale = float(target_pre.std()) or 1.0
    closeness = max(0.0, 1.0 - rmse / scale)
    return {"corr": round(corr, 3), "rmse": round(rmse, 4), "score": round(0.5 * max(corr, 0.0) + 0.5 * closeness, 3)}


def permutation_p(effect: float, placebo_effects: list[float]) -> float:
    """공간 플라시보: 정책이 없던 지역들에 같은 분석을 돌렸을 때, 대상 지역만큼 큰 값이 나오는 비율."""
    if not placebo_effects:
        return float("nan")
    bigger = sum(1 for e in placebo_effects if abs(e) >= abs(effect))
    return (1 + bigger) / (1 + len(placebo_effects))


def robust_scale(values: list[float]) -> float:
    """이상값에 둔감한 표준편차 추정(MAD×1.4826). 플라시보 지역 중 실제 충격을 받은 곳이 섞여도 덜 흔들린다."""
    arr = np.asarray(values, dtype=float)
    return float(1.4826 * np.median(np.abs(arr - np.median(arr))))


def conservative(est: Estimate, placebo_effects: list[float]) -> Estimate:
    """대상 지역이 1곳이면 HAC 표준오차가 과소 추정되기 쉽다.
    정책이 없던 지역들의 플라시보 효과 산포를 하한으로 삼아 더 넓은 쪽의 신뢰구간을 보고한다."""
    if len(placebo_effects) < 5:
        return est
    se = max(est.se, robust_scale(placebo_effects))
    return Estimate(coef=est.coef, se=se, p=_normal_p(est.coef / se), n=est.n)
