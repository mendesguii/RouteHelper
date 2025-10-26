from __future__ import annotations

from typing import Dict, List, Tuple
from sqlalchemy.orm import Session

from app.db.models import Airport, Fix, Procedure


def get_airport_coords_db(db: Session) -> Dict[str, Tuple[float, float]]:
    coords: Dict[str, Tuple[float, float]] = {}
    for icao, lat, lon in db.query(Airport.icao, Airport.lat, Airport.lon).all():
        if icao:
            coords[icao.upper()] = (float(lat), float(lon))
    return coords


def get_route_fix_coords_db(db: Session, items_text: str) -> List[Tuple[float, float, str]]:
    seq = [s for s in (items_text or '').split() if s.strip()]
    out: List[Tuple[float, float, str]] = []
    if not seq:
        return out
    # Build an index of positions for quick lookup
    # multiple rows can exist for same ident; we pick ENRT, else first
    # prefetch all idents we need
    idents = list({t.upper() for t in seq})
    rows = (
        db.query(Fix.ident, Fix.usage, Fix.country, Fix.lat, Fix.lon)
        .filter(Fix.ident.in_(idents))
        .all()
    )
    by_ident: dict[str, list[tuple[str | None, str | None, float, float]]] = {}
    for ident, usage, country, lat, lon in rows:
        by_ident.setdefault(ident.upper(), []).append((usage, country, float(lat), float(lon)))
    def pick(ident: str):
        lst = by_ident.get(ident.upper())
        if not lst:
            return None
        for u, c, lat, lon in lst:
            if (u or '').upper() == 'ENRT':
                return (lat, lon)
        u0, c0, lat, lon = lst[0]
        return (lat, lon)
    for it in seq:
        pos = pick(it)
        if pos:
            out.append((pos[0], pos[1], it.upper()))
    return out


def list_icaos_db(db: Session, prefix: str = "", limit: int = 20) -> List[str]:
    q = (prefix or '').strip().upper()
    query = db.query(Airport.icao)
    if q:
        query = query.filter(Airport.icao.like(f"{q}%"))
    rows = query.order_by(Airport.icao.asc()).limit(max(0, int(limit or 20))).all()
    return [r[0] for r in rows]


def get_procedure_texts_db(db: Session, icao: str, *, kind: str) -> dict[str, str]:
    """Return dict name-start -> route for a given ICAO and kind in {'SID','STAR'}."""
    rows = (
        db.query(Procedure.name, Procedure.start, Procedure.route)
        .filter(Procedure.icao == (icao or '').upper(), Procedure.proc_type == kind)
        .all()
    )
    out: dict[str, str] = {}
    for name, start, route in rows:
        key = f"{name}-{start or ''}"
        out[key] = route or ''
    return out