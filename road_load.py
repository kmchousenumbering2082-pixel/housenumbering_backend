import json
import math
import random
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, MultiLineString, shape
from shapely.ops import transform
from sqlalchemy import func
from sqlalchemy.orm import Session

from src import database
from src.models import Road, RoadGeometry
from src.users.models import User
from src.enums.roads import RoadCategory, RoadClass, RoadLane, RoadType, RoadDirection


def clean_nan(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_nan(v) for v in value]
    return value


def remove_z(geom):
    """Strip Z dimension from geometry if present."""
    return transform(lambda x, y, z=None: (x, y), geom)


def get_prop(props: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in props:
            return props[key]
    return None


def normalize_unique_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().replace(" ", "")
    return normalized or None


def get_enum_value_or_random(value: Any, enum_cls) -> str:
    if value is None:
        return random.choice([item.value for item in enum_cls])

    normalized = str(value).strip().lower()
    if not normalized:
        return random.choice([item.value for item in enum_cls])

    for item in enum_cls:
        if normalized in (item.value.lower(), item.name.lower()):
            return item.value

    return random.choice([item.value for item in enum_cls])


with open("road14.geojson", encoding="utf-8") as f:
    data = json.load(f)

db: Session = database.SessionLocal()
counter = 0
skipped = 0
created_roads = 0

for feature in data["features"]:
    geom = feature["geometry"]
    props = feature["properties"]

    geom_shape = remove_z(shape(geom))

    if isinstance(geom_shape, LineString):
        geom_shape = MultiLineString([geom_shape])

    if geom_shape.is_empty:
        print(f"Skipping empty geometry for id={props.get('id')}")
        skipped += 1
        continue

    unique_id = normalize_unique_id(get_prop(props, "Unique_ID", "unique_id", "UNIQUE_ID"))
    if not unique_id:
        print(f"Missing Unique_ID for feature id={props.get('id')}, skipping.")
        skipped += 1
        continue

    road = (
        db.query(Road)
        .filter(func.lower(func.replace(func.trim(Road.unique_id), " ", "")) == unique_id.lower())
        .first()
    )

    centroid = geom_shape.centroid
    lat_value = str(centroid.y)
    lon_value = str(centroid.x)

    lane_value = get_enum_value_or_random(get_prop(props, "road_lane", "roadlane"), RoadLane)
    category_value = get_enum_value_or_random(
        get_prop(props, "road_category", "road_categ", "category"),
        RoadCategory,
    )
    type_value = get_enum_value_or_random(
        get_prop(props, "road_type", "road_typ", "type"), RoadType
    )
    class_value = get_enum_value_or_random(
        get_prop(props, "road_class", "road_clas", "class"), RoadClass
    )
    direction_value = get_enum_value_or_random(
        get_prop(props, "direction"), RoadDirection
    )

    if not road:
        road = Road(
            unique_id=unique_id,
            road_id=get_prop(props, "id", "road_id"),
            road_name_en=get_prop(props, "kvmp_nam"),
            road_name_ne=get_prop(props, "nepali_nam"),
            road_width=clean_nan(get_prop(props, "road_width")),
            road_class=class_value,
            attr_data=clean_nan(props),
            road_type=type_value,
            road_lane=lane_value,
            road_category=category_value,
            direction=direction_value,
            lat_field=lat_value,
            long_field=lon_value,
        )
        db.add(road)
        db.flush()
        created_roads += 1
        print(f"Created missing Road row for unique_id={unique_id}.")
    else:
        # Backfill missing metadata from geometry and enum defaults.
        if not road.road_lane:
            road.road_lane = lane_value
        if not road.road_category:
            road.road_category = category_value
        if not road.lat_field:
            road.lat_field = lat_value
        if not road.long_field:
            road.long_field = lon_value

    existing = db.query(RoadGeometry).filter(RoadGeometry.road_id == road.id).first()
    if existing:
        print(f"Geometry already exists for road.id={road.id}, skipping.")
        skipped += 1
        continue

    road_geometry = RoadGeometry(
        geom=from_shape(geom_shape, srid=4326),
        road_id=road.id,
    )

    db.add(road_geometry)
    counter += 1

db.commit()
db.close()

print(f"\n{counter} geometries inserted successfully")
print(f"{created_roads} missing roads auto-created")
print(f"{skipped} skipped")