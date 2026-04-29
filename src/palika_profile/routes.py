import json
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile

from src.auth.dependencies import get_current_user
from src.database import get_db

from src.palika_profile.schema import (
    PalikaGeometryResponse,
    PalikaGeometryUploadSummary,
    PalikaProfileCreate,
    PalikaProfileResponse,
    PalikaProfileUpdate,
    PalikaWardGeometryResponse,
    PalikaWardGeometryUploadSummary,
)
from src.palika_profile import service as palika_service

router = APIRouter(prefix="/api/v1/palika_profile", tags=["palika_profile"])

PROFILE_LOGO_DIR = Path("media") / "palika_profile" / "logos"


def _save_profile_logo(upload: UploadFile, field_name: str) -> str:
    if not upload.filename:
        raise HTTPException(
            status_code=422, detail=f"{field_name} file must have a filename"
        )

    PROFILE_LOGO_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename).suffix.lower()
    safe_name = f"{field_name}_{uuid.uuid4().hex}{suffix}"
    destination = PROFILE_LOGO_DIR / safe_name

    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return str(destination).replace("\\", "/")


def _is_upload_file(value: object) -> bool:
    return isinstance(value, (UploadFile, StarletteUploadFile))


async def _parse_profile_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "").lower()

    # Support both JSON payloads and multipart form-data from tools like Postman.
    if (
        "multipart/form-data" in content_type
        or "application/x-www-form-urlencoded" in content_type
    ):
        form = await request.form()
        payload = {str(key).strip(): value for key, value in form.items()}
    else:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Invalid request body") from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422, detail="Payload must be a JSON object or form fields"
        )

    # Persist uploaded logo files and replace the payload value with a string path.
    for field_name in ("logo_en", "logo_ne"):
        if _is_upload_file(payload.get(field_name)):
            payload[field_name] = _save_profile_logo(payload[field_name], field_name)

    important_links = payload.get("important_links")
    if isinstance(important_links, str) and important_links.strip():
        try:
            payload["important_links"] = json.loads(important_links)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=422, detail="important_links must be valid JSON"
            ) from exc

    return payload


@router.post("/profiles/", response_model=PalikaProfileResponse)
async def create_palika_profile(
    request: Request,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = PalikaProfileCreate(**(await _parse_profile_payload(request)))
    return palika_service.create_palika_profile(db=db, payload=payload)


@router.get("/profiles/", response_model=List[PalikaProfileResponse])
def list_palika_profiles(db: Session = Depends(get_db)):
    return palika_service.list_palika_profiles(db=db)


@router.get("/profiles/{profile_id}", response_model=PalikaProfileResponse)
def get_palika_profile(profile_id: int, db: Session = Depends(get_db)):
    return palika_service.get_palika_profile(db=db, profile_id=profile_id)


@router.patch("/profiles/{profile_id}", response_model=PalikaProfileResponse)
async def update_palika_profile(
    profile_id: int,
    request: Request,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = PalikaProfileUpdate(**(await _parse_profile_payload(request)))
    return palika_service.update_palika_profile(
        db=db, profile_id=profile_id, payload=payload
    )


@router.post("/geometry_files/upload", response_model=PalikaGeometryUploadSummary)
def upload_palika_geometry_file(
    file_upload: UploadFile = File(...),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return palika_service.upload_palika_geometry_file(db=db, upload=file_upload)


@router.post("/ward_geometries/upload", response_model=PalikaWardGeometryUploadSummary)
def upload_palika_ward_geometry_file(
    file_upload: UploadFile = File(...),
    ward_column: str | None = Form(default=None),
    numbering_status: str | None = Form(default=None),
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return palika_service.upload_palika_ward_geometry_file(
        db=db,
        upload=file_upload,
        ward_column=ward_column,
        numbering_status=numbering_status,
    )


@router.get("/geometries/current", response_model=PalikaGeometryResponse)
def get_palika_geometry(db: Session = Depends(get_db)):
    return palika_service.get_palika_geometry(db=db)


@router.get("/ward_geometries", response_model=List[PalikaWardGeometryResponse])
def list_palika_ward_geometries(
    db: Session = Depends(get_db), ward_no: str | None = None
):
    ward_nos = None
    if ward_no:
        ward_nos = [int(w.strip()) for w in ward_no.split(",")]
    return palika_service.list_palika_ward_geometries(db=db, ward_no=ward_nos)


@router.get("/ward_geometries/{ward_no}", response_model=PalikaWardGeometryResponse)
def get_palika_ward_geometry(ward_no: int, db: Session = Depends(get_db)):
    return palika_service.get_palika_ward_geometry_by_ward(db=db, ward_no=ward_no)


@router.get("/ward_numbers", response_model=List[int])
def get_unique_ward_numbers(db: Session = Depends(get_db)):
    return palika_service.get_unique_ward_numbers(db=db)
