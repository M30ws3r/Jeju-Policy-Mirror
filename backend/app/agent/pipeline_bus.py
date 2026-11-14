"""버스 노선 단위 정책 검증 (실데이터용).

새 파일로 만든 이유: 기존 pipeline.py 는 '지역 × 월 카드 소비' 합성 샘플 기준으로 검증돼 있다.
실제 지정 데이터를 조회해 보니 카드(605)와 버스(614)의 제공 기간이 겹치지 않아, 분석 단위를
'노선 × 월 하루 평균 승차 인원'으로 바꿔야 했다. 검증된 기존 흐름을 건드리지 않도록 노선용 흐름을 따로 둔다.
통계 계산(stats.py)과 보조 함수(pipeline.py)는 그대로 재사용한다.

입력
- data/real/bus_monthly.csv : route, ym, wd_mean, we_mean, n_wd, n_we  (scripts/build_bus_monthly.py 가 생성)
- data/policy_cases.json    : 정책 사례표 (시행월, 대상 노선 묶음, 비교 후보에서 뺄 노선)
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from . import stats
from .pipeline import _check, _gap, _pick_controls, _r

K_CONTROLS = 8
MIN_CONTROLS = 3
MIN_PRE, MIN_POST = 12, 3
MIN_DAYS_PER_MONTH = 3
DATASET = "제주데이터허브 614 · 일일 노선별 버스 이용자 정보 (API) — 승차·일반·카드, 4일 간격 표본"


def load_panel(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(평일·주말 가중 하루 평균, 평일만의 하루 평균) 두 개의 노선×월 표를 돌려준다."""
    df = pd.read_csv(csv_path, dtype={"route": str})
    df["n"] = df["n_wd"] + df["n_we"]
    df = df[df["n"] >= MIN_DAYS_PER_MONTH]
    wd, we = df["wd_mean"], df["we_mean"]
    df["value"] = np.where(wd.notna() & we.notna(), (5 * wd + 2 * we) / 7, wd.fillna(we))
    weighted = df.pivot(index="ym", columns="route", values="value").sort_index()
    weekday = df.pivot(index="ym", columns="route", values="wd_mean").sort_index()
    return weighted, weekday


def load_cases(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _unit(wide: pd.DataFrame, routes: list[str]) -> pd.Series:
    present = [r for r in routes if r in wide.columns]
    return wide[present].fillna(0).sum(axis=1)


def run_case(case_id: str, cases: dict, weighted: pd.DataFrame, weekday: pd.DataFrame) -> dict:
    case = cases["cases"][case_id]
    policy_month, label, targets = case["policy_month"], case["label"], case["routes"]
    excluded = sorted(set(cases.get("known_affected", [])) | set(targets))
    steps = [{"name": "질문 해석", "summary": f"대상={label}, 시행월={policy_month} (정책 사례표)"}]

    months = list(weighted.index)
    post = np.array([m >= policy_month for m in months])
    pre = ~post
    n_pre, n_post = int(pre.sum()), int(post.sum())
    # 비교 후보: 사례표에 조정 노선으로 적히지 않았고, 전 기간 매달 이용객이 있는 노선
    pool_wide = weighted.drop(columns=[c for c in excluded if c in weighted.columns]).dropna(axis=1, how="any")
    pool_wide = pool_wide.loc[:, (pool_wide > 0).all()]
    target = _unit(weighted, targets)
    target_ok = bool((target > 0).all())
    log_wide = np.log(pool_wide.assign(__target__=target).clip(lower=1.0))
    pool = list(pool_wide.columns)
    steps.append({"name": "데이터 구성", "summary": f"노선 {weighted.shape[1]}개 × {len(months)}개월 (시행 전 {n_pre}, 후 {n_post}개월), "
                                                    f"비교 후보 {len(pool)}개 노선"})

    chosen = _pick_controls(log_wide, "__target__", pool, pre, K_CONTROLS) if n_pre >= 3 and target_ok else []
    controls = [c["area"] for c in chosen]
    for c in chosen:
        c["area"] = f"{c['area']}번"
    steps.append({"name": "비교 노선 선정", "summary": f"시행 전 흐름이 비슷한 {len(controls)}개 노선: {', '.join(controls)}"})

    checks: list[dict] = []
    span_ok = n_pre >= MIN_PRE and n_post >= MIN_POST and target_ok
    checks.append(_check("span", "관측 기간", "pass" if span_ok else "fail",
                         f"시행 전 {n_pre}개월(기준 {MIN_PRE}), 시행 후 {n_post}개월(기준 {MIN_POST})"
                         + ("" if target_ok else " / 대상 노선의 이용 기록이 없는 달이 있음"), True))
    ctrl_ok = len(controls) >= MIN_CONTROLS
    checks.append(_check("controls", "비교 노선 수", "pass" if ctrl_ok else "fail", f"{len(controls)}곳 확보 (기준 {MIN_CONTROLS}곳)", True))

    estimates: dict = {}
    series: dict = {}
    primary = None
    if span_ok and ctrl_ok:
        gap = _gap(log_wide, "__target__", controls)
        raw = stats.did(gap, post)
        placebo = []
        for other in pool:
            rest = [a for a in pool if a != other]
            o_ctrl = [c["area"] for c in _pick_controls(log_wide, other, rest, pre, K_CONTROLS)]
            placebo.append(stats.did(_gap(log_wide, other, o_ctrl), post).coef)
        primary = stats.conservative(raw, placebo)
        estimates["did"] = {**primary.as_dict(), "method": "이중차분 (노선 단위)",
                            "ci_method": "플라시보 노선 산포로 넓힌 보수적 구간" if primary.se > raw.se else "Newey–West HAC"}

        trend = stats.pretrend(gap[pre])
        status = "pass" if trend.p >= 0.10 else ("warn" if trend.p >= 0.05 else "fail")
        checks.append(_check("pretrend", "시행 전 추세 일치(평행추세)", status,
                             f"시행 전 격차의 월별 기울기 {trend.coef * 100:+.2f}%p (p={trend.p:.3f})", True))
        # 본 추정과 같은 기준(플라시보 노선 산포를 하한으로 한 보수적 표준오차)으로 판정한다.
        # HAC 표준오차만 쓰면 아주 작은 차이도 '구분됨'으로 나와 본 추정의 판정 기준과 어긋난다.
        fake = stats.conservative(stats.placebo_in_time(gap[pre]), placebo)
        checks.append(_check("placebo_time", "가짜 시행일 점검", "fail" if fake.excludes_zero else "pass",
                             f"시행 전 기간 한가운데를 시행일로 가정한 추정 {fake.pct:+.1f}% "
                             f"({'0과 구분됨 → 설계 의심' if fake.excludes_zero else '0과 구분되지 않음'})", True))
        idx = np.arange(len(months), dtype=float)
        drift = trend.coef * (idx[post].mean() - idx[pre].mean())
        drift_ok = abs(drift) < max(0.5 * abs(primary.coef), 1.96 * primary.se * 0.5)
        checks.append(_check("drift", "추세 연장만으로 생기는 차이", "pass" if drift_ok else "warn",
                             f"시행 전 추세가 이어졌다면 생겼을 차이 {(math.exp(drift) - 1) * 100:+.1f}% vs 추정 {primary.pct:+.1f}%", False))
        # 계절 민감도: 시행 후와 같은 달(전년)만 시행 전으로 써서 다시 추정
        post_moy = {m[5:] for m, p in zip(months, post) if p}
        keep = np.array([p or (m[5:] in post_moy and m >= f"{int(policy_month[:4]) - 1}{policy_month[4:]}") for m, p in zip(months, post)])
        if (keep & pre).sum() >= 3:
            matched = stats.did(gap[keep], post[keep])
            ok = abs(matched.coef - primary.coef) <= 1.96 * primary.se
            estimates["did_same_months"] = matched.as_dict()
            checks.append(_check("seasonality", "계절 민감도(전년 같은 달끼리 비교)", "pass" if ok else "warn",
                                 f"전 기간 기준 {primary.pct:+.1f}% / 전년 같은 달 기준 {matched.pct:+.1f}%", False))
        perm_p = stats.permutation_p(primary.coef, placebo)
        estimates["placebo_space"] = {"p_value": _r(perm_p, 3), "n_placebos": len(placebo)}
        agree = (not primary.excludes_zero) or perm_p <= 0.20
        checks.append(_check("placebo_space", "다른 노선에 같은 분석 반복", "pass" if agree else "warn",
                             f"비교 후보 {len(placebo)}개 노선 중 이만큼 큰 변화가 나온 비율 p={perm_p:.2f}", False))
        # 표본·요일 민감도: 평일만으로 다시 계산
        wk_pool = weekday[controls].dropna(how="any")
        wk_target = _unit(weekday, targets).reindex(wk_pool.index)
        if len(wk_pool) == len(months) and (wk_target > 0).all():
            wk_gap = np.log(wk_target.clip(lower=1.0)).to_numpy() - np.log(wk_pool.clip(lower=1.0)).mean(axis=1).to_numpy()
            wk = stats.did(wk_gap, post)
            ok = abs(wk.coef - primary.coef) <= 1.96 * primary.se
            estimates["did_weekdays_only"] = wk.as_dict()
            checks.append(_check("sampling", "표본·요일 민감도(평일만으로 재계산)", "pass" if ok else "warn",
                                 f"평일·주말 가중 {primary.pct:+.1f}% / 평일만 {wk.pct:+.1f}%", False))
        # 비교 노선 순도: 조정 노선 전체 목록이 없으면 비교 노선에도 조정된 노선이 섞였을 수 있다
        complete = bool(cases.get("affected_list_complete", False))
        checks.append(_check("purity", "비교 노선에 조정 노선이 섞이지 않았는가", "pass" if complete else "warn",
                             "정책 사례표가 조정 노선 전체를 담고 있음" if complete else
                             "조정된 85개 노선의 전체 목록을 확보하지 못해, 비교 노선 일부도 조정되었을 수 있음 → 효과가 실제보다 작게 추정될 수 있음", False))
        steps.append({"name": "통계 검증", "summary": f"점검 {len(checks)}개 수행"})

        ctrl_mean = log_wide[controls].mean(axis=1).to_numpy()
        tgt = log_wide["__target__"].to_numpy()
        series = {"months": months,
                  "treated": [round(float(v), 1) for v in np.exp(tgt - tgt[pre].mean()) * 100],
                  "control": [round(float(v), 1) for v in np.exp(ctrl_mean - ctrl_mean[pre].mean()) * 100]}

    observed: dict = {"n_pre": n_pre, "n_post": n_post,
                      "before_after_pct": _r((target[post].mean() / target[pre].mean() - 1) * 100, 1) if n_pre and n_post else None,
                      "target_daily_pre": _r(float(target[pre].mean()), 0), "target_daily_post": _r(float(target[post].mean()), 0)}
    all_total = weighted.fillna(0).sum(axis=1)
    observed["island_before_after_pct"] = _r((all_total[post].mean() / all_total[pre].mean() - 1) * 100, 1)

    required_fail = any(c["required"] and c["status"] == "fail" for c in checks)
    any_warn = any(c["status"] == "warn" for c in checks)
    level = "C" if required_fail else ("B" if any_warn else "A")
    if level == "C":
        estimates = {}
        statement = (f"비교 조건이 충족되지 않아 '{case['policy']}'의 인과효과는 추정하지 않았습니다. 관측된 사실만 보고합니다. "
                     f"{label}의 하루 평균 승차 인원은 시행 전 {observed['target_daily_pre']:,.0f}명에서 시행 후 {observed['target_daily_post']:,.0f}명으로 "
                     f"{observed['before_after_pct']:+.1f}% 변했고, 같은 기간 전체 노선 합계는 {observed['island_before_after_pct']:+.1f}% 변했습니다. "
                     "이 변화가 정책 때문인지는 이 자료로 판단할 수 없습니다.")
        title = "관측된 연관성만 보고"
    else:
        lo, hi = primary.ci_pct
        core = (f"{label}의 하루 평균 승차 인원은 '{case['policy']}'({policy_month}) 이후 "
                f"비교 노선 대비 {primary.pct:+.1f}% (95% 신뢰구간 {lo:+.1f}% ~ {hi:+.1f}%) 변한 것으로 추정됩니다.")
        if not primary.excludes_zero:
            core += " 신뢰구간이 0을 포함하므로 뚜렷한 변화가 있었다고 말하기 어렵습니다. 효과가 없다는 뜻이 아니라 이 자료로는 구분되지 않는다는 뜻입니다."
        if level == "A":
            title, statement = "준실험 근거 충족", core + " 비교 조건 점검을 모두 통과했습니다."
        else:
            warns = ", ".join(c["label"] for c in checks if c["status"] == "warn")
            title, statement = "잠정 추정 (주의 항목 있음)", core + f" 다만 다음 항목에 주의가 필요해 정책 효과로 단정할 수 없습니다: {warns}."

    steps.append({"name": "판정", "summary": f"{level} 등급 · {title}"})
    limitations = [
        "관측 자료 분석이므로 무작위 실험과 같은 수준의 인과 증명은 아닙니다.",
        "4일 간격으로 표본 수집한 날의 평균입니다. 허브에 자료가 없는 날도 있어 월 평균에 표본 오차가 있습니다.",
        "'승차·일반·카드' 이용만 집계했습니다. 현금, 청소년·어린이 요금, 환승은 빠져 있습니다.",
        "노선번호 기준으로 묶었습니다. '251-1'처럼 번호에 '-'가 들어가는 노선은 본 노선과 구분되지 않습니다.",
        "같은 시기에 시행된 다른 변화(요금, 정류소, 도로, 행사 등)는 자동으로 걸러내지 못합니다. 담당자의 확인이 필요합니다.",
        "버스 이용객 감소는 승객이 다른 노선·교통수단으로 옮겨 간 결과일 수 있습니다. 이동 수요 자체의 감소를 뜻하지 않습니다.",
    ]
    return {"status": "done", "case_id": case_id, "question": case.get("question", label),
            "spec": {"area": label, "policy_month": policy_month, "industry": "승차·일반·카드", "policy_label": case["policy"],
                     "missing": [], "parsed_by": "case_table"},
            "data_source": {"mode": "real", "label": "제주데이터허브 실데이터 (표본 수집)", "datasets": [DATASET]},
            "controls": chosen, "excluded_neighbors": [], "estimates": estimates, "observed": observed,
            "checks": checks, "verdict": {"level": level, "title": title, "statement": statement,
                                          "causal_language_allowed": level != "C"},
            "series": series, "limitations": limitations, "steps": steps}
