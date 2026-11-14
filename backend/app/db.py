"""DB 연결과 모델. 모든 질의는 SQLAlchemy 바인드 파라미터(Prepared Statement)로만 실행한다."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text, create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email_enc: Mapped[str] = mapped_column(Text, nullable=False)                  # AES-256-GCM 암호문
    email_bidx: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # HMAC 블라인드 인덱스
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)       # bcrypt
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)  # 추측 불가한 UUID4
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    question_enc: Mapped[str] = mapped_column(Text, nullable=False)   # 질문 원문도 암호화 저장
    result_json: Mapped[str] = mapped_column(Text, nullable=False)    # 집계 결과만 (개인정보 없음)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    """보안 감사 로그. 이메일·비밀번호·질문 원문은 남기지 않는다."""

    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def make_session_factory(database_url: str) -> sessionmaker:
    kwargs: dict = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if database_url in {"sqlite://", "sqlite:///:memory:"}:   # 테스트용 메모리 DB 는 연결 1개를 공유
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
