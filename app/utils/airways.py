import os
import os.path
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .navdata import load_fix_catalog
from .logging_utils import debug
from .geo import haversine_nm


def _data_path() -> str:
    return os.getenv("DATA_PATH", ".")


@dataclass(frozen=True)
class AirwaySegment:
    fix1: str
    fix1_cc: str
    fix2: str
    fix2_cc: str
    direction: str  # 'N', 'P', 'M'
    route_class: int  # 1 lower, 2 upper
    lower_fl: int  # in FL (hundreds of feet)
    upper_fl: int  # in FL (hundreds of feet)
    airway: str


def _parse_awy_line(line: str) -> Optional[AirwaySegment]:
    """Parse a single earth_awy.dat line.

    Supports both formats:
    - With explicit freq fields (13 tokens total)
    - Without freq fields (11 tokens total)
    """
    if not line or line.startswith(";"):
        return None
    parts = line.strip().split()
    # Heuristic: ignore very short or malformed lines
    if len(parts) < 11:
        return None

    try:
        if len(parts) >= 13:
            # fix1_id fix1_cc fix1_type fix1_freq fix2_id fix2_cc fix2_type fix2_freq dir cls low up name
            fix1 = parts[0].upper()
            fix1_cc = parts[1].upper()
            # parts[2] type
            # parts[3] freq
            fix2 = parts[4].upper()
            fix2_cc = parts[5].upper()
            direction = parts[8].upper()
            route_class = int(parts[9])
            lower_fl = int(parts[10])
            upper_fl = int(parts[11])
            airway = parts[12].upper()
        else:
            # 11 tokens: fix1_id fix1_cc fix1_type fix2_id fix2_cc fix2_type dir cls low up name
            fix1 = parts[0].upper()
            fix1_cc = parts[1].upper()
            fix2 = parts[3].upper()
            fix2_cc = parts[4].upper()
            direction = parts[6].upper()
            route_class = int(parts[7])
            lower_fl = int(parts[8])
            upper_fl = int(parts[9])
            airway = parts[10].upper()
    except Exception:
        return None

    if direction not in ("N", "P", "M"):
        # Some data may use other markers; ignore
        return None

    return AirwaySegment(
        fix1=fix1,
        fix1_cc=fix1_cc,
        fix2=fix2,
        fix2_cc=fix2_cc,
        direction=direction,
        route_class=route_class,
        lower_fl=lower_fl,
        upper_fl=upper_fl,
        airway=airway,
    )


def load_airway_segments() -> List[AirwaySegment]:
    path = os.path.join(_data_path(), "earth_awy.dat")
    segs: List[AirwaySegment] = []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                seg = _parse_awy_line(raw)
                if seg:
                    segs.append(seg)
    except FileNotFoundError:
        return []
    debug(f"Loaded airway segments: {len(segs)} from {path}")
    return segs


def _fl_overlaps(edge: AirwaySegment, fl_range: Tuple[int, int]) -> bool:
    lo, hi = fl_range
    return not (edge.upper_fl < lo or edge.lower_fl > hi)


def _class_matches(edge: AirwaySegment, cruise_fl: int) -> bool:
    # If cruise FL is upper airspace (>=245), prefer class 2, else class 1
    desired = 2 if cruise_fl >= 245 else 1
    return edge.route_class == desired


def build_graph(
    *,
    cruise_fl: int,
    fl_range: Tuple[int, int],
    include_only_matching_class: bool = True,
) -> Tuple[Dict[str, List[Tuple[str, float, str]]], Dict[str, Tuple[float, float]]]:
    """Build adjacency graph from airway segments.

    Returns (adj, coords_index) where adj maps FIX -> list of (neighbor, distance_nm, airway_name).
    """
    segs = load_airway_segments()
    catalog = load_fix_catalog()
    # Coordinates keyed by IDENT@CC
    coords: Dict[str, Tuple[float, float]] = {}

    # Filter segments by altitude overlap and class
    # First compute overlap stats for debugging
    desired_class = 2 if cruise_fl >= 245 else 1
    overlap_c1 = 0
    overlap_c2 = 0
    usable: List[AirwaySegment] = []
    for s in segs:
        if not _fl_overlaps(s, fl_range):
            continue
        if s.route_class == 1:
            overlap_c1 += 1
        elif s.route_class == 2:
            overlap_c2 += 1
        if include_only_matching_class and not _class_matches(s, cruise_fl):
            continue
        usable.append(s)
    debug(
        f"Graph filter: FL={cruise_fl} desired_class={desired_class} range={fl_range} "
        f"overlap_c1={overlap_c1} overlap_c2={overlap_c2} usable_segments={len(usable)}"
    )

    adj: Dict[str, List[Tuple[str, float, str]]] = {}

    def resolve(ident: str, cc: str) -> Optional[Tuple[float, float]]:
        lst = catalog.get(ident)
        if not lst:
            return None
        # prefer exact country match
        for rec in lst:
            if rec.country == cc:
                return (rec.lat, rec.lon)
        # fallback ENRT anywhere
        for rec in lst:
            if rec.usage == 'ENRT':
                debug(f"No country match for {ident}@{cc}; using ENRT fallback")
                return (rec.lat, rec.lon)
        # last resort: first
        debug(f"No country/ENRT match for {ident}@{cc}; using first record fallback")
        r0 = lst[0]
        return (r0.lat, r0.lon)

    def add_edge(a_ident: str, a_cc: str, b_ident: str, b_cc: str, airway: str) -> None:
        a_key = f"{a_ident}@{a_cc}"
        b_key = f"{b_ident}@{b_cc}"
        if a_key not in coords:
            c = resolve(a_ident, a_cc)
            if c:
                coords[a_key] = c
        if b_key not in coords:
            c = resolve(b_ident, b_cc)
            if c:
                coords[b_key] = c
        if a_key not in coords or b_key not in coords:
            return
        lat1, lon1 = coords[a_key]
        lat2, lon2 = coords[b_key]
        d = haversine_nm(lat1, lon1, lat2, lon2)
        adj.setdefault(a_key, []).append((b_key, d, airway))

    for s in usable:
        if s.direction in ("N", "P"):
            add_edge(s.fix1, s.fix1_cc, s.fix2, s.fix2_cc, s.airway)
        if s.direction in ("N", "M"):
            add_edge(s.fix2, s.fix2_cc, s.fix1, s.fix1_cc, s.airway)
    debug(f"Graph nodes={len(adj)} edges={sum(len(v) for v in adj.values())}")
    return adj, coords


def nearest_graph_fixes(
    coords_index: Dict[str, Tuple[float, float]],
    graph: Dict[str, List[Tuple[str, float, str]]],
    ref_lat: float,
    ref_lon: float,
    *,
    max_radius_nm: float = 100.0,
    limit: int = 10,
) -> List[Tuple[str, float]]:
    """Return up to `limit` fixes present in the graph within radius, with distances from ref point."""
    out: List[Tuple[str, float]] = []
    for fix, (lat, lon) in coords_index.items():
        if fix not in graph:
            continue
        d = haversine_nm(ref_lat, ref_lon, lat, lon)
        if d <= max_radius_nm:
            out.append((fix, d))
    out.sort(key=lambda x: x[1])
    return out[:limit]

