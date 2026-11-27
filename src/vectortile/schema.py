from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ProjectMediaBase(BaseModel):
    """Base schema for project media."""

    name: Optional[str] = Field(None, description="Display name for the media file")


class ProjectMediaCreate(ProjectMediaBase):
    """Schema for creating project media."""

    pass


class ProjectMediaUpdate(BaseModel):
    """Schema for updating project media details."""

    name: Optional[str] = Field(None, description="Display name for the media file")


class ProjectMediaResponse(ProjectMediaBase):
    """Response schema for project media with all fields."""

    id: int = Field(..., description="Unique identifier")
    name: Optional[str] = Field(None, description="Display name for the media file")
    file_path: str = Field(..., description="Path to the stored file")
    uploaded_by: Optional[int] = Field(
        None, description="User ID who uploaded the file"
    )
    timestamp: Optional[datetime] = Field(None, description="Upload timestamp")

    class Config:
        from_attributes = True
