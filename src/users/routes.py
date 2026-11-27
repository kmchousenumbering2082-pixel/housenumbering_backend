from typing import List

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.pagination import Pagination
from src.users.schema import UserCreate, UserUpdate, UserResponse
from src.users import service as user_service

router = APIRouter(prefix="/api/v1/user", tags=["Users"])


@router.post("/", response_model=UserResponse)
def create_user(
    user: UserCreate, _=Depends(get_current_user), db: Session = Depends(get_db)
):
    return user_service.create_user(db, user)


@router.get("/", response_model=List[UserResponse])
def get_users(pagination: Pagination = Depends(), db: Session = Depends(get_db)):
    return user_service.get_users(db, skip=pagination.skip, limit=pagination.limit)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, _=Depends(get_current_user), db: Session = Depends(get_db)):
    return user_service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: Request,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    form = await request.form()
    payload = {str(key).strip(): value for key, value in form.items()}

    user = UserUpdate(**payload)
    return user_service.update_user(db, user_id, user)


@router.delete("/{user_id}")
def delete_user(
    user_id: int, _=Depends(get_current_user), db: Session = Depends(get_db)
):
    user_service.delete_user(db, user_id)
    return {"message": "User deleted successfully"}
