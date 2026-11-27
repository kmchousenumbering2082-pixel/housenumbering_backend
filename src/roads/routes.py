from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.enums.roads import RoadCategory, RoadClass, RoadLane, RoadType
from src.pagination import Pagination

from src.roads.schema import (
    RoadCreate,
    RoadPublicPageResponse,
    RoadResponse,
    RoadUpdate,
)
from src.roads.service import (
    count_roads,
    create_road,
    delete_road,
    get_road,
    list_roads,
    list_public_roads,
    update_road,
)

router = APIRouter(prefix="/api/v1/road", tags=["roads"])


@router.post("/", response_model=RoadResponse)
def create_road_route(
    road: RoadCreate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_road(db=db, road_data=road)


@router.get("/count", response_model=dict)
def get_roads_count_route(
    road_type: Optional[RoadType] = Query(default=None),
    road_category: Optional[RoadCategory] = Query(default=None),
    road_class: Optional[RoadClass] = Query(default=None),
    road_lane: Optional[RoadLane] = Query(default=None),
    ward_no: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    # Parse comma-separated ward numbers
    ward_nos = None
    if ward_no:
        ward_nos = [int(w.strip()) for w in ward_no.split(",") if w.strip()]

    count = count_roads(
        db=db,
        road_type=road_type,
        road_category=road_category,
        road_class=road_class,
        road_lane=road_lane,
        ward_nos=ward_nos,
    )
    return {"count": count}


@router.get("/", response_model=List[RoadResponse])
def list_roads_route(
    pagination: Pagination = Depends(),
    road_type: Optional[RoadType] = Query(default=None),
    road_category: Optional[RoadCategory] = Query(default=None),
    road_class: Optional[RoadClass] = Query(default=None),
    road_lane: Optional[RoadLane] = Query(default=None),
    sort_by: str = Query(default="id"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
):
    return list_roads(
        db=db,
        skip=pagination.skip,
        limit=pagination.limit,
        road_type=road_type,
        road_category=road_category,
        road_class=road_class,
        road_lane=road_lane,
        sort_by=sort_by,
        order=order,
    )


@router.get("/{road_id}", response_model=RoadResponse)
def get_road_route(
    road_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_road(db=db, road_id=road_id)


@router.patch("/{road_id}", response_model=RoadResponse)
def update_road_route(
    road_id: int,
    road: RoadUpdate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_road(db=db, road_id=road_id, road_data=road)


@router.put("/{road_id}", response_model=RoadResponse)
def update_road_route(
    road_id: int,
    road: RoadUpdate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_road(db=db, road_id=road_id, road_data=road)


@router.delete("/{road_id}")
def delete_road_route(
    road_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_road(db=db, road_id=road_id)
    return {"detail": "Road deleted"}


@router.get("/road_data/", response_model=RoadPublicPageResponse)
def public_road_data_route(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: Optional[str] = Query(
        default=None,
        description="Search by road name, road type, road category, road class, lane, or road id",
    ),
    db: Session = Depends(get_db),
):
    count, results = list_public_roads(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
    )

    next_url = None
    previous_url = None

    if page * page_size < count:
        next_url = str(
            request.url.include_query_params(page=page + 1, page_size=page_size)
        )
    if page > 1 and count > 0:
        previous_url = str(
            request.url.include_query_params(page=page - 1, page_size=page_size)
        )

    return {
        "count": count,
        "next": next_url,
        "previous": previous_url,
        "results": results,
    }
