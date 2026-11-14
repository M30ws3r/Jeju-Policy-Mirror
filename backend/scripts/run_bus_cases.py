"""정책 사례표(data/policy_cases.json)의 모든 사례를 버스 실데이터로 분석해 output/ 에 JSON 과 PDF 로 저장한다.

사용: python scripts/build_bus_monthly.py  →  python scripts/run_bus_cases.py [bus_monthly.csv 경로]
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.agent import pipeline_bus, pipeline_bus_v2, report_bus  # noqa: E402


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "data" / "real" / "bus_monthly.csv"
    out = BACKEND / "output"
    out.mkdir(exist_ok=True)
    weighted, weekday = pipeline_bus.load_panel(csv_path)
    cases = pipeline_bus.load_cases(BACKEND / "data" / "policy_cases.json")
    card = pipeline_bus_v2.load_card(csv_path.parent / pipeline_bus_v2.CARD_FILE)
    summary = []
    for case_id in cases["cases"]:
        result = pipeline_bus_v2.run_case(case_id, cases, weighted, weekday, card)
        (out / f"{case_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / f"{case_id}.pdf").write_bytes(report_bus.build_pdf(result))
        did = result["estimates"].get("did")
        summary.append((case_id, result["verdict"]["level"], result["observed"]["before_after_pct"],
                        f"{did['effect_pct']:+.1f}% ({did['ci_low']:+.1f}~{did['ci_high']:+.1f})" if did else "추정 안 함"))
    print(f"{'사례':<16}{'등급':<6}{'전후 변화':<12}비교 노선 대비")
    for cid, level, ba, est in summary:
        print(f"{cid:<16}{level:<6}{ba:+.1f}%      {est}")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
