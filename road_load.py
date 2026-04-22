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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

transformer = Transformer.from_crs("EPSG:32645", "EPSG:4326", always_xy=True)

def parse_geometry(geom_dict):
    """Parse GeoJSON geometry, reproject from UTM to WGS84."""
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


def get_enum_value(value, enum_cls):
    if value:
        normalized = str(value).strip().lower()
        for item in enum_cls:
            if normalized in (item.value.lower(), item.name.lower()):
                return item.value
    return random.choice([item.value for item in enum_cls])


with open("finalroad.geojson", encoding="utf-8") as f:
    data = json.load(f)

db: Session = database.SessionLocal()
imported = skipped = created = 0

logger.info(f"Processing {len(data['features'])} features...")

try:
    for feature in data["features"]:
        props = feature.get("properties", {})
        raw_id = get_prop(props, "Unique_ID", "unique_id", "UNIQUE_ID")
        unique_id = str(raw_id).strip().replace(" ", "") if raw_id else None

        if not unique_id:
            logger.warning("Missing Unique_ID, skipping.")
            skipped += 1
            continue

        # Parse full geometry
        geom_shape = parse_geometry(feature["geometry"])
        if not geom_shape or geom_shape.is_empty:
            logger.warning(f"Invalid geometry for {unique_id}, skipping.")
            skipped += 1
            continue

        # Find or create Road
        road = db.query(Road).filter(Road.unique_id == unique_id).first()
        centroid = geom_shape.centroid

        if not road:
            road = Road(
                unique_id=unique_id,
                road_id=get_prop(props, "id", "road_id"),
                road_name_en=get_prop(props, "kvmp_nam"),
                road_name_ne=get_prop(props, "nepali_nam"),
                road_width=clean_nan(get_prop(props, "road_width")),
                road_class=get_enum_value(get_prop(props, "road_class", "road_clas"), RoadClass),
                road_type=get_enum_value(get_prop(props, "road_type", "road_typ"), RoadType),
                road_lane=get_enum_value(get_prop(props, "road_lane", "roadlane"), RoadLane),
                road_category=get_enum_value(get_prop(props, "road_category", "road_categ"), RoadCategory),
                direction=get_enum_value(get_prop(props, "direction"), RoadDirection),
                lat_field=str(centroid.y),
                long_field=str(centroid.x),
                attr_data=clean_nan(props),
            )
            db.add(road)
            db.flush()
            created += 1
            logger.info(f"Created road: {unique_id}")

        # Skip if geometry already exists
        if db.query(RoadGeometry).filter(RoadGeometry.road_id == road.id).first():
            logger.info(f"Geometry exists for {unique_id}, skipping.")
            skipped += 1
            continue

        # Store full geometry
        db.add(RoadGeometry(
            road_id=road.id,
            geom=from_shape(geom_shape, srid=4326),
        ))
        imported += 1
        logger.info(f" Imported {unique_id}")

    db.commit()
    logger.info(f"\n Done — imported: {imported}, created: {created}, skipped: {skipped}")

except Exception as e:
    db.rollback()
    logger.error(f"Fatal error: {e}")
    raise
finally:
    db.close()