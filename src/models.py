from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    JSON,
    DateTime,
    ForeignKey,
    Boolean,
)
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
    building = relationship("Building", back_populates="geometry")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_deleted = Column(Boolean, default=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    last_data_request = Column(DateTime, nullable=True)


class Building(Base):
    __tablename__ = "buildings"

    geometry = relationship(
        "BuildingGeometry",
        back_populates="building",
        uselist=False,
        cascade="all, delete-orphan",
    )

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, nullable=True)
    road_id = Column(
        Integer, ForeignKey("roads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    main_building_id = Column(Integer, nullable=True)

    # Geometry fields
    centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    ref_centroid = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)
    gate_location = Column(Geometry(geometry_type="POINT", srid=4326), nullable=True)

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
    road = relationship("Road", back_populates="buildings", foreign_keys=[road_id])


class RoadGeometry(Base):
    __tablename__ = "road_geometry"

    id = Column(Integer, primary_key=True, index=True)

    geom = Column(Geometry("MULTILINESTRING", srid=4326), nullable=True)

    road_id = Column(Integer, ForeignKey("roads.id"), unique=True)
    road = relationship("Road", back_populates="geometry")

    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_deleted = Column(Boolean, default=False)

    timestamp = Column(DateTime, default=datetime.utcnow)
    last_data_request = Column(DateTime, nullable=True)


class Road(Base):
    __tablename__ = "roads"

    geometry = relationship(
        "RoadGeometry",
        back_populates="road",
        uselist=False,
        cascade="all, delete-orphan",
    )
    buildings = relationship("Building", back_populates="road")

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


class RasterLayer(Base):
    """
    A raster is a grid-based representation of geographic data.
    This model stores information about the raster file, associated layer, attribute data, and ID.
    """

    __tablename__ = "raster_layers"

    id = Column(Integer, primary_key=True, index=True)
    name_en = Column(String(50), nullable=True)
    name_ne = Column(String(50), nullable=True)
    raster_file = Column(String(500), nullable=False)  # File path stored as string
    sld_file = Column(String(500), nullable=True)  # SLD file path for styling
    attr_data = Column(JSONB, nullable=True)
    status = Column(
        String(15), nullable=True, default="pending"
    )  # pending, completed, failed
    display_on_map = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)
    bbox = Column(JSONB, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationship to metadata (renamed from 'metadata' to avoid SQLAlchemy reserved attr)
    raster_metadata = relationship(
        "RasterLayerMetadata",
        back_populates="raster_layer",
        cascade="all, delete-orphan",
    )


class RasterLayerMetadata(Base):
    """
    Stores metadata for a raster layer including width, height, bands,
    spatial reference, extent, legend, and statistics.
    """

    __tablename__ = "raster_layer_metadata"

    id = Column(Integer, primary_key=True, index=True)
    raster_layer_id = Column(Integer, ForeignKey("raster_layers.id"), nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    numbands = Column(Integer, nullable=True)
    srid = Column(Integer, nullable=True)
    extent = Column(JSONB, nullable=True)  # [minx, miny, maxx, maxy]
    legend = Column(JSONB, nullable=True)
    stats = Column(JSONB, nullable=True)
    pixel_size = Column(Float, default=0)
    minx = Column(Float, default=0)
    maxx = Column(Float, default=0)
    miny = Column(Float, default=0)
    maxy = Column(Float, default=0)
    file_name = Column(String(100), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationship back to RasterLayer
    raster_layer = relationship("RasterLayer", back_populates="raster_metadata")


class BaseLayer(Base):
    """
    Stores base layer information (e.g., OSM, Satellite, Orthophoto).
    """

    __tablename__ = "base_layers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    layer_type = Column(String(50), nullable=False)  # osm, satellite, orthophoto, etc.
    url = Column(String(500), nullable=True)  # URL for external tile services
    attribution = Column(String(500), nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class BaseLayerName(Base):
    """
    Stores localized names and display order for base layers.
    """

    __tablename__ = "base_layer_names"

    id = Column(Integer, primary_key=True, index=True)
    base_layer_id = Column(Integer, ForeignKey("base_layers.id"), nullable=False)
    name = Column(String(100), nullable=True, index=True)
    label_en = Column(String(100), nullable=True)
    label_ne = Column(String(100), nullable=True)
    order = Column(Integer, default=1)
    is_visible = Column(Boolean, default=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        # Ensure this order field is properly indexed for sorting
    )


class LayerVisibility(Base):
    __tablename__ = "layer_visibility"

    id = Column(Integer, primary_key=True, index=True)
    layer_name = Column(String(255), nullable=False, unique=True)
    is_visible = Column(Integer, nullable=False, default=1)  # 1 for True, 0 for False
    styling = Column(JSONB, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class ProjectMedia(Base):
    __tablename__ = "project_media"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True)
    file_path = Column(String(500), nullable=False, default="/media")
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_deleted = Column(Boolean, default=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class VectorLayer(Base):
    """
    Stores vector layer information for GeoJSON and Shapefile uploads.
    Supports polygon, line, and point geometries.
    """

    __tablename__ = "vector_layers"

    id = Column(Integer, primary_key=True, index=True)
    name_en = Column(String(255), nullable=True)
    name_ne = Column(String(255), nullable=True)
    layer_type = Column(String(50), nullable=True)  # polygon, line, point
    attr_data = Column(JSONB, nullable=True)
    style_value = Column(String(500), nullable=True)
    label_value = Column(String(500), nullable=True)
    is_public = Column(Boolean, default=True)
    display_on_map = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    features = relationship(
        "FeatureCollection",
        back_populates="vector_layer",
        cascade="all, delete-orphan",
    )
    created_by_user = relationship(
        "User",
        foreign_keys=[created_by],
        primaryjoin="VectorLayer.created_by == User.id",
    )
    updated_by_user = relationship(
        "User",
        foreign_keys=[updated_by],
        primaryjoin="VectorLayer.updated_by == User.id",
    )


class FeatureCollection(Base):
    """
    Stores individual features/geometries within a vector layer.
    Each feature contains geometry and associated attributes.
    """

    __tablename__ = "feature_collections"

    id = Column(Integer, primary_key=True, index=True)
    vector_layer_id = Column(
        Integer, ForeignKey("vector_layers.id"), nullable=False, index=True
    )
    attr_data = Column(JSONB, nullable=True)
    geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True)
    style_value = Column(String(500), nullable=True)
    label_value = Column(String(500), nullable=True)
    is_deleted = Column(Boolean, default=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    # Relationships
    vector_layer = relationship(
        "VectorLayer", back_populates="features", foreign_keys=[vector_layer_id]
    )
