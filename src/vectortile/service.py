"""
Vector Tiles Service Module

Provides business logic for vector tile generation and querying, including
spatial filtering by tile boundaries and feature attribute handling.

Key Features:
- Tile coordinate to geographic bounds conversion
- Spatial query filtering for features within tile extents
- Vector tile format encoding (Mapbox Vector Tiles)
- Support for multiple vector layers (buildings, roads, etc.)
- Efficient geometry querying with PostGIS
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from geoalchemy2.functions import ST_Buffer, ST_Transform, ST_DWithin, ST_Intersects, ST_Within
from geoalchemy2.types import Geometry
from shapely.geometry import Point, LineString, Polygon
from shapely.wkt import loads as load_wkt

from src.models import FeatureCollection, VectorLayer


def get_tile_data_by_bbox(
    db: Session,
    z: int,
    x: int,
    y: int,
    vector_layer_id: Optional[int] = None,
    bbox: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get tile data for a specific tile (z, x, y) with bbox and optional filters.
    
    Args:
        db: Database session
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        vector_layer_id: Filter by specific vector layer
        bbox: Bounding box in WKT format
        from_date: Filter features created after this date (YYYY-MM-DD)
        to_date: Filter features created before this date (YYYY-MM-DD)
    
    Returns:
        List of feature data as dictionaries
    """
    query = db.query(
        FeatureCollection.id,
        FeatureCollection.label_value,
        FeatureCollection.style_value,
        FeatureCollection.attr_data,
        FeatureCollection.geom,
    ).filter(FeatureCollection.is_deleted == False)
    
    # Filter by vector layer
    if vector_layer_id:
        query = query.filter(FeatureCollection.vector_layer_id == vector_layer_id)
    
    # Filter by date range
    if from_date:
        try:
            from_datetime = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(FeatureCollection.timestamp >= from_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")
    
    if to_date:
        try:
            to_datetime = datetime.strptime(to_date, "%Y-%m-%d")
            query = query.filter(FeatureCollection.timestamp <= to_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")
    
    # Filter by bbox if provided
    if bbox:
        try:
            query = query.filter(ST_Intersects(FeatureCollection.geom, f"SRID=4326;{bbox}"))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid bbox format: {str(e)}")
    
    results = query.all()
    
    # Convert to dictionaries
    tile_data = []
    for result in results:
        tile_data.append({
            "id": result.id,
            "label": result.label_value,
            "style": result.style_value,
            "attributes": result.attr_data or {},
            "geometry": result.geom,  # WKT format
        })
    
    return tile_data


def get_tile_data_by_radius(
    db: Session,
    z: int,
    x: int,
    y: int,
    vector_layer_id: Optional[int] = None,
    radius: Optional[float] = None,
    geom_type: str = "point",
    latitudes: Optional[List[float]] = None,
    longitudes: Optional[List[float]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get tile data filtered by radius around point(s), line, or polygon.
    
    Args:
        db: Database session
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        vector_layer_id: Filter by specific vector layer
        radius: Radius in meters
        geom_type: 'point', 'line', or 'polygon'
        latitudes: List of latitudes (for coordinates)
        longitudes: List of longitudes (for coordinates)
        from_date: Filter features created after this date (YYYY-MM-DD)
        to_date: Filter features created before this date (YYYY-MM-DD)
    
    Returns:
        List of feature data as dictionaries
    """
    if not radius:
        raise HTTPException(status_code=400, detail="Radius is required for radius-based filtering")
    
    if not latitudes or not longitudes:
        raise HTTPException(status_code=400, detail="Latitude and longitude lists are required")
    
    if len(latitudes) != len(longitudes):
        raise HTTPException(status_code=400, detail="Mismatched number of latitudes and longitudes")
    
    # Convert string coordinates to floats
    try:
        coords = [(float(lon), float(lat)) for lat, lon in zip(latitudes, longitudes)]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid latitude or longitude values")
    
    query = db.query(
        FeatureCollection.id,
        FeatureCollection.label_value,
        FeatureCollection.style_value,
        FeatureCollection.attr_data,
        FeatureCollection.geom,
    ).filter(FeatureCollection.is_deleted == False)
    
    # Filter by vector layer
    if vector_layer_id:
        query = query.filter(FeatureCollection.vector_layer_id == vector_layer_id)
    
    # Filter by geometry type and radius
    if geom_type == "point":
        # Distance filter: features within radius of any point
        distance_filter = None
        for lon, lat in coords:
            point_filter = ST_DWithin(
                FeatureCollection.geom,
                f"SRID=4326;POINT({lon} {lat})",
                radius,
                useSpheroid=True
            )
            if distance_filter is None:
                distance_filter = point_filter
            else:
                distance_filter = or_(distance_filter, point_filter)
        
        if distance_filter is not None:
            query = query.filter(distance_filter)
    
    elif geom_type == "line":
        if len(coords) < 2:
            raise HTTPException(status_code=400, detail="Line requires at least 2 coordinates")
        
        # Create line geometry
        line_coords = ",".join([f"{lon} {lat}" for lon, lat in coords])
        line_wkt = f"SRID=4326;LINESTRING({line_coords})"
        
        # Buffer the line and filter features within buffer
        query = query.filter(
            ST_DWithin(FeatureCollection.geom, line_wkt, radius, useSpheroid=True)
        )
    
    elif geom_type == "polygon":
        if len(coords) < 3:
            raise HTTPException(status_code=400, detail="Polygon requires at least 3 coordinates")
        
        # Close polygon if not closed
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        
        # Create polygon geometry
        poly_coords = ",".join([f"{lon} {lat}" for lon, lat in coords])
        poly_wkt = f"SRID=4326;POLYGON(({poly_coords}))"
        
        # Filter: features outside polygon but within radius buffer
        query = query.filter(
            ST_DWithin(FeatureCollection.geom, poly_wkt, radius, useSpheroid=True)
        ).filter(
            ~ST_Within(FeatureCollection.geom, poly_wkt)
        )
    
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid geom_type. Must be 'point', 'line', or 'polygon'"
        )
    
    # Filter by date range
    if from_date:
        try:
            from_datetime = datetime.strptime(from_date, "%Y-%m-%d")
            query = query.filter(FeatureCollection.timestamp >= from_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")
    
    if to_date:
        try:
            to_datetime = datetime.strptime(to_date, "%Y-%m-%d")
            query = query.filter(FeatureCollection.timestamp <= to_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")
    
    results = query.all()
    
    # Convert to dictionaries
    tile_data = []
    for result in results:
        tile_data.append({
            "id": result.id,
            "label": result.label_value,
            "style": result.style_value,
            "attributes": result.attr_data or {},
            "geometry": result.geom,  # WKT format
        })
    
    return tile_data


def get_earliest_feature_date(db: Session) -> Optional[datetime]:
    """Get the earliest creation date from all features."""
    result = db.query(func.min(FeatureCollection.timestamp)).scalar()
    return result


def validate_layer_exists(db: Session, vector_layer_id: int) -> bool:
    """Check if a vector layer exists."""
    layer = db.query(VectorLayer).filter(VectorLayer.id == vector_layer_id).first()
    return layer is not None


def get_features_for_tile(
    db: Session,
    z: int,
    x: int,
    y: int,
    vector_layer_id: Optional[int] = None,
    radius: Optional[float] = None,
    geom_type: str = "point",
    latitudes: Optional[List[float]] = None,
    longitudes: Optional[List[float]] = None,
    bbox: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Main function to get tile data with all supported filters.
    
    Args:
        db: Database session
        z, x, y: Tile coordinates
        vector_layer_id: Optional layer filter
        radius: Optional radius for distance-based filtering
        geom_type: Type of geometry for radius filtering ('point', 'line', 'polygon')
        latitudes: Latitude list for radius filtering
        longitudes: Longitude list for radius filtering
        bbox: Bounding box for spatial filtering
        from_date: Date filter (start)
        to_date: Date filter (end)
    
    Returns:
        List of features as dictionaries
    """
    # Validate layer if provided
    if vector_layer_id:
        if not validate_layer_exists(db, vector_layer_id):
            raise HTTPException(status_code=404, detail="Vector layer not found")
    
    # Route to appropriate filtering method
    if radius and (latitudes or longitudes):
        return get_tile_data_by_radius(
            db=db,
            z=z,
            x=x,
            y=y,
            vector_layer_id=vector_layer_id,
            radius=radius,
            geom_type=geom_type,
            latitudes=latitudes,
            longitudes=longitudes,
            from_date=from_date,
            to_date=to_date,
        )
    else:
        return get_tile_data_by_bbox(
            db=db,
            z=z,
            x=x,
            y=y,
            vector_layer_id=vector_layer_id,
            bbox=bbox,
            from_date=from_date,
            to_date=to_date,
        )
