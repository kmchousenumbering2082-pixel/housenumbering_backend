from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr


class PalikaProfileBase(BaseModel):
    name_en: str | None = None
    name_ne: str | None = None
    description_en: str | None = None
    description_ne: str | None = None
    logo_en: str | None = None
    logo_ne: str | None = None
    contact_info: str | None = None
    important_links: dict[str, Any] | None = None
    email: EmailStr | None = None
    zip_code: str | None = None
    address: str | None = None
    local_coordinate_system: int | None = None


class PalikaProfileCreate(PalikaProfileBase):
    pass


class PalikaProfileUpdate(PalikaProfileBase):
    pass


class PalikaProfileResponse(PalikaProfileBase):
    id: int
    timestamp: datetime | None = None

    class Config:
        from_attributes = True


class PalikaGeometryBase(BaseModel):
    area: float | None = None
    bbox: dict[str, Any] | None = None
    geom: str | None = None


class PalikaGeometryResponse(PalikaGeometryBase):
    id: int
    timestamp: datetime | None = None

    class Config:
        from_attributes = True


class PalikaWardGeometryBase(BaseModel):
    ward_no: int | None = None
    numbering_status: str | None = None
    area: float | None = None
    bbox: dict[str, Any] | None = None
    geom: str | None = None


class PalikaWardGeometryResponse(PalikaWardGeometryBase):
    id: int
    timestamp: datetime | None = None

    class Config:
        from_attributes = True


class PalikaGeometryUploadSummary(BaseModel):
    file_id: int
    file_type: str
    file_upload: str
    feature_count: int
    updated_geometry_id: int


class PalikaWardGeometryUploadSummary(BaseModel):
    file_id: int
    file_type: str
    file_upload: str
    feature_count: int
    ward_count: int
    updated_ward_ids: list[int]


class WardNumbersResponse(BaseModel):
    count: int
    ward_numbers: list[int]
