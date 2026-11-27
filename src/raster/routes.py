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
import rasterio
from rasterio.windows import Window

from src.database import get_db
from src.raster import service as raster_service
from src.raster.schema import (
    RasterLayerCreate,
    RasterLayerResponse,
    RasterUploadSummary,
    BaseLayerResponse,
)
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from rasterio.windows import from_bounds
from affine import Affine

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
                (SELECT geom FROM bounds),
                4096,
                256,
                true
            ) AS geom
        FROM building_geometry bg
        JOIN buildings b ON b.id = bg.building_id
        WHERE bg.geom IS NOT NULL
          AND COALESCE(bg.is_deleted, false) = false
          AND ST_Intersects(ST_Transform(bg.geom, 3857), (SELECT geom FROM bounds))
          AND (
                :ward_nos IS NULL
                OR b.ward_no IS NULL
                OR b.ward_no = ANY(string_to_array(:ward_nos, ',')::int[])
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
            r.road_class,
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


def _normalize_raster_data(data: np.ndarray) -> np.ndarray:
    """Normalize raster data to uint8 (0-255) using percentile clipping for better contrast."""
    if data.size == 0:
        return np.zeros((256, 256, 3), dtype=np.uint8)

    # Check if already uint8
    if data.dtype == np.uint8:
        return data

    data = data.astype(np.float64)

    # Use percentile-based clipping for better contrast
    p2, p98 = np.percentile(data, [2, 98])

    # Handle edge cases
    if np.isnan(p2) or np.isnan(p98) or p2 == p98:
        return np.full_like(data, 128, dtype=np.uint8)

    # Clip and normalize
    data_clipped = np.clip(data, p2, p98)
    data_normalized = ((data_clipped - p2) / (p98 - p2)) * 255

    return np.uint8(data_normalized)


def _extract_raster_tile(raster_path: str, z: int, x: int, y: int) -> bytes:
    try:
        with rasterio.open(raster_path) as src:

            # Tile bounds in EPSG:3857
            minx, miny, maxx, maxy = _mercator_tile_to_bbox(z, x, y)

            # Resolution per pixel
            res = (maxx - minx) / 256

            # Proper tile transform
            dst_transform = rasterio.transform.from_bounds(
                minx,
                miny,
                maxx,
                maxy,
                256,
                256,
            )

            # Warp raster dynamically into WebMercator
            with WarpedVRT(
                src,
                crs="EPSG:3857",
                transform=dst_transform,
                width=256,
                height=256,
                resampling=Resampling.bilinear,
            ) as vrt:

                data = vrt.read(out_shape=(vrt.count, 256, 256))

                if data.size == 0:
                    img = Image.new("RGB", (256, 256), (200, 200, 200))
                else:

                    # RGB
                    if vrt.count >= 3:
                        img_array = np.transpose(data[:3], (1, 2, 0))
                    else:
                        band = data[0]
                        img_array = np.stack([band] * 3, axis=-1)

                    # Normalize
                    if img_array.dtype != np.uint8:
                        img_array = np.clip(img_array, 0, 255).astype(np.uint8)

                    img = Image.fromarray(img_array)

                buffer = io.BytesIO()
                img.save(buffer, format="PNG")

                return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tile extraction failed: {str(e)}")


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
