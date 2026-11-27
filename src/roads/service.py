from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import String, cast, or_, text

from src.enums.roads import RoadCategory, RoadClass, RoadLane, RoadType
from src.models import Road

from .schema import RoadCreate, RoadUpdate


def create_road(db: Session, road_data: RoadCreate) -> Road:
    db_road = Road(**road_data.model_dump(exclude_unset=True))
    db.add(db_road)
    db.commit()
    db.refresh(db_road)
    return db_road


def count_roads(
    db: Session,
    road_type: Optional[RoadType] = None,
    road_category: Optional[RoadCategory] = None,
    road_class: Optional[RoadClass] = None,
    road_lane: Optional[RoadLane] = None,
    ward_nos: Optional[List[int]] = None,
) -> int:
    query = db.query(Road)

    if ward_nos is not None and len(ward_nos) > 0:
        # ward_no is stored as JSONB array, check if it contains any of the values
        # Use OR to check if array contains any of the ward numbers
        conditions = [Road.ward_no.op("@>")(f"[{ward}]") for ward in ward_nos]
        query = query.filter(or_(*conditions))
    if road_type is not None:
        query = query.filter(Road.road_type == road_type.value)
    if road_category is not None:
        query = query.filter(Road.road_category == road_category.value)
    if road_class is not None:
        query = query.filter(Road.road_class == road_class.value)
    if road_lane is not None:
        query = query.filter(Road.road_lane == road_lane.value)

    return query.count()


def list_roads(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    road_type: Optional[RoadType] = None,
    road_category: Optional[RoadCategory] = None,
    road_class: Optional[RoadClass] = None,
    road_lane: Optional[RoadLane] = None,
    sort_by: str = "id",
    order: str = "asc",
):
    query = db.query(Road)

    if road_type is not None:
        query = query.filter(Road.road_type == road_type.value)
    if road_category is not None:
        query = query.filter(Road.road_category == road_category.value)
    if road_class is not None:
        query = query.filter(Road.road_class == road_class.value)
    if road_lane is not None:
        query = query.filter(Road.road_lane == road_lane.value)

    sort_column = getattr(Road, sort_by, Road.id)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    return query.offset(skip).limit(limit).all()


def search_roads(query, search: Optional[str]):
    search_query = (search or "").strip()
    if not search_query:
        return query

    return query.filter(
        or_(
            Road.road_name_en.ilike(f"%{search_query}%"),
            Road.road_type.ilike(f"%{search_query}%"),
            Road.road_category.ilike(f"%{search_query}%"),
            Road.road_class.ilike(f"%{search_query}%"),
            Road.road_lane.ilike(f"%{search_query}%"),
            Road.unique_id.ilike(f"%{search_query}%"),
            cast(Road.road_id, String).ilike(f"%{search_query}%"),
        )
    )


def _public_road_item(road: Road) -> dict:
    return {
        "id": road.id,
        "road_id": road.road_id,
        "road_name_en": road.road_name_en,
        "road_type": road.road_type,
        "road_category": road.road_category,
        "road_class": road.road_class,
        "road_lane": road.road_lane,
        "road_width": road.road_width,
        "road_length": road.road_length,
        "direction": road.direction,
        "ward_no": road.ward_no,
        "bbox": road.bbox,
    }


def list_public_roads(
    db: Session,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
):
    query = db.query(Road)
    query = search_roads(query, search)

    total = query.count()
    offset = (page - 1) * page_size
    roads = query.order_by(Road.id.desc()).offset(offset).limit(page_size).all()

    return total, [_public_road_item(road) for road in roads]


def get_road(db: Session, road_id: int) -> Road:
    road = db.query(Road).filter(Road.id == road_id).first()
    if not road:
        raise HTTPException(status_code=404, detail="Road not found")
    return road


def update_road(db: Session, road_id: int, road_data: RoadUpdate) -> Road:
    road = get_road(db=db, road_id=road_id)
    for key, value in road_data.model_dump(exclude_unset=True).items():
        setattr(road, key, value)
    db.commit()
    db.refresh(road)
    return road


def delete_road(db: Session, road_id: int) -> None:
    road = get_road(db=db, road_id=road_id)
    db.delete(road)
    db.commit()
