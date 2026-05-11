from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, field_validator


class RasterLayerMetadataBase(BaseModel):
    """Base schema for raster layer metadata."""

    width: Optional[int] = None
    height: Optional[int] = None
    numbands: Optional[int] = None
    srid: Optional[int] = None
    extent: Optional[Union[dict[str, Any], list]] = None  # Accept both dict and list
    legend: Optional[dict[str, Any]] = None
    stats: Optional[dict[str, Any]] = None
    pixel_size: Optional[float] = None
    minx: float = 0
    maxx: float = 0
    miny: float = 0
    maxy: float = 0
    file_name: Optional[str] = None


class RasterLayerMetadataResponse(RasterLayerMetadataBase):
    """Response schema for raster layer metadata."""

    id: int
    raster_layer_id: int
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class RasterLayerBase(BaseModel):
    """Base schema for raster layer."""

    name_en: Optional[str] = None
    name_ne: Optional[str] = None
    attr_data: Optional[dict[str, Any]] = None
    display_on_map: bool = True
    is_public: bool = True


class RasterLayerCreate(RasterLayerBase):
    """Schema for creating a raster layer."""

    pass


class RasterLayerUpdate(RasterLayerBase):
    """Schema for updating a raster layer."""

    status: Optional[str] = None


class RasterLayerResponse(RasterLayerBase):
    """Response schema for raster layer with metadata."""

    id: int
    raster_file: str
    sld_file: Optional[str] = None
    status: Optional[str] = None
    bbox: Optional[dict[str, Any]] = None
    raster_metadata: list[RasterLayerMetadataResponse] = []
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class RasterUploadSummary(BaseModel):
    """Summary response for raster file upload."""

    raster_id: int
    file_name: str
    status: str
    message: str
    width: Optional[int] = None
    height: Optional[int] = None
    numbands: Optional[int] = None
    srid: Optional[int] = None


class BaseLayerBase(BaseModel):
    """Base schema for base layer."""

    name: Optional[str] = None
    layer_type: str
    url: Optional[str] = None
    attribution: Optional[str] = None
    is_active: bool = True


class BaseLayerCreate(BaseLayerBase):
    """Schema for creating a base layer."""

    name: str  # Required for creation
    pass


class BaseLayerUpdate(BaseLayerBase):
    """Schema for updating a base layer."""

    pass


class BaseLayerNameBase(BaseModel):
    """Base schema for base layer name."""

    name: str
    label_en: Optional[str] = None
    label_ne: Optional[str] = None
    order: int = 1
    is_visible: bool = True


class BaseLayerNameCreate(BaseLayerNameBase):
    """Schema for creating a base layer name."""

    base_layer_id: int


class BaseLayerNameUpdate(BaseLayerNameBase):
    """Schema for updating a base layer name."""

    pass


class BaseLayerNameResponse(BaseLayerNameBase):
    """Response schema for base layer name."""

    id: int
    base_layer_id: int
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class BaseLayerResponse(BaseLayerBase):
    """Response schema for base layer."""

    id: int
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True


class BaseLayerWithNamesResponse(BaseLayerResponse):
    """Response schema for base layer with its names."""

    names: list[BaseLayerNameResponse] = []

    class Config:
        from_attributes = True
