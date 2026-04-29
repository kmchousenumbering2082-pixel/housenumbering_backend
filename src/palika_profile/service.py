import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import geopandas as gpd
from fastapi import HTTPException, UploadFile
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union
from sqlalchemy.orm import Session

from src.palika_profile.models import (
    PalikaGeometry,
    PalikaGeometryFile,
    PalikaProfile,
    PalikaWardGeometry,
)
from src.palika_profile.schema import PalikaProfileCreate, PalikaProfileUpdate

PALIKA_UPLOAD_ROOT = Path("media") / "palika_profile"
EXTENSION_TO_FILE_TYPE = {
    ".geojson": "geojson",
    ".json": "geojson",
    ".shp": "shp",
    ".zip": "shp",
}
WARD_COLUMN_CANDIDATES = ("ward_no", "ward", "wardno", "ward_number", "ward_num")
SHAPEFILE_REQUIRED_EXTENSIONS = (".shp", ".dbf", ".shx")
PROFILE_MUTABLE_FIELDS = {
    "name_en",
    "name_ne",
    "description_en",
    "description_ne",
    "logo_en",
    "logo_ne",
    "contact_info",
    "important_links",
    "email",
    "zip_code",
    "address",
    "local_coordinate_system",
}


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _save_upload_file(upload: UploadFile, category: str) -> tuple[Path, str, str]:
    if not upload.filename:
        raise _bad_request("Uploaded file must have a filename")

    suffix = Path(upload.filename).suffix.lower()
    file_type = EXTENSION_TO_FILE_TYPE.get(suffix)
    if not file_type:
        raise _bad_request("Only .shp, .geojson, or .zip files are supported")

    upload_dir = PALIKA_UPLOAD_ROOT / category
    upload_dir.mkdir(parents=True, exist_ok=True)

    destination = upload_dir / f"{uuid.uuid4().hex}_{Path(upload.filename).name}"
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

    return destination, file_type, str(destination).replace("\\", "/")


def _read_shapefile_zip(zip_path: Path) -> gpd.GeoDataFrame:
    try:
        with tempfile.TemporaryDirectory(prefix="palika_shp_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                members = zip_ref.infolist()
                for member in members:
                    member_path = Path(member.filename)
                    if member_path.is_absolute() or ".." in member_path.parts:
                        raise _bad_request("Invalid zip file structure")
                zip_ref.extractall(tmp_path)

            # A valid shapefile dataset requires .shp + .dbf + .shx for the same basename.
            shp_files = sorted(p for p in tmp_path.rglob("*.shp") if p.is_file())
            if not shp_files:
                raise _bad_request("Zip must contain at least one .shp file")

            for shp in shp_files:
                base = shp.with_suffix("")
                if all(
                    base.with_suffix(ext).exists()
                    for ext in SHAPEFILE_REQUIRED_EXTENSIONS
                ):
                    return gpd.read_file(shp)

            raise _bad_request("Zip must include matching .shp, .dbf, and .shx files")
    except zipfile.BadZipFile as exc:
        raise _bad_request("Invalid zip archive") from exc


def _read_geodataframe(path: Path) -> gpd.GeoDataFrame:
    try:
        gdf = (
            _read_shapefile_zip(path)
            if path.suffix.lower() == ".zip"
            else gpd.read_file(path)
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _bad_request(f"Unable to read geometry file: {exc}") from exc

    if gdf.empty:
        raise _bad_request("Uploaded file contains no features")
    if "geometry" not in gdf.columns:
        raise _bad_request("Uploaded file has no geometry column")

    gdf = gdf[gdf.geometry.notnull()].copy()
    if gdf.empty:
        raise _bad_request("Uploaded file has no valid geometries")

    return (
        gdf.set_crs(epsg=4326, allow_override=True)
        if gdf.crs is None
        else gdf.to_crs(epsg=4326)
    )


def _to_multipolygon(geometries) -> MultiPolygon:
    # Normalize any polygon-like collection into a single MultiPolygon for storage.
    merged = unary_union(
        [geom for geom in geometries if geom is not None and not geom.is_empty]
    )
    if merged.is_empty:
        raise _bad_request("Cannot build geometry from empty dataset")
    if isinstance(merged, Polygon):
        return MultiPolygon([merged])
    if isinstance(merged, MultiPolygon):
        return merged

    polygons: list[Polygon] = []
    if hasattr(merged, "geoms"):
        for geom in merged.geoms:
            if isinstance(geom, Polygon):
                polygons.append(geom)
            elif isinstance(geom, MultiPolygon):
                polygons.extend(list(geom.geoms))

    if not polygons:
        raise _bad_request("No polygon geometry found in uploaded file")

    unified = unary_union(polygons)
    if isinstance(unified, Polygon):
        return MultiPolygon([unified])
    if isinstance(unified, MultiPolygon):
        return unified
    raise _bad_request("Unsupported geometry type for palika boundary")


def _upsert_file_record(
    db: Session, file_type: str, file_upload: str
) -> PalikaGeometryFile:
    row = PalikaGeometryFile(file_type=file_type, file_upload=file_upload)
    db.add(row)
    db.flush()
    return row


def _upsert_palika_geometry(db: Session, gdf: gpd.GeoDataFrame) -> PalikaGeometry:
    metric_gdf = gdf.to_crs(epsg=3857)
    row = db.query(PalikaGeometry).first() or PalikaGeometry()
    if row.id is None:
        db.add(row)

    row.area = float(metric_gdf.geometry.area.sum())
    row.bbox = {"type": "bbox", "coordinates": gdf.total_bounds.tolist()}
    row.geom = from_shape(_to_multipolygon(gdf.geometry.tolist()), srid=4326)
    db.flush()
    return row


def _resolve_ward_column(gdf: gpd.GeoDataFrame, ward_column: str | None) -> str:
    if ward_column and ward_column in gdf.columns:
        return ward_column

    lookup = {column.lower(): column for column in gdf.columns}
    for candidate in WARD_COLUMN_CANDIDATES:
        if candidate in lookup:
            return lookup[candidate]

    raise _bad_request(
        "Ward column not found. Provide ward_column or include one of: ward_no, ward, wardno"
    )


def _parse_ward_no(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _upsert_ward_geometries(
    db: Session,
    gdf: gpd.GeoDataFrame,
    ward_column: str,
    numbering_status: str | None = None,
) -> list[PalikaWardGeometry]:
    rows: list[PalikaWardGeometry] = []
    for ward_value, group in gdf.groupby(ward_column):
        ward_no = _parse_ward_no(ward_value)
        if ward_no is None:
            continue

        metric_group = group.to_crs(epsg=3857)
        row = (
            db.query(PalikaWardGeometry)
            .filter(PalikaWardGeometry.ward_no == ward_no)
            .first()
        )
        if not row:
            row = PalikaWardGeometry(ward_no=ward_no)
            db.add(row)

        row.numbering_status = numbering_status or row.numbering_status
        row.area = float(metric_group.geometry.area.sum())
        row.bbox = {"type": "bbox", "coordinates": group.total_bounds.tolist()}
        row.geom = from_shape(_to_multipolygon(group.geometry.tolist()), srid=4326)
        db.flush()
        rows.append(row)

    if not rows:
        raise _bad_request(
            "No valid ward geometries could be extracted from uploaded file"
        )
    return rows


def _profile_payload(payload: PalikaProfileCreate | PalikaProfileUpdate) -> dict:
    data = payload.model_dump(exclude_unset=True)
    return {key: value for key, value in data.items() if key in PROFILE_MUTABLE_FIELDS}


def get_palika_profile(db: Session, profile_id: int) -> PalikaProfile:
    row = db.query(PalikaProfile).filter(PalikaProfile.id == profile_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Palika profile not found")
    return row


def list_palika_profiles(db: Session) -> list[PalikaProfile]:
    return db.query(PalikaProfile).order_by(PalikaProfile.id.asc()).all()


def create_palika_profile(db: Session, payload: PalikaProfileCreate) -> PalikaProfile:
    row = PalikaProfile(**_profile_payload(payload))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_palika_profile(
    db: Session, profile_id: int, payload: PalikaProfileUpdate
) -> PalikaProfile:
    row = get_palika_profile(db, profile_id)
    for key, value in _profile_payload(payload).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def upload_palika_geometry_file(db: Session, upload: UploadFile) -> dict:
    path, file_type, file_upload = _save_upload_file(upload, category="geometry")
    gdf = _read_geodataframe(path)
    file_row = _upsert_file_record(db, file_type=file_type, file_upload=file_upload)
    geom_row = _upsert_palika_geometry(db, gdf)
    db.commit()

    return {
        "file_id": file_row.id,
        "file_type": file_type,
        "file_upload": file_upload,
        "feature_count": int(len(gdf)),
        "updated_geometry_id": geom_row.id,
    }


def upload_palika_ward_geometry_file(
    db: Session,
    upload: UploadFile,
    ward_column: str | None = None,
    numbering_status: str | None = None,
) -> dict:
    path, file_type, file_upload = _save_upload_file(upload, category="ward_geometry")
    gdf = _read_geodataframe(path)
    file_row = _upsert_file_record(db, file_type=file_type, file_upload=file_upload)
    rows = _upsert_ward_geometries(
        db=db,
        gdf=gdf,
        ward_column=_resolve_ward_column(gdf, ward_column),
        numbering_status=numbering_status,
    )
    db.commit()

    return {
        "file_id": file_row.id,
        "file_type": file_type,
        "file_upload": file_upload,
        "feature_count": int(len(gdf)),
        "ward_count": len(rows),
        "updated_ward_ids": [row.id for row in rows],
    }


def _geometry_to_dict(geom_obj) -> dict:
    """Convert ORM geometry object to dict with WKT string geom."""
    return {
        "id": geom_obj.id,
        "area": geom_obj.area,
        "bbox": geom_obj.bbox,
        "timestamp": geom_obj.timestamp,
        "geom": to_shape(geom_obj.geom).wkt if geom_obj.geom else None,
    }


def _ward_geometry_to_dict(geom_obj) -> dict:
    """Convert ORM ward geometry object to dict with WKT string geom."""
    return {
        "id": geom_obj.id,
        "ward_no": geom_obj.ward_no,
        "numbering_status": geom_obj.numbering_status,
        "area": geom_obj.area,
        "bbox": geom_obj.bbox,
        "timestamp": geom_obj.timestamp,
        "geom": to_shape(geom_obj.geom).wkt if geom_obj.geom else None,
    }


def get_palika_geometry(db: Session) -> dict:
    row = db.query(PalikaGeometry).first()
    if not row:
        raise HTTPException(status_code=404, detail="Palika geometry not found")
    return _geometry_to_dict(row)


def list_palika_ward_geometries(
    db: Session, ward_no: list[int] | None = None
) -> list[dict]:
    query = db.query(PalikaWardGeometry)
    if ward_no:
        query = query.filter(PalikaWardGeometry.ward_no.in_(ward_no))
    rows = query.order_by(PalikaWardGeometry.ward_no.asc()).all()
    return [_ward_geometry_to_dict(row) for row in rows]


def get_palika_ward_geometry_by_ward(db: Session, ward_no: int) -> dict:
    row = (
        db.query(PalikaWardGeometry)
        .filter(PalikaWardGeometry.ward_no == ward_no)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Palika ward geometry not found")
    return _ward_geometry_to_dict(row)


def get_unique_ward_numbers(db: Session) -> list[int]:
    ward_numbers = (
        db.query(PalikaWardGeometry.ward_no)
        .order_by(PalikaWardGeometry.ward_no.asc())
        .distinct()
        .all()
    )
    return [ward[0] for ward in ward_numbers]
