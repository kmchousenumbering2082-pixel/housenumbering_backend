"""
Vector Layer Service Module

Handles CRUD operations and file uploads for vector layers (GeoJSON, Shapefile).
Provides:
  - Vector layer management (create, read, update, delete)
  - Feature collection management with geometry support
  - GeoJSON and Shapefile parsing and import
  - Geometry type detection and conversion to WKT format
"""

from typing import Optional, List, Dict, Any
import json
import zipfile
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func
import geopandas as gpd
from shapely.geometry import shape
from shapely import wkt

from src.models import FeatureCollection, VectorLayer
from src.vector.schema import (
    VectorLayerCreate,
    VectorLayerUpdate,
    FeatureCollectionCreate,
    FeatureCollectionUpdate,
)


# ============ HELPER FUNCTIONS ============

def _get_username(user_obj: Any) -> Optional[str]:
    """Extract username from a User object."""
    if user_obj is None:
        return None
    if hasattr(user_obj, 'username'):
        return user_obj.username
    return None


# ============ VECTOR LAYER SERVICE ============

def create_vector_layer(
    db: Session,
    layer_data: VectorLayerCreate,
    user_id: int,
) -> VectorLayer:
    """Create a new vector layer."""
    payload = layer_data.model_dump(exclude_unset=True)
    payload["created_by"] = user_id
    payload["updated_by"] = user_id

    db_layer = VectorLayer(**payload)
    db.add(db_layer)
    db.commit()
    db.refresh(db_layer)
    return db_layer


def list_vector_layers(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    layer_type: Optional[str] = None,
    is_public: Optional[bool] = None,
    display_on_map: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = "id",
    order: str = "asc",
) -> List[VectorLayer]:
    """List vector layers with filtering and pagination."""
    query = db.query(VectorLayer).options(
        joinedload(VectorLayer.features),
        joinedload(VectorLayer.created_by_user),
        joinedload(VectorLayer.updated_by_user)
    )

    # Apply filters
    if layer_type:
        query = query.filter(VectorLayer.layer_type == layer_type)
    
    if is_public is not None:
        query = query.filter(VectorLayer.is_public == is_public)
    
    if display_on_map is not None:
        query = query.filter(VectorLayer.display_on_map == display_on_map)
    
    if search:
        query = query.filter(
            or_(
                VectorLayer.name_en.ilike(f"%{search}%"),
                VectorLayer.name_ne.ilike(f"%{search}%"),
            )
        )

    # Apply sorting
    sort_column = getattr(VectorLayer, sort_by, VectorLayer.id)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    return query.offset(skip).limit(limit).all()


def get_vector_layer(db: Session, layer_id: int) -> VectorLayer:
    """Get a specific vector layer with all its features."""
    layer = (
        db.query(VectorLayer)
        .options(
            joinedload(VectorLayer.features),
            joinedload(VectorLayer.created_by_user),
            joinedload(VectorLayer.updated_by_user)
        )
        .filter(VectorLayer.id == layer_id)
        .first()
    )
    if not layer:
        raise HTTPException(status_code=404, detail="Vector layer not found")
    
    # Fix: Use PostGIS ST_AsText to extract geometry as text for each feature
    # This avoids issues with WKBElement conversion
    try:
        for feature in layer.features:
            if feature.geom is not None:
                # Query geometry as WKT text using PostGIS
                geom_result = db.query(
                    func.ST_AsText(FeatureCollection.geom)
                ).filter(
                    FeatureCollection.id == feature.id
                ).scalar()
                
                if geom_result:
                    # Replace the geometry object with the WKT string
                    feature.geom = geom_result
    except Exception as e:
        print(f"Warning: Could not extract geometry as WKT text: {e}")
        # Continue anyway - geometry might still be usable
    
    return layer


def update_vector_layer(
    db: Session,
    layer_id: int,
    layer_data: VectorLayerUpdate,
    user_id: int,
) -> VectorLayer:
    """Update a vector layer."""
    layer = get_vector_layer(db=db, layer_id=layer_id)
    
    update_data = layer_data.model_dump(exclude_unset=True)
    update_data["updated_by"] = user_id

    for key, value in update_data.items():
        setattr(layer, key, value)
    
    db.commit()
    db.refresh(layer)
    return layer


def delete_vector_layer(db: Session, layer_id: int) -> None:
    """Delete a vector layer and all its features."""
    layer = get_vector_layer(db=db, layer_id=layer_id)
    db.delete(layer)
    db.commit()


def get_vector_layer_count(db: Session) -> int:
    """Get total count of vector layers."""
    return db.query(VectorLayer).count()


# ============ FEATURE COLLECTION SERVICE ============

def create_feature(
    db: Session,
    feature_data: FeatureCollectionCreate,
    user_id: int,
) -> FeatureCollection:
    """Create a new feature in a vector layer."""
    # Validate vector layer exists if provided
    if feature_data.vector_layer_id:
        layer = db.query(VectorLayer).filter(
            VectorLayer.id == feature_data.vector_layer_id
        ).first()
        if not layer:
            raise HTTPException(status_code=404, detail="Vector layer not found")

    payload = feature_data.model_dump(exclude_unset=True)
    payload["created_by"] = user_id
    payload["updated_by"] = user_id

    db_feature = FeatureCollection(**payload)
    db.add(db_feature)
    db.commit()
    db.refresh(db_feature)
    return db_feature


def list_features(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    vector_layer_id: Optional[int] = None,
    is_deleted: Optional[bool] = None,
    search: Optional[str] = None,
    sort_by: str = "id",
    order: str = "asc",
) -> List[FeatureCollection]:
    """List features with filtering and pagination."""
    query = db.query(FeatureCollection).options(
        joinedload(FeatureCollection.created_by_user),
        joinedload(FeatureCollection.updated_by_user)
    )

    # Apply filters
    if vector_layer_id is not None:
        query = query.filter(FeatureCollection.vector_layer_id == vector_layer_id)
    
    if is_deleted is not None:
        query = query.filter(FeatureCollection.is_deleted == is_deleted)
    else:
        # By default, exclude deleted features
        query = query.filter(FeatureCollection.is_deleted == False)
    
    if search:
        query = query.filter(
            or_(
                FeatureCollection.label_value.ilike(f"%{search}%"),
                FeatureCollection.style_value.ilike(f"%{search}%"),
            )
        )

    # Apply sorting
    sort_column = getattr(FeatureCollection, sort_by, FeatureCollection.id)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    return query.offset(skip).limit(limit).all()


def get_feature(db: Session, feature_id: int) -> FeatureCollection:
    """Get a specific feature."""
    feature = db.query(FeatureCollection).options(
        joinedload(FeatureCollection.created_by_user),
        joinedload(FeatureCollection.updated_by_user)
    ).filter(
        FeatureCollection.id == feature_id
    ).first()
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature


def update_feature(
    db: Session,
    feature_id: int,
    feature_data: FeatureCollectionUpdate,
    user_id: int,
) -> FeatureCollection:
    """Update a feature."""
    feature = get_feature(db=db, feature_id=feature_id)
    
    # Validate vector layer if being updated
    if feature_data.vector_layer_id:
        layer = db.query(VectorLayer).filter(
            VectorLayer.id == feature_data.vector_layer_id
        ).first()
        if not layer:
            raise HTTPException(status_code=404, detail="Vector layer not found")

    update_data = feature_data.model_dump(exclude_unset=True)
    update_data["updated_by"] = user_id

    for key, value in update_data.items():
        setattr(feature, key, value)
    
    db.commit()
    db.refresh(feature)
    return feature


def delete_feature(db: Session, feature_id: int) -> None:
    """Soft delete a feature."""
    feature = get_feature(db=db, feature_id=feature_id)
    feature.is_deleted = True
    db.commit()


def permanently_delete_feature(db: Session, feature_id: int) -> None:
    """Permanently delete a feature from database."""
    feature = get_feature(db=db, feature_id=feature_id)
    db.delete(feature)
    db.commit()


def get_layer_features_count(db: Session, layer_id: int) -> int:
    """Get count of active features in a layer."""
    return db.query(FeatureCollection).filter(
        and_(
            FeatureCollection.vector_layer_id == layer_id,
            FeatureCollection.is_deleted == False,
        )
    ).count()


def restore_feature(db: Session, feature_id: int, user_id: int) -> FeatureCollection:
    """Restore a soft-deleted feature."""
    feature = get_feature(db=db, feature_id=feature_id)
    feature.is_deleted = False
    feature.updated_by = user_id
    db.commit()
    db.refresh(feature)
    return feature     


# ============ FILE UPLOAD SERVICE ============

def _determine_geometry_type(geom_type: str) -> str:
    """Determine if geometry is polygon, line, or point."""
    geom_type_lower = geom_type.lower()
    if "polygon" in geom_type_lower:
        return "polygon"
    elif "line" in geom_type_lower:
        return "line"
    elif "point" in geom_type_lower:
        return "point"
    else:
        return "polygon"  # default


def _geometry_to_wkt(geom) -> str:
    """Convert geometry object to WKT string."""
    try:
        if isinstance(geom, dict):
            # GeoJSON geometry
            geom = shape(geom)
        elif isinstance(geom, str):
            # Already WKT - try to parse it
            geom = wkt.loads(geom)
        
        # Return WKT string
        return geom.wkt if hasattr(geom, 'wkt') else str(geom)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to convert geometry: {str(e)}"
        )


def _geometry_to_shapely(geom):
    """Convert geometry object to Shapely geometry object for database storage."""
    try:
        if geom is None:
            return None
            
        if isinstance(geom, dict):
            # GeoJSON geometry dict
            return shape(geom)
        elif isinstance(geom, str):
            # WKT string
            return wkt.loads(geom)
        else:
            # Assume it's already a Shapely geometry
            return geom
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse geometry: {str(e)}"
        )


def _parse_geojson_file(upload: UploadFile) -> Dict[str, Any]:
    """
    Parse a GeoJSON file and extract features.
    
    Args:
        upload: Uploaded GeoJSON file
        
    Returns:
        Dictionary with layer_type and features list
    """
    try:
        content = upload.file.read()
        geojson_data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid GeoJSON file: must be valid JSON"
        )
    
    # Validate GeoJSON structure
    if "type" not in geojson_data:
        raise HTTPException(
            status_code=400,
            detail="Invalid GeoJSON: missing 'type' property"
        )
    
    geojson_type = geojson_data["type"].lower()
    features = []
    layer_type = None

    if geojson_type == "featurecollection":
        if "features" not in geojson_data:
            raise HTTPException(
                status_code=400,
                detail="Invalid GeoJSON FeatureCollection: missing 'features'"
            )
        
        features_with_geom = 0
        features_without_geom = 0
        
        for feature in geojson_data["features"]:
            if "geometry" not in feature or not feature["geometry"]:
                features_without_geom += 1
                continue
            
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})
            
            # Determine geometry type
            geom_type = geometry.get("type", "Polygon")
            if not layer_type:
                layer_type = _determine_geometry_type(geom_type)
            
            # Convert geometry to WKT string for storage
            geom_wkt = _geometry_to_wkt(geometry)
            
            features.append({
                "geom": geom_wkt,
                "attr_data": properties or {},
            })
            features_with_geom += 1
        
        if features_without_geom > 0:
            print(f"[GeoJSON] WARNING: {features_without_geom} features had null/missing geometry and were SKIPPED")
            print(f"[GeoJSON] INFO: Check if your GeoJSON file has valid coordinates in the 'geometry' field")
            if features_with_geom == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"UPLOAD FAILED: No features with valid geometry. All {features_without_geom} features have null/empty geometry. Your GeoJSON file must have coordinates!"
                )

    
    elif geojson_type == "feature":
        if "geometry" not in geojson_data or not geojson_data["geometry"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid GeoJSON Feature: missing geometry"
            )
        
        geometry = geojson_data.get("geometry", {})
        properties = geojson_data.get("properties", {})
        
        geom_type = geometry.get("type", "Polygon")
        layer_type = _determine_geometry_type(geom_type)
        geom_wkt = _geometry_to_wkt(geometry)
        
        features.append({
            "geom": geom_wkt,
            "attr_data": properties or {},
        })
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported GeoJSON type: {geojson_type}. Must be 'FeatureCollection' or 'Feature'"
        )
    
    if not features:
        raise HTTPException(
            status_code=400,
            detail="No valid features found in GeoJSON file"
        )
    
    if not layer_type:
        layer_type = "polygon"
    
    return {
        "layer_type": layer_type,
        "features": features,
    }


def _parse_shapefile(upload: UploadFile) -> Dict[str, Any]:
    """
    Parse a Shapefile (uploaded as .zip containing .shp, .shx, .dbf files).
    
    Args:
        upload: Uploaded zipfile containing Shapefile
        
    Returns:
        Dictionary with layer_type and features list
    """
    try:
        # Save to temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Extract zip file
            with zipfile.ZipFile(upload.file) as zf:
                zf.extractall(temp_path)
            
            # Find .shp file
            shp_files = list(temp_path.glob("*.shp"))
            if not shp_files:
                raise HTTPException(
                    status_code=400,
                    detail="No .shp file found in uploaded zip"
                )
            
            shp_path = shp_files[0]
            
            # Read shapefile with geopandas
            gdf = gpd.read_file(shp_path)
            
            if gdf.empty:
                raise HTTPException(
                    status_code=400,
                    detail="Shapefile contains no features"
                )
            
            # Determine geometry type from first feature
            first_geom_type = gdf.geometry.iloc[0].geom_type
            layer_type = _determine_geometry_type(first_geom_type)
            
            # Extract features
            features = []
            for idx, row in gdf.iterrows():
                geom = row.geometry
                
                # Convert Shapely geometry to WKT string for storage
                geom_wkt = geom.wkt if hasattr(geom, 'wkt') else str(geom)
                
                # Extract properties (exclude geometry column)
                attr_data = {}
                for col in gdf.columns:
                    if col != 'geometry':
                        value = row[col]
                        # Convert numpy types to Python types for JSON serialization
                        if hasattr(value, 'item'):
                            value = value.item()
                        elif value is None or isinstance(value, (str, int, float, bool)):
                            pass
                        else:
                            value = str(value)
                        attr_data[col] = value
                
                features.append({
                    "geom": geom_wkt,
                    "attr_data": attr_data,
                })
            
            return {
                "layer_type": layer_type,
                "features": features,
            }
    
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=400,
            detail="Invalid zip file format"
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse Shapefile: {str(e)}"
        )


def upload_vector_file(
    db: Session,
    upload: UploadFile,
    layer_name_en: str,
    layer_name_ne: Optional[str],
    user_id: int,
    is_public: bool = True,
    display_on_map: bool = True,
) -> Dict[str, Any]:
    """
    Upload and parse a vector file (GeoJSON or Shapefile).
    
    Args:
        db: Database session
        upload: Uploaded file
        layer_name_en: Layer name in English
        layer_name_ne: Layer name in Nepali
        user_id: ID of user uploading
        is_public: Whether layer is public
        display_on_map: Whether to display on map
        
    Returns:
        Dictionary with upload summary
    """
    if not upload.filename:
        raise HTTPException(
            status_code=400,
            detail="File must have a filename"
        )
    
    # Determine file type and parse accordingly
    file_ext = Path(upload.filename).suffix.lower()
    
    if file_ext == ".geojson" or file_ext == ".json":
        parsed = _parse_geojson_file(upload)
    elif file_ext == ".zip":
        parsed = _parse_shapefile(upload)
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid file format. Supported formats: .geojson, .json, .zip (for Shapefiles)"
        )
    
    # Create vector layer
    layer_data = VectorLayerCreate(
        name_en=layer_name_en,
        name_ne=layer_name_ne,
        layer_type=parsed["layer_type"],
        is_public=is_public,
        display_on_map=display_on_map,
    )
    
    db_layer = create_vector_layer(db=db, layer_data=layer_data, user_id=user_id)
    
    # Create features from parsed data
    feature_count = 0
    for idx, feature_data in enumerate(parsed["features"]):
        try:
            geom_val = feature_data.get("geom")
            feature_create = FeatureCollectionCreate(
                vector_layer_id=db_layer.id,
                attr_data=feature_data.get("attr_data", {}),
                geom=geom_val,
            )
            created = create_feature(db=db, feature_data=feature_create, user_id=user_id)
            feature_count += 1
            if geom_val:
                print(f"  Feature {idx}: Created with geometry")
            else:
                print(f"  Feature {idx}: WARNING - Created WITHOUT geometry!")
        except Exception as e:
            print(f"  Feature {idx}: Failed to create: {str(e)}")
            continue
    
    return {
        "layer_id": db_layer.id,
        "layer_name": layer_name_en,
        "layer_type": parsed["layer_type"],
        "feature_count": feature_count,
        "file_name": upload.filename,
        "message": f"Successfully uploaded {feature_count} features",
        "status": "success" if feature_count > 0 else "partial",
    }

