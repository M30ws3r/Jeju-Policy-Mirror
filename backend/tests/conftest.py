import base64
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 테스트용 임시 키 (실행할 때마다 새로 생성 — 저장소에 비밀값을 두지 않는다)
os.environ.update({
    "APP_ENV": "test",
    "CORS_ORIGIN": "https://myapp.com",
    "JWT_SECRET": secrets.token_urlsafe(48),
    "DATA_KEYS": "v1:" + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "INDEX_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    "DATABASE_URL": "sqlite://",
    "AUTH_REQUIRED": "false",
    "DATA_MODE": "sample",
    "COOKIE_SECURE": "true",
})
