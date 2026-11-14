"""사례 API 검증: 실데이터 대신 합성 노선 표를 임시 폴더에 두고 확인한다."""
import csv
import json
import shutil

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rng = np.random.default_rng(3)
    months = [str(p) for p in pd.period_range("2022-12", "2025-05", freq="M")]
    (tmp_path / "real").mkdir()
    with open(tmp_path / "real" / "bus_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["route", "ym", "wd_mean", "we_mean", "n_wd", "n_we"])
        for i in range(30):
            base = rng.uniform(100, 1000)
            for k, ym in enumerate(months):
                eff = 0.8 if (i == 0 and ym >= "2024-08") else 1.0
                v = base * eff * np.exp(rng.normal(0, 0.03))
                w.writerow([str(300 + i), ym, round(v, 2), round(v * 0.8, 2), 5, 2])
    cases = {"affected_list_complete": True, "known_affected": ["300"],
             "cases": {"demo_cut": {"label": "300번", "policy": "감차", "policy_month": "2024-08", "routes": ["300"],
                                    "question": "300번 감차 효과"}}}
    (tmp_path / "policy_cases.json").write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib

    from app import config
    config.get_settings.cache_clear()
    import app.main as main_mod
    importlib.reload(main_mod)
    import app.main_v2 as v2
    importlib.reload(v2)
    yield TestClient(v2.app, base_url="https://testserver")
    config.get_settings.cache_clear()
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_case_list_and_result(client):
    listing = client.get("/api/cases").json()
    assert listing["available"] is True and listing["items"][0]["id"] == "demo_cut"
    r = client.get("/api/cases/demo_cut").json()
    assert r["verdict"]["level"] in {"A", "B"}
    assert r["estimates"]["did"]["ci_low"] < -20.0 < r["estimates"]["did"]["ci_high"]


def test_case_pdf(client):
    pdf = client.get("/api/cases/demo_cut/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_unknown_or_malformed_case_is_404(client):
    assert client.get("/api/cases/nope").status_code == 404
    assert client.get("/api/cases/..%2F..%2Fetc").status_code == 404
    assert client.get("/api/cases/DROP TABLE").status_code == 404
