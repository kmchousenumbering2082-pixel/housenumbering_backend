"""
Vector Layer Pydantic Schemas

Request/response schemas for vector layer and feature management:
  - VectorLayerCreate/Update: Layer configuration
  - VectorLayerResponse: Layer with features
  - FeatureCollectionCreate/Update: Feature geometry and attributes
  - FeatureCollectionResponse: Feature with metadata
  - VectorUploadSummary: File upload results
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class VectorLayerBase(BaseModel):
    """Base schema for vector layer."""

    name_en: Optional[str] = None
    name_ne: Optional[str] = None
    layer_type: Optional[str] = None  # polygon, line, point
    attr_data: Optional[dict[str, Any]] = None
    style_value: Optional[str] = None
    label_value: Optional[str] = None
    is_public: bool = True
    display_on_map: bool = False


class VectorLayerCreate(VectorLayerBase):
    """Schema for creating a vector layer."""

    pass


class VectorLayerUpdate(VectorLayerBase):
    """Schema for updating a vector layer."""

    pass


class FeatureCollectionBase(BaseModel):
    """Base schema for feature collection."""

    vector_layer_id: Optional[int] = None
    attr_data: Optional[dict[str, Any]] = None
    geom: Optional[str] = None  # Geometry as WKT string
    style_value: Optional[str] = None
    label_value: Optional[str] = None


class FeatureCollectionCreate(FeatureCollectionBase):
    """Schema for creating a feature."""

    pass


class FeatureCollectionUpdate(FeatureCollectionBase):
    """Schema for updating a feature."""

    is_deleted: Optional[bool] = None


class FeatureCollectionResponse(FeatureCollectionBase):
    """Response schema for a feature."""

    id: int
    attr_data: Optional[dict[str, Any]] = None
    geom: Optional[str] = None
    style_value: Optional[str] = None
    label_value: Optional[str] = None
    is_deleted: bool = False
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = False


class VectorLayerResponse(VectorLayerBase):
    """Response schema for vector layer."""

    id: int
    name_en: Optional[str] = None
    name_ne: Optional[str] = None
    layer_type: Optional[str] = None
    attr_data: Optional[dict[str, Any]] = None
    style_value: Optional[str] = None
    label_value: Optional[str] = None
    is_public: bool = True
    display_on_map: bool = False
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    timestamp: Optional[datetime] = None
    # features: list[FeatureCollectionResponse] = []

    class Config:
        from_attributes = False


class VectorLayerDetailResponse(VectorLayerResponse):
    """Detailed response schema for vector layer with all features."""

    features: list[FeatureCollectionResponse] = []

    class Config:
        from_attributes = False


class FeatureCollectionListResponse(BaseModel):
    """Response schema for feature list with pagination."""

    id: int
    vector_layer_id: Optional[int] = None
    style_value: Optional[str] = None
    label_value: Optional[str] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class VectorUploadSummary(BaseModel):
    """Response schema for vector file upload."""

    layer_id: int
    layer_name: str
    layer_type: str
    feature_count: int
    file_name: str
    message: str
    status: str = "success"


class VectorUploadResponse(VectorLayerResponse):
    """Response schema for vector upload with layer details."""

    feature_count: int = 0

    class Config:
        from_attributes = True


# Map Popup Schemas


class BuildingPopupResponse(BaseModel):
    """Building information for map popup."""

    id: int
    building_id: Optional[int] = None
    house_no: Optional[str] = None
    plot_no: Optional[str] = None
    tole_name: Optional[str] = None
    ward_no: Optional[int] = None
    owner_name: Optional[str] = None
    owner_status: Optional[str] = None
    building_use: Optional[str] = None
    building_structure: Optional[str] = None
    roof_type: Optional[str] = None
    floor: Optional[float] = None
    plinth_area: Optional[float] = None
    road_type: Optional[str] = None
    road_lane: Optional[str] = None
    road_width: Optional[float] = None
    direction: Optional[str] = None
    reg_type: Optional[str] = None
    plus_code: Optional[str] = None
    metric_address: Optional[str] = None
    remarks: Optional[str] = None
    attr_data: Optional[dict[str, Any]] = None
    timestamp: Optional[str] = None


class RoadPopupResponse(BaseModel):
    """Road information for map popup."""

    id: int
    road_id: Optional[int] = None
    unique_id: Optional[str] = None
    road_name_en: Optional[str] = None
    road_name_ne: Optional[str] = None
    road_type: Optional[str] = None
    road_category: Optional[str] = None
    road_class: Optional[str] = None
    road_lane: Optional[str] = None
    road_width: Optional[float] = None
    road_length: Optional[float] = None
    direction: Optional[str] = None
    ward_no: Optional[list] = None
    remarks: Optional[str] = None
    slope_distance: Optional[float] = None
    attr_data: Optional[dict[str, Any]] = None
    timestamp: Optional[str] = None


class MapPopupResponse(BaseModel):
    """Generic map popup response for building or road."""

    id: int
    type: str  # "building" or "road"
    data: Optional[dict[str, Any]] = None
