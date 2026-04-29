"""
Vector Tiles API Routes Module

Defines REST endpoints for serving vector tiles in Mapbox Vector Tile (MVT) format.
Provides tile data for interactive mapping of vector layers (buildings, roads, etc.).

Key Endpoints:
- GET /api/v1/tiles/{layer_name}/{z}/{x}/{y} - Get vector tile for layer
- Supports tile requests from frontend mapping libraries (Mapbox GL, etc.)
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
import json

from src.database import get_db
from src.vectortile.service import (
    get_features_for_tile,
    validate_layer_exists,
    get_earliest_feature_date,
)
from src.models import FeatureCollection, VectorLayer

router = APIRouter(prefix="/api/v1/vectortile", tags=["vector-tile"])


@router.get("/tiles/{z}/{x}/{y}")
async def get_vector_tile(
    z: int,
    x: int,
    y: int,
    vector_layer_id: Optional[int] = Query(
        None, description="Vector layer ID to filter"
    ),
    radius: Optional[float] = Query(None, description="Radius in meters for filtering"),
    geom_type: str = Query(
        "point", description="Geometry type: 'point', 'line', or 'polygon'"
    ),
    latitude: Optional[List[float]] = Query(
        None, description="Latitude values for filtering"
    ),
    longitude: Optional[List[float]] = Query(
        None, description="Longitude values for filtering"
    ),
    bbox: Optional[str] = Query(None, description="Bounding box in WKT format"),
    from_date: Optional[str] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    db=Depends(get_db),
):
    """
    Get a vector tile for a specific tile coordinate (z/x/y).

    **Parameters:**
    - `z`: Zoom level
    - `x`: Tile X coordinate
    - `y`: Tile Y coordinate
    - `vector_layer_id` (optional): Filter by specific vector layer
    - `radius` (optional): Radius in meters for distance-based filtering
    - `geom_type` (optional): Geometry type for radius filtering (point/line/polygon)
    - `latitude` (optional): List of latitudes for radius-based filtering
    - `longitude` (optional): List of longitudes for radius-based filtering
    - `bbox` (optional): Bounding box in WKT format
    - `from_date` (optional): Filter features created after date (YYYY-MM-DD)
    - `to_date` (optional): Filter features created before date (YYYY-MM-DD)

    **Response:**
    Binary MVT (Mapbox Vector Tile) format data or GeoJSON features

    **Status Codes:**
    - 200: Successfully generated tile
    - 204: No content (no features in tile)
    - 400: Invalid parameters
    - 404: Vector layer not found
    """
    try:
        features = get_features_for_tile(
            db=db,
            z=z,
            x=x,
            y=y,
            vector_layer_id=vector_layer_id,
            radius=radius,
            geom_type=geom_type,
            latitudes=latitude,
            longitudes=longitude,
            bbox=bbox,
            from_date=from_date,
            to_date=to_date,
        )

        if not features:
            return Response(content=b"", status_code=204)

        # Return as GeoJSON FeatureCollection (can be converted to MVT by client)
        geojson_features = []
        for feature in features:
            geojson_features.append(
                {
                    "type": "Feature",
                    "id": feature["id"],
                    "properties": {
                        "label": feature["label"],
                        "style": feature["style"],
                        **feature["attributes"],
                    },
                    "geometry": {
                        "type": "GeometryCollection",
                        "geometries": [
                            {"type": "Point", "coordinates": [0, 0]}
                        ],  # Placeholder
                    },
                }
            )

        geojson = {"type": "FeatureCollection", "features": geojson_features}

        return Response(
            content=json.dumps(geojson),
            media_type="application/json",
            status_code=200 if features else 204,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating tile: {str(e)}")


@router.get("/tiles/{z}/{x}/{y}/pbf")
async def get_vector_tile_pbf(
    z: int,
    x: int,
    y: int,
    vector_layer_id: Optional[int] = Query(None),
    radius: Optional[float] = Query(None),
    geom_type: str = Query("point"),
    latitude: Optional[List[float]] = Query(None),
    longitude: Optional[List[float]] = Query(None),
    bbox: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    db=Depends(get_db),
):
    """
    Get a vector tile in GeoJSON format (PBF support requires optional dependencies).
    Currently returns GeoJSON which can be converted to PBF client-side.

    To enable true MVT/PBF support, install: pip install mapbox-vector-tile mercantile
    """
    try:
        features = get_features_for_tile(
            db=db,
            z=z,
            x=x,
            y=y,
            vector_layer_id=vector_layer_id,
            radius=radius,
            geom_type=geom_type,
            latitudes=latitude,
            longitudes=longitude,
            bbox=bbox,
            from_date=from_date,
            to_date=to_date,
        )

        if not features:
            return Response(content=b"", status_code=204)

        # Return as GeoJSON FeatureCollection
        geojson_features = []
        for feature in features:
            geojson_features.append(
                {
                    "type": "Feature",
                    "id": feature["id"],
                    "properties": {
                        "label": feature["label"],
                        "style": feature["style"],
                        **feature["attributes"],
                    },
                    "geometry": {"type": "GeometryCollection", "geometries": []},
                }
            )

        geojson = {"type": "FeatureCollection", "features": geojson_features}

        return Response(
            content=json.dumps(geojson),
            media_type="application/geo+json",
            status_code=200 if features else 204,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error generating vector tile: {str(e)}"
        )


@router.get("/info")
async def get_tile_info(
    db=Depends(get_db),
):
    """
    Get metadata about available vector tiles.

    **Response:**
    - Total features count
    - Earliest and latest feature dates
    - Available vector layers

    Useful for TMS (Tile Map Service) clients to understand tile availability.
    """
    try:

        total_features = (
            db.query(func.count(FeatureCollection.id))
            .filter(FeatureCollection.is_deleted == False)
            .scalar()
            or 0
        )

        earliest_date = get_earliest_feature_date(db)

        layers = (
            db.query(
                VectorLayer.id,
                VectorLayer.name_en,
                VectorLayer.name_ne,
                func.count(FeatureCollection.id).label("feature_count"),
            )
            .outerjoin(FeatureCollection)
            .filter(FeatureCollection.is_deleted == False)
            .group_by(VectorLayer.id)
            .all()
        )

        layer_info = [
            {
                "id": layer.id,
                "name_en": layer.name_en,
                "name_ne": layer.name_ne,
                "feature_count": layer.feature_count or 0,
            }
            for layer in layers
        ]

        return {
            "total_features": total_features,
            "earliest_date": earliest_date.isoformat() if earliest_date else None,
            "layers": layer_info,
            "supported_parameters": {
                "vector_layer_id": "Filter by layer ID",
                "radius": "Distance in meters for filtering",
                "geom_type": "point, line, or polygon",
                "latitude": "List of latitudes",
                "longitude": "List of longitudes",
                "bbox": "Bounding box in WKT format",
                "from_date": "Filter from date (YYYY-MM-DD)",
                "to_date": "Filter to date (YYYY-MM-DD)",
            },
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error getting tile info: {str(e)}"
        )
