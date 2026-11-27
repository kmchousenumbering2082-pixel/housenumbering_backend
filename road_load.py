import json
import math
import random
import logging
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, MultiLineString

from src import database
from src.models import Road, RoadGeometry
from src.enums.roads import RoadCategory, RoadClass, RoadLane, RoadType, RoadDirection
from src.users.models import User
from pyproj import Transformer
from shapely.ops import transform

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

transformer = Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)


def parse_geometry(geom_dict):
    """Parse GeoJSON geometry. Skip transformation if already in WGS84."""
    geom_type = geom_dict.get("type", "").upper()
    coords = geom_dict.get("coordinates", [])

    if geom_type == "LINESTRING":
        lines = [[(x, y) for x, y, *_ in coords]]
    elif geom_type == "MULTILINESTRING":
        lines = [[(x, y) for x, y, *_ in line] for line in coords]
    else:
        logger.warning(f"Unsupported geometry type: {geom_type}")
        return None

    valid_lines = [LineString(l) for l in lines if len(l) >= 2]
    if not valid_lines:
        return None

    # Check if coordinates are already in WGS84 (not UTM)
    # WGS84: lon -180 to 180, lat -90 to 90
    # UTM: much larger values (e.g., 82,000+ for UTM zone 45)
    first_coord = valid_lines[0].coords[0]
    if abs(first_coord[0]) <= 180 and abs(first_coord[1]) <= 90:
        # Already in WGS84, no transformation needed
        return MultiLineString(valid_lines)

    # Transform from UTM to WGS84
    raw = MultiLineString(valid_lines)
    return transform(transformer.transform, raw)


def clean_nan(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_nan(v) for v in value]
    return value


def get_prop(props, *keys):
    for key in keys:
        if key in props:
            return props[key]
    return None


def parse_ward_no(ward_value):
    """Parse ward_no from properties and return as list of numbers.

    Handles formats like:
    - "16.0" -> [16]
    - "3.0,4.0,7.0" -> [3, 4, 7]
    - 16.0 -> [16]
    - None -> []
    """
    if ward_value is None:
        return []

    ward_str = str(ward_value).strip()
    if not ward_str:
        return []

    # Split by comma if multiple wards
    ward_parts = [w.strip() for w in ward_str.split(",")]
    wards = []

    for part in ward_parts:
        try:
            # Convert to float first (handles "16.0"), then to int
            ward_num = int(float(part))
            if ward_num > 0:  # Only add positive ward numbers
                wards.append(ward_num)
        except (ValueError, TypeError):
            logger.warning(f"Invalid ward number: {part}")
            continue

    return wards if wards else []


def get_enum_value(value, enum_cls):
    if value:
        normalized = str(value).strip().lower()
        for item in enum_cls:
            if normalized in (item.value.lower(), item.name.lower()):
                return item.value
    return random.choice([item.value for item in enum_cls])


with open("new_road.geojson", encoding="utf-8") as f:
    data = json.load(f)

db: Session = database.SessionLocal()
imported = skipped = created = 0

logger.info(f"Processing {len(data['features'])} features...")

try:
    for feature in data["features"]:
        props = feature.get("properties", {})

        # Get fid as primary identifier
        fid = get_prop(props, "fid", "FID", "id", "ID")
        if not fid:
            logger.warning("Missing fid/ID, skipping.")
            skipped += 1
            continue

        # Get unique_id if available (ROAD_CODE preferred)
        unique_id = get_prop(props, "ROAD_CODE", "Unique_ID", "unique_id", "UNIQUE_ID")
        unique_id = str(unique_id).strip() if unique_id else None

        # Get road_id from properties
        road_id_value = get_prop(props, "road_id", "ROAD_ID", "ROAD_ID_2")
        road_id_value = clean_nan(road_id_value) if road_id_value else None

        # Parse full geometry
        geom_shape = parse_geometry(feature["geometry"])
        if not geom_shape or geom_shape.is_empty:
            logger.warning(f"Invalid geometry for fid={fid}, skipping.")
            skipped += 1
            continue

        centroid = geom_shape.centroid

        # Create a NEW Road for each feature (don't reuse)
        road = Road(
            unique_id=unique_id,  # Can be None
            road_id=road_id_value,
            road_name_en=get_prop(props, "kvmp_nam"),
            road_name_ne=get_prop(props, "nepali_nam"),
            road_width=clean_nan(get_prop(props, "road_width")),
            road_class=get_enum_value(
                get_prop(props, "road_class", "road_clas"), RoadClass
            ),
            road_type=get_enum_value(
                get_prop(props, "road_type", "road_typ"), RoadType
            ),
            road_lane=get_enum_value(
                get_prop(props, "road_lane", "roadlane"), RoadLane
            ),
            road_category=get_enum_value(
                get_prop(props, "road_category", "road_categ"), RoadCategory
            ),
            direction=get_enum_value(get_prop(props, "direction"), RoadDirection),
            ward_no=parse_ward_no(get_prop(props, "ward_no")),
            lat_field=str(centroid.y),
            long_field=str(centroid.x),
            attr_data=clean_nan(props),
        )
        db.add(road)
        db.flush()
        created += 1
        logger.info(f"Created road: fid={fid}")

        # Store geometry for this road
        db.add(
            RoadGeometry(
                road_id=road.id,
                geom=from_shape(geom_shape, srid=4326),
            )
        )
        imported += 1
        logger.info(f"Imported geometry for fid={fid}")

    db.commit()
    logger.info(
        f"\n Done — imported: {imported}, created: {created}, skipped: {skipped}"
    )

except Exception as e:
    db.rollback()
    logger.error(f"Fatal error: {e}")
    raise
finally:
    db.close()
