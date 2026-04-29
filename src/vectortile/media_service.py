"""ProjectMedia CRUD Service Module"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from src.models import ProjectMedia
from src.vectortile.schema import ProjectMediaCreate, ProjectMediaUpdate

logger = logging.getLogger(__name__)


def list_project_media(db: Session, skip: int = 0, limit: int = 100) -> dict:
    """
    Get all non-deleted project media with file names and paths.

    Returns dict where key is name (or filename) and value is file_path.
    For duplicate names, uses filename as fallback to ensure uniqueness.
    """
    media_items = (
        db.query(ProjectMedia)
        .filter(ProjectMedia.is_deleted == False)
        .offset(skip)
        .limit(limit)
        .all()
    )

    logger.debug(
        f"Retrieved {len(media_items)} media items (skip={skip}, limit={limit})"
    )

    media_data = {}
    for item in media_items:
        # Use custom name if provided, fallback to extracted filename, then ID-based name
        name = item.name
        if not name:
            name = (
                item.file_path.split("/")[-1] if item.file_path else f"file_{item.id}"
            )

        # Handle duplicate names by appending ID suffix
        if name in media_data:
            logger.warning(f"Duplicate name found: {name}, appending ID")
            name = f"{name}_{item.id}"

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
        logger.warning(f"Media not found: id={media_id}")
        raise HTTPException(
            status_code=404, detail=f"Project media with id {media_id} not found"
        )
    return media


def create_project_media(
    db: Session,
    file_path: str,
    user_id: Optional[int] = None,
    name: Optional[str] = None,
) -> ProjectMedia:
    """Create a new project media entry."""
    try:
        media = ProjectMedia(
            name=name,
            file_path=file_path,
            uploaded_by=user_id,
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        logger.info(
            f"Created media record: id={media.id}, path={file_path}, user={user_id}"
        )
        return media
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating media: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create media record")


def update_project_media(
    db: Session,
    media_id: int,
    payload: ProjectMediaUpdate,
) -> ProjectMedia:
    """Update project media details."""
    try:
        media = get_project_media_by_id(db, media_id)

        update_data = payload.dict(exclude_unset=True)
        if not update_data:
            logger.warning(f"Update called with no changes: id={media_id}")
            return media

        for field, value in update_data.items():
            setattr(media, field, value)

        db.commit()
        db.refresh(media)
        logger.info(f"Updated media: id={media_id}, fields={list(update_data.keys())}")
        return media
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating media {media_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update media")


def delete_project_media(db: Session, media_id: int) -> None:
    """Soft delete a project media."""
    try:
        media = get_project_media_by_id(db, media_id)
        media.is_deleted = True
        db.commit()
        logger.info(f"Soft deleted media: id={media_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting media {media_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete media")


def search_project_media(
    db: Session,
    search_query: str,
    skip: int = 0,
    limit: int = 100,
) -> List[ProjectMedia]:
    """
    Search project media by name or file path.

    Searches in both name and file_path fields for comprehensive results.
    Handles NULL names gracefully.
    """
    try:
        results = (
            db.query(ProjectMedia)
            .filter(
                ProjectMedia.is_deleted == False,
                or_(
                    ProjectMedia.name.ilike(f"%{search_query}%"),
                    ProjectMedia.file_path.ilike(f"%{search_query}%"),
                ),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        logger.debug(f"Search results: query='{search_query}', found={len(results)}")
        return results
    except Exception as e:
        logger.error(f"Error searching media: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")
