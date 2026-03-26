from sqlalchemy.orm import Session
from fastapi import HTTPException
from src.users.models import User
from src.users.schema import UserCreate, UserUpdate
from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    if user_data.email:
        existing_email = db.query(User).filter(User.email == user_data.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists")

    if user_data.username:
        existing_username = db.query(User).filter(User.username == user_data.username).first()
        if existing_username:
            raise HTTPException(status_code=400, detail="Username already exists")

    hashed_password = hash_password(user_data.password)

    db_user = User(
        **user_data.model_dump(exclude={"password"}),
        password=hashed_password
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def update_user(db: Session, user_id: int, user_data: UserUpdate) -> User:
    user = get_user(db, user_id)

    update_data = user_data.model_dump(exclude_unset=True)

    if "password" in update_data:
        update_data["password"] = hash_password(update_data["password"])

    if "email" in update_data and update_data["email"]:
        existing_email = (
            db.query(User)
            .filter(User.email == update_data["email"], User.id != user_id)
            .first()
        )
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already exists")

    if "username" in update_data and update_data["username"]:
        existing_username = (
            db.query(User)
            .filter(User.username == update_data["username"], User.id != user_id)
            .first()
        )
        if existing_username:
            raise HTTPException(status_code=400, detail="Username already exists")

    for key, value in update_data.items():
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


def delete_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    db.delete(user)
    db.commit()