import json
import random
import math
from sqlalchemy.orm import Session
from src import database
from shapely.geometry import shape
from geoalchemy2 import WKTElement
from src.models import Building, BuildingGeometry
from src.users import models as user_models

BUILDING_USES = ["residential", "commercial", "government", "private", "other"]
DIRECTIONS = ["north", "south", "east", "west"]
NEPALI_LOCATIONS = [
    "Baneshwor", "Koteshwor", "Kalanki", "Chabahil",
    "Gwarko", "Satdobato", "Pulchowk", "Maharajgunj",
    "Thapathali", "Tripureshwor", "Bhatbhateni", "Kumaripati",
    "Patan", "Bhaktapur", "Lalitpur", "Kirtipur",
    "Durbarmarg", "New Road", "Thamel", "Pashupatinath",
    "Boudhanath", "Swayambhunath", "Patan Durbar Square", "Bhaktapur Durbar Square",
    "Lalitpur Durbar Square", "Kirtipur Durbar Square", "Durbarmarg", "New Road", "Thamel", "Pashupatinath", "Boudhanath", "Swayambhunath", 
    "Patan Durbar Square", "Bhaktapur Durbar Square", "Lalitpur Durbar Square", "Kirtipur Durbar Square",
]
OWNER_NAMES = [
    "Ram Bahadur", "Sita Devi", "Hari Prasad",
    "Gita Kumari", "Shyam Lal", "Nabin Shrestha", "Anita Thapa", "Ramesh Karki",
    "Sushma Rai", "Bishnu Adhikari", "Kiran Shrestha", "Maya Gurung",
    "Prakash Thapa", "Sunita Lama", "Dipak Shrestha", "Laxmi Devi",
    "Raju Thapa", "Sita Shrestha", "Hari Bahadur", "Gita Thapa", "Shyam Kumar", "Anita Shrestha", "Ramesh Lama",
    "Sushma Adhikari", "Bishnu Shrestha", "Kiran Thapa", "Maya Shrestha", "Prakash Lama", "Sunita Shrestha", "Dipak Thapa", "Laxmi Shrestha",
]
REG_TYPES = ["registered", "unregistered"]
BUILDING_STRUCTURES = ["RCC", "brick", "mud", "wood", "upvc", "concrete"]
ASSOCIATION_TYPES = ["main", "associate", "dissociate"]
YES_NO = ["yes", "no"]
OWNER_STATUS = ["private", "government", "non-government", "residential"]

def clean_nan(value):
    """Replace NaN values with None for JSON compatibility."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: clean_nan(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean_nan(v) for v in value]
    return value


# Load GeoJSON
with open("building14.geojson") as f:
    data = json.load(f)

# DB session
db: Session = database.SessionLocal()

features = data["features"]
incoming_building_ids = list(range(1, len(features) + 1))

# Preload existing buildings once to avoid one query per feature.
existing_buildings = (
    db.query(Building.id, Building.building_id)
    .filter(Building.building_id.in_(incoming_building_ids))
    .all()
)
existing_building_map = {row.building_id: row.id for row in existing_buildings}

existing_geometry_building_fk_ids = set()
if existing_building_map:
    existing_geometry_building_fk_ids = {
        row[0]
        for row in db.query(BuildingGeometry.building_id)
        .filter(BuildingGeometry.building_id.in_(existing_building_map.values()))
        .all()
    }

for building_counter, feature in enumerate(features, start=1):
    geom = feature["geometry"]
    props = feature["properties"]

    geom_shape = shape(geom)

    # ---- Centroid & Bbox ----
    if geom_shape.is_empty:
        geom_wkt = None
        centroid_wkt = None
        lat = None
        lon = None
        bbox = None
    else:
        geom_wkt = WKTElement(geom_shape.wkt, srid=4326)
        centroid = geom_shape.centroid
        centroid_wkt = WKTElement(centroid.wkt, srid=4326)
        lat = centroid.y
        lon = centroid.x
        min_x, min_y, max_x, max_y = geom_shape.bounds
        bbox = clean_nan({
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
        })

    # ---- Create Building ----
    building = Building(
        building_id=building_counter,
        roof_type=props.get("Roof_Type"),
        plinth_area=props.get("Shape_Area"),

        centroid=centroid_wkt,
        bbox=bbox,                       

        lat_field=str(lat) if lat is not None else None, 
        long_field=str(lon) if lon is not None else None, 

        ward_no=14,

        building_use=random.choice(BUILDING_USES),
        building_sp_use=random.choice(BUILDING_USES),
        direction=random.choice(DIRECTIONS),
        metric_address=random.choice(NEPALI_LOCATIONS),
        owner_name=random.choice(OWNER_NAMES),
        reg_type=random.choice(REG_TYPES),
        building_structure=random.choice(BUILDING_STRUCTURES),
        association_type=random.choice(ASSOCIATION_TYPES),
        temporary_type=random.choice(YES_NO),
        owner_status=random.choice(OWNER_STATUS),
    )

    existing_building_pk = existing_building_map.get(building_counter)
    if existing_building_pk:
        if existing_building_pk in existing_geometry_building_fk_ids:
            print(
                f"Building with building_id={building_counter} already has geometry, skipping."
            )
            continue

        db.add(
            BuildingGeometry(
                building_id=existing_building_pk,
                geom=geom_wkt,
            )
        )
        existing_geometry_building_fk_ids.add(existing_building_pk)
        continue

    building.geometry = BuildingGeometry(geom=geom_wkt)
    db.add(building)

db.commit()
db.close()

print("GeoJSON data inserted successfully")