from typing import List, Optional
import json

from shapely import wkb
from fastapi import APIRouter, Depends, Query, HTTPException, Form, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.pagination import Pagination
from src.users.models import User
from src.models import FeatureCollection

from src.vector.schema import (
    VectorLayerCreate,
    VectorLayerUpdate,
    VectorLayerResponse,
    VectorLayerDetailResponse,
    FeatureCollectionCreate,
    FeatureCollectionUpdate,
    FeatureCollectionResponse,
    FeatureCollectionListResponse,
    VectorUploadSummary,
    VectorUploadResponse,
)
from src.vector.service import (
    create_vector_layer,
    list_vector_layers,
    get_vector_layer,
    update_vector_layer,
    delete_vector_layer,
    create_feature,
    list_features,
    get_feature,
    update_feature,
    delete_feature,
    get_layer_features_count,
    _get_username,
    upload_vector_file,
)

router = APIRouter(prefix="/api/v1/vector", tags=["Vector Layers"])


def _geometry_to_string(geom) -> str | None:
    """Convert geometry object (WKBElement) to WKT string format."""
    if geom is None:
        return None

    try:
        # Handle different geometry object types

        # If it's a string already, return as-is
        if isinstance(geom, str):
            return geom

        # If it's a Shapely geometry object with WKT
        if hasattr(geom, "wkt"):
            return geom.wkt

        # If it's a WKBElement from GeoAlchemy2
        if hasattr(geom, "data"):
            try:
                # Try to load as WKB binary
                shapely_geom = wkb.loads(geom.data)
                return shapely_geom.wkt
            except Exception as e:
                # If WKB parsing fails, try to convert the object directly to string
                # This handles cases where geom might already be text-based
                geom_str = str(geom)
                if geom_str and geom_str.startswith(
                    ("POINT", "LINESTRING", "POLYGON", "MULTI")
                ):
                    return geom_str
                raise e

        # Last resort: convert to string
        geom_str = str(geom)
        if geom_str and geom_str.startswith(
            ("POINT", "LINESTRING", "POLYGON", "MULTI")
        ):
            return geom_str

        return None

    except Exception as e:
        print(f"Warning: Failed to convert geometry: {e}")
        print(f"  Geometry type: {type(geom)}")
        print(f"  Geometry value: {str(geom)[:100]}")
        return None


def _build_layer_response(layer) -> VectorLayerResponse:
    """Convert VectorLayer model to response with usernames resolved."""
    features_list = []
    if layer.features:
        for feat in layer.features:
            features_list.append(
                FeatureCollectionResponse(
                    id=feat.id,
                    vector_layer_id=feat.vector_layer_id,
                    attr_data=feat.attr_data,
                    geom=_geometry_to_string(feat.geom),
                    style_value=feat.style_value,
                    label_value=feat.label_value,
                    created_by=_get_username(feat.created_by_user),
                    updated_by=_get_username(feat.updated_by_user),
                    is_deleted=feat.is_deleted,
                    timestamp=feat.timestamp,
                )
            )

    return VectorLayerResponse(
        id=layer.id,
        name_en=layer.name_en,
        name_ne=layer.name_ne,
        layer_type=layer.layer_type,
        attr_data=layer.attr_data,
        style_value=layer.style_value,
        label_value=layer.label_value,
        is_public=layer.is_public,
        display_on_map=layer.display_on_map,
        created_by=_get_username(layer.created_by_user),
        updated_by=_get_username(layer.updated_by_user),
        timestamp=layer.timestamp,
        features=features_list,
    )


def _build_feature_response(feature) -> FeatureCollectionResponse:
    """Convert FeatureCollection model to response with usernames resolved."""
    return FeatureCollectionResponse(
        id=feature.id,
        vector_layer_id=feature.vector_layer_id,
        attr_data=feature.attr_data,
        geom=_geometry_to_string(feature.geom),
        style_value=feature.style_value,
        label_value=feature.label_value,
        created_by=_get_username(feature.created_by_user),
        updated_by=_get_username(feature.updated_by_user),
        is_deleted=feature.is_deleted,
        timestamp=feature.timestamp,
    )


# ============ VECTOR LAYER ENDPOINTS ============


@router.post("/layers", response_model=VectorLayerResponse, status_code=201)
def create_layer(
    layer: VectorLayerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new vector layer (JSON body)."""
    db_layer = create_vector_layer(db=db, layer_data=layer, user_id=current_user.id)
    return _build_layer_response(db_layer)


@router.post("/layers_form", response_model=VectorLayerResponse, status_code=201)
def create_layer_form(
    name_en: str = Form(...),
    name_ne: str = Form(...),
    layer_type: str = Form(...),
    style_value: Optional[str] = Form(None),
    label_value: Optional[str] = Form(None),
    is_public: str = Form("true"),
    display_on_map: str = Form("true"),
    attr_data_json: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new vector layer (form-data). attr_data should be JSON string."""
    # Convert string booleans to actual booleans
    is_public_bool = is_public.lower() in ("true", "1", "yes")
    display_on_map_bool = display_on_map.lower() in ("true", "1", "yes")

    try:
        attr_data = {}
        if attr_data_json:
            attr_data = json.loads(attr_data_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid attr_data JSON format")

    layer_data = VectorLayerCreate(
        name_en=name_en,
        name_ne=name_ne,
        layer_type=layer_type,
        style_value=style_value,
        label_value=label_value,
        is_public=is_public_bool,
        display_on_map=display_on_map_bool,
        attr_data=attr_data,
    )
    db_layer = create_vector_layer(
        db=db, layer_data=layer_data, user_id=current_user.id
    )
    return _build_layer_response(db_layer)


@router.post("/upload", response_model=VectorUploadSummary, status_code=201)
def upload_vector_file_endpoint(
    file: UploadFile = File(
        ..., description="GeoJSON (.geojson/.json) or Shapefile (.zip)"
    ),
    name_en: str = Form(..., description="Layer name in English"),
    name_ne: Optional[str] = Form(None, description="Layer name in Nepali"),
    is_public: str = Form("true", description="Make layer public"),
    display_on_map: str = Form("true", description="Display layer on map by default"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a vector file (GeoJSON or Shapefile) and create a vector layer.

    **Supported Formats:**
    - `.geojson` or `.json`: GeoJSON FeatureCollection or Feature
    - `.zip`: Shapefile archive (must contain .shp, .shx, .dbf files)

    **Parameters:**
    - `file`: Vector file to upload
    - `name_en`: Layer name in English (required)
    - `name_ne`: Layer name in Nepali (optional)
    - `is_public`: Whether layer is publicly accessible (default: true)
    - `display_on_map`: Display layer in map by default (default: true)

    **Returns:** Layer ID, feature count, and upload status
    """
    # Convert string booleans to actual booleans
    is_public_bool = is_public.lower() in ("true", "1", "yes")
    display_on_map_bool = display_on_map.lower() in ("true", "1", "yes")

    result = upload_vector_file(
        db=db,
        upload=file,
        layer_name_en=name_en,
        layer_name_ne=name_ne,
        user_id=current_user.id,
        is_public=is_public_bool,
        display_on_map=display_on_map_bool,
    )
    return result


@router.post("/upload/", response_model=VectorUploadSummary, status_code=201)
def upload_vector_file_endpoint_with_slash(
    file: UploadFile = File(
        ..., description="GeoJSON (.geojson/.json) or Shapefile (.zip)"
    ),
    name_en: str = Form(..., description="Layer name in English"),
    name_ne: Optional[str] = Form(None, description="Layer name in Nepali"),
    is_public: str = Form("true", description="Make layer public"),
    display_on_map: str = Form("true", description="Display layer on map by default"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Same as /upload but accepts trailing slash"""
    is_public_bool = is_public.lower() in ("true", "1", "yes")
    display_on_map_bool = display_on_map.lower() in ("true", "1", "yes")

    result = upload_vector_file(
        db=db,
        upload=file,
        layer_name_en=name_en,
        layer_name_ne=name_ne,
        user_id=current_user.id,
        is_public=is_public_bool,
        display_on_map=display_on_map_bool,
    )
    return result


@router.get("/layers", response_model=List[VectorLayerResponse])
def list_layers(
    pagination: Pagination = Depends(),
    layer_type: Optional[str] = Query(
        None, description="Filter by layer type: polygon, line, point"
    ),
    is_public: Optional[bool] = Query(None, description="Filter by public status"),
    display_on_map: Optional[bool] = Query(
        None, description="Filter by map display status"
    ),
    search: Optional[str] = Query(
        None, description="Search by name in English or Nepali"
    ),
    sort_by: str = Query("id", description="Sort by field"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db),
):
    """
    List all vector layers with filtering, pagination and sorting.

    **Filter Parameters:**
    - `layer_type`: polygon, line, or point
    - `is_public`: true or false
    - `display_on_map`: true or false
    - `search`: Search in name_en or name_ne
    - `sort_by`: Field to sort by (id, name_en, name_ne, layer_type, etc)
    - `order`: asc or desc
    """
    layers = list_vector_layers(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        layer_type=layer_type,
        is_public=is_public,
        display_on_map=display_on_map,
        search=search,
        sort_by=sort_by,
        order=order,
    )
    return [_build_layer_response(layer) for layer in layers]


@router.get("/layers/{layer_id}", response_model=VectorLayerDetailResponse)
def get_layer(
    layer_id: int,
    has_geometry: Optional[bool] = Query(
        None,
        description="Filter by geometry presence: true=has geometry, false=no geometry, null=all",
    ),
    db: Session = Depends(get_db),
):
    """
    Get a specific vector layer with all its features.

    **Parameters:**
    - `has_geometry`: Optional filter
      - `true`: Only features WITH geometry (mappable)
      - `false`: Only features WITHOUT geometry (data-only)
      - `null` (default): All features
    """
    db_layer = get_vector_layer(db=db, layer_id=layer_id)

    # Filter features if requested
    if has_geometry is not None:
        filtered_features = [
            f for f in db_layer.features if (f.geom is not None) == has_geometry
        ]
        db_layer.features = filtered_features

    return _build_layer_response(db_layer)


@router.patch("/layers/{layer_id}", response_model=VectorLayerResponse)
def update_layer(
    layer_id: int,
    layer: VectorLayerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a vector layer."""
    db_layer = update_vector_layer(
        db=db, layer_id=layer_id, layer_data=layer, user_id=current_user.id
    )
    return _build_layer_response(db_layer)


@router.delete("/layers/{layer_id}", status_code=204)
def remove_layer(
    layer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a vector layer and all its features."""
    delete_vector_layer(db=db, layer_id=layer_id)
    return None


@router.get("/layers/{layer_id}/features-count")
def get_features_count(
    layer_id: int,
    db: Session = Depends(get_db),
):
    """Get count of active features in a layer."""
    return {
        "layer_id": layer_id,
        "feature_count": get_layer_features_count(db=db, layer_id=layer_id),
    }


# ============ FEATURE COLLECTION ENDPOINTS ============


@router.post("/features", response_model=FeatureCollectionResponse, status_code=201)
def create_feature_endpoint(
    feature: FeatureCollectionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new feature in a vector layer (JSON body)."""
    db_feature = create_feature(db=db, feature_data=feature, user_id=current_user.id)
    return _build_feature_response(db_feature)


@router.post(
    "/features_form", response_model=FeatureCollectionResponse, status_code=201
)
def create_feature_form(
    vector_layer_id: int = Form(...),
    geom: Optional[str] = Form(
        None, description="Geometry in WKT format (e.g., 'POINT(85.3 27.7)')"
    ),
    style_value: Optional[str] = Form(None),
    label_value: Optional[str] = Form(None),
    attr_data_json: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new feature (form-data).

    **Parameters:**
    - `vector_layer_id`: Vector layer ID (required)
    - `geom`: Geometry in WKT format (e.g., 'POINT(85.3 27.7)', 'POLYGON(...)')
    - `attr_data_json`: Feature attributes as JSON string

    **Without geometry, features won't be mappable in the frontend!**
    """
    try:
        attr_data = {}
        if attr_data_json:
            attr_data = json.loads(attr_data_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid attr_data JSON format")

    feature_data = FeatureCollectionCreate(
        vector_layer_id=vector_layer_id,
        geom=geom,
        style_value=style_value,
        label_value=label_value,
        attr_data=attr_data,
    )
    db_feature = create_feature(
        db=db, feature_data=feature_data, user_id=current_user.id
    )
    return _build_feature_response(db_feature)


@router.get("/features", response_model=List[FeatureCollectionListResponse])
def list_features_endpoint(
    pagination: Pagination = Depends(),
    vector_layer_id: Optional[int] = Query(
        None, description="Filter by vector layer ID"
    ),
    is_deleted: Optional[bool] = Query(None, description="Include deleted features"),
    search: Optional[str] = Query(None, description="Search by label or style value"),
    sort_by: str = Query("id", description="Sort by field"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db),
):
    """
    List features with filtering, pagination and sorting.

    **Filter Parameters:**
    - `vector_layer_id`: Filter by specific layer
    - `is_deleted`: Include deleted features (null = exclude deleted)
    - `search`: Search in label_value or style_value
    - `sort_by`: Field to sort by
    - `order`: asc or desc
    """
    features = list_features(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        vector_layer_id=vector_layer_id,
        is_deleted=is_deleted,
        search=search,
        sort_by=sort_by,
        order=order,
    )
    return [_build_feature_response(feature) for feature in features]


@router.get("/features_with_geom", response_model=List[FeatureCollectionResponse])
def list_features_with_geom_endpoint(
    skip: int = Query(0, ge=0, description="Skip N rows"),
    limit: int = Query(10, ge=1, le=10000, description="Limit results (up to 10000)"),
    vector_layer_id: int = Query(..., description="Vector layer ID (required)"),
    is_deleted: Optional[bool] = Query(None, description="Include deleted features"),
    search: Optional[str] = Query(None, description="Search by label or style value"),
    sort_by: str = Query("id", description="Sort by field"),
    order: str = Query("asc", pattern="^(asc|desc)$", description="Sort order"),
    db: Session = Depends(get_db),
):
    """
    List features for a layer with full geometry payload for map rendering.

    **Use this endpoint when you need `geom` in response.**
    """
    features = list_features(
        db=db,
        skip=skip,
        limit=limit,
        vector_layer_id=vector_layer_id,
        is_deleted=is_deleted,
        search=search,
        sort_by=sort_by,
        order=order,
    )

    feature_responses = []
    for feature in features:
        geom_text = None
        if feature.geom is not None:
            # Use PostGIS text conversion directly to avoid WKB parse issues.
            geom_text = (
                db.query(func.ST_AsText(FeatureCollection.geom))
                .filter(FeatureCollection.id == feature.id)
                .scalar()
            )

        feature_responses.append(
            FeatureCollectionResponse(
                id=feature.id,
                vector_layer_id=feature.vector_layer_id,
                attr_data=feature.attr_data,
                geom=geom_text,
                style_value=feature.style_value,
                label_value=feature.label_value,
                created_by=_get_username(feature.created_by_user),
                updated_by=_get_username(feature.updated_by_user),
                is_deleted=feature.is_deleted,
                timestamp=feature.timestamp,
            )
        )

    return feature_responses


@router.get("/features/{feature_id}", response_model=FeatureCollectionResponse)
def get_feature_endpoint(
    feature_id: int,
    db: Session = Depends(get_db),
):
    """Get a specific feature."""
    db_feature = get_feature(db=db, feature_id=feature_id)
    return _build_feature_response(db_feature)


@router.patch("/features/{feature_id}", response_model=FeatureCollectionResponse)
def update_feature_endpoint(
    feature_id: int,
    feature: FeatureCollectionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a feature (partial update via JSON)."""
    db_feature = update_feature(
        db=db, feature_id=feature_id, feature_data=feature, user_id=current_user.id
    )
    return _build_feature_response(db_feature)


@router.patch(
    "/features/{feature_id}/geometry", response_model=FeatureCollectionResponse
)
def update_feature_geometry(
    feature_id: int,
    geom: str = Form(
        ..., description="Geometry in WKT format (e.g., 'POINT(85.3 27.7)')"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add or update geometry for an existing feature.

    **Use this to:**
    - Add geometry to features created without it
    - Update an existing feature's geometry

    **Example:** `POINT(85.3240 27.7172)`
    """
    feature_data = FeatureCollectionUpdate(geom=geom)
    db_feature = update_feature(
        db=db, feature_id=feature_id, feature_data=feature_data, user_id=current_user.id
    )
    return _build_feature_response(db_feature)


@router.delete("/features/{feature_id}", status_code=204)
def soft_delete_feature_endpoint(
    feature_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft delete a feature (mark as deleted)."""
    delete_feature(db=db, feature_id=feature_id)
    return None
