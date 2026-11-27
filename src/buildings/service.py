import io
import math
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import geopandas as gpd
import shapely
from fastapi import HTTPException, UploadFile
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import MultiPolygon, Polygon
from shapely.prepared import prep
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, text

from src.enums.buildings import RoofType
from src.models import Building, BuildingGeometry, Road
from src.palika_profile.models import PalikaWardGeometry

from src.buildings.schema import BuildingCreate
from src.utils.pluscode import encode as encode_plus_code


def _compute_plus_code(
    lat_value: Optional[str], long_value: Optional[str]
) -> Optional[str]:
    if lat_value is None or long_value is None:
        return None

    try:
        latitude = float(lat_value)
        longitude = float(long_value)
    except (TypeError, ValueError):
        return None

    return encode_plus_code(latitude, longitude)


def _validate_road_id(db: Session, road_id: Optional[int]) -> None:
    if road_id is None:
        return

    road = db.query(Road).filter(Road.id == road_id).first()
    if not road:
        raise HTTPException(status_code=404, detail=f"Road with ID {road_id} not found")


def create_building(db: Session, building_data: BuildingCreate) -> Building:
    payload = building_data.model_dump(exclude_unset=True)
    _validate_road_id(db, payload.get("road_id"))

    computed_plus_code = _compute_plus_code(
        payload.get("lat_field"), payload.get("long_field")
    )
    if computed_plus_code:
        payload["plus_code"] = computed_plus_code

    db_building = Building(**payload)
    db.add(db_building)
    db.commit()
    db.refresh(db_building)
    return db_building


def count_buildings(
    db: Session,
    ward_no: Optional[int] = None,
    min_floor: Optional[float] = None,
    roof_type: Optional[RoofType] = None,
) -> int:
    query = db.query(Building)

    if ward_no is not None:
        query = query.filter(Building.ward_no == ward_no)
    if min_floor is not None:
        query = query.filter(Building.floor >= min_floor)
    if roof_type is not None:
        query = query.filter(Building.roof_type == roof_type.value)

    return query.count()


def search_buildings(query, search: Optional[str]):
    search_query = (search or "").strip()
    if not search_query:
        return query

    if "-" in search_query:
        house_no, other_info = map(str.strip, search_query.split("-", 1))
        # If both sides present use exact-match semantics (house_no + tole/road)
        if house_no and other_info:
            return query.filter(
                Building.house_no.isnot(None),
                func.lower(Building.house_no) == house_no.lower(),
                or_(
                    func.lower(Building.tole_name) == other_info.lower(),
                    Building.road.has(
                        func.lower(Road.road_name_en) == other_info.lower()
                    ),
                ),
            )

        # If one side is missing, search each available part separately
        filters = []
        if house_no:
            filters.append(Building.house_no.ilike(f"%{house_no}%"))
        if other_info:
            filters.append(Building.tole_name.ilike(f"%{other_info}%"))
            filters.append(Building.owner_name.ilike(f"%{other_info}%"))
            filters.append(Building.plus_code.ilike(f"%{other_info}%"))
            filters.append(Building.metric_address.ilike(f"%{other_info}%"))
            filters.append(
                Building.road.has(Road.road_name_en.ilike(f"%{other_info}%"))
            )

        # Fallback: if nothing parsed, return original query
        if not filters:
            return query

        return query.filter(or_(*filters))

    return query.filter(
        or_(
            Building.house_no.ilike(f"%{search_query}%"),
            Building.tole_name.ilike(f"%{search_query}%"),
            Building.owner_name.ilike(f"%{search_query}%"),
            Building.plus_code.ilike(f"%{search_query}%"),
            Building.metric_address.ilike(f"%{search_query}%"),
            Building.road.has(Road.road_name_en.ilike(f"%{search_query}%")),
        )
    )


def _public_building_item(building: Building) -> dict:
    road = building.road
    return {
        "id": building.id,
        "building_id": building.building_id,
        "ward_no": building.ward_no,
        "plus_code": building.plus_code,
        "house_no": building.house_no,
        "association_type": building.association_type,
        "associate_road_name": road.road_name_en if road else None,
        "bbox": building.bbox,
    }


def list_buildings(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    ward_no: Optional[int] = None,
    min_floor: Optional[float] = None,
    roof_type: Optional[RoofType] = None,
    search: Optional[str] = None,
    sort_by: str = "building_id",
    order: str = "asc",
):
    query = db.query(Building).options(joinedload(Building.road))

    if ward_no is not None:
        query = query.filter(Building.ward_no == ward_no)
    if min_floor is not None:
        query = query.filter(Building.floor >= min_floor)
    if roof_type is not None:
        query = query.filter(Building.roof_type == roof_type.value)

    query = search_buildings(query, search)

    sort_column = getattr(Building, sort_by, Building.building_id)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    return query.offset(skip).limit(limit).all()


def list_public_buildings(
    db: Session,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
):
    query = db.query(Building).options(joinedload(Building.road))
    query = search_buildings(query, search)

    total = query.count()
    offset = (page - 1) * page_size
    buildings = query.order_by(Building.id.desc()).offset(offset).limit(page_size).all()

    return total, [_public_building_item(building) for building in buildings]


def get_building(db: Session, building_id: int) -> Building:
    building = (
        db.query(Building)
        .options(joinedload(Building.road))
        .filter(Building.id == building_id)
        .first()
    )
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building


def update_building(
    db: Session, building_id: int, building_data: BuildingCreate
) -> Building:
    building = get_building(db=db, building_id=building_id)
    update_data = building_data.model_dump(exclude_unset=True)
    _validate_road_id(db, update_data.get("road_id"))

    computed_plus_code = _compute_plus_code(
        update_data.get("lat_field", building.lat_field),
        update_data.get("long_field", building.long_field),
    )
    if computed_plus_code:
        update_data["plus_code"] = computed_plus_code

    for key, value in update_data.items():
        setattr(building, key, value)
    db.commit()
    db.refresh(building)
    return building


def update_building_plus_code(db: Session, building_id: int) -> Building:
    building = get_building(db=db, building_id=building_id)
    computed_plus_code = _compute_plus_code(building.lat_field, building.long_field)

    if not computed_plus_code:
        raise HTTPException(
            status_code=400,
            detail="Building does not have valid lat_field and long_field values",
        )

    building.plus_code = computed_plus_code
    db.commit()
    db.refresh(building)
    return building


def bulk_update_building_plus_codes(db: Session) -> dict:
    buildings = db.query(Building).all()
    updated_count = 0
    skipped_count = 0

    for building in buildings:
        computed_plus_code = _compute_plus_code(building.lat_field, building.long_field)
        if not computed_plus_code:
            skipped_count += 1
            continue

        building.plus_code = computed_plus_code
        updated_count += 1

    db.commit()

    return {
        "total_buildings": len(buildings),
        "updated_buildings": updated_count,
        "skipped_buildings": skipped_count,
    }


def delete_building(db: Session, building_id: int) -> None:
    building = get_building(db=db, building_id=building_id)
    db.delete(building)
    db.commit()


def assign_road_to_building(
    db: Session,
    building: Building,
    distance_limit: int = 100,
):
    point_hex = (
        building.gate_location.desc
        if building.gate_location
        else (building.centroid.desc if building.centroid else None)
    )
    if not point_hex:
        return None

    result = db.execute(
        text("""
            SELECT r.road_id
            FROM roads r
            JOIN road_geometry rg ON rg.road_id = r.id
            WHERE rg.geom IS NOT NULL
              AND ST_DWithin(
                    ST_Transform(ST_GeomFromWKB(decode(:point, 'hex')), 3857),
                    ST_Transform(rg.geom, 3857),
                    :distance_limit
              )
            ORDER BY ST_Distance(
                ST_Transform(ST_GeomFromWKB(decode(:point, 'hex')), 3857),
                ST_Transform(rg.geom, 3857)
            )
            LIMIT 1
        """),
        {"point": point_hex, "distance_limit": distance_limit},
    ).fetchone()

    if result:
        building.road_id = result[0]
        return result[0]
    return None


def assign_roads_to_all_buildings(
    db: Session,
    distance_limit: int = 100,
):
    buildings = (
        db.query(Building)
        .filter((Building.gate_location.isnot(None)) | (Building.centroid.isnot(None)))
        .all()
    )

    updated_count = sum(
        1 for b in buildings if assign_road_to_building(db, b, distance_limit)
    )
    db.commit()

    return {
        "total_buildings_checked": len(buildings),
        "updated_buildings": updated_count,
        "skipped_buildings": len(buildings) - updated_count,
    }


# ---------------------------------------------------------------------------
# Building upload (GeoJSON / zipped Shapefile) - POST /api/v1/building/upload
#
# Replaces the one-off `building_load.py` script. Unlike the script it:
#   * never fills in random/fake attribute values,
#   * gives new buildings numbers after the highest existing `building_id`
#     (so uploading ward after ward never overwrites earlier wards),
#   * skips buildings that are already stored (same centroid position), so
#     uploading the same file twice is safe,
#   * reprojects any coordinate system to EPSG:4326,
#   * writes everything in one transaction (all or nothing).
# ---------------------------------------------------------------------------

# Metric CRS used only to compute plinth area in m² (UTM zone 45N covers Kathmandu).
AREA_CRS = 32645
# Two buildings whose centroids round to the same 6 decimals (~0.1 m) are the same building.
CENTROID_DECIMALS = 6
MAX_REPORTED_PROBLEMS = 50

# Building column -> accepted attribute names in the uploaded file
# (compared lower-case with spaces/underscores/dashes removed).
COLUMN_ALIASES: Dict[str, Tuple[str, ...]] = {
    "ward_no": ("wardno", "ward", "wardno2"),
    "house_no": ("houseno", "finalhous", "finalhouse", "finalhouseno"),
    "roof_type": ("rooftype",),
    "plinth_area": ("plintharea",),
    "direction": ("direction", "side"),
    "building_use": ("buildinguse", "buildtype", "buildingtype"),
    "building_sp_use": ("buildingspuse",),
    "building_structure": ("buildingstructure", "structure"),
    "tole_name": ("tolename", "tole"),
    "owner_name": ("ownername",),
    "owner_status": ("ownerstatus",),
    "plot_no": ("plotno",),
    "floor": ("floor", "floors", "nooffloor", "nooffloors", "storey", "storeys"),
    "reg_type": ("regtype",),
    "temporary_type": ("temporarytype",),
    "association_type": ("associationtype",),
    "road_type": ("roadtype",),
    "road_lane": ("roadlane",),
    "road_width": ("roadwidth",),
    "remarks": ("remarks", "remark"),
    "metric_address": ("metricaddress",),
    "main_building_id": ("mainbuildingid",),
    "building_id": ("buildingid",),
}
INT_COLUMNS = {"ward_no", "main_building_id", "building_id"}
FLOAT_COLUMNS = {"plinth_area", "floor", "road_width"}
# Attributes that are kept in attr_data under a clearer name.
ATTR_RENAMES = {"roadid": "road_id_code", "uniqueid": "unique_id"}
# Columns the upload must not take from a file.
IGNORED_KEYS = {"geometry"}


def _norm(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


ALIAS_TO_COLUMN = {
    alias: column for column, aliases in COLUMN_ALIASES.items() for alias in (_norm(column), *aliases)
}
STRING_LIMITS = {
    column.name: column.type.length
    for column in Building.__table__.columns
    if getattr(column.type, "length", None)
}


def _clean(value: Any) -> Any:
    """NaN/empty -> None, numpy scalars -> Python values."""
    if value is None:
        return None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == "" or value.lower() in ("null", "none", "nan"):
            return None
    if not isinstance(value, (str, int, float, bool, dict, list)):
        value = str(value)
    return value


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


def _read_file(upload: UploadFile) -> gpd.GeoDataFrame:
    """Read GeoJSON or zipped Shapefile into a GeoDataFrame in EPSG:4326."""
    if not upload.filename:
        raise HTTPException(status_code=400, detail="File must have a filename")
    ext = Path(upload.filename).suffix.lower()
    content = upload.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")

    try:
        if ext in (".geojson", ".json"):
            gdf = gpd.read_file(io.BytesIO(content))
        elif ext == ".zip":
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    zf.extractall(tmp)
                shp_files = sorted(Path(tmp).rglob("*.shp"))
                if not shp_files:
                    raise HTTPException(status_code=400, detail="No .shp file found in the zip")
                if len(shp_files) > 1:
                    names = ", ".join(p.name for p in shp_files)
                    raise HTTPException(
                        status_code=400,
                        detail=f"The zip contains more than one shapefile ({names}). Upload one at a time.",
                    )
                gdf = gpd.read_file(shp_files[0])
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Supported: .geojson, .json, .zip (Shapefile)",
            )
    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip file")
    except Exception as exc:  # noqa: BLE001 - report any reader error to the user
        raise HTTPException(status_code=400, detail=f"Could not read the file: {exc}")

    if gdf.empty:
        raise HTTPException(status_code=400, detail="The file contains no features")

    # GeoJSON without a crs member is WGS84 by definition; a shapefile without .prj is ambiguous.
    if gdf.crs is None:
        if ext == ".zip":
            raise HTTPException(
                status_code=400,
                detail="The shapefile has no .prj (coordinate system). Add it to the zip and upload again.",
            )
        gdf = gdf.set_crs(4326)
    elif gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    return gdf


def _to_multipolygon(geom) -> Tuple[Optional[MultiPolygon], Optional[str]]:
    """Valid 2D MultiPolygon, or (None, reason)."""
    if geom is None or geom.is_empty:
        return None, "empty geometry"
    geom = shapely.force_2d(geom)
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts: List[Polygon] = []
    for part in getattr(geom, "geoms", [geom]):
        if isinstance(part, Polygon) and not part.is_empty:
            parts.append(part)
        elif isinstance(part, MultiPolygon):
            parts.extend(p for p in part.geoms if not p.is_empty)
    if not parts:
        return None, f"not a polygon ({geom.geom_type})"
    return MultiPolygon(parts), None


def _split_attributes(props: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """File attributes -> (Building column values, attr_data, warnings)."""
    columns: Dict[str, Any] = {}
    attr_data: Dict[str, Any] = {}
    warnings: List[str] = []

    for key, raw in props.items():
        if key in IGNORED_KEYS:
            continue
        value = _clean(raw)
        if value is None:
            continue
        if key == "attr_data" and isinstance(value, dict):
            attr_data.update({k: v for k, v in value.items() if _clean(v) is not None})
            continue

        norm = _norm(key)
        column = ALIAS_TO_COLUMN.get(norm)
        if column is None or column in columns:
            attr_data[ATTR_RENAMES.get(norm, key)] = value
            continue

        if column in INT_COLUMNS:
            converted = _to_int(value)
        elif column in FLOAT_COLUMNS:
            converted = _to_float(value)
        else:
            converted = str(value)
            if column == "roof_type":
                converted = converted.lower()
            limit = STRING_LIMITS.get(column)
            if limit and len(converted) > limit:
                warnings.append(f"{key} longer than {limit} characters; kept in attr_data only")
                attr_data[key] = value
                continue

        if converted is None:
            warnings.append(f"{key}={value!r} is not a number; kept in attr_data only")
            attr_data[key] = value
            continue
        columns[column] = converted

    return columns, attr_data, warnings


def _ward_lookup(db: Session):
    wards = [
        (row.ward_no, prep(to_shape(row.geom)))
        for row in db.query(PalikaWardGeometry.ward_no, PalikaWardGeometry.geom)
        .filter(PalikaWardGeometry.geom.isnot(None), PalikaWardGeometry.ward_no.isnot(None))
        .all()
    ]

    def find(point) -> Optional[int]:
        for ward_no, prepared in wards:
            if prepared.intersects(point):
                return int(ward_no)
        return None

    return find, len(wards)


def _existing_centroids(db: Session, bounds: Tuple[float, float, float, float]) -> Dict[Tuple[float, float], int]:
    """Centroids of stored buildings inside the upload's extent -> Building.id."""
    min_x, min_y, max_x, max_y = bounds
    pad = 0.0005
    envelope = func.ST_MakeEnvelope(min_x - pad, min_y - pad, max_x + pad, max_y + pad, 4326)
    rows = (
        db.query(Building.id, func.ST_X(Building.centroid), func.ST_Y(Building.centroid))
        .filter(Building.centroid.isnot(None))
        .filter(func.ST_Intersects(Building.centroid, envelope))
        .all()
    )
    return {
        (round(x, CENTROID_DECIMALS), round(y, CENTROID_DECIMALS)): building_pk
        for building_pk, x, y in rows
        if x is not None and y is not None
    }


def upload_buildings_file(
    db: Session,
    upload: UploadFile,
    user_id: Optional[int],
    ward_no: Optional[int] = None,
    update_existing: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    gdf = _read_file(upload)
    total = len(gdf)

    # Plinth area in m², computed from the footprint (more reliable than file columns
    # such as Shape_Area, which depend on the file's coordinate system).
    areas_m2 = gdf.geometry.to_crs(AREA_CRS).area

    find_ward, ward_polygons = _ward_lookup(db)
    existing = _existing_centroids(db, tuple(float(v) for v in gdf.total_bounds))
    existing_by_building_id = {
        row.building_id: row.id
        for row in db.query(Building.building_id, Building.id).filter(Building.building_id.isnot(None))
    }
    next_building_id = (db.query(func.max(Building.building_id)).scalar() or 0) + 1
    first_new_id = next_building_id

    inserted = updated = skipped_existing = skipped_in_file = 0
    invalid: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    ward_counts: Dict[str, int] = {}
    seen_in_file: set = set()
    attribute_columns_used: set = set()

    for row_no, (geom, area_m2, props) in enumerate(
        zip(gdf.geometry, areas_m2, gdf.drop(columns=gdf.geometry.name).to_dict("records")),
        start=1,
    ):
        multipolygon, reason = _to_multipolygon(geom)
        if multipolygon is None:
            invalid.append({"row": row_no, "reason": reason})
            continue

        columns, attr_data, row_warnings = _split_attributes(props)
        attribute_columns_used.update(columns)
        if row_warnings:
            warnings.append({"row": row_no, "warnings": row_warnings})

        centroid = multipolygon.centroid
        key = (round(centroid.x, CENTROID_DECIMALS), round(centroid.y, CENTROID_DECIMALS))
        if key in seen_in_file:
            skipped_in_file += 1
            continue
        seen_in_file.add(key)

        # Which stored building is this, if any: same building_id from the file, else same position.
        file_building_id = columns.pop("building_id", None)
        match_pk = existing_by_building_id.get(file_building_id) if file_building_id else None
        if match_pk is None:
            match_pk = existing.get(key)
        if match_pk == -1:  # another row of this same file already claimed it
            skipped_in_file += 1
            continue
        if match_pk is not None and not update_existing:
            skipped_existing += 1
            continue

        if ward_no is not None:
            columns["ward_no"] = ward_no
        elif columns.get("ward_no") is None:
            inferred = find_ward(centroid)
            if inferred is not None:
                columns["ward_no"] = inferred
        if columns.get("plinth_area") is None and area_m2 and not math.isnan(area_m2):
            columns["plinth_area"] = round(float(area_m2), 2)

        min_x, min_y, max_x, max_y = multipolygon.bounds
        computed = {
            "centroid": WKTElement(centroid.wkt, srid=4326),
            "bbox": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
            "lat_field": str(centroid.y),
            "long_field": str(centroid.x),
            "plus_code": encode_plus_code(centroid.y, centroid.x),
        }
        geom_wkt = WKTElement(multipolygon.wkt, srid=4326)
        ward_key = str(columns.get("ward_no")) if columns.get("ward_no") is not None else "unknown"
        ward_counts[ward_key] = ward_counts.get(ward_key, 0) + 1

        if match_pk is not None:
            building = db.get(Building, match_pk)
            for field, value in {**columns, **computed}.items():
                setattr(building, field, value)
            if attr_data:
                building.attr_data = {**(building.attr_data or {}), **attr_data}
            if building.geometry is None:
                building.geometry = BuildingGeometry(geom=geom_wkt, created_by=user_id)
            else:
                building.geometry.geom = geom_wkt
                building.geometry.updated_by = user_id
            updated += 1
            continue

        building = Building(
            building_id=file_building_id
            if file_building_id and file_building_id not in existing_by_building_id
            else next_building_id,
            **columns,
            **computed,
            attr_data=attr_data or None,
        )
        if building.building_id == next_building_id:
            next_building_id += 1
        existing_by_building_id[building.building_id] = -1  # reserve this number
        building.geometry = BuildingGeometry(geom=geom_wkt, created_by=user_id)
        db.add(building)
        existing[key] = -1
        inserted += 1

    summary = {
        "file": upload.filename,
        "dry_run": dry_run,
        "total_features": total,
        "inserted": inserted,
        "updated": updated,
        "skipped_already_in_database": skipped_existing,
        "skipped_duplicate_in_file": skipped_in_file,
        "skipped_invalid_geometry": len(invalid),
        "new_building_ids": [first_new_id, next_building_id - 1] if next_building_id > first_new_id else None,
        "buildings_per_ward": dict(sorted(ward_counts.items(), key=lambda kv: (kv[0] == "unknown", kv[0].zfill(4)))),
        "ward_polygons_available": ward_polygons,
        "columns_filled_from_file": sorted(attribute_columns_used - {"building_id"}),
        "invalid_rows": invalid[:MAX_REPORTED_PROBLEMS],
        "warnings": warnings[:MAX_REPORTED_PROBLEMS],
    }

    if dry_run:
        db.rollback()
        return summary
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Saving failed, nothing was written: {exc}")
    return summary