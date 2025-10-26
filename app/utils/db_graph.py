from __future__ import annotations

from typing import Dict, List, Tuple, Optional
from sqlalchemy.orm import Session, aliased

from app.db.models import Airway, Fix
from app.utils.geo import haversine_nm


def _fl_overlaps(lo: int, hi: int, seg_lo: int, seg_hi: int) -> bool:
    return not (seg_hi < lo or seg_lo > hi)


def build_graph_from_db(
    db: Session,
    *,
    cruise_fl: int,
    fl_range: Tuple[int, int],
    include_only_matching_class: bool = True,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], Dict[str, Tuple[float, float]]]:
    """Build adjacency graph from Airway and Fix tables.

    Returns (adj, coords_index) where adj maps FIX@CC -> list of (neighbor, distance_nm, airway_name).
    """
    lo, hi = fl_range
    desired_class = 2 if cruise_fl >= 245 else 1

    # Prefetch airway segments joined with endpoints' Fix coords
    # We'll resolve fixes into keys IDENT@CC using stored Fix.country
    F1 = aliased(Fix)
    F2 = aliased(Fix)
    segs = (
        db.query(
            Airway.name,
            Airway.direction,
            Airway.route_class,
            Airway.lower_fl,
            Airway.upper_fl,
            F1.id.label('f1_id'), F1.ident.label('f1_ident'), F1.country.label('f1_cc'), F1.lat.label('f1_lat'), F1.lon.label('f1_lon'),
            F2.id.label('f2_id'), F2.ident.label('f2_ident'), F2.country.label('f2_cc'), F2.lat.label('f2_lat'), F2.lon.label('f2_lon'),
        )
        .join(F1, F1.id == Airway.fix1_id)
        .join(F2, F2.id == Airway.fix2_id)
        .all()
    )

    adj: Dict[str, List[Tuple[str, float, str]]] = {}
    coords: Dict[str, Tuple[float, float]] = {}

    def key(ident: Optional[str], cc: Optional[str]) -> Optional[str]:
        if not ident:
            return None
        cc_u = (cc or '').upper()
        return f"{ident.upper()}@{cc_u}" if cc_u else ident.upper()

    for (name, direction, rclass, seg_lo, seg_hi,
         f1_id, f1_ident, f1_cc, f1_lat, f1_lon,
         f2_id, f2_ident, f2_cc, f2_lat, f2_lon) in segs:
        if not _fl_overlaps(lo, hi, seg_lo, seg_hi):
            continue
        if include_only_matching_class and (rclass != desired_class):
            continue
        k1 = key(f1_ident, f1_cc)
        k2 = key(f2_ident, f2_cc)
        if not k1 or not k2:
            continue
        coords.setdefault(k1, (float(f1_lat), float(f1_lon)))
        coords.setdefault(k2, (float(f2_lat), float(f2_lon)))
        d = haversine_nm(float(f1_lat), float(f1_lon), float(f2_lat), float(f2_lon))
        if direction in ("N", "P"):
            adj.setdefault(k1, []).append((k2, d, name))
        if direction in ("N", "M"):
            adj.setdefault(k2, []).append((k1, d, name))

    return adj, coords


def nearest_graph_fixes_db(
    coords_index: Dict[str, Tuple[float, float]],
    graph: Dict[str, List[Tuple[str, float, str]]],
    ref_lat: float,
    ref_lon: float,
    *,
    max_radius_nm: float = 100.0,
    limit: int = 10,
) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for fix, (lat, lon) in coords_index.items():
        if fix not in graph:
            continue
        d = haversine_nm(ref_lat, ref_lon, lat, lon)
        if d <= max_radius_nm:
            out.append((fix, d))
    out.sort(key=lambda x: x[1])
    return out[:limit]