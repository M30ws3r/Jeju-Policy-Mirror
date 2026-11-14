"""보안 요구사항 검증: bcrypt, 암호화, CORS, CSRF, 오류 메시지, 접근 통제, 입력 검증."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import config, security
from app.config import get_settings
from app.main import create_app

ORIGIN = "https://myapp.com"
PW = "Halla-san1950m"
# 예약 도메인(example.com)의 자리표시자 주소만 사용
MAIL_A, MAIL_B = "tester-a@example.com", "tester-b@example.com"


@pytest.fixture()
def client():
    return TestClient(create_app(get_settings()), base_url="https://testserver")


def _signup(c, mail):
    r = c.post("/api/auth/register", json={"email": mail, "password": PW})
    assert r.status_code == 201
    return r.json()["csrf_token"]


def test_password_is_bcrypt_and_email_is_encrypted(client):
    _signup(client, MAIL_A)
    r = client.get("/api/auth/me")
    assert r.status_code == 200 and "***" in r.json()["email_masked"]
    hashed = security.hash_password(PW)
    assert hashed.startswith("$2b$12$") and security.verify_password(PW, hashed)
    assert not security.verify_password(PW + "x", hashed)


def test_field_cipher_roundtrip_aad_binding_and_rotation():
    k1, k2 = b"\x01" * 32, b"\x02" * 32
    old = security.FieldCipher({"v1": k1}, "v1")
    token = old.encrypt("secret@example.com", aad="users.email:1")
    assert "secret" not in token and token.startswith("v1.")
    rotated = security.FieldCipher({"v1": k1, "v2": k2}, "v2")
    assert rotated.decrypt(token, aad="users.email:1") == "secret@example.com"   # 옛 키로 쓴 값도 읽힌다
    assert rotated.encrypt("x", aad="a").startswith("v2.")                        # 새 값은 새 키로
    with pytest.raises(ValueError):
        rotated.decrypt(token, aad="users.email:2")                               # 다른 행에 붙여넣기 차단


def test_cors_allows_only_configured_origin_with_credentials(client):
    ok = client.options("/api/analyze", headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert ok.headers["access-control-allow-credentials"] == "true"
    bad = client.options("/api/analyze", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_wildcard_or_http_cors_origin_is_rejected(monkeypatch):
    for value in ("*", "http://myapp.com", "https://a.com,https://b.com"):
        monkeypatch.setenv("CORS_ORIGIN", value)
        with pytest.raises(config.ConfigError):
            config.load_settings()


def test_production_requires_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET")
    with pytest.raises(config.ConfigError):
        config.load_settings()


def test_session_cookie_flags_and_security_headers(client):
    r = client.post("/api/auth/register", json={"email": MAIL_A, "password": PW})
    cookie = next(h for h in r.headers.get_list("set-cookie") if h.startswith("jpm_session="))
    assert "HttpOnly" in cookie and "Secure" in cookie and "samesite=lax" in cookie.lower()
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "max-age" in r.headers["strict-transport-security"]


def test_csrf_token_required_for_cookie_authenticated_post(client):
    csrf = _signup(client, MAIL_A)
    q = {"question": "2024년 7월 함덕 버스 노선 조정 효과"}
    assert client.post("/api/analyze", json=q).status_code == 403
    assert client.post("/api/analyze", json=q, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_login_error_does_not_reveal_which_field_is_wrong(client):
    _signup(client, MAIL_A)
    wrong_pw = client.post("/api/auth/login", json={"email": MAIL_A, "password": PW + "9"})
    no_user = client.post("/api/auth/login", json={"email": MAIL_B, "password": PW})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_sql_injection_payload_is_inert(client):
    r = client.post("/api/auth/login", json={"email": "x' OR '1'='1@example.com", "password": PW})
    assert r.status_code in (401, 422)
    r = client.post("/api/analyze", json={"question": "함덕'; DROP TABLE users;-- 2024년 7월"})
    assert r.status_code == 200
    assert client.post("/api/auth/register", json={"email": MAIL_B, "password": PW}).status_code == 201  # 테이블 건재


def test_validation_and_errors_hide_internals(client):
    r = client.post("/api/analyze", json={"question": "x" * 600, "debug": True})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "invalid_input" and "Traceback" not in r.text and "pydantic" not in r.text
    assert client.post("/api/analyze", json={"question": "함덕 효과", "area": "없는지역"}).status_code == 422


def test_html_is_stripped_from_question(client):
    r = client.post("/api/analyze", json={"question": "<script>alert(1)</script>2024년 7월 함덕 버스 노선 효과"})
    assert r.status_code == 200 and "<script>" not in r.json()["question"]


def test_other_users_analysis_and_pdf_are_not_accessible(client):
    csrf = _signup(client, MAIL_A)
    r = client.post("/api/analyze", json={"question": "2024년 7월 함덕 버스 노선 조정 효과"}, headers={"X-CSRF-Token": csrf})
    aid = r.json()["analysis_id"]
    pdf = client.get(f"/api/analyses/{aid}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    client.cookies.clear()
    _signup(client, MAIL_B)
    assert client.get(f"/api/analyses/{aid}/pdf").status_code == 404
    assert client.get("/api/analyses/not-an-id/pdf").status_code == 404


def test_question_is_not_stored_in_plaintext(client):
    marker = "2024년 7월 함덕 버스 노선 조정 효과 표식문구"
    _signup(client, MAIL_A)
    client.cookies.clear()
    client.post("/api/analyze", json={"question": marker})
    with client.app.state.session_factory() as s:
        rows = s.execute(text("SELECT question_enc, result_json FROM analyses")).all()
        users = s.execute(text("SELECT email_enc, password_hash FROM users")).all()
    assert rows and all("표식문구" not in q and "표식문구" not in j for q, j in rows)
    assert all("@" not in e and h.startswith("$2b$") for e, h in users)
