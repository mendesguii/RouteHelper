from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.models import Base, AiracCycle, Airport, Fix, Airway, FlightPlan, Procedure
from app.db.session import engine
from app.core.indexer import run_full_index


router = APIRouter(prefix="/admin", tags=["admin"])
log = logging.getLogger(__name__)


def templates(request: Request):
    return request.app.state.templates


def _p(msg: str, *args):
    try:
        text = msg % args if args else msg
    except Exception:
        text = f"{msg} {args}"
    print(f"[INFO] {text}", flush=True)


def _render_status(request: Request, db: Session, notice: Optional[dict] = None) -> HTMLResponse:
    airac = db.query(AiracCycle).order_by(AiracCycle.id.desc()).first()
    counts = {
        "airports": db.query(Airport).count(),
        "fixes": db.query(Fix).count(),
        "airways": db.query(Airway).count(),
        "procedures": db.query(Procedure).count(),
        "flights": db.query(FlightPlan).count(),
    }
    return templates(request).TemplateResponse("partials/admin_status.html", {
        "request": request,
        "airac": {"cycle": airac.cycle if airac else None, "name": airac.name if airac else None},
        "counts": counts,
        "notice": notice,
    })


@router.get("/", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)):
    log.info("Admin page opened")
    _p("Admin page opened")
    airac = db.query(AiracCycle).order_by(AiracCycle.id.desc()).first()
    counts = {
        "airports": db.query(Airport).count(),
        "fixes": db.query(Fix).count(),
        "airways": db.query(Airway).count(),
        "procedures": db.query(Procedure).count(),
        "flights": db.query(FlightPlan).count(),
    }
    return templates(request).TemplateResponse("admin.html", {
        "request": request,
        "airac": {"cycle": airac.cycle if airac else None, "name": airac.name if airac else None},
        "counts": counts,
    })


@router.post("/init")
def init_db():
    """Create all tables if they don't exist."""
    log.info("Admin action: init tables")
    _p("Admin action: init tables")
    Base.metadata.create_all(bind=engine)
    return {"status": "ok"}


@router.post("/index")
def trigger_index(force: bool = False, db: Session = Depends(get_db)):
    log.info("Admin action: index (force=%s)", force)
    _p("Admin action: index (force=%s)", force)
    counts = run_full_index(db, force=force)
    db.commit()
    _p("Admin action: index done -> %s", counts)
    return {"status": "ok", "counts": counts}


@router.get("/status")
def status(db: Session = Depends(get_db)):
    log.info("Admin action: status")
    _p("Admin action: status")
    airac = db.query(AiracCycle).order_by(AiracCycle.id.desc()).first()
    counts = {
        "airports": db.query(Airport).count(),
        "fixes": db.query(Fix).count(),
        "airways": db.query(Airway).count(),
        "procedures": db.query(Procedure).count(),
        "flights": db.query(FlightPlan).count(),
    }
    return {"airac": {"cycle": airac.cycle if airac else None, "name": airac.name if airac else None}, "counts": counts}


# HTML partial endpoints for HTMX
@router.get("/status_view", response_class=HTMLResponse)
def status_view(request: Request, db: Session = Depends(get_db)):
    log.info("Admin action: status_view")
    _p("Admin action: status_view")
    return _render_status(request, db, notice={"kind": "info", "text": "Status refreshed."})


@router.post("/init_view", response_class=HTMLResponse)
def init_view(request: Request, db: Session = Depends(get_db)):
    log.info("Admin action: init_view")
    _p("Admin action: init_view")
    Base.metadata.create_all(bind=engine)
    # After init, show status
    return _render_status(request, db, notice={"kind": "success", "text": "Tables initialized successfully."})


@router.post("/index_view", response_class=HTMLResponse)
def index_view(request: Request, force: bool = False, db: Session = Depends(get_db)):
    log.info("Admin action: index_view (force=%s)", force)
    _p("Admin action: index_view (force=%s)", force)
    counts = run_full_index(db, force=force)
    db.commit()
    msg = f"Index complete (force={force}). Airports={counts.get('airports',0)} Fixes={counts.get('fixes',0)} Airways={counts.get('airways',0)} Procedures={counts.get('procedures',{})}."
    _p("Admin action: index_view done -> %s", counts)
    return _render_status(request, db, notice={"kind": "success", "text": msg})


## Simplified UI: logs and procedures endpoints are not exposed anymore
