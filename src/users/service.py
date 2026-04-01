from sqlalchemy.orm import Session
from fastapi import HTTPException
from src.users.models import User
from src.users.schema import UserCreate, UserUpdate
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _ensure_unique_email(db: Session, email: str | None, exclude_user_id: int | None = None) -> None:
    if not email:
        return

    normalized_email = User.normalize_email(email)
    query = db.query(User).filter(User.email == normalized_email)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)

    if query.first():
        raise HTTPException(status_code=400, detail="Email already exists")


def _ensure_unique_username(
    db: Session,
    username: str | None,
    exclude_user_id: int | None = None,
) -> None:
    normalized_username = _normalize_optional_text(username)
    if not normalized_username:
        return

    query = db.query(User).filter(User.username == normalized_username)
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)

    if query.first():
        raise HTTPException(status_code=400, detail="Username already exists")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_users(db: Session, skip: int = 0, limit: int = 10):
    return db.query(User).offset(skip).limit(limit).all()


def get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def create_user(db: Session, user_data: UserCreate) -> User:
    _ensure_unique_email(db, user_data.email)
    _ensure_unique_username(db, user_data.username)

    normalized_email = User.normalize_email(user_data.email) if user_data.email else None
    normalized_username = _normalize_optional_text(user_data.username)

    db_user = User(
        **user_data.model_dump(exclude={"password", "email", "username"}),
        email=normalized_email,
        username=normalized_username,
        password=hash_password(user_data.password),
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user_data: UserUpdate) -> User:
    user = get_user(db, user_id)

    update_data = user_data.model_dump(exclude_unset=True)

    if "email" in update_data:
        _ensure_unique_email(db, update_data.get("email"), exclude_user_id=user_id)
        update_data["email"] = (
            User.normalize_email(update_data["email"]) if update_data.get("email") else None
        )

    if "username" in update_data:
        _ensure_unique_username(db, update_data.get("username"), exclude_user_id=user_id)
        update_data["username"] = _normalize_optional_text(update_data.get("username"))

    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])
    elif "password" in update_data:
        update_data.pop("password")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    db.delete(user)
    db.commit()