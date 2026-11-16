"""실데이터 문장 질문 API: 노선·연월 해석, 부족한 입력 안내, 입력 검증."""
from app.agent import parser_bus

KNOWN = {"311", "325", "326", "201"}


def test_parse_routes_and_month():
    s = parser_bus.parse("2024년 8월 326번을 폐지하고 325번으로 합친 뒤", KNOWN, "2023-01", "2025-05")
    assert s.routes == ["326", "325"] and s.policy_month == "2024-08" and not s.missing
    assert s.policy_label == "노선 폐지·노선 통합"


def test_year_is_not_a_route_and_missing_month_reported():
    s = parser_bus.parse("311번 감차 효과는?", KNOWN, "2023-01", "2025-05")
    assert s.routes == ["311"] and "policy_month" in s.missing
    s = parser_bus.parse("2024.8 개편", KNOWN, "2023-01", "2025-05")
    assert s.routes == [] and "routes" in s.missing


def test_unknown_route_and_out_of_range():
    s = parser_bus.parse("2021년 3월 777번", KNOWN, "2023-01", "2025-05")
    assert s.unknown_routes == ["777"] and {"routes", "policy_month_range"} <= set(s.missing)
