from typing import Optional
from datetime import datetime
from pydantic import BaseModel


class ProjectMediaBase(BaseModel):
    """Base schema for project media."""

    name: Optional[str] = None


class ProjectMediaCreate(ProjectMediaBase):
    """Schema for creating project media."""

    pass


class ProjectMediaUpdate(BaseModel):
    """Schema for updating project media."""

    name: Optional[str] = None


class ProjectMediaResponse(ProjectMediaBase):
    """Response schema for project media."""

    id: int
    name: Optional[str] = None
    file_path: str
    uploaded_by: Optional[int] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True
