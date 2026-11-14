"""보안 유틸: 비밀번호 해싱(bcrypt), 세션 토큰(JWT), 필드 암호화(AES-256-GCM),
조회용 블라인드 인덱스(HMAC), 입력 정제, 로그인 시도 제한."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import nh3
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings

TOKEN_TTL_MINUTES = 60
JWT_ALG = "HS256"
JWT_ISS = "jeju-policy-mirror"
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------- 비밀번호 ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


# 존재하지 않는 계정에도 같은 시간을 쓰게 해 계정 존재 여부가 응답 시간으로 새지 않게 한다.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# ---------- 세션 토큰 ----------
def create_session_token(settings: Settings, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iss": JWT_ISS,
        "iat": now,
        "exp": now + timedelta(minutes=TOKEN_TTL_MINUTES),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALG)


def read_session_token(settings: Settings, token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALG],  # 알고리즘 고정 (alg=none, 알고리즘 혼동 차단)
            issuer=JWT_ISS,
            options={"require": ["exp", "sub", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_matches(cookie_value: str | None, header_value: str | None) -> bool:
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)


# ---------- 필드 암호화 ----------
class FieldCipher:
    """AES-256-GCM. 암호문 형식: `<키ID>.<nonce b64>.<ciphertext+tag b64>`

    - 키ID를 암호문에 남겨 여러 키 버전을 동시에 복호화할 수 있다(무중단 키 교체).
    - AAD(부가 인증 데이터)로 `테이블.컬럼:행ID` 를 묶어, 암호문을 다른 행·컬럼에 옮겨 붙이는 공격을 막는다.
    """

    def __init__(self, keys: dict[str, bytes], active_key_id: str):
        self._keys = {kid: AESGCM(key) for kid, key in keys.items()}
        self._active = active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active

    def encrypt(self, plaintext: str, aad: str) -> str:
        nonce = secrets.token_bytes(12)
        ct = self._keys[self._active].encrypt(nonce, plaintext.encode("utf-8"), aad.encode("utf-8"))
        return ".".join((self._active, _b64e(nonce), _b64e(ct)))

    def decrypt(self, token: str, aad: str) -> str:
        try:
            kid, nonce_b64, ct_b64 = token.split(".")
            aes = self._keys[kid]
            return aes.decrypt(_b64d(nonce_b64), _b64d(ct_b64), aad.encode("utf-8")).decode("utf-8")
        except (ValueError, KeyError, InvalidTag) as exc:
            raise ValueError("복호화 실패") from exc

    def key_id_of(self, token: str) -> str:
        return token.split(".", 1)[0]


def blind_index(index_key: bytes, value: str) -> str:
    """암호화된 값을 '같은지'만 비교하기 위한 HMAC-SHA256 색인 (이메일 중복·로그인 조회)."""
    return hmac.new(index_key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


# ---------- 입력 정제 ----------
def sanitize_text(value: str) -> str:
    """HTML/스크립트 제거(nh3) + 유니코드 정규화 + 제어문자 제거."""
    value = unicodedata.normalize("NFKC", value)
    value = _CONTROL_CHARS.sub("", value)
    value = nh3.clean(value, tags=set(), attributes={})
    # nh3 는 남은 특수문자를 엔티티로 바꾼다. 저장은 평문으로 하고 출력 시점에 이스케이프한다.
    value = value.replace("&amp;", "&").replace("&lt;", "").replace("&gt;", "")
    return re.sub(r"\s+", " ", value).strip()


# ---------- 로그인 시도 제한 ----------
class RateLimiter:
    """프로세스 메모리 기반 슬라이딩 윈도. 인스턴스가 여러 개면 공유 저장소(예: DB)로 바꿔야 한다."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            if len(self._hits) > 10_000:  # 메모리 상한
                self._hits.clear()
            return True
