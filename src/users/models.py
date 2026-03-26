from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from datetime import datetime
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
    email = Column(String(100), unique=True, nullable=True)
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

    is_active = Column(Boolean, default=True)
    is_staff = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)