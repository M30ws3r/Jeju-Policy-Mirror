"""data/real/bus_days/*.csv (하루치 노선별 합계) → data/real/bus_monthly.csv (노선×월 하루 평균).

표준 라이브러리만 쓴다 (센터 PC 에서 패키지 설치 전에도 실행 가능).
- 세부 경로(예: 325-15)를 노선번호(325)로 묶는다. '251-1'처럼 번호에 '-'가 든 노선은 본 노선과 합쳐진다.
- 허브에 자료가 없는 날(빈 파일)은 평균에서 뺀다. 자료가 있는 날에 기록이 없는 노선은 0명으로 센다.
- 평일과 주말을 따로 평균해 둔다 (표본일의 요일 구성이 달마다 달라 생기는 흔들림을 줄이기 위함).

사용: python scripts/build_bus_monthly.py [시작연도 기본 2022]
"""
import collections
import csv
import datetime
import glob
import sys
from pathlib import Path

REAL = Path(__file__).resolve().parent.parent / "data" / "real"


def main() -> None:
    first_year = sys.argv[1] if len(sys.argv) > 1 else "2022"
    day: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    empty = 0
    for path in sorted(glob.glob(str(REAL / "bus_days" / "*.csv"))):
        date = Path(path).stem
        if date[:4] < first_year:
            continue
        with open(path, encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r["routeName"]]
        if not rows:
            empty += 1
            continue
        for r in rows:
            day[date][r["routeName"].split("-")[0]] += int(float(r["userCount"]))
    routes = sorted({r for c in day.values() for r in c})
    agg: dict = collections.defaultdict(lambda: {"wd": [], "we": []})
    for date, counts in day.items():
        kind = "we" if datetime.date(int(date[:4]), int(date[4:6]), int(date[6:])).weekday() >= 5 else "wd"
        for r in routes:
            agg[(r, f"{date[:4]}-{date[4:6]}")][kind].append(counts.get(r, 0))

    def mean(xs: list) -> object:
        return round(sum(xs) / len(xs), 2) if xs else ""

    with open(REAL / "bus_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["route", "ym", "wd_mean", "we_mean", "n_wd", "n_we"])
        for (r, ym), v in sorted(agg.items()):
            w.writerow([r, ym, mean(v["wd"]), mean(v["we"]), len(v["wd"]), len(v["we"])])
    print(f"자료 있는 날 {len(day)}일, 빈 날 {empty}일, 노선 {len(routes)}개 → {REAL / 'bus_monthly.csv'}")


if __name__ == "__main__":
    main()
