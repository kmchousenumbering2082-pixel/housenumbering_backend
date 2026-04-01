import os
import shutil
import uuid
from pathlib import Path
from typing import Optional
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session
from osgeo import osr, gdal, gdalconst

from src.raster.schema import (
    RasterLayerCreate,
    RasterLayerUpdate,
    BaseLayerCreate,
    BaseLayerUpdate,
    BaseLayerNameCreate,
    BaseLayerNameUpdate,
)
from src.models import RasterLayer, RasterLayerMetadata, BaseLayer, BaseLayerName
RASTER_UPLOAD_ROOT = Path("media") / "raster"
VALID_RASTER_EXTENSIONS = {".tif", ".tiff", ".geotiff", ".ecw", ".vrt", ".jp2", ".jp2k"}


def _bad_request(detail: str) -> HTTPException:
    """Create a 400 Bad Request exception."""
    return HTTPException(status_code=400, detail=detail)


def _save_raster_file(upload: UploadFile) -> tuple[Path, str]:
    """
    Save the uploaded raster file to the media directory.
    
    Args:
        upload: The uploaded file object
        
    Returns:
        Tuple of (destination_path, relative_path)
        
    Raises:
        HTTPException: If file validation fails
    """
    if not upload.filename:
        raise _bad_request("Uploaded file must have a filename")

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in VALID_RASTER_EXTENSIONS:
        raise _bad_request(
            f"Invalid raster format. Supported formats: {', '.join(VALID_RASTER_EXTENSIONS)}"
        )

    # Ensure raster upload directory exists
    RASTER_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    # Generate a unique filename
    unique_name = f"{uuid.uuid4().hex}_{Path(upload.filename).name}"
    destination = RASTER_UPLOAD_ROOT / unique_name

    try:
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
    except IOError as exc:
        raise _bad_request(f"Failed to save raster file: {exc}") from exc

    # Return both absolute path and relative path
    relative_path = str(destination).replace("\\", "/")
    return destination, relative_path


def _extract_raster_metadata(file_path: Path) -> dict:
    """
    Extract metadata from a raster file using GDAL.
    
    Args:
        file_path: Path to the raster file
        
    Returns:
        Dictionary containing raster metadata
        
    Raises:
        HTTPException: If metadata extraction fails
    """
    try:
        
        
        # Suppress GDAL warnings
        gdal.UseExceptions()
        
        dataset = gdal.Open(str(file_path), gdalconst.GA_ReadOnly)
        if dataset is None:
            raise _bad_request(f"Failed to open raster file: {file_path}")

        # Extract basic properties
        width = dataset.RasterXSize
        height = dataset.RasterYSize
        numbands = dataset.RasterCount
        srid = None

        # Get spatial reference (SRID)
        projection = dataset.GetProjection()
        if projection:
            
            spatialref = osr.SpatialReference(wkt=projection)
            srid = spatialref.GetAttrValue("AUTHORITY", 1)
            if srid:
                srid = int(srid)

        # Get geotransform (extent information)
        geotransform = dataset.GetGeoTransform()
        if geotransform:
            minx = geotransform[0]
            miny = geotransform[3] + (height * geotransform[5])
            maxx = geotransform[0] + (width * geotransform[1])
            maxy = geotransform[3]
        else:
            minx = miny = maxx = maxy = 0

        # Get extent as dictionary
        extent = {"minx": minx, "miny": miny, "maxx": maxx, "maxy": maxy} if geotransform else None

        # Calculate pixel size
        pixel_size = abs(geotransform[1]) if geotransform else 0

        dataset = None  # Close dataset

        return {
            "width": width,
            "height": height,
            "numbands": numbands,
            "srid": srid,
            "extent": extent,
            "pixel_size": pixel_size,
            "minx": minx,
            "maxx": maxx,
            "miny": miny,
            "maxy": maxy,
        }
    except ImportError:
        # GDAL not available - return minimal metadata
        return {
            "width": None,
            "height": None,
            "numbands": None,
            "srid": None,
            "extent": None,
            "pixel_size": 0,
            "minx": 0,
            "maxx": 0,
            "miny": 0,
            "maxy": 0,
        }
    except Exception as exc:
        # Format not supported by GDAL or other GDAL errors - return minimal metadata
        # This allows uploads of unsupported formats (.ecw without driver, etc.) to still work
        print(f"Warning: Could not extract raster metadata: {exc}")
        return {
            "width": None,
            "height": None,
            "numbands": None,
            "srid": None,
            "extent": None,
            "pixel_size": 0,
            "minx": 0,
            "maxx": 0,
            "miny": 0,
            "maxy": 0,
        }


def create_raster_layer(
    db: Session,
    upload: UploadFile,
    payload: RasterLayerCreate,
    user_id: Optional[int] = None,
) -> dict:
    """
    Create a new raster layer with uploaded file.
    
    Args:
        db: Database session
        upload: Uploaded raster file
        payload: Raster layer creation payload
        user_id: ID of user creating the layer
        
    Returns:
        Dictionary with raster layer details and metadata
    """
    # Save the raster file
    file_path, relative_path = _save_raster_file(upload)

    # Extract metadata from raster
    metadata_dict = _extract_raster_metadata(file_path)

    # Create RasterLayer entry
    raster_layer = RasterLayer(
        name_en=payload.name_en,
        name_ne=payload.name_ne,
        raster_file=relative_path,
        attr_data=payload.attr_data,
        display_on_map=payload.display_on_map,
        is_public=payload.is_public,
        status="completed",
        bbox={
            "minx": metadata_dict["minx"],
            "miny": metadata_dict["miny"],
            "maxx": metadata_dict["maxx"],
            "maxy": metadata_dict["maxy"],
        } if metadata_dict["extent"] else None,
        created_by=user_id,
    )
    
    db.add(raster_layer)
    db.flush()  # Get the ID without committing

    # Create RasterLayerMetadata entry
    metadata = RasterLayerMetadata(
        raster_layer_id=raster_layer.id,
        file_name=upload.filename,
        **metadata_dict,
    )
    
    db.add(metadata)
    db.commit()
    db.refresh(raster_layer)

    return {
        "raster_id": raster_layer.id,
        "file_name": upload.filename,
        "status": raster_layer.status,
        "message": "Raster file uploaded successfully",
        "width": metadata_dict["width"],
        "height": metadata_dict["height"],
        "numbands": metadata_dict["numbands"],
        "srid": metadata_dict["srid"],
    }


def get_raster_layer(db: Session, raster_id: int) -> RasterLayer:
    """Get a raster layer by ID with relationships."""
    
    raster = db.query(RasterLayer).options(
        joinedload(RasterLayer.raster_metadata)
    ).filter(RasterLayer.id == raster_id).first()
    if not raster:
        raise _bad_request(f"Raster layer with ID {raster_id} not found")
    return raster


def list_raster_layers(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    is_public: bool = True,
) -> list[RasterLayer]:
    """List raster layers with pagination."""
    
    query = db.query(RasterLayer).options(joinedload(RasterLayer.raster_metadata))
    
    if is_public:
        query = query.filter(RasterLayer.is_public == True)
    
    return query.offset(skip).limit(limit).all()


def update_raster_layer(
    db: Session,
    raster_id: int,
    payload: RasterLayerUpdate,
) -> RasterLayer:
    """Update a raster layer."""
    raster = get_raster_layer(db, raster_id)
    
    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(raster, field, value)
    
    db.commit()
    db.refresh(raster)
    return raster


def delete_raster_layer(db: Session, raster_id: int) -> None:
    """Delete a raster layer and its file."""
    raster = get_raster_layer(db, raster_id)
    
    # Delete the file from disk
    if raster.raster_file:
        file_path = Path(raster.raster_file)
        try:
            if file_path.exists():
                file_path.unlink()
        except OSError as exc:
            # Log error but don't fail the deletion
            print(f"Failed to delete raster file: {exc}")
    
    # Delete from database (cascade will handle metadata)
    db.delete(raster)
    db.commit()


# BaseLayer functions

def create_base_layer(
    db: Session,
    payload: BaseLayerCreate,
    user_id: Optional[int] = None,
) -> BaseLayer:
    """Create a new base layer."""
    base_layer = BaseLayer(
        name=payload.name,
        layer_type=payload.layer_type,
        url=payload.url,
        attribution=payload.attribution,
        is_active=payload.is_active,
        created_by=user_id,
    )
    
    db.add(base_layer)
    db.commit()
    db.refresh(base_layer)
    return base_layer


def get_base_layer(db: Session, layer_id: int) -> BaseLayer:
    """Get a base layer by ID."""
    layer = db.query(BaseLayer).filter(BaseLayer.id == layer_id).first()
    if not layer:
        raise _bad_request(f"Base layer with ID {layer_id} not found")
    return layer


def list_base_layers(db: Session, skip: int = 0, limit: int = 100) -> list[BaseLayer]:
    """List base layers with pagination."""
    return db.query(BaseLayer).offset(skip).limit(limit).all()


def update_base_layer(
    db: Session,
    layer_id: int,
    payload: BaseLayerUpdate,
) -> BaseLayer:
    """Update a base layer."""
    layer = get_base_layer(db, layer_id)
    
    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(layer, field, value)
    
    db.commit()
    db.refresh(layer)
    return layer


def delete_base_layer(db: Session, layer_id: int) -> None:
    """Delete a base layer."""
    layer = get_base_layer(db, layer_id)
    db.delete(layer)
    db.commit()


# BaseLayerName functions

def create_base_layer_name(
    db: Session,
    payload: BaseLayerNameCreate,
) -> BaseLayerName:
    """Create a new base layer name."""
    # Verify base layer exists
    get_base_layer(db, payload.base_layer_id)
    
    layer_name = BaseLayerName(
        base_layer_id=payload.base_layer_id,
        name=payload.name,
        label_en=payload.label_en,
        label_ne=payload.label_ne,
        order=payload.order,
        is_visible=payload.is_visible,
    )
    
    db.add(layer_name)
    db.commit()
    db.refresh(layer_name)
    return layer_name


def get_base_layer_names(db: Session, layer_id: int) -> list[BaseLayerName]:
    """Get all names for a base layer."""
    get_base_layer(db, layer_id)  # Verify layer exists
    
    return (
        db.query(BaseLayerName)
        .filter(BaseLayerName.base_layer_id == layer_id)
        .order_by(BaseLayerName.order)
        .all()
    )


def update_base_layer_name(
    db: Session,
    name_id: int,
    payload: BaseLayerNameUpdate,
) -> BaseLayerName:
    """Update a base layer name."""
    layer_name = db.query(BaseLayerName).filter(BaseLayerName.id == name_id).first()
    if not layer_name:
        raise _bad_request(f"Base layer name with ID {name_id} not found")
    
    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(layer_name, field, value)
    
    db.commit()
    db.refresh(layer_name)
    return layer_name


def delete_base_layer_name(db: Session, name_id: int) -> None:
    """Delete a base layer name."""
    layer_name = db.query(BaseLayerName).filter(BaseLayerName.id == name_id).first()
    if not layer_name:
        raise _bad_request(f"Base layer name with ID {name_id} not found")
    
    db.delete(layer_name)
    db.commit()
