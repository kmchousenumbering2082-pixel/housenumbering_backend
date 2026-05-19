from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, text

from src.enums.buildings import RoofType
from src.models import Building, Road

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
