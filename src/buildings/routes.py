from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user
from src.database import get_db
from src.enums.buildings import RoofType
from src.pagination import Pagination

from src.buildings.schema import (
    BuildingCreate,
    BuildingPublicPageResponse,
    BuildingResponse,
)
from src.buildings.service import (
    assign_roads_to_all_buildings,
    bulk_update_building_plus_codes,
    count_buildings,
    create_building,
    delete_building,
    get_building,
    list_buildings,
    list_public_buildings,
    update_building,
    update_building_plus_code,
    upload_buildings_file,
)

router = APIRouter(prefix="/api/v1/building", tags=["buildings"])


@router.post("/", response_model=BuildingResponse)
def create_building_route(
    building: BuildingCreate,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_building(db=db, building_data=building)


@router.get("/count", response_model=dict)
def get_buildings_count_route(
    ward_no: Optional[int] = Query(default=None),
    min_floor: Optional[float] = Query(default=None, ge=0),
    roof_type: Optional[RoofType] = Query(default=None),
    db: Session = Depends(get_db),
):
    count = count_buildings(
        db=db,
        ward_no=ward_no,
        min_floor=min_floor,
        roof_type=roof_type,
    )
    return {"count": count}


@router.get("/", response_model=List[BuildingResponse])
def list_buildings_route(
    pagination: Pagination = Depends(),
    ward_no: Optional[int] = Query(default=None),
    min_floor: Optional[float] = Query(default=None, ge=0),
    roof_type: Optional[RoofType] = Query(default=None),
    search: Optional[str] = Query(
        default=None,
        description="Search by house number, road name, owner name, plus code, or 'house_no-other_info'",
    ),
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
        search=search,
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


@router.post("/plus_code/bulk/")
def bulk_update_building_plus_code_route(
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return bulk_update_building_plus_codes(db=db)


@router.post("/plus_code/{building_id}", response_model=BuildingResponse)
def update_building_plus_code_route(
    building_id: int,
    _=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_building_plus_code(db=db, building_id=building_id)


@router.post("/assign_road")
def assign_building_roads(
    distance_limit: int = 100,
    db: Session = Depends(get_db),
):
    return assign_roads_to_all_buildings(
        db=db,
        distance_limit=distance_limit,
    )


def _form_bool(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


@router.post("/upload", status_code=201)
def upload_buildings_route(
    file: UploadFile = File(
        ..., description="Building footprints: GeoJSON (.geojson/.json) or zipped Shapefile (.zip)"
    ),
    ward_no: Optional[int] = Form(
        None,
        description="Set this ward number on every building. Leave empty to read it from the file "
        "(Ward_No / ward_no) or, if missing, from the ward boundaries.",
    ),
    update_existing: str = Form(
        "false",
        description="true = buildings already in the database (same position or building_id) are updated "
        "with the file's values. false = they are skipped.",
    ),
    dry_run: str = Form(
        "false",
        description="true = only check the file and report what would happen; nothing is saved.",
    ),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload building footprints (replaces the `building_load.py` script).

    - Any coordinate system is accepted; it is converted to EPSG:4326.
    - Columns are matched by name (e.g. `Ward_No`, `Final_Hous`/`house_no`, `Roof_Type`,
      `Side`/`direction`, `Build_Type`/`building_use`, `tole_name`, `floor`);
      every other column is kept in `attr_data`.
    - New buildings get `building_id` numbers after the highest existing one.
    - Buildings already in the database are skipped (or updated with `update_existing=true`),
      so uploading the same file twice does not create duplicates.
    - Plinth area (m²), centroid, bbox and plus code are calculated from the footprint.
    - All or nothing: if saving fails, nothing is written.

    Tip: run once with `dry_run=true` to see the report before saving.
    """
    return upload_buildings_file(
        db=db,
        upload=file,
        user_id=current_user.id,
        ward_no=ward_no,
        update_existing=_form_bool(update_existing),
        dry_run=_form_bool(dry_run),
    )


@router.post("/upload/", status_code=201, include_in_schema=False)
def upload_buildings_route_with_slash(
    file: UploadFile = File(...),
    ward_no: Optional[int] = Form(None),
    update_existing: str = Form("false"),
    dry_run: str = Form("false"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Same as /upload, with a trailing slash."""
    return upload_buildings_route(file, ward_no, update_existing, dry_run, current_user, db)


@router.get("/building_data/", response_model=BuildingPublicPageResponse)
def public_building_data_route(
    request: Request,
    is_public: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=1000),
    search: Optional[str] = Query(
        default=None,
        description="Search by house number, road name, owner name, plus code, or house_no-other_info",
    ),
    db: Session = Depends(get_db),
):
    count, results = list_public_buildings(
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