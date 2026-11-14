"""요청 스키마. 모든 외부 입력은 pydantic 으로 형식·길이를 검증하고 nh3 로 정제한다."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .security import sanitize_text

_YM = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(_Strict):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def _password_rules(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:          # bcrypt 는 72바이트 뒤를 버린다
            raise ValueError("비밀번호가 너무 깁니다")
        if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
            raise ValueError("영문과 숫자를 함께 써 주세요")
        return value


class AnalyzeRequest(_Strict):
    question: str = Field(min_length=2, max_length=500)
    area: str | None = Field(default=None, max_length=40)
    policy_month: str | None = Field(default=None, max_length=7)
    industry: str | None = Field(default=None, max_length=40)

    @field_validator("question", "area", "industry")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = sanitize_text(value)
        if not cleaned:
            raise ValueError("내용이 비어 있습니다")
        return cleaned

    @field_validator("policy_month")
    @classmethod
    def _ym(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not _YM.match(value):
            raise ValueError("YYYY-MM 형식이어야 합니다")
        return value
