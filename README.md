# Name

Kathmandu Metropolitan City House Numbering System (Bid Management System)

# Description

This project is a FastAPI-based backend for the Kathmandu Metropolitan City house numbering workflow. It manages building and road records, stores geospatial geometry in PostGIS, and provides authenticated APIs for operational use.

It includes:
- JWT authentication (signup, login, refresh, current user)
- CRUD APIs for buildings, roads, and users
- PostGIS geometry support using GeoAlchemy2
- GeoJSON ingestion scripts for building and road data
- Redis + Celery worker/beat setup for background processing

# Features

- FastAPI REST API with OpenAPI docs
- PostgreSQL + PostGIS geospatial storage
- Building and road domain modules with filters, sorting, and pagination
- Token-based access control on protected routes
- Docker Compose setup for local deployment

# Tech Stack

- Python 3.12
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL + PostGIS
- GeoAlchemy2 + Shapely
- Redis + Celery
- Docker / Docker Compose

# Requirements

- Docker and Docker Compose (recommended)
- Or local setup with:
  - Python 3.12+
  - PostgreSQL with PostGIS extension
  - Redis

# Installation

## Option 1: Docker Compose (Recommended)

1. Create a `.env` file in the project root.
2. Add environment values:

```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/bid_db
JWT_SECRET_KEY=replace-with-a-strong-secret
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7
```

3. Build and run:

```bash
docker compose up --build
```

4. Access API:
- http://localhost:8000
- http://localhost:8000/docs

## Option 2: Local Python Runtime

1. Create and activate virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Make sure PostgreSQL (with PostGIS) and Redis are running.
4. Export environment variables.
5. Start API:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

# Support

For implementation or deployment support, create an issue in this repository or contact the project maintainer team.

# Roadmap

- Add Alembic migrations
- Add automated test suite
- Add role-based authorization rules
- Add `.env.example`
- Add production deployment guide

# Contributing

1. Create a branch from `main`.
2. Commit small, focused changes.
3. Test affected endpoints.
4. Open a merge request with clear description.

# Authors and Acknowledgment

Developed for Kathmandu Metropolitan City house numbering operations.

# License

License not specified yet.

# Project Status

Active development.
