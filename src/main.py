import logging
import time

from celery import Celery
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.auth.routes import router as auth
from src.buildings.routes import router as buildings
from src.database import engine
from src.models import Base
from src.palika_profile.routes import router as palika_profile
from src.roads.routes import router as roads
from src.users.routes import router as users
from src.raster.routes import router as raster, base_layer, tile_router
from src.vectortile.media_routes import router as project_media
from src.vector.routes import router as vector
from src.palika_profile import models as palika_models
from src.users import models as user_models

app = FastAPI()

app.mount("/media", StaticFiles(directory="media"), name="media")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


logger = logging.getLogger(__name__)


@app.on_event("startup")
def initialize_database() -> None:
    """Initialize DB objects after the app starts so import doesn't fail if DB is not ready."""
    attempts = 10
    delay_seconds = 3

    for attempt in range(1, attempts + 1):
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            Base.metadata.create_all(bind=engine)
            logger.info("Database initialized successfully.")
            return
        except OperationalError as exc:
            logger.warning(
                "Database not ready (attempt %s/%s): %s", attempt, attempts, exc
            )
            if attempt == attempts:
                raise
            time.sleep(delay_seconds)
        except SQLAlchemyError:
            logger.exception("Database initialization failed due to SQLAlchemy error.")
            raise


@app.get("/")
async def root():
    return {"message": "Hello World"}


celery_app = Celery(
    "worker",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
)

app.include_router(buildings)
app.include_router(roads)
app.include_router(users)
app.include_router(auth)
app.include_router(palika_profile)
app.include_router(raster)
app.include_router(base_layer)
app.include_router(tile_router)
app.include_router(vector)
app.include_router(project_media)
