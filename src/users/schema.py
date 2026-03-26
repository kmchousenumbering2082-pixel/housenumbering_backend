from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str 

    gender: Optional[str] = "Male"
    ward: Optional[List[int]] = None

    group_id: Optional[int] = None
    designation: Optional[str] = None

    phone: Optional[str] = None
    address: Optional[str] = None

    image: Optional[str] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

    gender: Optional[str] = None
    ward: Optional[List[int]] = None

    group_id: Optional[int] = None
    designation: Optional[str] = None

    phone: Optional[str] = None
    address: Optional[str] = None

    image: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    username: Optional[str]
    email: Optional[EmailStr]

    gender: Optional[str]
    ward: Optional[List[int]]

    group_id: Optional[int]
    designation: Optional[str]

    phone: Optional[str]
    address: Optional[str]

    image: Optional[str]
    thumbnail: Optional[str]

    is_active: bool
    is_staff: bool
    is_superuser: bool

    date_created: Optional[datetime]
    date_modified: Optional[datetime]

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True