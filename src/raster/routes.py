from typing import List

from pathlib import Path as FilePath

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    Response,
    Path,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.raster import service as raster_service
from src.raster.schema import (
    RasterLayerCreate,
    RasterLayerResponse,
    RasterLayerUpdate,
    RasterUploadSummary,
    BaseLayerCreate,
    BaseLayerResponse,
    BaseLayerUpdate,
    BaseLayerNameCreate,
    BaseLayerNameResponse,
    BaseLayerWithNamesResponse,
)

router = APIRouter(prefix="/api/v1/raster", tags=["Rasters"])
base_layer = APIRouter(prefix="/api/v1/base_layers", tags=["Base Layers"])


# ============================================================================
# RASTER LAYER ENDPOINTS
# ============================================================================


def _process_raster_upload(
    file_upload: UploadFile,
    name_en: str | None,
    name_ne: str | None,
    display_on_map: bool,
    is_public: bool,
    current_user,
    db: Session,
):
    """Shared upload logic for both /upload and /upload/ routes"""
    payload = RasterLayerCreate(
        name_en=name_en,
        name_ne=name_ne,
        display_on_map=display_on_map,
        is_public=is_public,
    )

    result = raster_service.create_raster_layer(
        db=db,
        upload=file_upload,
        payload=payload,
        user_id=current_user.id if current_user else None,
    )
    return result


@router.post("/upload", response_model=RasterUploadSummary)
def upload_raster_file(
    file_upload: UploadFile = File(...),
    name_en: str | None = Form(None),
    name_ne: str | None = Form(None),
    display_on_map: bool = Form(default=True),
    is_public: bool = Form(default=True),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a raster DEM/orthophoto file and save it with automatic metadata extraction.

    Supported formats: .tif, .tiff, .geotiff, .ecw, .vrt, .jp2, .jp2k

    The endpoint will:
    - Validate the raster file format
    - Extract raster metadata (width, height, bands, SRID, extent)
    - Store the file and metadata in the database
    - Return raster details for frontend visualization
    """
    return _process_raster_upload(
        file_upload, name_en, name_ne, display_on_map, is_public, current_user, db
    )


@router.get("/", response_model=List[RasterLayerResponse])
def list_raster_layers(
    skip: int = 0,
    limit: int = 100,
    public_only: bool = True,
    db: Session = Depends(get_db),
):
    """
    List all raster layers with pagination.

    Args:
        skip: Number of records to skip (default: 0)
        limit: Maximum records to return (default: 100)
        public_only: If True, only return public layers (default: True)
    """
    layers = raster_service.list_raster_layers(
        db=db,
        skip=skip,
        limit=limit,
        is_public=public_only,
    )
    return layers


@router.get("/{raster_id}", response_model=RasterLayerResponse)
def get_raster_layer(raster_id: int, db: Session = Depends(get_db)):
    """Get a specific raster layer with its metadata."""
    layer = raster_service.get_raster_layer(db, raster_id)
    return layer


@router.get("/{raster_id}/file")
def get_raster_file(raster_id: int, db: Session = Depends(get_db)):
    """Download the uploaded raster file for client-side rendering."""
    layer = raster_service.get_raster_layer(db, raster_id)
    file_path = FilePath(layer.raster_file)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Raster file not found")

    return FileResponse(
        path=str(file_path),
        media_type="image/tiff",
        filename=file_path.name,
    )


@router.patch("/{raster_id}", response_model=RasterLayerResponse)
def update_raster_layer(
    raster_id: int,
    payload: RasterLayerUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update raster layer properties (name, status, visibility, etc.)."""
    layer = raster_service.update_raster_layer(db, raster_id, payload)
    return layer


@router.delete("/{raster_id}")
def delete_raster_layer(
    raster_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a raster layer and its associated file."""
    raster_service.delete_raster_layer(db, raster_id)
    return {"message": "Raster layer deleted successfully"}


# ============================================================================
# BASE LAYER ENDPOINTS
# ============================================================================


@base_layer.post("/", response_model=BaseLayerResponse)
def create_base_layer(
    layer_type: str = Form(...),
    name: str | None = Form(None),
    url: str | None = Form(None),
    attribution: str | None = Form(None),
    is_active: str = Form("true"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new base layer."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="name field is required")

    is_active_bool = is_active.lower() in ("true", "1", "yes")

    payload = BaseLayerCreate(
        name=name.strip(),
        layer_type=layer_type,
        url=url,
        attribution=attribution,
        is_active=is_active_bool,
    )

    layer = raster_service.create_base_layer(
        db=db,
        payload=payload,
        user_id=current_user.id if current_user else None,
    )
    return layer


@base_layer.get("/", response_model=List[BaseLayerResponse])
def list_base_layers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    List all available base layers.

    Returns base layers ordered by their display order.
    """
    layers = raster_service.list_base_layers(db, skip=skip, limit=limit)
    return layers


@base_layer.get("/names", response_model=List[BaseLayerWithNamesResponse])
def list_all_base_layer_names(db: Session = Depends(get_db)):
    """Get all base layers with their names."""
    layers = raster_service.list_base_layers(db=db, skip=0, limit=9999)
    result = []
    for layer in layers:
        layer_dict = {
            "id": layer.id,
            "name": layer.name,
            "layer_type": layer.layer_type,
            "url": layer.url,
            "attribution": layer.attribution,
            "is_active": layer.is_active,
            "timestamp": layer.timestamp,
            "names": raster_service.get_base_layer_names(db=db, layer_id=layer.id),
        }
        result.append(layer_dict)
    return result


@base_layer.get("/{layer_id}", response_model=BaseLayerResponse)
def get_base_layer(layer_id: int, db: Session = Depends(get_db)):
    """Get a specific base layer."""
    layer = raster_service.get_base_layer(db, layer_id)
    return layer


@base_layer.patch("/{layer_id}", response_model=BaseLayerResponse)
def update_base_layer(
    layer_id: int,
    payload: BaseLayerUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a base layer's properties."""
    layer = raster_service.update_base_layer(db, layer_id, payload)
    return layer


@base_layer.delete("/{layer_id}")
def delete_base_layer(
    layer_id: int,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a base layer."""
    raster_service.delete_base_layer(db, layer_id)
    return {"message": "Base layer deleted successfully"}


# =============================================================================
# VECTOR TILE ENDPOINTS
# =============================================================================

_BUILDING_MVT_SQL = text("""
    WITH bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS geom
    ),
    tile_features AS (
        SELECT
            b.id,
            b.building_id,
            b.ward_no,
            b.floor,
            ST_AsMVTGeom(
                ST_Transform(bg.geom, 3857),
                bounds.geom,
                4096,
                256,
                true
            ) AS geom
        FROM building_geometry bg
        JOIN buildings b ON b.id = bg.building_id
        JOIN bounds ON ST_Intersects(ST_Transform(bg.geom, 3857), bounds.geom)
        WHERE bg.geom IS NOT NULL
          AND COALESCE(bg.is_deleted, false) = false
            AND (
                :ward_nos IS NULL
                OR b.ward_no::text = ANY(string_to_array(:ward_nos, ','))
            )
    )
    SELECT COALESCE(ST_AsMVT(tile_features, 'buildings', 4096, 'geom'), '\\x'::bytea) AS tile
    FROM tile_features
    """)

_ROAD_MVT_SQL = text("""
    WITH bounds AS (
        SELECT ST_TileEnvelope(:z, :x, :y) AS geom
    ),
    tile_features AS (
        SELECT
            r.id,
            r.road_id,
            r.ward_no,
            r.road_type,
            ST_AsMVTGeom(
                ST_Transform(rg.geom, 3857),
                bounds.geom,
                4096,
                256,
                true
            ) AS geom
        FROM road_geometry rg
        JOIN roads r ON r.id = rg.road_id
        JOIN bounds ON ST_Intersects(ST_Transform(rg.geom, 3857), bounds.geom)
        WHERE rg.geom IS NOT NULL
          AND COALESCE(rg.is_deleted, false) = false
          AND (
                :ward_nos IS NULL
                OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(r.ward_no) AS elem
                    WHERE (elem::text)::int = ANY(string_to_array(:ward_nos, ',')::int[])
                )
          )
    )
    SELECT COALESCE(ST_AsMVT(tile_features, 'roads', 4096, 'geom'), '\\x'::bytea) AS tile
    FROM tile_features
    """)


def _normalize_ward_nos(ward_no: str | None) -> str | None:
    if ward_no is None:
        return None

    values = [part.strip() for part in ward_no.split(",") if part.strip()]
    return ",".join(values) if values else None


def _fetch_building_tile(
    db: Session, z: int, x: int, y: int, ward_nos: str | None = None
) -> bytes:
    result = db.execute(
        _BUILDING_MVT_SQL, {"z": z, "x": x, "y": y, "ward_nos": ward_nos}
    ).scalar()
    if result is None:
        return b""
    return bytes(result)


def _fetch_road_tile(
    db: Session, z: int, x: int, y: int, ward_nos: str | None = None
) -> bytes:
    result = db.execute(
        _ROAD_MVT_SQL, {"z": z, "x": x, "y": y, "ward_nos": ward_nos}
    ).scalar()
    if result is None:
        return b""
    return bytes(result)


@router.get("/building_vector_tile/{z}/{x}/{y}")
def get_building_vector_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
    ward_no: str | None = None,
    db: Session = Depends(get_db),
):
    max_index = (1 << z) - 1
    if x > max_index or y > max_index:
        raise HTTPException(
            status_code=400, detail="Tile x/y is out of range for zoom level"
        )

    ward_nos = _normalize_ward_nos(ward_no)
    tile_bytes = _fetch_building_tile(db, z, x, y, ward_nos)
    return Response(content=tile_bytes, media_type="application/vnd.mapbox-vector-tile")


@router.get("/road_vector_tile/{z}/{x}/{y}")
def get_road_vector_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
    ward_no: str | None = None,
    db: Session = Depends(get_db),
):
    max_index = (1 << z) - 1
    if x > max_index or y > max_index:
        raise HTTPException(
            status_code=400, detail="Tile x/y is out of range for zoom level"
        )

    ward_nos = _normalize_ward_nos(ward_no)
    tile_bytes = _fetch_road_tile(db, z, x, y, ward_nos)
    return Response(content=tile_bytes, media_type="application/vnd.mapbox-vector-tile")


@base_layer.post("/names", response_model=BaseLayerNameResponse)
def create_base_layer_name(payload: BaseLayerNameCreate, db: Session = Depends(get_db)):
    """Create a new base layer name."""
    return raster_service.create_base_layer_name(db=db, payload=payload)
