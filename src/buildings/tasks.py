from celery import shared_task
from src.database import SessionLocal
from src.buildings.house_numbering import (
    generate_house_number_for_building,
    generate_associated_building_number,
    generate_house_numbers_for_all_buildings,
)
from src.models import Building
from sqlalchemy import and_
from src.buildings.house_numbering import get_ward_for_point
from shapely.wkt import loads as load_wkt

@shared_task(bind=True)
def generate_house_numbers_task(self, building_id: int | None = None):
    """
    Celery task for asynchronous house number generation.
    
    """
    db = SessionLocal()
    
    try:
        if building_id is None:
            # Process all buildings
            result = generate_house_numbers_for_all_buildings(db)
            return result
        else:
            # Process single building
            building = db.query(Building).filter(Building.id == building_id).first()
            
            if not building:
                return {
                    "status": "error",
                    "message": f"Building {building_id} not found",
                }
            
            # Update task state with progress
            self.update_state(
                state="PROGRESS",
                meta={"current": 1, "total": 1}
            )
            
            # Generate house number based on association type
            if building.association_type == "main":
                success = generate_house_number_for_building(db, building)
            else:
                success = generate_associated_building_number(db, building)
            
            if success:
                return {
                    "status": "success",
                    "building_id": building_id,
                    "house_no": building.house_no,
                    "message": f"House number generated: {building.house_no}",
                }
            else:
                return {
                    "status": "error",
                    "building_id": building_id,
                    "message": "Failed to generate house number",
                }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }
    
    finally:
        db.close()


@shared_task
def regenerate_ward_for_building(building_id: int):
    """
    Celery task to update ward information for a building.
    """
    db = SessionLocal()
    
    try:
        building = db.query(Building).filter(Building.id == building_id).first()
        
        if not building or not building.centroid:
            return {
                "status": "error",
                "message": "Building or centroid not found",
            }
        
        centroid = load_wkt(str(building.centroid))
        ward_no = get_ward_for_point(db, centroid)
        
        if ward_no:
            building.ward_no = ward_no
            db.commit()
            
            return {
                "status": "success",
                "building_id": building_id,
                "ward_no": ward_no,
            }
        else:
            return {
                "status": "error",
                "message": "Could not determine ward for building",
            }
    
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
        }
    
    finally:
        db.close()