from typing import Any, List, Optional

from pydantic import BaseModel

from src.roads.schema import RoadResponse


class BuildingCreate(BaseModel):
    building_id: Optional[int]
    road_id: Optional[int]
    main_building_id: Optional[int]
    owner_status: Optional[str]
    temporary_type: Optional[str]
    association_type: Optional[str]
    roof_type: Optional[str]
    building_structure: Optional[str]
    reg_type: Optional[str]
    building_use: Optional[str]
    building_sp_use: Optional[str]
    road_type: Optional[str]
    road_lane: Optional[str]
    road_width: Optional[float]
    direction: Optional[str]
    plot_no: Optional[str]
    house_no: Optional[str]
    ward_no: Optional[int]
    floor: Optional[float]
    tole_name: Optional[str]
    owner_name: Optional[str]
    plinth_area: Optional[float]
    remarks: Optional[str]
    metric_address: Optional[str]
    attr_data: Optional[dict]
    lat_field: Optional[str]
    long_field: Optional[str]
    plus_code: Optional[str]
    bbox: Optional[dict]


class BuildingGeometryCreate(BaseModel):
    building_id: int
    geom: Optional[str]


class BuildingResponse(BaseModel):
    building_id: Optional[int]
    road_id: Optional[int]
    house_no: Optional[str]
    metric_address: Optional[str]
    roof_type: Optional[str]
    plinth_area: Optional[float]
    lat_field: Optional[str]
    long_field: Optional[str]
    ward_no: Optional[int]
    plus_code: Optional[str] = None
    road: Optional[RoadResponse] = None

    class Config:
        from_attributes = True


class BuildingPublicItemResponse(BaseModel):
    id: int
    building_id: Optional[int] = None
    ward_no: Optional[int] = None
    plus_code: Optional[str] = None
    house_no: Optional[str] = None
    association_type: Optional[str] = None
    associate_road_name: Optional[str] = None
    bbox: Optional[Any] = None

    class Config:
        from_attributes = True


class BuildingPublicPageResponse(BaseModel):
    count: int
    next: Optional[str] = None
    previous: Optional[str] = None
    results: List[BuildingPublicItemResponse]


class BuildingGeometryResponse(BaseModel):
    id: int
    building_id: int
    geom: Optional[str]

    created_by: Optional[int]
    updated_by: Optional[int]

    is_deleted: bool

    class Config:
        from_attributes = True
