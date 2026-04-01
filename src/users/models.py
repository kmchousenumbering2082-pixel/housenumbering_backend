import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from src.models import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)

    users = relationship("User", back_populates="group")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(100), nullable=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)

    gender = Column(String(15), default="Male")
    ward = Column(JSON, nullable=True)

    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)
    group = relationship("Group", back_populates="users")

    designation = Column(String(100), nullable=True)
    phone = Column(String(100), nullable=True)
    address = Column(String(500), nullable=True)

    image = Column(String, nullable=True)
    thumbnail = Column(String, nullable=True)

    is_deleted = Column(Boolean, default=False)

    date_created = Column(DateTime, default=datetime.utcnow)
    date_modified = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    email_verified_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    # New users must verify email and set their password before login.
    is_active = Column(Boolean, default=False)
    is_staff = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)

    auth_tokens = relationship(
        "UserAuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    def can_login(self) -> bool:
        return bool(self.is_active and not self.is_deleted)

    def mark_email_verified(self) -> None:
        self.is_active = True
        self.email_verified_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_login(self) -> None:
        self.last_login_at = datetime.now(UTC).replace(tzinfo=None)


class AuthTokenPurpose(StrEnum):
    ACTIVATE_ACCOUNT = "activate_account"
    RESET_PASSWORD = "reset_password"


class UserAuthToken(Base):
    """Stores one-time tokens used for account activation and password reset."""

    __tablename__ = "user_auth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="auth_tokens")

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    @classmethod
    def issue(
        cls,
        user_id: int,
        purpose: AuthTokenPurpose | str,
        expires_in: timedelta,
    ) -> tuple["UserAuthToken", str]:
        raw_token = secrets.token_urlsafe(48)
        token_hash = cls.hash_token(raw_token)
        expires_at = datetime.utcnow() + expires_in
        token = cls(
            user_id=user_id,
            purpose=str(purpose),
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return token, raw_token

    def verify(self, raw_token: str) -> bool:
        return self.token_hash == self.hash_token(raw_token)

    def is_expired(self) -> bool:
        return self.expires_at <= datetime.utcnow()

    def is_usable(self) -> bool:
        return self.consumed_at is None and not self.is_expired()

    def consume(self) -> None:
        self.consumed_at = datetime.utcnow()