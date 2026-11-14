"""데이터 적재 계층.

표준 스키마(내부)
- card      : area, ym(YYYY-MM), industry, amount, count   ← 관광지·상업지구 업종별 카드 데이터
- bus       : route_no, date(YYYY-MM-DD 또는 YYYYMMDD), riders ← 일일 노선별 버스 이용자 정보
- route_map : route_no, area   ← 노선이 지나는 상권(운영자가 관리하는 연결표)
- areas     : area, neighbors(세미콜론 구분)  ← 인접 지역(파급효과 때문에 비교 후보에서 제외)

실데이터(real) 모드는 data/real/ 의 CSV 를 읽고, schema_map.json 의 '원본 컬럼명 → 표준 컬럼명' 대응표를 적용한다.
허브 API 의 실제 필드명은 센터에서 확인해 대응표만 고치면 되고, 코드는 고칠 필요가 없다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from . import sample

REQUIRED = {
    "card": ["area", "ym", "industry", "amount"],
    "bus": ["route_no", "date", "riders"],
    "route_map": ["route_no", "area"],
}
ALL_INDUSTRY = "전체"


class DataError(RuntimeError):
    """사용자에게 그대로 보여줘도 되는 데이터 준비 오류."""


@dataclass(frozen=True)
class DataBundle:
    mode: str                      # sample | real
    card: pd.DataFrame             # area, ym, industry, amount
    bus_monthly: pd.DataFrame      # area, ym, riders
    neighbors: dict[str, list[str]]
    areas: list[str]
    industries: list[str]
    months: list[str]

    @property
    def label(self) -> str:
        return "합성 샘플 데이터 (실제 수치 아님)" if self.mode == "sample" else "제주데이터허브·제주빅데이터센터 실데이터"


def _read_real(data_dir: Path) -> dict[str, pd.DataFrame]:
    real = data_dir / "real"
    map_path = data_dir / "schema_map.json"
    if not map_path.is_file():
        raise DataError("schema_map.json 이 없습니다. docs/DATA_SPEC.md 의 설정 절차를 확인해 주세요.")
    schema = json.loads(map_path.read_text(encoding="utf-8"))
    out: dict[str, pd.DataFrame] = {}
    for name in ("card", "bus", "route_map", "areas"):
        spec = schema.get(name, {})
        path = (real / spec.get("file", f"{name}.csv")).resolve()
        if real.resolve() not in path.parents:          # 경로 이탈 차단
            raise DataError(f"{name}: 데이터 폴더 밖의 파일은 읽을 수 없습니다.")
        if not path.is_file():
            if name == "areas":
                out[name] = pd.DataFrame(columns=["area", "neighbors"])
                continue
            raise DataError(f"실데이터 파일이 없습니다: real/{path.name}")
        df = pd.read_csv(path, dtype=str, encoding=spec.get("encoding", "utf-8-sig"))
        df = df.rename(columns=spec.get("columns", {}))
        missing = [c for c in REQUIRED.get(name, []) if c not in df.columns]
        if missing:
            raise DataError(f"{name}: 필요한 항목이 없습니다 → {', '.join(missing)} (schema_map.json 확인)")
        out[name] = df
    return out


def _normalize(raw: dict[str, pd.DataFrame], mode: str) -> DataBundle:
    card = raw["card"].copy()
    card["ym"] = card["ym"].astype(str).str.replace(r"[^0-9]", "", regex=True).str.slice(0, 6)
    card["ym"] = card["ym"].str.slice(0, 4) + "-" + card["ym"].str.slice(4, 6)
    card["amount"] = pd.to_numeric(card["amount"], errors="coerce")
    card["area"] = card["area"].astype(str).str.strip()
    card["industry"] = card["industry"].astype(str).str.strip()
    card = card.dropna(subset=["amount"])
    card = card[card["ym"].str.match(r"^\d{4}-(0[1-9]|1[0-2])$")]
    card = card.groupby(["area", "ym", "industry"], as_index=False)["amount"].sum()

    bus = raw["bus"].copy()
    digits = bus["date"].astype(str).str.replace(r"[^0-9]", "", regex=True)
    bus["ym"] = digits.str.slice(0, 4) + "-" + digits.str.slice(4, 6)
    bus["riders"] = pd.to_numeric(bus["riders"], errors="coerce")
    bus["route_no"] = bus["route_no"].astype(str).str.strip()
    bus = bus.dropna(subset=["riders"])
    route_map = raw["route_map"].copy()
    route_map["route_no"] = route_map["route_no"].astype(str).str.strip()
    route_map["area"] = route_map["area"].astype(str).str.strip()
    bus_monthly = (
        bus.merge(route_map, on="route_no", how="inner")
        .groupby(["area", "ym"], as_index=False)["riders"].sum()
    )

    neighbors: dict[str, list[str]] = {}
    for _, row in raw.get("areas", pd.DataFrame()).iterrows():
        items = [x.strip() for x in str(row.get("neighbors") or "").split(";") if x.strip() and x.strip() != "nan"]
        neighbors[str(row["area"]).strip()] = items

    if card.empty:
        raise DataError("카드 데이터에서 쓸 수 있는 행이 없습니다.")
    return DataBundle(
        mode=mode,
        card=card,
        bus_monthly=bus_monthly,
        neighbors=neighbors,
        areas=sorted(card["area"].unique()),
        industries=sorted(card["industry"].unique()),
        months=sorted(card["ym"].unique()),
    )


@lru_cache(maxsize=2)
def load_bundle(mode: str, data_dir: str) -> DataBundle:
    raw = sample.generate() if mode == "sample" else _read_real(Path(data_dir))
    return _normalize(raw, mode)


def outcome_panel(bundle: DataBundle, industry: str) -> pd.DataFrame:
    """지역×월 카드 이용금액 (wide: index=ym, columns=area). 결측 월이 있는 지역은 제외."""
    card = bundle.card
    if industry != ALL_INDUSTRY:
        card = card[card["industry"] == industry]
    wide = card.groupby(["ym", "area"])["amount"].sum().unstack("area").sort_index()
    return wide.dropna(axis=1, how="any")


def bus_panel(bundle: DataBundle) -> pd.DataFrame:
    wide = bundle.bus_monthly.groupby(["ym", "area"])["riders"].sum().unstack("area").sort_index()
    return wide.dropna(axis=1, how="any")
