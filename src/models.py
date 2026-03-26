from sqlalchemy import Column, Integer, Float, String, JSON, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from geoalchemy2 import Geometry
from datetime import datetime, UTC
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

Base = declarative_base()


class BuildingGeometry(Base):
    __tablename__ = "building_geometry"

    id = Column(Integer, primary_key=True, index=True)

    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    building_id = Column(Integer, ForeignKey("buildings.id"), unique=True)
    building = relationship("Building", back_populates = "geometry")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_deleted = Column(Boolean, default=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    last_data_request = Column(DateTime, nullable=True)


class Building(Base):
    __tablename__ = "buildings"

    geometry = relationship("BuildingGeometry", back_populates = "building", 
                            uselist = False, cascade= "all, delete-orphan")

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, nullable=True)
    road_id = Column(Integer, nullable=True)
    main_building_id = Column(Integer, nullable=True)
    
    # Geometry fields
    centroid = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    ref_centroid = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    gate_location = Column(Geometry(geometry_type='POINT', srid=4326), nullable=True)
    
    owner_status = Column(String(20), nullable=True)
    temporary_type = Column(String(20), nullable=True)
    association_type = Column(String(20), nullable=True)
    roof_type = Column(String(20), nullable=True)
    building_structure = Column(String(50), nullable=True)
    reg_type = Column(String(50), nullable=True)
    building_use = Column(String(50), nullable=True)
    building_sp_use = Column(String(500), nullable=True)  # Store as CSV or JSON
    road_type = Column(String(20), nullable=True)
    road_lane = Column(String(20), nullable=True)
    road_width = Column(Float, nullable=True)
    direction = Column(String(10), nullable=True)
    plot_no = Column(String(255), nullable=True)
    house_no = Column(String(255), nullable=True)
    ward_no = Column(Integer, nullable=True)
    floor = Column(Float, nullable=True)
    tole_name = Column(String(200), nullable=True)
    owner_name = Column(String(30), nullable=True)
    plinth_area = Column(Float, nullable=True)
    remarks = Column(String(500), nullable=True)
    metric_address = Column(String(254), nullable=True, index=True)
    attr_data = Column(JSON, nullable=True)
    lat_field = Column(String(250), nullable=True)
    long_field = Column(String(250), nullable=True)
    plus_code = Column(String(20), nullable=True)
    bbox = Column(JSON, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class RoadGeometry(Base):
    __tablename__ = "road_geometry"

    id = Column(Integer, primary_key=True, index=True)

    geom = Column(Geometry("MULTILINESTRING", srid=4326), nullable=True)

    road_id = Column(Integer, ForeignKey("roads.id"), unique=True)
    road = relationship("Road", back_populates = "geometry")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_deleted = Column(Boolean, default=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    last_data_request = Column(DateTime, nullable=True)

class Road(Base):
    __tablename__ = "roads"

    geometry = relationship("RoadGeometry", back_populates = "road",
                            uselist = False, cascade = "all, delete-orphan")

    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String(100), nullable=True)
    road_name_en = Column(String(500), nullable=True)
    road_name_ne = Column(String(500), nullable=True)
    road_id = Column(Integer, nullable=True)
    road_type = Column(String(20), nullable=True)
    road_category = Column(String(20), nullable=True)
    road_class = Column(String(30), nullable=True)
    road_lane = Column(String(30), nullable=True)
    road_width = Column(Float, nullable=True)
    road_length = Column(Float, nullable=True)
    direction = Column(String(50), nullable=True)
    ward_no = Column(JSONB, nullable=True)
    start_point = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    end_point = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    attr_data = Column(JSONB, nullable=True)
    lat_field = Column(String(250), nullable=True)
    long_field = Column(String(250), nullable=True)
    remarks = Column(String(50), nullable=True)
    bbox = Column(JSONB, nullable=True)
    timestamp = Column(DateTime, nullable=True)
    last_data_request = Column(DateTime, nullable=True)
    slope_distance = Column(Float, nullable=True)




    