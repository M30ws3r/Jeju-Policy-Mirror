"""비밀값 생성기. 출력은 .env 또는 배포 플랫폼의 환경변수(Secret)에만 넣고, 저장소에 커밋하지 않는다.

사용: python scripts/gen_keys.py
"""
import base64
import secrets


def b64(n: int = 32) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(n)).decode()


if __name__ == "__main__":
    print(f"JWT_SECRET={secrets.token_urlsafe(48)}")
    print(f"DATA_KEYS=v1:{b64()}")
    print("ACTIVE_KEY_ID=v1")
    print(f"INDEX_KEY={b64()}")
