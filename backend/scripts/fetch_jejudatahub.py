"""제주데이터허브 Open API → data/real/*.csv 저장 (센터 PC 또는 반출이 허용된 환경에서만 실행).

대상 (둘 다 API)
- 614 · 일일 노선별 버스 이용자 정보      → data/real/bus.csv
- 605 · 관광지·상업지구 업종별 카드 데이터 → data/real/card.csv

API 주소와 프로젝트 키는 환경변수로만 받는다 (키를 코드·저장소·제출물에 넣지 않는다).
  JEJU_API_URL_BUS   허브의 614 '요청 주소' 전체 (프로젝트 키 포함된 형태 그대로)
  JEJU_API_URL_CARD  허브의 605 '요청 주소' 전체
허브 문서의 요청 변수명(기간, 페이지 번호 등)은 데이터마다 다르므로 --param 으로 넘긴다.
  예) python scripts/fetch_jejudatahub.py bus --param startDate=20240101 --param endDate=20241231

주의: 이 스크립트는 허브 응답 형식(JSON, data 배열, 페이지 변수 number/limit)을 가정해 작성했고
      개발 환경에서는 허브에 접속할 수 없어 실제 호출로 검증하지 못했다. 응답 구조가 다르면 --list-key, --page-param 으로 맞춘다.
"""
import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

DATA_REAL = Path(__file__).resolve().parent.parent / "data" / "real"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("target", choices=["bus", "card"])
    ap.add_argument("--param", action="append", default=[], help="key=value (여러 번 지정 가능)")
    ap.add_argument("--list-key", default="data")
    ap.add_argument("--page-param", default="number")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-pages", type=int, default=2000)
    args = ap.parse_args()

    base = os.environ.get(f"JEJU_API_URL_{args.target.upper()}", "")
    if not base.startswith("https://"):
        sys.exit(f"JEJU_API_URL_{args.target.upper()} 환경변수에 https 요청 주소를 넣어 주세요.")
    params = dict(p.split("=", 1) for p in args.param)
    rows: list[dict] = []
    for page in range(1, args.max_pages + 1):
        query = urllib.parse.urlencode({**params, args.page_param: page, "limit": args.limit})
        with urllib.request.urlopen(f"{base}{'&' if '?' in base else '?'}{query}", timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        batch = payload.get(args.list_key) or []
        rows.extend(batch)
        if len(batch) < args.limit or payload.get("hasMore") is False:
            break
    if not rows:
        sys.exit("받은 데이터가 없습니다. 요청 변수와 기간을 확인해 주세요.")
    DATA_REAL.mkdir(parents=True, exist_ok=True)
    out = DATA_REAL / f"{args.target}.csv"
    fields = sorted({k for r in rows for k in r})
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)}행 저장: {out}")
    print("원본 필드:", ", ".join(fields), "\n→ data/schema_map.json 의 columns 에 '원본 필드명: 표준 컬럼명'을 맞춰 주세요.")


if __name__ == "__main__":
    main()
