import json
import random
import math
from sqlalchemy.orm import Session
from src import database
from shapely.geometry import shape
from shapely.prepared import prep
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from src.models import Building, BuildingGeometry
from src.palika_profile.models import PalikaWardGeometry
from src.users import models as user_models

BUILDING_USES = ["residential", "commercial", "government", "private", "other"]
DIRECTIONS = ["north", "south", "east", "west"]
NEPALI_LOCATIONS = [
    "Baneshwor",
    "Koteshwor",
    "Kalanki",
    "Chabahil",
    "Gwarko",
    "Satdobato",
    "Pulchowk",
    "Maharajgunj",
    "Thapathali",
    "Tripureshwor",
    "Bhatbhateni",
    "Kumaripati",
    "Patan",
    "Bhaktapur",
    "Lalitpur",
    "Kirtipur",
    "Durbarmarg",
    "New Road",
    "Thamel",
    "Pashupatinath",
    "Boudhanath",
    "Swayambhunath",
    "Patan Durbar Square",
    "Bhaktapur Durbar Square",
    "Lalitpur Durbar Square",
    "Kirtipur Durbar Square",
    "Durbarmarg",
    "New Road",
    "Thamel",
    "Pashupatinath",
    "Boudhanath",
    "Swayambhunath",
    "Patan Durbar Square",
    "Bhaktapur Durbar Square",
    "Lalitpur Durbar Square",
    "Kirtipur Durbar Square",
]
OWNER_NAMES = [
    "Ram Bahadur",
    "Sita Devi",
    "Hari Prasad",
    "Gita Kumari",
    "Shyam Lal",
    "Nabin Shrestha",
    "Anita Thapa",
    "Ramesh Karki",
    "Sushma Rai",
    "Bishnu Adhikari",
    "Kiran Shrestha",
    "Maya Gurung",
    "Prakash Thapa",
    "Sunita Lama",
    "Dipak Shrestha",
    "Laxmi Devi",
    "Raju Thapa",
    "Sita Shrestha",
    "Hari Bahadur",
    "Gita Thapa",
    "Shyam Kumar",
    "Anita Shrestha",
    "Ramesh Lama",
    "Sushma Adhikari",
    "Bishnu Shrestha",
    "Kiran Thapa",
    "Maya Shrestha",
    "Prakash Lama",
    "Sunita Shrestha",
    "Dipak Thapa",
    "Laxmi Shrestha",
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


def strip_z_coordinate(geom_dict):
    """Remove Z dimension from geometry (convert 3D to 2D)."""
    if geom_dict["type"] == "MultiPolygon":
        # MultiPolygon: [ [ [ [lon, lat, z], ... ] ] ]
        new_coords = []
        for polygon in geom_dict["coordinates"]:
            new_polygon = []
            for ring in polygon:
                new_ring = [
                    [coord[0], coord[1]] for coord in ring
                ]  # Keep only lon, lat
                new_polygon.append(new_ring)
            new_coords.append(new_polygon)
        return {"type": "MultiPolygon", "coordinates": new_coords}
    elif geom_dict["type"] == "Polygon":
        # Polygon: [ [ [lon, lat, z], ... ] ]
        new_coords = []
        for ring in geom_dict["coordinates"]:
            new_ring = [[coord[0], coord[1]] for coord in ring]
            new_coords.append(new_ring)
        return {"type": "Polygon", "coordinates": new_coords}
    return geom_dict


def parse_ward_no(value):
    """Convert a ward value from GeoJSON into an integer ward number."""
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "null":
        return None

    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def infer_ward_no_from_geometry(geom_shape, ward_geometries):
    """Infer a ward number from a building geometry using ward boundary polygons."""
    if geom_shape.is_empty:
        return None

    probe_point = geom_shape.centroid
    for ward_no, prepared_geom in ward_geometries:
        if prepared_geom.contains(probe_point) or prepared_geom.intersects(probe_point):
            return ward_no
    return None


# Load GeoJSON
with open("final_buildings.geojson", encoding="utf-8") as f:
    data = json.load(f)

# DB session
db: Session = database.SessionLocal()

ward_geometries = [
    (row.ward_no, prep(to_shape(row.geom)))
    for row in db.query(PalikaWardGeometry.ward_no, PalikaWardGeometry.geom)
    .filter(PalikaWardGeometry.geom.isnot(None))
    .filter(PalikaWardGeometry.ward_no.isnot(None))
    .all()
]

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

    # Strip Z coordinate (convert 3D geometry to 2D)
    geom = strip_z_coordinate(geom)

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
        bbox = clean_nan(
            {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
            }
        )

    # ---- Extract ward_no (try multiple field names) ----
    ward_no_value = None
    for ward_key in ("Ward_No", "ward_no", "ward_no_2"):
        ward_no_value = parse_ward_no(props.get(ward_key))
        if ward_no_value is not None:
            break

    if ward_no_value is None:
        ward_no_value = infer_ward_no_from_geometry(geom_shape, ward_geometries)

    # ---- Extract house_no from Final_Hous ----
    house_no_value = props.get("Final_Hous")

    # ---- Extract other fields from GeoJSON ----
    roof_type_value = props.get("Roof_Type") or props.get("Rooftype")
    plinth_area_value = props.get("Shape_Area") or props.get("Area")
    # NOTE: Road_ID is a road CODE (like "R-27-KMC-C-555"), not a database integer ID
    # Store it in metadata instead of trying to set the road_id FK
    road_code_value = props.get("Road_ID")
    direction_value = props.get("Side")

    # Store additional metadata in attr_data JSON
    attr_data_dict = {
        "perimeter": props.get("Perimeter"),
        "area": props.get("Area"),
        "build_type": props.get("Build_Type"),
        "build_type_2": props.get("build_type_2"),
        "gid": props.get("gid"),
        "gid_2": props.get("gid_2"),
        "id_2": props.get("id_2"),
        "roof_type_2": props.get("roof_type_2"),
        "perimeter_2": props.get("perimeter_2"),
        "area_2": props.get("area_2"),
        "road_id_code": road_code_value,  # Store road code as metadata
        "scienti_na": props.get("scienti_na"),
        "recommend": props.get("recommend"),
        "unique_id": props.get("Unique_ID"),
        "layer": props.get("layer"),
    }
    # Remove None values
    attr_data_dict = {k: v for k, v in attr_data_dict.items() if v is not None}

    # ---- Create Building ----
    building = Building(
        building_id=building_counter,
        roof_type=roof_type_value,
        plinth_area=plinth_area_value,
        centroid=centroid_wkt,
        bbox=bbox,
        lat_field=str(lat) if lat is not None else None,
        long_field=str(lon) if lon is not None else None,
        ward_no=ward_no_value,
        house_no=house_no_value,
        direction=direction_value,
        # Note: road_id is NOT set here because Road_ID in GeoJSON is a code, not a DB ID
        # The road code is stored in attr_data for later lookup
        attr_data=attr_data_dict if attr_data_dict else None,
        building_use=random.choice(BUILDING_USES),
        building_sp_use=random.choice(BUILDING_USES),
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
        # Update existing building with new data
        existing_building = (
            db.query(Building).filter(Building.id == existing_building_pk).first()
        )
        if existing_building:
            # Update building fields with data from GeoJSON
            existing_building.roof_type = roof_type_value
            existing_building.plinth_area = plinth_area_value
            existing_building.centroid = centroid_wkt
            existing_building.bbox = bbox
            existing_building.lat_field = str(lat) if lat is not None else None
            existing_building.long_field = str(lon) if lon is not None else None
            if ward_no_value is not None:
                existing_building.ward_no = ward_no_value
            existing_building.house_no = house_no_value
            existing_building.direction = direction_value
            if attr_data_dict:
                existing_building.attr_data = attr_data_dict

        if existing_building_pk in existing_geometry_building_fk_ids:
            print(
                f"Building with building_id={building_counter} already has geometry, updated attributes only."
            )
            db.add(existing_building)
            continue

        db.add(
            BuildingGeometry(
                building_id=existing_building_pk,
                geom=geom_wkt,
            )
        )
        db.add(existing_building)
        existing_geometry_building_fk_ids.add(existing_building_pk)
        continue

    building.geometry = BuildingGeometry(geom=geom_wkt)
    db.add(building)

db.commit()
db.close()

print("GeoJSON data inserted successfully")
