import os
import sys
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .api.routes import router as api_router
from .api.admin import router as admin_router
from .db.models import Base
from .db.session import engine


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")


def _configure_logging():
    """Ensure app loggers emit to stdout at INFO level.

    Uvicorn installs its own logging config; we attach a handler to the 'app'
    logger hierarchy so our modules (app.*) print regardless of root settings.
    """
    logger = logging.getLogger("app")
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        formatter = logging.Formatter('[%(levelname)s] %(name)s: %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def create_app() -> FastAPI:
    app = FastAPI()

    # Mount static if present
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Store templates on app state for reuse
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Configure logging for app modules before wiring routes
    _configure_logging()

    # Include API routes
    app.include_router(api_router)
    app.include_router(admin_router)

    return app


app = create_app()

# Ensure tables exist on import (container start)
try:
    Base.metadata.create_all(bind=engine)
except Exception:
    # Lazy create will be available via /admin/init if this fails
    pass
