"""환경변수 기반 설정.

비밀값(JWT 서명키, 데이터 암호화키, 색인키)은 코드에 기본값을 두지 않는다.
- production: 하나라도 없으면 기동을 거부한다.
- development: 없으면 프로세스 수명 동안만 쓰는 임시 키를 만든다(재시작 시 세션·암호문 무효).
"""
from __future__ import annotations

import base64
import logging
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("jpm.config")
BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    pass


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _b64key(raw: str, name: str, size: int = 32) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw.strip() + "=" * (-len(raw.strip()) % 4))
    except Exception as exc:  # noqa: BLE001
        raise ConfigError(f"{name}: base64 형식이 아닙니다") from exc
    if len(key) != size:
        raise ConfigError(f"{name}: {size}바이트 키가 필요합니다")
    return key


def _parse_keyring(raw: str) -> dict[str, bytes]:
    """DATA_KEYS="v1:<base64 32바이트>,v2:<...>" 형식. 키 교체 시 새 버전을 추가한다."""
    ring: dict[str, bytes] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        kid, _, value = part.partition(":")
        if not kid or not value or not kid.isalnum():
            raise ConfigError("DATA_KEYS 형식 오류 (예: v1:<base64>)")
        ring[kid] = _b64key(value, f"DATA_KEYS[{kid}]")
    return ring


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    cors_origin: str
    jwt_secret: str
    data_keys: dict[str, bytes]
    active_key_id: str
    index_key: bytes
    cookie_samesite: str
    cookie_secure: bool
    auth_required: bool
    data_mode: str
    data_dir: Path
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    trusted_hosts: tuple[str, ...]

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def _load_dotenv(path: Path) -> None:
    """backend/.env 가 있으면 읽는다 (이미 설정된 환경변수가 우선). 별도 패키지 없이 KEY=VALUE 만 지원."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def load_settings() -> Settings:
    if os.environ.get("APP_ENV") != "test":
        _load_dotenv(BASE_DIR / ".env")
    env = os.environ.get("APP_ENV", "development").strip().lower()
    if env not in {"development", "production", "test"}:
        raise ConfigError("APP_ENV 는 development | production | test 중 하나여야 합니다")
    prod = env == "production"

    # --- CORS: 와일드카드 금지, 단일 출처만 허용 ---
    cors_origin = os.environ.get("CORS_ORIGIN", "https://myapp.com").strip().rstrip("/")
    if "*" in cors_origin or "," in cors_origin or " " in cors_origin:
        raise ConfigError("CORS_ORIGIN 은 와일드카드 없이 출처 1개만 지정해야 합니다")
    is_local = cors_origin.startswith(("http://localhost", "http://127.0.0.1"))
    if not cors_origin.startswith("https://") and not (is_local and not prod):
        raise ConfigError("CORS_ORIGIN 은 https:// 출처여야 합니다 (개발 시 localhost 만 http 허용)")

    # --- 비밀값 ---
    jwt_secret = os.environ.get("JWT_SECRET", "")
    data_keys_raw = os.environ.get("DATA_KEYS", "")
    index_key_raw = os.environ.get("INDEX_KEY", "")
    if prod and not (jwt_secret and data_keys_raw and index_key_raw):
        raise ConfigError("production 에서는 JWT_SECRET, DATA_KEYS, INDEX_KEY 가 모두 필요합니다")
    if jwt_secret and len(jwt_secret) < 32:
        raise ConfigError("JWT_SECRET 은 32자 이상이어야 합니다")
    if not jwt_secret:
        jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET 미설정: 임시 키 사용 (재시작 시 로그인 세션이 무효화됩니다)")
    if data_keys_raw:
        data_keys = _parse_keyring(data_keys_raw)
    else:
        data_keys = {"dev": secrets.token_bytes(32)}
        log.warning("DATA_KEYS 미설정: 임시 암호화 키 사용 (재시작 시 저장된 암호문을 풀 수 없습니다)")
    active_key_id = os.environ.get("ACTIVE_KEY_ID", "") or next(reversed(data_keys))
    if active_key_id not in data_keys:
        raise ConfigError("ACTIVE_KEY_ID 가 DATA_KEYS 에 없습니다")
    index_key = _b64key(index_key_raw, "INDEX_KEY") if index_key_raw else secrets.token_bytes(32)

    # --- DB ---
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR / 'jpm_local.db'}")
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
    if prod and database_url.startswith("postgresql") and "sslmode=" not in database_url:
        database_url += ("&" if "?" in database_url else "?") + "sslmode=require"

    samesite = os.environ.get("COOKIE_SAMESITE", "lax").strip().lower()
    if samesite not in {"lax", "strict", "none"}:
        raise ConfigError("COOKIE_SAMESITE 는 lax | strict | none")
    cookie_secure = _flag("COOKIE_SECURE", True)
    if prod and not cookie_secure:
        raise ConfigError("production 에서는 COOKIE_SECURE 를 끌 수 없습니다")
    if samesite == "none" and not cookie_secure:
        raise ConfigError("SameSite=None 쿠키는 Secure 가 필요합니다")

    data_mode = os.environ.get("DATA_MODE", "sample").strip().lower()
    if data_mode not in {"sample", "real"}:
        raise ConfigError("DATA_MODE 는 sample | real")
    data_dir = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data"))).resolve()

    llm_provider = os.environ.get("LLM_PROVIDER", "none").strip().lower()
    if llm_provider not in {"none", "ollama", "openai_compat"}:
        raise ConfigError("LLM_PROVIDER 는 none | ollama | openai_compat")

    hosts = tuple(h.strip() for h in os.environ.get("TRUSTED_HOSTS", "").split(",") if h.strip())
    if prod and not hosts:
        raise ConfigError("production 에서는 TRUSTED_HOSTS(허용 Host 헤더)를 지정해야 합니다")

    return Settings(
        env=env,
        database_url=database_url,
        cors_origin=cors_origin,
        jwt_secret=jwt_secret,
        data_keys=data_keys,
        active_key_id=active_key_id,
        index_key=index_key,
        cookie_samesite=samesite,
        cookie_secure=cookie_secure,
        auth_required=_flag("AUTH_REQUIRED", prod),
        data_mode=data_mode,
        data_dir=data_dir,
        llm_provider=llm_provider,
        llm_base_url=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        llm_model=os.environ.get("LLM_MODEL", ""),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        trusted_hosts=hosts,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
