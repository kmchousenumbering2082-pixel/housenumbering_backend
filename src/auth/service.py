import os
from datetime import datetime, timedelta, UTC

from fastapi import HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from src.users.models import User
from src.users.service import hash_password, verify_password

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret-in-env")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))


def _create_token(user: User, token_type: str, expires_delta: timedelta) -> tuple[str, datetime]:
    issued_at = datetime.now(UTC)
    expire_at = issued_at + expires_delta
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "type": token_type,
        "exp": expire_at,
        "iat": issued_at,
    }
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return token, expire_at


def _issue_token_pair(user: User) -> tuple[str, datetime, str, datetime]:
    access_token, access_expires_at = _create_token(
        user=user,
        token_type="access",
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    refresh_token, refresh_expires_at = _create_token(
        user=user,
        token_type="refresh",
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    return access_token, access_expires_at, refresh_token, refresh_expires_at


def signup(db: Session, email: str, password: str, username: str | None = None):
    email = email.strip().lower()
    username = username.strip() if isinstance(username, str) and username.strip() else None

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    user = User(
        email=email,
        username=username,
        password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_token_pair(user)


def login(db: Session, email: str, password: str):
    email = email.strip().lower()

    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return _issue_token_pair(user)


def refresh_tokens(db: Session, refresh_token: str):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(refresh_token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        token_type: str | None = payload.get("type")
        user_id: str | None = payload.get("sub")
        if token_type != "refresh" or user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception

    return _issue_token_pair(user)


def get_current_user_from_token(db: Session, token: str) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        token_type: str | None = payload.get("type")
        user_id: str | None = payload.get("sub")
        if token_type != "access" or user_id is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise credentials_exception

    return user
