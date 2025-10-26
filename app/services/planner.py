from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import logging
from sqlalchemy.orm import Session

from app.utils.db_graph import build_graph_from_db, nearest_graph_fixes_db
from app.utils.dbnav import get_airport_coords_db

log = logging.getLogger(__name__)


@dataclass
class PlannerOptions:
    origin: str
    dest: str
    fl_start: int
    fl_end: int
    prefer_upper_by_fl: bool = True
    enable_directs_in_fra: bool = True  # placeholder for future enhancement
    sid_star_assist: bool = True        # hook to prefer fixes aligned to SIDs/STARs later
    # New tuning knobs
    strict_class_match: bool = True     # if False, allow mixing lower/upper classes
    allow_dct_bridging: bool = True     # enable DCT fallback
    max_dct_steps: int = 3              # max number of DCT hops (we may cap to 5)
    dct_radius_nm: float = 120.0        # search radius for DCT neighbors
    dct_neighbors_limit: int = 25       # limit neighbors examined per node


def _pick_cruise_fl(fl_start: int, fl_end: int) -> int:
    # Simple heuristic: choose midpoint rounded to nearest 10
    lo, hi = min(fl_start, fl_end), max(fl_start, fl_end)
    mid = (lo + hi) // 2
    return (mid // 10) * 10


def _dijkstra(
    adj: Dict[str, List[Tuple[str, float, str]]],
    start: str,
    goal: str,
) -> Tuple[List[str], float, List[str]]:
    import heapq

    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, Tuple[str, str]] = {}  # node -> (prev_node, airway)
    pq: List[Tuple[float, str]] = [(0.0, start)]

    visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, w, awy in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float('inf')):
                dist[v] = nd
                prev[v] = (u, awy)
                heapq.heappush(pq, (nd, v))

    if goal not in dist:
        return [], float('inf'), []

    # Reconstruct path nodes and airway labels between them
    route_nodes: List[str] = []
    airway_labels: List[str] = []
    cur = goal
    while cur != start:
        route_nodes.append(cur)
        p, awy = prev[cur]
        airway_labels.append(awy)
        cur = p
    route_nodes.append(start)
    route_nodes.reverse()
    airway_labels.reverse()
    return route_nodes, dist[goal], airway_labels


def _dijkstra_with_dct(
    adj: Dict[str, List[Tuple[str, float, str]]],
    coords: Dict[str, Tuple[float, float]],
    start: str,
    goal: str,
    *,
    max_dct_steps: int = 2,
    dct_radius_nm: float = 80.0,
    dct_neighbors_limit: int = 15,
) -> Tuple[List[str], float, List[str]]:
    """Dijkstra variant that allows up to N DCT hops between nearby graph nodes.

    DCT edges are created on-the-fly between the current node and up to K nearest
    graph nodes within radius, with cost equal to great-circle distance.
    """
    import heapq

    def coord(n: str) -> Optional[Tuple[float, float]]:
        return coords.get(n)

    # state is (node, dct_used)
    dist: Dict[Tuple[str, int], float] = {(start, 0): 0.0}
    prev: Dict[Tuple[str, int], Tuple[Tuple[str, int], Optional[str]]] = {}
    pq: List[Tuple[float, Tuple[str, int]]] = [(0.0, (start, 0))]
    visited: set[Tuple[str, int]] = set()

    # Cache DCT neighbor queries
    dct_cache: Dict[str, List[Tuple[str, float]]] = {}

    while pq:
        d, state = heapq.heappop(pq)
        if state in visited:
            continue
        visited.add(state)
        u, used = state
        if u == goal:
            # Found path; unwind using the best used count for goal
            break

        # Regular graph edges
        for v, w, awy in adj.get(u, []):
            ns = (v, used)
            nd = d + w
            if nd < dist.get(ns, float('inf')):
                dist[ns] = nd
                prev[ns] = (state, awy)
                heapq.heappush(pq, (nd, ns))

        # DCT expansion
        if used < max_dct_steps:
            if u not in dct_cache:
                latlon = coord(u)
                if latlon is None:
                    dct_cache[u] = []
                else:
                    # Reuse nearest_graph_fixes_db helper to get nearby graph nodes
                    near = nearest_graph_fixes_db(coords, adj, latlon[0], latlon[1], max_radius_nm=dct_radius_nm, limit=dct_neighbors_limit)
                    dct_cache[u] = [(fix, dist_nm) for fix, dist_nm in near if fix != u]
            for v, d_nm in dct_cache[u]:
                # Skip if already a direct graph neighbor
                if any(nb == v for (nb, _, _) in adj.get(u, [])):
                    continue
                ns = (v, used + 1)
                nd = d + d_nm
                if nd < dist.get(ns, float('inf')):
                    dist[ns] = nd
                    prev[ns] = (state, None)  # None airway denotes DCT leg
                    heapq.heappush(pq, (nd, ns))

    # Pick best goal state among used=0..max_dct_steps
    best_goal_state = None
    best_cost = float('inf')
    for used in range(0, max_dct_steps + 1):
        st = (goal, used)
        if st in dist and dist[st] < best_cost:
            best_goal_state = st
            best_cost = dist[st]

    if best_goal_state is None:
        return [], float('inf'), []

    # Reconstruct
    route_nodes: List[str] = []
    airway_labels: List[str] = []
    cur = best_goal_state
    while True:
        u, used = cur
        route_nodes.append(u)
        if cur not in prev:
            break
        p_state, awy = prev[cur]
        airway_labels.append(awy if awy is not None else "DCT")
        cur = p_state
    route_nodes.reverse()
    airway_labels.reverse()
    return route_nodes, best_cost, airway_labels


def plan_standards_route(db: Session, opts: PlannerOptions) -> Tuple[List[str], str]:
    """Generate a route list per standards in route_generator_context.md.

    Output is (route_list, route_text)
    """
    origin = (opts.origin or "").upper().strip()
    dest = (opts.dest or "").upper().strip()
    log.info("Planner start: %s->%s FL[%s,%s]", origin, dest, opts.fl_start, opts.fl_end)
    if not origin or not dest:
        return [], "No route generated."

    # Choose a representative cruise FL and graph altitude window
    cruise_fl = _pick_cruise_fl(opts.fl_start, opts.fl_end)
    fl_lo, fl_hi = min(opts.fl_start, opts.fl_end), max(opts.fl_start, opts.fl_end)

    # Build airway graph filtered by class and altitude
    adj, coords = build_graph_from_db(
        db,
        cruise_fl=cruise_fl,
        fl_range=(fl_lo, fl_hi),
        include_only_matching_class=opts.strict_class_match,
    )

    apt_coords = get_airport_coords_db(db)
    o_ll = apt_coords.get(origin)
    d_ll = apt_coords.get(dest)
    if not o_ll or not d_ll:
        log.warning("Missing airport coords for origin/dest")
        return [], "No route generated. (Airport coordinates not found)"

    # Candidate graph nodes near origin/dest to attach to en-route network
    # Use user-selected radius first, then adaptively expand
    base_radius = max(10.0, float(opts.dct_radius_nm or 120.0))
    limit_n = max(5, int(opts.dct_neighbors_limit or 25))
    log.debug("Candidate search radius=%sNM limit=%s", base_radius, limit_n)

    def adaptive_candidates(lat: float, lon: float) -> List[Tuple[str, float]]:
        for mul in (1.0, 1.5, 2.0, 3.0, 4.0):
            r = min(500.0, base_radius * mul)
            cands = nearest_graph_fixes_db(coords, adj, lat, lon, max_radius_nm=r, limit=limit_n)
            log.debug("Candidate pass r=%.1f -> %d", r, len(cands))
            if cands:
                return cands
        return []

    origin_candidates = adaptive_candidates(o_ll[0], o_ll[1])
    dest_candidates = adaptive_candidates(d_ll[0], d_ll[1])
    if not origin_candidates or not dest_candidates:
        log.warning("Candidates missing. origin=%d dest=%d", len(origin_candidates), len(dest_candidates))
        return [], "No route generated. (No nearby airway fixes)"
    log.debug("Origin candidates: %s", origin_candidates[:6])
    log.debug("Dest candidates: %s", dest_candidates[:6])

    # Try shortest pair among top-N candidates
    best_route: List[str] = []
    best_airways: List[str] = []
    best_cost = float('inf')
    best_pair: Tuple[str, str] | None = None
    # Limit combinations to keep it snappy
    top_o = [o for o, _ in origin_candidates[:7]]
    top_d = [d for d, _ in dest_candidates[:7]]
    log.debug("Try pairs: %dx%d candidates", len(top_o), len(top_d))
    for s in top_o:
        for g in top_d:
            if not adj.get(s):
                log.debug("Skip start %s: no outgoing edges", s)
                continue
            if not adj.get(g) and all(g != k for k in adj.keys()):
                log.debug("Note: goal %s not present in graph nodes", g)
            nodes, cost, awys = _dijkstra(adj, s, g)
            log.debug("Try %s->%s: nodes=%d cost=%s", s, g, len(nodes), (cost if cost != float('inf') else 'inf'))
            if nodes and cost < best_cost:
                best_cost = cost
                best_route = nodes
                best_airways = awys
                best_pair = (s, g)

    if not best_route:
        if not opts.allow_dct_bridging or opts.max_dct_steps <= 0:
            log.info("No graph path found and DCT bridging disabled")
            return [], "No route generated. (No graph path)"
        log.info("No graph-only path found. Retrying with limited DCT bridging...")
        # Retry allowing DCT hops, gradually increasing steps
        max_steps_cap = min(5, max(1, opts.max_dct_steps))
        steps_seq = list(range(1, max_steps_cap + 1)) if opts.max_dct_steps > 0 else []
        if not steps_seq:
            steps_seq = [1]
        for steps in steps_seq:
            for s in top_o:
                for g in top_d:
                    nodes, cost, awys = _dijkstra_with_dct(
                        adj,
                        coords,
                        s,
                        g,
                        max_dct_steps=steps,
                        dct_radius_nm=opts.dct_radius_nm,
                        dct_neighbors_limit=opts.dct_neighbors_limit,
                    )
                    log.debug("DCT(%d) %s->%s: nodes=%d cost=%s", steps, s, g, len(nodes), (cost if cost != float('inf') else 'inf'))
                    if nodes and cost < best_cost:
                        best_cost = cost
                        best_route = nodes
                        best_airways = awys
                        best_pair = (s, g)
            if best_route:
                break
        if not best_route:
            log.info("No graph path found between any candidate pairs (even with DCT)")
            # Fallback: rebuild graph allowing mixed route classes and retry
            if opts.strict_class_match:
                log.info("Retrying with mixed route classes (strict_class_match=False)")
                adj2, coords2 = build_graph_from_db(
                    db,
                    cruise_fl=cruise_fl,
                    fl_range=(fl_lo, fl_hi),
                    include_only_matching_class=False,
                )
                def adaptive_candidates2(lat: float, lon: float) -> List[Tuple[str, float]]:
                    for mul in (1.0, 1.5, 2.0, 3.0, 4.0):
                        r = min(600.0, base_radius * mul)
                        cands = nearest_graph_fixes_db(coords2, adj2, lat, lon, max_radius_nm=r, limit=max(10, limit_n))
                        log.debug("[mix] Candidate pass r=%.1f -> %d", r, len(cands))
                        if cands:
                            return cands
                    return []
                origin_candidates2 = adaptive_candidates2(o_ll[0], o_ll[1])
                dest_candidates2 = adaptive_candidates2(d_ll[0], d_ll[1])
                if origin_candidates2 and dest_candidates2:
                    top_o2 = [o for o, _ in origin_candidates2[:8]]
                    top_d2 = [d for d, _ in dest_candidates2[:8]]
                    log.debug("[mix] Try pairs: %dx%d candidates", len(top_o2), len(top_d2))
                    # Try graph only
                    for s in top_o2:
                        for g in top_d2:
                            nodes, cost, awys = _dijkstra(adj2, s, g)
                            log.debug("[mix] Try %s->%s: nodes=%d cost=%s", s, g, len(nodes), (cost if cost != float('inf') else 'inf'))
                            if nodes and cost < best_cost:
                                best_cost = cost
                                best_route = nodes
                                best_airways = awys
                                best_pair = (s, g)
                    # If still not found, allow DCT up to cap
                    if not best_route and opts.allow_dct_bridging:
                        for steps in range(1, max_steps_cap + 1):
                            for s in top_o2:
                                for g in top_d2:
                                    nodes, cost, awys = _dijkstra_with_dct(
                                        adj2,
                                        coords2,
                                        s,
                                        g,
                                        max_dct_steps=steps,
                                        dct_radius_nm=max(120.0, opts.dct_radius_nm),
                                        dct_neighbors_limit=max(25, opts.dct_neighbors_limit),
                                    )
                                    log.debug("[mix] DCT(%d) %s->%s: nodes=%d cost=%s", steps, s, g, len(nodes), (cost if cost != float('inf') else 'inf'))
                                    if nodes and cost < best_cost:
                                        best_cost = cost
                                        best_route = nodes
                                        best_airways = awys
                                        best_pair = (s, g)
                if not best_route:
                    return [], "No route generated. (No graph/DCT path)"
            else:
                return [], "No route generated. (No graph/DCT path)"

    # Assemble route string: we will output fixes separated with airways when airway changes
    # e.g., FIX1 AWY FIX2 FIX3 AWY2 FIX4 ...
    pieces: List[str] = []
    last_awy: Optional[str] = None
    for i, fix in enumerate(best_route):
        if i == 0:
            pieces.append(fix.split('@')[0])
        else:
            awy = best_airways[i - 1] if i - 1 < len(best_airways) else None
            if awy and awy != last_awy:
                pieces.append(awy)
                last_awy = awy
            pieces.append(fix.split('@')[0])

    route_list = pieces
    route_text = " ".join(route_list)
    log.info(
        "Planner success: fixes=%d tokens=%d dist≈%.1fnm start=%s end=%s",
        len([p for p in pieces if p.isalpha()]),
        len(pieces),
        best_cost if best_cost != float('inf') else -1.0,
        best_pair[0] if best_pair else '',
        best_pair[1] if best_pair else '',
    )
    return route_list, route_text

