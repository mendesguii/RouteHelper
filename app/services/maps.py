from typing import List, Tuple, Dict
import folium
from app.utils.geo import haversine_nm


def _add_distance_label(m: folium.Map, lat: float, lon: float, text: str, color: str = '#cfd8dc') -> None:
    folium.map.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(html=(
            f'<div style="position: relative; left: 50%; transform: translate(-50%, -10px);'
            f' font-size: 11px; color: {color}; background: rgba(0,0,0,0.35); padding: 2px 4px; border-radius: 3px;'
            f' white-space: nowrap; text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{text}</div>'
        ))
    ).add_to(m)


def _add_text_label(m: folium.Map, lat: float, lon: float, text: str, *, color: str = '#8bd9f8', dy_px: int = -14, size_px: int = 11, weight='normal') -> None:
    folium.map.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(html=(
            f'<div style="position: relative; left: 50%; transform: translate(-50%, {dy_px}px);'
            f' font-size: {size_px}px; font-weight: {weight}; color: {color}; white-space: nowrap;'
            f' text-shadow: 0 0 2px #000, 0 0 3px #000; pointer-events: none;">{text}</div>'
        ))
    ).add_to(m)


def build_route_map_html(
    coords: List[Tuple[float, float, str]],
    apt_coords: Dict[str, Tuple[float, float]],
    origin: str,
    dest: str,
    route_indicates_none: bool,
    theme: str | None = None,
) -> tuple[str, float]:
    """Build a folium map HTML and compute total distance over legs.

    theme: 'light' | 'dark' | 'auto' | None
    - Default behavior: treat 'auto'/None as dark tiles (map defaults to dark).
      Only when theme is explicitly 'light' do we use light tiles.
    """
    theme = (theme or 'auto').lower()
    # Default map theme is dark. Use light tiles only if explicitly requested.
    tiles_name = 'CartoDB positron' if theme == 'light' else 'CartoDB dark_matter'
    m = folium.Map(location=[0, 0], zoom_start=2, tiles=tiles_name)

    points: List[Tuple[float, float]] = []
    if len(coords) >= 2:
        folium.PolyLine([(c[0], c[1]) for c in coords], color='#00c2ff', weight=3, opacity=0.85).add_to(m)
    for lat, lon, name in coords:
        folium.CircleMarker(location=[lat, lon], radius=4, color='#00c2ff', fill=True, fill_color='#ffffff', fill_opacity=0.9, popup=name, tooltip=name).add_to(m)
        _add_text_label(m, lat, lon, name, color="#8bd9f8", dy_px=-14, size_px=11, weight='normal')
        points.append((lat, lon))

    o = (apt_coords.get((origin or '').upper()) if origin else None)
    d = (apt_coords.get((dest or '').upper()) if dest else None)
    if o:
        folium.Marker(location=[o[0], o[1]], icon=folium.Icon(color='lightgreen', icon='plane', prefix='fa'), popup=f"{origin.upper()} (Origin)", tooltip=f"{origin.upper()} (Origin)").add_to(m)
        _add_text_label(m, o[0], o[1], origin.upper(), color="#a2f5bf", dy_px=-16, size_px=12, weight=700)
        points.append(o)
    if d:
        folium.Marker(location=[d[0], d[1]], icon=folium.Icon(color='orange', icon='flag', prefix='fa'), popup=f"{dest.upper()} (Destination)", tooltip=f"{dest.upper()} (Destination)").add_to(m)
        _add_text_label(m, d[0], d[1], dest.upper(), color="#ffcc80", dy_px=-16, size_px=12, weight=700)
        points.append(d)

    label_legs: List[Tuple[float, float, float, float, str]] = []
    if o and coords:
        first = coords[0]
        folium.PolyLine([[o[0], o[1]], [first[0], first[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((o[0], o[1], first[0], first[1], '#cfd8dc'))
    if len(coords) >= 2:
        for i in range(len(coords) - 1):
            lat1, lon1, _ = coords[i]
            lat2, lon2, _ = coords[i + 1]
            label_legs.append((lat1, lon1, lat2, lon2, '#ffd54f'))
    if d and coords:
        last = coords[-1]
        folium.PolyLine([[last[0], last[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((last[0], last[1], d[0], d[1], '#cfd8dc'))
    if (o and d) and route_indicates_none and not coords:
        folium.PolyLine([[o[0], o[1]], [d[0], d[1]]], color='#90a4ae', weight=2, opacity=0.85, dash_array='4,6').add_to(m)
        label_legs.append((o[0], o[1], d[0], d[1], '#cfd8dc'))

    total_distance_nm = 0.0
    for (lat1, lon1, lat2, lon2, color) in label_legs:
        leg_nm = haversine_nm(lat1, lon1, lat2, lon2)
        total_distance_nm += leg_nm
        mid_lat = (lat1 + lat2) / 2
        mid_lon = (lon1 + lon2) / 2
        _add_distance_label(m, mid_lat, mid_lon, f"{leg_nm:.1f} nm", color=color)

    if points:
        min_lat = min(p[0] for p in points)
        max_lat = max(p[0] for p in points)
        min_lon = min(p[1] for p in points)
        max_lon = max(p[1] for p in points)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]], padding=(20, 20))

    html = m.get_root().render()
    return html, total_distance_nm
