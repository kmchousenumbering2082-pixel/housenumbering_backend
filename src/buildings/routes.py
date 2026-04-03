from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.enums.buildings import RoofType
from src.pagination import Pagination

from src.buildings.schema import BuildingCreate, BuildingResponse
from src.buildings.service import (
    assign_roads_to_all_buildings,
    create_building,
    delete_building,
    get_building,
    list_buildings,
    update_building,
)

router = APIRouter(prefix="/buildings", tags=["buildings"])


@router.post("/", response_model=BuildingResponse)
def create_building_route(
    building: BuildingCreate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_building(db=db, building_data=building)


@router.get("/", response_model=List[BuildingResponse])
def list_buildings_route(
    pagination: Pagination = Depends(),
    ward_no: Optional[int] = Query(default=None),
    min_floor: Optional[float] = Query(default=None, ge=0),
    roof_type: Optional[RoofType] = Query(default=None),
    sort_by: str = Query(default="building_id"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    return list_buildings(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        ward_no=ward_no,
        min_floor=min_floor,
        roof_type=roof_type,
        sort_by=sort_by,
        order=order,
    )


@router.patch("/{building_id}", response_model=BuildingResponse)
def partial_update_building_route(
    building_id: int,
    building: BuildingCreate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_building(db=db, building_id=building_id, building_data=building)


@router.get("/{building_id}", response_model=BuildingResponse)
def get_building_route(
    building_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_building(db=db, building_id=building_id)


@router.put("/{building_id}", response_model=BuildingResponse)
def update_building_route(
    building_id: int,
    building: BuildingCreate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_building(db=db, building_id=building_id, building_data=building)


@router.delete("/{building_id}")
def delete_building_route(
    building_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_building(db=db, building_id=building_id)
    return {"detail": "Building deleted"}


@router.post("/assign-road")
def assign_building_roads(
    distance_limit: int = 100,
    db: Session = Depends(get_db),
):
    return assign_roads_to_all_buildings(
        db=db,
        distance_limit=distance_limit,
    )
