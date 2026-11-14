"""데이터 암호화 키 교체 (무중단).

절차
1) 새 키를 추가한다:  DATA_KEYS="v1:<기존>,v2:<새 키>"  ACTIVE_KEY_ID=v2  → 재배포 (이 시점부터 새 데이터는 v2 로 암호화)
2) 이 스크립트를 실행해 기존 행을 v2 로 다시 암호화한다:  python scripts/rotate_keys.py
3) 출력에서 '남은 옛 키 암호문 0건'을 확인한 뒤 DATA_KEYS 에서 v1 을 제거하고 재배포한다.
INDEX_KEY(블라인드 인덱스 키)는 이 스크립트로 바꾸지 않는다 — 바꾸려면 전 사용자의 색인을 다시 계산해야 한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Analysis, User, make_session_factory  # noqa: E402
from app.security import FieldCipher  # noqa: E402


def main() -> None:
    settings = get_settings()
    cipher = FieldCipher(settings.data_keys, settings.active_key_id)
    factory = make_session_factory(settings.database_url)
    moved = left = 0
    with factory() as session:
        for model, column, table in ((User, "email_enc", "users.email"), (Analysis, "question_enc", "analyses.question")):
            for row in session.scalars(select(model)):
                token = getattr(row, column)
                if cipher.key_id_of(token) == cipher.active_key_id:
                    continue
                aad = f"{table}:{row.id}"
                try:
                    setattr(row, column, cipher.encrypt(cipher.decrypt(token, aad), aad))
                    moved += 1
                except ValueError:
                    left += 1
        session.commit()
    print(f"재암호화 {moved}건 완료 / 남은 옛 키 암호문 {left}건 (활성 키: {cipher.active_key_id})")


if __name__ == "__main__":
    main()
