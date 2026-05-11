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
