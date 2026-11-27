from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel


class RoadBase(BaseModel):
    road_name_en: Optional[str] = None
    road_name_ne: Optional[str] = None
    road_id: Optional[int] = None
    unique_id: Optional[str] = None
    road_type: Optional[str] = None
    road_category: Optional[str] = None
    road_class: Optional[str] = None
    road_lane: Optional[str] = None
    road_width: Optional[float] = None
    road_length: Optional[float] = None
    direction: Optional[str] = None
    # Some records store a single ward number, others store structured JSON.
    ward_no: Optional[Union[int, dict, list]] = None
    attr_data: Optional[dict] = None
    lat_field: Optional[str] = None
    long_field: Optional[str] = None
    remarks: Optional[str] = None
    bbox: Optional[dict] = None
    timestamp: Optional[datetime] = None
    last_data_request: Optional[datetime] = None
    slope_distance: Optional[float] = None


class RoadCreate(RoadBase):
    pass


class RoadUpdate(RoadBase):
    pass


class RoadResponse(RoadBase):
    id: int

    class Config:
        from_attributes = True


class RoadPublicItemResponse(BaseModel):
    id: int
    road_id: Optional[int] = None
    road_name_en: Optional[str] = None
    road_type: Optional[str] = None
    road_category: Optional[str] = None
    road_class: Optional[str] = None
    road_lane: Optional[str] = None
    road_width: Optional[float] = None
    road_length: Optional[float] = None
    direction: Optional[str] = None
    ward_no: Optional[Union[int, dict, list]] = None
    bbox: Optional[dict] = None

    class Config:
        from_attributes = True


class RoadPublicPageResponse(BaseModel):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[RoadPublicItemResponse]


class RoadGeometryCreate(BaseModel):
    road_id: int
    geom: Optional[str]


class RoadGeometryResponse(BaseModel):
    id: int
    road_id: int
    geom: Optional[str]

    created_by: Optional[int]
    updated_by: Optional[int]

    is_deleted: bool

    class Config:
        from_attributes = True
