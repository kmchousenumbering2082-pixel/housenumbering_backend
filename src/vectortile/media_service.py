"""ProjectMedia CRUD Service Module"""

from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.models import ProjectMedia
from src.vectortile.schema import ProjectMediaCreate, ProjectMediaUpdate


def list_project_media(db: Session, skip: int = 0, limit: int = 100) -> dict:
    """Get all non-deleted project media with file names and paths."""
    media_items = (
        db.query(ProjectMedia)
        .filter(ProjectMedia.is_deleted == False)
        .offset(skip)
        .limit(limit)
        .all()
    )

    media_data = {}
    for item in media_items:
        # Use name from model, fallback to extracted filename
        name = item.name or (
            item.file_path.split("/")[-1] if item.file_path else f"file_{item.id}"
        )
        media_data[name] = item.file_path

    return media_data


def get_project_media_by_id(db: Session, media_id: int) -> ProjectMedia:
    """Get a project media by ID."""
    media = (
        db.query(ProjectMedia)
        .filter(ProjectMedia.id == media_id, ProjectMedia.is_deleted == False)
        .first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="Project media not found")
    return media


def create_project_media(
    db: Session,
    file_path: str,
    user_id: Optional[int] = None,
    name: Optional[str] = None,
) -> ProjectMedia:
    """Create a new project media entry."""
    media = ProjectMedia(
        name=name,
        file_path=file_path,
        uploaded_by=user_id,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


def update_project_media(
    db: Session,
    media_id: int,
    payload: ProjectMediaUpdate,
) -> ProjectMedia:
    """Update project media details."""
    media = get_project_media_by_id(db, media_id)

    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(media, field, value)

    db.commit()
    db.refresh(media)
    return media


def delete_project_media(db: Session, media_id: int) -> None:
    """Soft delete a project media."""
    media = get_project_media_by_id(db, media_id)
    media.is_deleted = True
    db.commit()


def search_project_media(
    db: Session,
    search_query: str,
    skip: int = 0,
    limit: int = 100,
) -> List[ProjectMedia]:
    """Search project media by name."""
    return (
        db.query(ProjectMedia)
        .filter(
            ProjectMedia.is_deleted == False,
            ProjectMedia.name.ilike(f"%{search_query}%"),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
