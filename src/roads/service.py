from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.enums.roads import RoadCategory, RoadClass, RoadLane, RoadType
from src.models import Road

from .schema import RoadCreate, RoadUpdate


def create_road(db: Session, road_data: RoadCreate) -> Road:
    db_road = Road(**road_data.model_dump(exclude_unset=True))
    db.add(db_road)
    db.commit()
    db.refresh(db_road)
    return db_road


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