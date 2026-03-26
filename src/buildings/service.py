from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.enums.buildings import RoofType
from src.models import Building

from src.buildings.schema import BuildingCreate


def create_building(db: Session, building_data: BuildingCreate) -> Building:
    db_building = Building(**building_data.model_dump(exclude_unset=True))
    db.add(db_building)
    db.commit()
    db.refresh(db_building)
    return db_building


def list_buildings(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    ward_no: Optional[int] = None,
    min_floor: Optional[float] = None,
    roof_type: Optional[RoofType] = None,
    sort_by: str = "building_id",
    order: str = "asc",
):
    query = db.query(Building)

    if ward_no is not None:
        query = query.filter(Building.ward_no == ward_no)
    if min_floor is not None:
        query = query.filter(Building.floor >= min_floor)
    if roof_type is not None:
        query = query.filter(Building.roof_type == roof_type.value)

    sort_column = getattr(Building, sort_by, Building.building_id)
    query = query.order_by(sort_column.desc() if order == "desc" else sort_column.asc())

    return query.offset(skip).limit(limit).all()


def get_building(db: Session, building_id: int) -> Building:
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")
    return building


def update_building(db: Session, building_id: int, building_data: BuildingCreate) -> Building:
    building = get_building(db=db, building_id=building_id)
    for key, value in building_data.model_dump(exclude_unset=True).items():
        setattr(building, key, value)
    db.commit()
    db.refresh(building)
    return building


def delete_building(db: Session, building_id: int) -> None:
    building = get_building(db=db, building_id=building_id)
    db.delete(building)
    db.commit()