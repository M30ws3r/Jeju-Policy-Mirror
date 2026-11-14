"""에이전트 본체: 조건 해석 → 패널 구성 → 비교 지역 선정 → 추정 → 검증 게이트 → 판정문.

핵심 규칙(주장 강등 게이트)
- 필수 조건이 하나라도 깨지면 C 등급: 인과효과 추정치를 결과에서 제거하고 관측된 사실만 보고한다.
- 필수 조건은 통과했지만 보조 점검에 경고가 있으면 B 등급: 추정치를 '잠정'으로 표시한다.
- 전부 통과하면 A 등급: 준실험 근거가 충족된 추정치로 보고한다. (효과가 '있다'는 뜻이 아니라 '추정이 타당하다'는 뜻)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..config import Settings
from . import llm, stats
from .data import ALL_INDUSTRY, DataBundle, DataError, bus_panel, outcome_panel
from .parser import PolicySpec, parse_question

K_CONTROLS = 4
MIN_CONTROLS = 3
MIN_PRE, MIN_POST = 12, 3
NEGATIVE_CONTROL_INDUSTRY = "숙박"


def _r(value: float, digits: int = 2):
    return None if value is None or (isinstance(value, float) and not math.isfinite(value)) else round(float(value), digits)


def _pick_controls(log_wide: pd.DataFrame, target: str, pool: list[str], pre_mask: np.ndarray, k: int) -> list[dict]:
    t_pre = log_wide[target].to_numpy()[pre_mask]
    scored = [{"area": a, **stats.similarity(t_pre, log_wide[a].to_numpy()[pre_mask])} for a in pool]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:k]


def _gap(log_wide: pd.DataFrame, target: str, controls: list[str]) -> np.ndarray:
    return log_wide[target].to_numpy() - log_wide[controls].mean(axis=1).to_numpy()


def _check(cid: str, label: str, status: str, detail: str, required: bool) -> dict:
    return {"id": cid, "label": label, "status": status, "detail": detail, "required": required}


def run(question: str, bundle: DataBundle, settings: Settings, overrides: dict | None = None) -> dict:
    steps: list[dict] = []
    spec: PolicySpec = parse_question(question, bundle, settings, overrides)
    steps.append({"name": "질문 해석", "summary": f"지역={spec.area or '미확인'}, 시행월={spec.policy_month or '미확인'}, "
                                                   f"업종={spec.industry} ({spec.parsed_by})"})
    base = {
        "question": question,
        "spec": spec.as_dict(),
        "data_source": {"mode": bundle.mode, "label": bundle.label, "datasets": [
            "제주데이터허브 614 · 일일 노선별 버스 이용자 정보 (API)",
            "제주데이터허브 605 · 관광지·상업지구 업종별 카드 데이터 (API)"]},
        "options": {"areas": bundle.areas, "industries": [ALL_INDUSTRY, *bundle.industries],
                    "first_month": bundle.months[0], "last_month": bundle.months[-1]},
    }
    if spec.missing:
        return {**base, "status": "needs_input", "steps": steps,
                "message": "분석할 지역과 정책 시행 연월을 알려 주세요. 아래에서 직접 고를 수도 있습니다."}

    wide = outcome_panel(bundle, spec.industry)
    if spec.area not in wide.columns:
        raise DataError(f"'{spec.area}' 지역은 해당 업종의 월별 자료가 끊겨 있어 분석할 수 없습니다.")
    months = list(wide.index)
    if not (months[0] < spec.policy_month <= months[-1]):
        raise DataError(f"정책 시행월은 {months[1]} ~ {months[-1]} 사이여야 합니다.")
    log_wide = np.log(wide.clip(lower=1.0))
    post = np.array([m >= spec.policy_month for m in months])
    pre = ~post
    moy = np.array([int(m[5:7]) for m in months])
    n_pre, n_post = int(pre.sum()), int(post.sum())
    steps.append({"name": "데이터 구성", "summary": f"{len(wide.columns)}개 지역 × {len(months)}개월 패널 "
                                                    f"(시행 전 {n_pre}개월, 후 {n_post}개월)"})

    # ---- 비교 지역 선정 ----
    excluded = sorted(set(bundle.neighbors.get(spec.area, [])) & set(wide.columns))
    pool = [a for a in wide.columns if a != spec.area and a not in excluded]
    chosen = _pick_controls(log_wide, spec.area, pool, pre, K_CONTROLS) if n_pre >= 3 else []
    controls = [c["area"] for c in chosen]
    steps.append({"name": "비교 지역 선정", "summary": f"시행 전 흐름이 가장 비슷한 {len(controls)}곳: {', '.join(controls) or '없음'}"
                                                      + (f" / 인접 지역 제외: {', '.join(excluded)}" if excluded else "")})

    checks: list[dict] = []
    span_ok = n_pre >= MIN_PRE and n_post >= MIN_POST
    checks.append(_check("span", "관측 기간", "pass" if span_ok else "fail",
                         f"시행 전 {n_pre}개월(기준 {MIN_PRE}), 시행 후 {n_post}개월(기준 {MIN_POST})", True))
    ctrl_ok = len(controls) >= MIN_CONTROLS
    checks.append(_check("controls", "비교 지역 수", "pass" if ctrl_ok else "fail",
                         f"{len(controls)}곳 확보 (기준 {MIN_CONTROLS}곳)", True))

    estimates: dict = {}
    primary = None
    series: dict = {}
    if span_ok and ctrl_ok:
        gap = _gap(log_wide, spec.area, controls)
        plain = stats.did(gap, post)
        seasonal = stats.did(gap, post, moy) if n_pre >= 24 else None
        raw_primary = seasonal or plain
        # 공간 플라시보: 정책이 없던 지역마다 같은 분석을 반복한다 (신뢰구간 보정과 순위 검정에 함께 쓴다)
        placebo_effects = []
        for other in pool:
            rest = [a for a in pool if a != other]
            if len(rest) < MIN_CONTROLS:
                continue
            o_ctrl = [c["area"] for c in _pick_controls(log_wide, other, rest, pre, K_CONTROLS)]
            placebo_effects.append(stats.did(_gap(log_wide, other, o_ctrl), post, moy if seasonal else None).coef)
        primary = stats.conservative(raw_primary, placebo_effects)
        widened = primary.se > raw_primary.se
        estimates["did"] = {**primary.as_dict(), "method": "계절(월) 보정 이중차분" if seasonal else "이중차분",
                            "ci_method": "플라시보 지역 산포로 넓힌 보수적 구간" if widened else "Newey–West HAC"}
        estimates["did_unadjusted"] = plain.as_dict()

        # 필수: 사전 추세
        trend = stats.pretrend(gap[pre])
        status = "pass" if trend.p >= 0.10 else ("warn" if trend.p >= 0.05 else "fail")
        checks.append(_check("pretrend", "시행 전 추세 일치(평행추세)", status,
                             f"시행 전 격차의 월별 기울기 {trend.coef * 100:+.2f}%p (p={trend.p:.3f})", True))
        # 필수: 시간 플라시보
        fake = stats.placebo_in_time(gap[pre])
        checks.append(_check("placebo_time", "가짜 시행일 점검", "fail" if fake.excludes_zero else "pass",
                             f"시행 전 기간 한가운데를 시행일로 가정한 추정 {fake.pct:+.1f}% "
                             f"({'0과 구분됨 → 설계 의심' if fake.excludes_zero else '0과 구분되지 않음'})", True))
        # 보조: 사전 추세만으로 설명되는 크기
        idx = np.arange(len(months), dtype=float)
        drift = trend.coef * (idx[post].mean() - idx[pre].mean())
        drift_ok = abs(drift) < max(0.5 * abs(primary.coef), 1.96 * primary.se * 0.5)
        checks.append(_check("drift", "추세 연장만으로 생기는 차이", "pass" if drift_ok else "warn",
                             f"시행 전 추세가 이어졌다면 생겼을 차이 {(math.exp(drift) - 1) * 100:+.1f}% "
                             f"vs 추정 {primary.pct:+.1f}%", False))
        # 보조: 계절성 민감도
        if seasonal:
            diff_ok = abs(plain.coef - seasonal.coef) <= 1.96 * seasonal.se
            checks.append(_check("seasonality", "계절성 보정 민감도", "pass" if diff_ok else "warn",
                                 f"보정 전 {plain.pct:+.1f}% / 보정 후 {seasonal.pct:+.1f}%", False))
        else:
            checks.append(_check("seasonality", "계절성 보정 민감도", "warn",
                                 "시행 전 자료가 24개월 미만이라 월별 계절 보정을 하지 못했습니다", False))
        # 보조: 공간 플라시보 순위 검정
        perm_p = stats.permutation_p(primary.coef, placebo_effects)
        estimates["placebo_space"] = {"p_value": _r(perm_p, 3), "n_placebos": len(placebo_effects)}
        if placebo_effects:
            agree = (not primary.excludes_zero) or perm_p <= 0.20
            checks.append(_check("placebo_space", "다른 지역에 같은 분석 반복", "pass" if agree else "warn",
                                 f"정책이 없던 {len(placebo_effects)}개 지역 중 이만큼 큰 변화가 나온 비율 p={perm_p:.2f}", False))
        # 보조: 음성 대조 결과 (정책 영향권 밖 업종)
        if spec.industry != NEGATIVE_CONTROL_INDUSTRY and NEGATIVE_CONTROL_INDUSTRY in bundle.industries:
            nc_wide = outcome_panel(bundle, NEGATIVE_CONTROL_INDUSTRY)
            if spec.area in nc_wide.columns and all(c in nc_wide.columns for c in controls):
                nc_gap = _gap(np.log(nc_wide.clip(lower=1.0)), spec.area, controls)
                nc = stats.did(nc_gap, post, moy if seasonal else None)
                estimates["negative_control"] = {**nc.as_dict(), "industry": NEGATIVE_CONTROL_INDUSTRY}
                checks.append(_check("negative_control", f"영향권 밖 업종({NEGATIVE_CONTROL_INDUSTRY}) 점검",
                                     "warn" if nc.excludes_zero else "pass",
                                     f"{NEGATIVE_CONTROL_INDUSTRY} 소비 변화 {nc.pct:+.1f}% "
                                     f"({'함께 움직임 → 관광객 등 지역 전체 요인 가능성' if nc.excludes_zero else '변화 없음'})", False))
        # 보조: 경로 점검 (버스 이용이 실제로 변했는가)
        bus = bus_panel(bundle)
        if spec.area in bus.columns and all(c in bus.columns for c in controls):
            bus = bus.reindex(months).dropna()
            if len(bus) == len(months):
                b_gap = _gap(np.log(bus.clip(lower=1.0)), spec.area, controls)
                mech = stats.did(b_gap, post, moy if seasonal else None)
                estimates["mechanism_bus"] = mech.as_dict()
                checks.append(_check("mechanism", "버스 이용 변화(정책이 실제 작동했는가)",
                                     "pass" if mech.excludes_zero else "warn",
                                     f"연결 노선 이용자 수 변화 {mech.pct:+.1f}% "
                                     f"({'확인됨' if mech.excludes_zero else '확인되지 않음 → 소비 변화의 경로가 불분명'})", False))
        steps.append({"name": "통계 검증", "summary": f"점검 {len(checks)}개 수행"})

        # 차트용 지수 (시행 전 평균 = 100)
        ctrl_mean = log_wide[controls].mean(axis=1).to_numpy()
        tgt = log_wide[spec.area].to_numpy()
        series = {"months": months,
                  "treated": [round(float(v), 1) for v in np.exp(tgt - tgt[pre].mean()) * 100],
                  "control": [round(float(v), 1) for v in np.exp(ctrl_mean - ctrl_mean[pre].mean()) * 100]}

    # ---- 관측 사실 (어느 등급에서나 보고) ----
    level_series = wide[spec.area]
    yoy_pairs = [(m, f"{int(m[:4]) - 1}{m[4:]}") for m in months if m >= spec.policy_month]
    yoy_pairs = [(a, b) for a, b in yoy_pairs if b in wide.index]
    observed: dict = {"n_pre": n_pre, "n_post": n_post}
    if yoy_pairs:
        cur = [m for m, _ in yoy_pairs]
        prev = [m for _, m in yoy_pairs]
        observed["area_yoy_pct"] = _r((level_series[cur].sum() / level_series[prev].sum() - 1) * 100, 1)
        total = wide.sum(axis=1)
        observed["island_yoy_pct"] = _r((total[cur].sum() / total[prev].sum() - 1) * 100, 1)
    observed["before_after_pct"] = _r((level_series[post].mean() / level_series[pre].mean() - 1) * 100, 1) if n_pre and n_post else None

    # ---- 게이트 ----
    required_fail = any(c["required"] and c["status"] == "fail" for c in checks)
    any_warn = any(c["status"] == "warn" for c in checks)
    level = "C" if required_fail else ("B" if any_warn else "A")
    ind_txt = "전체 업종" if spec.industry == ALL_INDUSTRY else f"{spec.industry} 업종"
    if level == "C":
        estimates = {}        # 인과 추정치는 결과에서 제거한다
        parts = [f"비교 조건이 충족되지 않아 '{spec.policy_label}'의 인과효과는 추정하지 않았습니다. 관측된 사실만 보고합니다."]
        if "area_yoy_pct" in observed:
            parts.append(f"시행 이후 {spec.area}의 {ind_txt} 카드 소비는 전년 같은 달 대비 {observed['area_yoy_pct']:+.1f}% 변했고, "
                         f"같은 기간 분석 대상 전체 지역은 {observed['island_yoy_pct']:+.1f}% 변했습니다.")
        parts.append("이 변화가 정책 때문인지는 이 자료로 판단할 수 없습니다.")
        title, statement = "관측된 연관성만 보고", " ".join(parts)
    else:
        lo, hi = primary.ci_pct
        core = (f"{spec.area}의 {ind_txt} 카드 소비는 '{spec.policy_label}'({spec.policy_month}) 이후 "
                f"비교 지역 대비 {primary.pct:+.1f}% (95% 신뢰구간 {lo:+.1f}% ~ {hi:+.1f}%) 변한 것으로 추정됩니다.")
        if not primary.excludes_zero:
            core += " 신뢰구간이 0을 포함하므로 뚜렷한 변화가 있었다고 말하기 어렵습니다. 효과가 없다는 뜻이 아니라 이 자료로는 구분되지 않는다는 뜻입니다."
        if level == "A":
            title = "준실험 근거 충족"
            statement = core + " 비교 조건 점검을 모두 통과했습니다."
        else:
            title = "잠정 추정 (주의 항목 있음)"
            warns = ", ".join(c["label"] for c in checks if c["status"] == "warn")
            statement = core + f" 다만 다음 항목에 주의가 필요해 정책 효과로 단정할 수 없습니다: {warns}."
    verdict = {"level": level, "title": title, "statement": statement, "causal_language_allowed": level != "C"}
    plain = llm.plain_explanation(settings, statement, level) if llm.enabled(settings) else None
    if plain:
        verdict["plain_explanation"] = plain
    steps.append({"name": "판정", "summary": f"{level} 등급 · {title}"})

    limitations = [
        "관측 자료 분석이므로 무작위 실험과 같은 수준의 인과 증명은 아닙니다.",
        "카드 데이터는 카드 결제만 반영하며 현금·지역화폐·간편결제 일부가 빠질 수 있습니다.",
        "노선–상권 연결표(route_map)는 운영자가 정한 대응 관계이며, 연결이 틀리면 버스 이용 변화 점검도 틀립니다.",
        "같은 시기에 시행된 다른 정책·행사·개발 사업은 자동으로 걸러내지 못합니다. 담당자의 확인이 필요합니다.",
        "대상 지역이 1곳이면 신뢰구간이 실제 불확실성보다 좁게 나올 수 있어 공간 플라시보 결과를 함께 봐야 합니다.",
    ]
    if bundle.mode == "sample":
        limitations.insert(0, "이 결과는 합성 샘플 데이터로 만든 시연이며 실제 제주 정책의 효과가 아닙니다.")

    return {**base, "status": "done", "controls": chosen, "excluded_neighbors": excluded,
            "estimates": estimates, "observed": observed, "checks": checks, "verdict": verdict,
            "series": series, "limitations": limitations, "steps": steps}
