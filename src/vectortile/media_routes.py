"""ProjectMedia CRUD API Routes"""

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

router = APIRouter(prefix="/api/v1/project_media", tags=["Project Media"])

MEDIA_DIR = Path("media")


def _save_upload_file(upload: UploadFile) -> str:
    """Save uploaded file and return file path."""

    if not upload.filename:
        raise HTTPException(status_code=422, detail="Filename is missing")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{suffix}"

    destination = MEDIA_DIR / safe_name

    with open(destination, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return str(destination).replace("\\", "/")


@router.post("/upload", response_model=ProjectMediaResponse)
def upload_project_media(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_path = _save_upload_file(file)

    media = create_project_media(
        db=db,
        file_path=file_path,
        user_id=current_user.id if current_user else None,
        name=name,
    )

    return media


@router.get("", response_model=dict)
def list_media(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Get all project media files (name -> file_path mapping)."""
    return list_project_media(db, skip=skip, limit=limit)


@router.get("/{media_id}", response_model=ProjectMediaResponse)
def get_media(
    media_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific project media by ID."""
    return get_project_media_by_id(db, media_id)


@router.get("/search", response_model=List[ProjectMediaResponse])
def search_media(
    q: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Search project media by name."""
    if not q or len(q) < 2:
        raise HTTPException(
            status_code=400, detail="Search query must be at least 2 characters"
        )
    return search_project_media(db, q, skip=skip, limit=limit)


@router.patch("/{media_id}", response_model=ProjectMediaResponse)
def update_media(
    media_id: int,
    payload: ProjectMediaUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update project media details."""
    return update_project_media(db, media_id, payload)


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete (soft delete) a project media."""
    delete_project_media(db, media_id)
    return {"message": "Project media deleted successfully"}
