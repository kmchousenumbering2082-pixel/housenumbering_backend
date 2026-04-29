"""ProjectMedia CRUD API Routes"""

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, File, UploadFile, Form, HTTPException
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import uuid

from src.database import get_db
from src.auth.dependencies import get_current_user
from src.vectortile.schema import ProjectMediaResponse, ProjectMediaUpdate
from src.vectortile.media_service import (
    list_project_media,
    get_project_media_by_id,
    create_project_media,
    update_project_media,
    delete_project_media,
    search_project_media,
)
from src.vectortile.config import (
    MEDIA_DIR,
    MEDIA_DIR_STR,
    MAX_FILE_SIZE,
    ALLOWED_EXTENSIONS,
    MISSING_FILENAME,
    INVALID_FILE_SIZE,
    INVALID_EXTENSION,
)

router = APIRouter(prefix="/api/v1/project_media", tags=["Project Media"])
logger = logging.getLogger(__name__)


def _save_upload_file(upload: UploadFile) -> str:
    """
    Save uploaded file with validation.

    Args:
        upload: UploadFile instance

    Returns:
        str: Relative file path (e.g., "media/uuid.pdf")

    Raises:
        HTTPException: If file validation fails
    """
    # Validate filename
    if not upload.filename:
        logger.warning("Upload attempted without filename")
        raise HTTPException(status_code=422, detail=MISSING_FILENAME)

    # Validate extension
    file_ext = Path(upload.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        logger.warning(f"Invalid extension attempted: {file_ext}")
        raise HTTPException(status_code=400, detail=INVALID_EXTENSION)

    # Validate file size
    upload.file.seek(0, 2)  # Seek to end
    file_size = upload.file.tell()
    upload.file.seek(0)  # Reset to start

    if file_size > MAX_FILE_SIZE:
        logger.warning(f"File size exceeds limit: {file_size} > {MAX_FILE_SIZE}")
        raise HTTPException(status_code=413, detail=INVALID_FILE_SIZE)

    # Create directory if needed
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    # Generate unique safe filename
    safe_name = f"{uuid.uuid4().hex}{file_ext}"
    destination = MEDIA_DIR / safe_name

    try:
        # Save file to disk
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)

        logger.info(f"File saved successfully: {safe_name}")
        return str(destination).replace("\\", "/")

    except Exception as e:
        logger.error(f"Failed to save file {safe_name}: {str(e)}")
        # Cleanup on failure
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to save file")


@router.post("/upload", response_model=ProjectMediaResponse)
def upload_project_media(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a project media file with optional name."""
    if not file:
        raise HTTPException(status_code=400, detail="File is required")

    file_path = _save_upload_file(file)

    try:
        media = create_project_media(
            db=db,
            file_path=file_path,
            user_id=current_user.id if current_user else None,
            name=name,
        )
        logger.info(
            f"Media created: id={media.id}, user={current_user.id if current_user else None}"
        )
        return media

    except Exception as e:
        # Cleanup file if database operation fails
        logger.error(f"Failed to create media record: {str(e)}")
        Path(file_path).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Failed to process upload")


@router.get("", response_model=dict)
def list_media(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get all project media files (name -> file_path mapping)."""
    logger.debug(f"Listing media: skip={skip}, limit={limit}")
    return list_project_media(db, skip=skip, limit=limit)


@router.get("/{media_id}", response_model=ProjectMediaResponse)
def get_media(
    media_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific project media by ID."""
    logger.debug(f"Fetching media: id={media_id}")
    return get_project_media_by_id(db, media_id)


@router.get("/search", response_model=List[ProjectMediaResponse])
def search_media(
    q: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Search project media by name or file path."""
    if not q or len(q) < 2:
        logger.warning(f"Invalid search query: '{q}'")
        raise HTTPException(
            status_code=400, detail="Search query must be at least 2 characters"
        )
    logger.debug(f"Searching media: query='{q}', skip={skip}, limit={limit}")
    return search_project_media(db, q, skip=skip, limit=limit)


@router.patch("/{media_id}", response_model=ProjectMediaResponse)
def update_media(
    media_id: int,
    payload: ProjectMediaUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update project media details."""
    logger.info(
        f"Updating media: id={media_id}, user={current_user.id if current_user else None}"
    )
    return update_project_media(db, media_id, payload)


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete (soft delete) a project media."""
    logger.info(
        f"Deleting media: id={media_id}, user={current_user.id if current_user else None}"
    )
    delete_project_media(db, media_id)
    return {"message": "Project media deleted successfully"}
