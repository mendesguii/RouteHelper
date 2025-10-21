from typing import Tuple, Optional, List
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from .loadsheets import parse_loadsheet

# These services currently reuse the logic from RouteHelper via HTTP/HTML parsing
# to minimize risk while modularizing. They can be improved later to share pure
# utility functions.


def fetch_loadsheet(origin: str, dest: str, plane: str) -> tuple[str, Optional[dict]]:
    headers = {
        'okstart': 1,
        'EQPT': plane.upper(),
        'ORIG': origin.upper(),
        'DEST': dest.upper(),
        'submit': 'LOADSHEET',
        'RULES': 'FARDOM',
        'UNITS': 'METRIC',
    }
    r = requests.post('http://fuelplanner.com/index.php', data=headers)
    soup = BeautifulSoup(r.text, 'html5lib')
    loadsheet = soup.pre.text.replace('fuelplanner.com | home', '').replace('Copyright 2008-2019 by Garen Evans', '')
    # Parse using shared loadsheets parser
    try:
        parsed = parse_loadsheet(loadsheet)
    except Exception:
        parsed = None
    return loadsheet, parsed


def fetch_route(origin: str, dest: str, minalt: str, maxalt: str, cycle: int) -> tuple[List[str], str]:
    headers = {
        'id1': origin.upper(),
        'ic1': '',
        'id2': dest.upper(),
        'ic2': '',
        'minalt': f'FL{minalt}',
        'maxalt': f'FL{maxalt}',
        'lvl': 'B',
        'dbid': cycle,
        'usesid': 'Y',
        'usestar': 'Y',
        'easet': 'Y',
        'rnav': 'Y',
        'nats': 'R'
    }
    r = requests.post('http://rfinder.asalink.net/free/autoroute_rtx.php', data=headers)
    soup = BeautifulSoup(r.text, 'html5lib')
    genroute_tags = soup.find_all('tt')
    if len(genroute_tags) < 2:
        return [], 'No route generated.'
    genroute = genroute_tags[1].text
    route_list = genroute.split(' ')[2:-2]
    route_text = ' '.join(route_list) if route_list else 'No route generated.'
    return route_list, route_text


def fetch_metar(icao: str) -> str:
    r = requests.get(f'https://aviationweather.gov/api/data/metar?ids={icao}')
    soup = BeautifulSoup(r.text, 'html5lib')
    return soup.text or ""
