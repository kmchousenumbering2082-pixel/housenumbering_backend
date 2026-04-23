

import logging
from typing import Optional, Tuple, Set
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, LineString, MultiLineString, base
from shapely.wkt import loads as load_wkt
from shapely.wkb import loads as load_wkb
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, text
from pyproj import Transformer

from src.models import Building, Road, RoadGeometry
from src.palika_profile.models import PalikaWardGeometry, PalikaProfile

# Constants
DISTANCE_EPSILON = 1.0 
MAX_ROAD_SEARCH_DISTANCE = 100  
MAX_DUPLICATE_CHECK_ATTEMPTS = 100  
MAX_RECURSION_DEPTH = 10  
logger = logging.getLogger(__name__)


def get_local_coordinate_system(db: Session) -> int:
    """
    Get the local coordinate system (CRS) from PalikaProfile.

    """
    try:
        palika_profile = db.query(PalikaProfile).first()
        if palika_profile and palika_profile.local_coordinate_system:
            return palika_profile.local_coordinate_system
    except Exception:
        pass
    return 3857


def load_geometry_from_wkt(wkt_string: str) -> Optional[base.BaseGeometry]:
    """
    Load a Shapely geometry object from WKT or WKB string.
    
    Attempts multiple parsing strategies:
    1. Direct WKT parsing
    2. PostGIS SRID format (SRID=xxxx;GEOMETRY(...))
    3. WKB hex format
    4. GeoAlchemy2 object
    
    Args:
        wkt_string: Geometry string in WKT, WKB, or PostGIS format
        
    Returns:
        Shapely geometry object or None if parsing fails
    """
    if not wkt_string:
        logger.debug("Empty WKT string provided")
        return None
    
    wkt_string = str(wkt_string).strip()
    
    # Strategy 1: Try direct WKT parsing
    try:
        return load_wkt(wkt_string)
    except ValueError as e:
        logger.debug(f"WKT parsing failed: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error in WKT parsing: {type(e).__name__}: {e}")
    
    # Strategy 2: Try PostGIS format (SRID=xxxx;GEOMETRY(...))
    try:
        if ';' in wkt_string and wkt_string.upper().startswith('SRID'):
            wkt_clean = wkt_string.split(';', 1)[1].strip()
            return load_wkt(wkt_clean)
    except ValueError as e:
        logger.debug(f"PostGIS format parsing failed: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error in PostGIS parsing: {type(e).__name__}: {e}")
    
    # Strategy 3: Try WKB hex format
    try:
        if all(c in '0123456789abcdefABCDEF' for c in wkt_string):
            return load_wkb(bytes.fromhex(wkt_string))
    except ValueError as e:
        logger.debug(f"WKB hex parsing failed: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error in WKB parsing: {type(e).__name__}: {e}")
    
    # Strategy 4: Try GeoAlchemy2 object
    try:
        if hasattr(wkt_string, 'type'):
            return to_shape(wkt_string)
    except TypeError as e:
        logger.debug(f"GeoAlchemy2 conversion failed: {e}")
    except Exception as e:
        logger.debug(f"Unexpected error in GeoAlchemy2 conversion: {type(e).__name__}: {e}")
    
    logger.warning(f"Failed to parse geometry from string: {wkt_string[:100]}...")
    return None

def get_direction_from_road(
    gate_point: Point,
    road_geometry: LineString | MultiLineString,
) -> str:
    """
    Determine building direction (Left/Right) relative to road using cross-product method.
    
    """
    try:
        # Project point onto road to find closest point
        dist_along = road_geometry.project(gate_point)
        closest_on_road = road_geometry.interpolate(dist_along)
        
        epsilon = min(DISTANCE_EPSILON, road_geometry.length * 0.1)
        dist_before = max(0.0, dist_along - epsilon)
        dist_after = min(road_geometry.length, dist_along + epsilon)
        
        point_before = road_geometry.interpolate(dist_before)
        point_after = road_geometry.interpolate(dist_after)
        
        # Road direction vector (from before to after)
        road_dx = point_after.x - point_before.x
        road_dy = point_after.y - point_before.y
        
        # Building vector (from road point to building)
        building_dx = gate_point.x - closest_on_road.x
        building_dy = gate_point.y - closest_on_road.y
        
        cross_product = (road_dx * building_dy) - (road_dy * building_dx)
        
        direction = "Left" if cross_product >= 0 else "Right"
        logger.debug(f"Direction calculation: cross_product={cross_product:.6f} → {direction}")
        return direction

    except Exception as e:
        logger.error(f"Error in direction calculation: {e}")
        return "Left"  # Fallback to Left on error


def round_distance_for_direction(distance: float, direction: str) -> int:
    """
    Apply direction-specific rounding to distance.

    """
    if direction == "Left":
        return round_distance_left_direction(distance)
    else:
        return round_distance_right_direction(distance)


def round_distance_left_direction(distance: float) -> int:
    """
    Round distance for buildings on the left side of road.
    Left side house numbers should be odd (1, 3, 5, ...).
    
    """
    if distance == 0:
        return distance
    else:
        answer = round(distance)
        if answer % 2:
            return answer
        if abs(answer + 1 - distance) > abs(answer - 1 - distance):
            return answer + 1
        else:
            return answer - 1


def round_distance_right_direction(distance: float) -> int:
    """
    Round distance for buildings on the right side of road.
    Right side house numbers should be even (2, 4, 6, ...).

    """
    if distance == 0:
        return distance
    else:
        answer = round(distance)
        if not answer % 2:
            return answer
        if abs(answer + 1 - distance) < abs(answer - 1 - distance):
            return answer + 1
        else:
            return answer - 1


def house_number_exists(db: Session, house_number: str, road_id: int) -> bool:
    """
    Check if a house number already exists for a road.

    """
    existing = db.query(Building).filter(
        and_(
            Building.house_no == house_number,
            Building.road_id == road_id
        )
    ).first()
    
    if existing:
        logger.warning(f"DUPLICATE_CHECK: house_no='{house_number}' already exists on road {road_id} (building {existing.id})")
    
    return existing is not None


def get_ward_for_point(db: Session, point: Point) -> Optional[int]:
    """
    Get ward number that contains the given point.

    """
    try:
        # Create WKB from point for spatial query
        point_wkb = from_shape(point, srid=4326)
        
        ward = db.query(PalikaWardGeometry).filter(
            PalikaWardGeometry.geom.contains(point_wkb)
        ).first()
        
        if ward:
            return ward.ward_no
    except Exception:
        pass
    
    return None


def find_connected_road_at_start(
    db: Session,
    road: Road,
    start_point: Point,
    max_distance: float = MAX_ROAD_SEARCH_DISTANCE,
    excluded_road_id: Optional[int] = None,
) -> Optional[Road]:
    """
    Find road connected to the start point of another road using spatial query.
    
    """
    try:
        target_crs = get_local_coordinate_system(db)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{target_crs}", always_xy=True)
        start_x_proj, start_y_proj = transformer.transform(start_point.x, start_point.y)
        start_point_proj = Point(start_x_proj, start_y_proj)
        
        # Convert point to WKT for spatial query
        point_wkt = f"POINT({start_x_proj} {start_y_proj})"
        
        # Use PostGIS spatial query to find nearest road - much more efficient
        exclude_clause = f"AND r.id != {excluded_road_id}" if excluded_road_id else ""
        
        result = db.execute(text(f"""
            SELECT r.id FROM roads r
            JOIN road_geometry rg ON rg.road_id = r.id
            WHERE rg.geom IS NOT NULL
              AND r.id != :road_id
              {exclude_clause}
              AND ST_DWithin(
                  ST_Transform(rg.geom, {target_crs}),
                  ST_GeomFromText('POINT({start_x_proj} {start_y_proj})', {target_crs}),
                  :max_distance
              )
            ORDER BY ST_Distance(
                ST_Transform(rg.geom, {target_crs}),
                ST_GeomFromText('POINT({start_x_proj} {start_y_proj})', {target_crs})
            )
            LIMIT 1
        """), {"road_id": road.id, "max_distance": max_distance}).first()
        
        if result:
            closest_road_id = result[0]
            return db.query(Road).filter(Road.id == closest_road_id).first()
        
        return None
    except ValueError as e:
        logger.error(f"Coordinate transformation failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error finding connected road: {type(e).__name__}: {e}")
        return None


def get_metric_address(db: Session, road: Road, visited_roads: Optional[set] = None) -> str:
    """
    Generate metric address by traversing road hierarchy.
    
    """
    if visited_roads is None:
        visited_roads = set()
    
    # Prevent infinite loops
    if road.id in visited_roads or len(visited_roads) > MAX_RECURSION_DEPTH:
        logger.debug(f"Max recursion depth reached for metric address (visited={len(visited_roads)})")
        return road.road_name_en or f"Road-{road.id}"
    
    visited_roads.add(road.id)
    
    # If major or minor road, just return name
    if road.road_category in ["major", "minor"]:
        return road.road_name_en or f"Road-{road.id}"
    
    # For subsidiary roads, find parent
    if road.road_category == "subsidiary" and road.start_point:
        try:
            start_point = load_geometry_from_wkt(str(road.start_point))
            if start_point:
                parent_road = find_connected_road_at_start(db, road, start_point, excluded_road_id=road.id)
                if parent_road:
                    parent_address = get_metric_address(db, parent_road, visited_roads)
                    return f"{parent_address} / {road.road_name_en or f'Road-{road.id}'}"
        except Exception:
            pass
    
    return road.road_name_en or f"Road-{road.id}"


def generate_house_number_for_building(
    db: Session,
    building: Building,
) -> bool:
    """
    Generate and assign house number for a building (main association type).
    
    """
    if not building.road_id:
        logger.warning(f"Building {building.id}: Missing road_id - cannot generate house number")
        return False
    
    if not building.main_building_id or building.main_building_id != building.id:
        building.main_building_id = building.id
        db.commit()
    
    try:
        road = db.query(Road).options(joinedload(Road.geometry)).filter(
            Road.id == building.road_id
        ).first()
        
        if not road:
            logger.error(f"Building {building.id}: Road ID {building.road_id} not found in database")
            return False
        
        if not road.geometry:
            logger.error(f"Building {building.id}: Road {building.road_id} has no RoadGeometry record")
            return False
        
        if not road.geometry.geom:
            logger.error(f"Building {building.id}: Road {building.road_id} geometry record has NULL geom column")
            return False
        
        road_geom = load_geometry_from_wkt(str(road.geometry.geom))
        if not road_geom:
            logger.error(f"Building {building.id}: Failed to parse road geometry WKT/WKB for road {building.road_id}")
            return False
        
        logger.debug(f"Building {building.id}: Road geometry loaded - type={road_geom.geom_type}, is_empty={road_geom.is_empty}")
        
        # Get local coordinate system and transform road geometry
        target_crs = get_local_coordinate_system(db)
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{target_crs}", always_xy=True)
        
        if road_geom.geom_type == 'LineString':
            road_coords = list(road_geom.coords)
            transformed_coords = [transformer.transform(x, y) for x, y in road_coords]
            road_geom = LineString(transformed_coords)
            logger.info(f"Building {building.id}: Road is LineString with {len(transformed_coords)} points, length={road_geom.length:.2f}m")
        elif road_geom.geom_type == 'MultiLineString':
            transformed_lines = [
                LineString([transformer.transform(x, y) for x, y in line.coords])
                for line in road_geom.geoms
            ]
            if not transformed_lines:
                logger.error(f"Building {building.id}: MultiLineString has no valid segments")
                return False
            road_geom = max(transformed_lines, key=lambda x: x.length)
            logger.info(f"Building {building.id}: Road is MultiLineString, using longest segment with length={road_geom.length:.2f}m")
        else:
            logger.error(f"Building {building.id}: Unsupported geometry type {road_geom.geom_type}")
            return False
        
        # Get and transform building location
        gate_location = None
        if building.gate_location:
            gate_location = load_geometry_from_wkt(str(building.gate_location))
        elif building.centroid:
            gate_location = load_geometry_from_wkt(str(building.centroid))
        
        if not gate_location or gate_location.geom_type != 'Point':
            logger.error(f"Building {building.id}: Invalid building location")
            return False
        
        x_proj, y_proj = transformer.transform(gate_location.x, gate_location.y)
        gate_location = Point(x_proj, y_proj)
        
        # Get direction
        direction = get_direction_from_road(gate_location, road_geom)
        building.direction = direction
        
        # Calculate 2D distance by projecting building onto road
        distance_along_road = road_geom.project(gate_location)
        logger.info(f"Building {building.id}: Projected distance along road: {distance_along_road:.2f}m")
        
        # Apply direction-specific rounding
        if direction == "Left":
            house_num = round_distance_left_direction(distance_along_road)
        else:
            house_num = round_distance_right_direction(distance_along_road)
        
        logger.info(f"Building {building.id}: Rounded to base house number {house_num} ({direction})")
        
        attempt = 0
        original_num = house_num
        
        while attempt < MAX_DUPLICATE_CHECK_ATTEMPTS and house_number_exists(db, str(house_num), road.id):
            logger.warning(f"Building {building.id}: House number {house_num} already exists on road {road.id}, attempting: {house_num + 2}")
            house_num += 2  # Increment by 2 to maintain parity (odd stays odd, even stays even)
            attempt += 1
        
        if attempt > 0:
            logger.info(f"Building {building.id}: Found available number after {attempt} attempts: {original_num} → {house_num}")
        
        if attempt >= MAX_DUPLICATE_CHECK_ATTEMPTS:
            logger.error(f"Building {building.id}: Could not find available house number after {MAX_DUPLICATE_CHECK_ATTEMPTS} attempts (started at {original_num})")
        
        # Build hierarchical house number
        house_number_final = _build_hierarchical_house_number(
            db, road, distance_along_road, direction, base_number=house_num
        )
        building.house_no = house_number_final
        
        # Get metric address
        metric_addr = get_metric_address(db, road)
        building.metric_address = metric_addr

        
        # Detect ward from centroid
        if building.centroid:
            centroid = load_geometry_from_wkt(str(building.centroid))
            if centroid:
                ward_no = get_ward_for_point(db, centroid)
                if ward_no:
                    building.ward_no = ward_no
                else:
                    logger.warning(f"Building {building.id}: Could not determine ward from centroid")
        
        db.commit()
        logger.info(f"Building {building.id}: Generated house number {building.house_no}")
        return True
    
    except Exception as e:
        logger.error(f"Building {building.id}: Error generating house number: {e}", exc_info=True)
        return False


def _build_hierarchical_house_number(
    db: Session,
    road: Road,
    distance: float,
    direction: str,
    visited_roads: Optional[Set[int]] = None,
    base_number: Optional[int] = None,
) -> str:
    """
    Recursively build hierarchical house number through road hierarchy.

    """
    if visited_roads is None:
        visited_roads = set()
    
    if road.id in visited_roads or len(visited_roads) > MAX_RECURSION_DEPTH:
        logger.debug(f"Max recursion depth reached for hierarchy (visited={len(visited_roads)})")
        if base_number is not None:
            return str(base_number)
        return str(round_distance_for_direction(distance, direction))
    
    visited_roads.add(road.id)
    
    # For main/minor roads, just return the number
    if road.road_category in ["major", "minor"]:
        if base_number is not None:
            return str(base_number)
        return str(round_distance_for_direction(distance, direction))
    
    # For subsidiary roads, find parent and build hierarchy
    if road.road_category == "subsidiary" and road.start_point:
        try:
            start_point = load_geometry_from_wkt(str(road.start_point))
            if start_point:
                parent_road = find_connected_road_at_start(db, road, start_point, excluded_road_id=road.id)
                if parent_road and parent_road.geometry and parent_road.geometry.geom:
                    parent_geom = load_geometry_from_wkt(str(parent_road.geometry.geom))
                    if parent_geom:
                        dist_to_this_road = parent_geom.project(start_point)
                        parent_direction = get_direction_from_road(start_point, parent_geom)
                        parent_hierarchy = _build_hierarchical_house_number(
                            db, parent_road, dist_to_this_road, parent_direction, visited_roads
                        )
                        final_num = base_number if base_number is not None else round_distance_for_direction(distance, direction)
                        return f"{parent_hierarchy}/{final_num}"
        except Exception:
            pass
    
    if base_number is not None:
        return str(base_number)
    return str(round_distance_for_direction(distance, direction))


def generate_associated_building_number(
    db: Session,
    building: Building,
) -> bool:
    """
    Generate house number for associate or dissociate buildings.

    """
    try:
        association_type = building.association_type
        if association_type not in ["associate", "dissociate"]:
            logger.warning(f"Building {building.id}: Invalid association_type {association_type}")
            return False
        
        # PREVENT CIRCULAR REFERENCE: Don't allow a building to be its own main building
        if building.main_building_id == building.id:
            logger.warning(f"Building {building.id}: Circular reference detected (main_building_id == building.id). Clearing main_building_id for {association_type} building.")
            building.main_building_id = None
            db.commit()
            # If has road_id, treat as main building, otherwise fail
            if building.road_id:
                logger.info(f"Building {building.id}: Numbering as main building (fallback from circular ref)")
                return generate_house_number_for_building(db, building)
            return False
        
        # Fallback: If missing main_building_id but has road_id, number as main
        if not building.main_building_id and building.road_id:
            logger.info(f"Building {building.id}: No main_building_id, numbering as main building (fallback)")
            return generate_house_number_for_building(db, building)
        
        if not building.main_building_id:
            logger.warning(f"Building {building.id}: Missing main_building_id")
            return False
        
        # Get main building
        main_building = db.query(Building).filter(
            Building.id == building.main_building_id
        ).first()
        
        if not main_building:
            logger.warning(f"Building {building.id}: Main building {building.main_building_id} not found")
            if building.road_id:
                return generate_house_number_for_building(db, building)
            return False
        
        if not main_building.house_no:
            logger.warning(f"Building {building.id}: Main building {building.main_building_id} has no house_no yet")
            if building.road_id:
                return generate_house_number_for_building(db, building)
            return False
        
        main_house_no = main_building.house_no
        logger.info(f"Building {building.id}: Main building house_no = {main_house_no}")
        
        if association_type == "associate":
            # Associate: Exact copy of main building number (no modifications)
            building.house_no = main_house_no
            building.metric_address = main_building.metric_address
            building.road_id = main_building.road_id
            building.direction = main_building.direction
            logger.info(f"Building {building.id}: Associate building, copied house_no={building.house_no}")
        
        elif association_type == "dissociate":
            other_dissociate = db.query(Building).filter(
                and_(
                    Building.main_building_id == building.main_building_id,
                    Building.association_type == "dissociate",
                    Building.id != building.id,
                    Building.house_no.isnot(None)
                )
            ).all()
            
            # Extract letters from existing dissociate buildings
            used_letters = []
            for other_bldg in other_dissociate:
                if other_bldg.house_no:
                    # Get last character only (the letter part)
                    last_char = other_bldg.house_no[-1]
                    if last_char.isalpha():
                        used_letters.append(last_char.upper())
            
            # Find next available letter
            used_letters_set = set(used_letters)
            next_letter = "A"
            for i in range(26):
                letter = chr(ord("A") + i)
                if letter not in used_letters_set:
                    next_letter = letter
                    break
            
            # Build final house number: main + "/" + letter
            building.house_no = f"{main_house_no}/{next_letter}"
            building.metric_address = main_building.metric_address
            building.road_id = main_building.road_id
            building.direction = main_building.direction
            logger.info(f"Building {building.id}: Dissociate building, house_no={building.house_no}")
        
        db.commit()
        return True
    
    except Exception as e:
        logger.error(f"Building {building.id}: Error generating associated building number: {e}", exc_info=True)
        return False


def generate_house_numbers_for_all_buildings(db: Session) -> dict:
    """
    Generate house numbers for all buildings without existing numbers.
    
    Processes main buildings first, then associated/dissociate buildings.
    This ensures main buildings are numbered before their dependents.
    
    """
    try:
        # Process main buildings first
        main_buildings = db.query(Building).filter(
            and_(
                Building.road_id.isnot(None),
                Building.association_type == "main",
                (Building.house_no.is_(None) | (Building.house_no == ""))
            )
        ).all()
        
        main_count = sum(1 for b in main_buildings if generate_house_number_for_building(db, b))
        
        # Then process associated buildings
        associated_buildings = db.query(Building).filter(
            and_(
                Building.main_building_id.isnot(None),
                Building.association_type.in_(["associate", "dissociate"]),
                (Building.house_no.is_(None) | (Building.house_no == ""))
            )
        ).all()
        
        associated_count = sum(
            1 for b in associated_buildings
            if generate_associated_building_number(db, b)
        )
        
        return {
            "status": "success",
            "main_buildings_numbered": main_count,
            "associated_buildings_numbered": associated_count,
            "total_processed": main_count + associated_count,
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }
