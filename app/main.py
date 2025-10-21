import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .api.routes import router as api_router


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")


def create_app() -> FastAPI:
    app = FastAPI()

    # Mount static if present
    if os.path.isdir(STATIC_DIR):
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Store templates on app state for reuse
    app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)

    # Include API routes
    app.include_router(api_router)

    return app


app = create_app()
