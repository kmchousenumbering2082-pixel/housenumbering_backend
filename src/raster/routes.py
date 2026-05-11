from typing import List
import io

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
    Query,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from osgeo import gdal, gdalconst
from PIL import Image
import numpy as np

from src.database import get_db
from src.raster import service as raster_service
from src.raster.schema import (
    RasterLayerCreate,
    RasterLayerResponse,
    RasterUploadSummary,
    BaseLayerResponse,
)

router = APIRouter(prefix="/api/v1/raster", tags=["Rasters"])
base_layer = APIRouter(prefix="/api/v1/base_layers", tags=["Base Layers"])
tile_router = APIRouter(prefix="/api/v1/tile", tags=["Tiles"])


# ============================================================================
# RASTER UPLOAD & MANAGEMENT
# ============================================================================


@router.post("/upload", response_model=RasterUploadSummary)
@router.post("/upload/", response_model=RasterUploadSummary)
def upload_raster_file(
    file_upload: UploadFile = File(...),
    name_en: str | None = Form(None),
    name_ne: str | None = Form(None),
    display_on_map: bool = Form(default=True),
    is_public: bool = Form(default=True),
    db: Session = Depends(get_db),
):
    """
    Upload a raster file (GeoTIFF, ECW, etc.) with automatic metadata extraction.

    Supported formats: .tif, .tiff, .geotiff, .ecw, .vrt, .jp2, .jp2k
    """
    try:
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
            user_id=None,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")


@router.get("/", response_model=List[RasterLayerResponse])
def list_raster_layers(
    skip: int = 0,
    limit: int = 100,
    public_only: bool = True,
    db: Session = Depends(get_db),
):
    """List all available raster layers."""
    layers = raster_service.list_raster_layers(
        db=db,
        skip=skip,
        limit=limit,
        is_public=public_only,
    )
    return layers


@router.get("/{raster_id}", response_model=RasterLayerResponse)
def get_raster_layer(raster_id: int, db: Session = Depends(get_db)):
    """Get raster layer metadata and details."""
    layer = raster_service.get_raster_layer(db, raster_id)
    return layer


@router.get("/{raster_id}/file")
def get_raster_file(raster_id: int, db: Session = Depends(get_db)):
    """Download the raster file."""
    layer = raster_service.get_raster_layer(db, raster_id)
    file_path = FilePath(layer.raster_file)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Raster file not found")

    return FileResponse(
        path=str(file_path),
        media_type="image/tiff",
        filename=file_path.name,
    )


# ============================================================================
# BASE LAYERS
# ============================================================================


@base_layer.get("/", response_model=List[BaseLayerResponse])
def list_base_layers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """List all available base layers."""
    layers = raster_service.list_base_layers(db, skip=skip, limit=limit)
    return layers


@base_layer.get("/{layer_id}", response_model=BaseLayerResponse)
def get_base_layer(layer_id: int, db: Session = Depends(get_db)):
    """Get a specific base layer."""
    layer = raster_service.get_base_layer(db, layer_id)
    return layer


# ============================================================================
# VECTOR TILES (BUILDINGS & ROADS)
# ============================================================================

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
    """Parse and normalize comma-separated ward numbers."""
    if ward_no is None:
        return None
    values = [part.strip() for part in ward_no.split(",") if part.strip()]
    return ",".join(values) if values else None


def _fetch_building_tile(
    db: Session, z: int, x: int, y: int, ward_nos: str | None = None
) -> bytes:
    """Fetch building vector tile."""
    result = db.execute(
        _BUILDING_MVT_SQL, {"z": z, "x": x, "y": y, "ward_nos": ward_nos}
    ).scalar()
    return bytes(result) if result else b""


def _fetch_road_tile(
    db: Session, z: int, x: int, y: int, ward_nos: str | None = None
) -> bytes:
    """Fetch road vector tile."""
    result = db.execute(
        _ROAD_MVT_SQL, {"z": z, "x": x, "y": y, "ward_nos": ward_nos}
    ).scalar()
    return bytes(result) if result else b""


@router.get("/building_vector_tile/{z}/{x}/{y}")
def get_building_vector_tile(
    z: int = Path(..., ge=0, le=22),
    x: int = Path(..., ge=0),
    y: int = Path(..., ge=0),
    ward_no: str | None = None,
    db: Session = Depends(get_db),
):
    """Get building vector tile."""
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
    """Get road vector tile."""
    max_index = (1 << z) - 1
    if x > max_index or y > max_index:
        raise HTTPException(
            status_code=400, detail="Tile x/y is out of range for zoom level"
        )
    ward_nos = _normalize_ward_nos(ward_no)
    tile_bytes = _fetch_road_tile(db, z, x, y, ward_nos)
    return Response(content=tile_bytes, media_type="application/vnd.mapbox-vector-tile")


# ============================================================================
# RASTER TILE SERVING
# ============================================================================


def _mercator_tile_to_bbox(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """Convert Web Mercator tile coordinates to geographic bounding box (EPSG:3857)."""
    n = 2.0**z
    pixel_size = 20037508.34 * 2 / (256 * n)
    minx = -20037508.34 + (x * 256 * pixel_size)
    maxy = 20037508.34 - (y * 256 * pixel_size)
    maxx = minx + (256 * pixel_size)
    miny = maxy - (256 * pixel_size)
    return minx, miny, maxx, maxy


def _extract_raster_tile(raster_path: str, z: int, x: int, y: int) -> bytes:
    """Extract a 256x256 PNG tile from raster at given Web Mercator coordinates."""
    try:
        dataset = gdal.Open(str(raster_path), gdalconst.GA_ReadOnly)
        if dataset is None:
            raise HTTPException(status_code=404, detail="Cannot open raster file")

        geo_transform = dataset.GetGeoTransform()
        raster_width = dataset.RasterXSize
        raster_height = dataset.RasterYSize
        band_count = dataset.RasterCount

        minx, miny, maxx, maxy = _mercator_tile_to_bbox(z, x, y)

        px_min = int((minx - geo_transform[0]) / geo_transform[1])
        py_max = int((maxy - geo_transform[3]) / geo_transform[5])
        px_max = int((maxx - geo_transform[0]) / geo_transform[1])
        py_min = int((miny - geo_transform[3]) / geo_transform[5])

        px_min = max(0, min(px_min, raster_width - 1))
        px_max = max(0, min(px_max, raster_width))
        py_min = max(0, min(py_min, raster_height - 1))
        py_max = max(0, min(py_max, raster_height))

        width = max(0, px_max - px_min)
        height = max(0, py_max - py_min)

        if width == 0 or height == 0:
            img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

        if band_count == 1:
            band = dataset.GetRasterBand(1)
            data = band.ReadArray(px_min, py_min, width, height)
            img_data = np.stack([data, data, data], axis=2)
        elif band_count >= 3:
            r_band = dataset.GetRasterBand(1)
            g_band = dataset.GetRasterBand(2)
            b_band = dataset.GetRasterBand(3)

            r = r_band.ReadArray(px_min, py_min, width, height)
            g = g_band.ReadArray(px_min, py_min, width, height)
            b = b_band.ReadArray(px_min, py_min, width, height)

            img_data = np.stack([r, g, b], axis=2)
        else:
            raise HTTPException(status_code=400, detail="Unsupported raster format")

        if img_data.dtype != np.uint8:
            img_data = np.uint8(np.clip(img_data / img_data.max() * 255, 0, 255))

        img = Image.fromarray(img_data)
        img = img.resize((256, 256), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        dataset = None

        return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting tile: {str(e)}")


@tile_router.get("/raster-tiles/{z}/{x}/{y}.png")
def get_raster_tile(
    z: int = Path(..., ge=0, le=28),
    x: int = Path(...),
    y: int = Path(...),
    raster_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Serve a raster tile at specified Web Mercator coordinates."""
    max_tile = 2**z
    if x < 0 or x >= max_tile or y < 0 or y >= max_tile:
        raise HTTPException(
            status_code=400, detail="Tile x/y out of range for zoom level"
        )

    raster = raster_service.get_raster_layer(db, raster_id)
    if not raster:
        raise HTTPException(status_code=404, detail="Raster not found")

    raster_path = FilePath(raster.raster_file)
    if not raster_path.exists():
        raise HTTPException(status_code=404, detail="Raster file not found")

    tile_bytes = _extract_raster_tile(str(raster_path), z, x, y)
    return Response(content=tile_bytes, media_type="image/png")
