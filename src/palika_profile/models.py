from datetime import datetime, UTC

from geoalchemy2 import Geometry
from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from src.models import Base


class PalikaProfile(Base):
    __tablename__ = "palika_profiles"

    id = Column(Integer, primary_key=True, index=True)

    name_en = Column(String(255), nullable=True)
    name_ne = Column(String(255), nullable=True)
    description_en = Column(String(1000), nullable=True)
    description_ne = Column(String(1000), nullable=True)

    # File paths/URLs should be persisted as plain strings in API-first services.
    logo_en = Column(String(500), nullable=True)
    logo_ne = Column(String(500), nullable=True)

    contact_info = Column(String, nullable=True)
    important_links = Column(JSONB, nullable=True)

    email = Column(String(255), unique=True, nullable=True, index=True)
    zip_code = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)

    local_coordinate_system = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PalikaGeometryFile(Base):
    __tablename__ = "palika_geometry_files"

    id = Column(Integer, primary_key=True, index=True)
    file_type = Column(String(20), nullable=True)
    file_upload = Column(String(1000), nullable=False)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PalikaGeometry(Base):
    __tablename__ = "palika_geometries"

    id = Column(Integer, primary_key=True, index=True)
    area = Column(Float, nullable=True)
    bbox = Column(JSONB, nullable=True)
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class PalikaWardGeometry(Base):
    __tablename__ = "palika_ward_geometries"

    id = Column(Integer, primary_key=True, index=True)
    ward_no = Column(Integer, nullable=True)
    numbering_status = Column(String(20), nullable=True)
    area = Column(Float, nullable=True)
    bbox = Column(JSONB, nullable=True)
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), nullable=True)

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
