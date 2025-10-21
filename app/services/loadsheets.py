import re
from typing import Optional, Dict, Any


def parse_loadsheet(text: str) -> Dict[str, Any]:
    """Parse the fuelplanner loadsheet text into a structured dictionary.

    Returns a dict with top-level keys: database, flight, routing, weights, times, end.
    Values are numbers where applicable; missing values will be None.
    """
    lines = [ln.rstrip() for ln in (text or '').splitlines()]
    data: dict = {
        'database': None,
        'flight': {
            'from': None,
            'to': None,
            'flight': None,
            'ac_reg': None,
            'version': None,
            'crew': None,
            'date': None,
            'time': None,
            'tc': None,
        },
        'weights': {
            'load_compartments': None,
            'load_compartments_dist': None,
            'passenger_cabin_bag': None,
            'passenger_cabin_bag_dist': None,
            'efu': None,
            'reserve_fuel': None,
            'total_traffic_load': None,
            'dry_operating_weight': None,
            'zfw_actual': None,
            'zfw_max': None,
            'takeoff_fuel': None,
            'tow_actual': None,
            'tow_max': None,
            'trip_fuel': None,
            'ldw_actual': None,
            'ldw_max': None,
            'underload_before_lmc': None,
            'lmc_total': None,
        },
        'times': {
            'block_time': None,
            'reserve': None,
            'time_to_empty': None,
            'ci': None,
        },
        'end': {
            'aircraft': None,
            'route': None,
            'date': None,
        }
    }

    def to_int(s):
        try:
            return int(s)
        except Exception:
            return None

    # database line
    for ln in lines:
        m = re.search(r'^DATABASE\s+(.+)$', ln)
        if m:
            data['database'] = m.group(1).strip()
            break

    # FROM/TO header and values
    for idx, ln in enumerate(lines):
        if re.search(r'^FROM/TO\s+FLIGHT\s+A/C-REG\s+VERSION\s+CREW\s+DATE\s+TIME', ln):
            for j in range(idx+1, min(idx+4, len(lines))):
                vals = lines[j].strip()
                if not vals:
                    continue
                m = re.match(r'^(?P<from>[A-Z0-9]{4})/(?P<to>[A-Z0-9]{4})\s+'
                             r'(?P<flight>\S+)\s+'
                             r'(?P<ac_reg>\S+)\s+'
                             r'(?P<version>\S+)\s+'
                             r'(?P<crew>\S+)\s+'
                             r'(?P<date>\S+)\s+'
                             r'(?P<time>\S+)$', vals)
                if m:
                    data['flight'].update({k: m.group(k) for k in m.groupdict()})
                    break
            # Optional TC line follows
            if idx+2 < len(lines):
                tc_line = lines[idx+2].strip()
                m_tc = re.match(r'^TC\s+(.+)$', tc_line)
                if m_tc:
                    data['flight']['tc'] = m_tc.group(1).strip()
            break

    # Weights and distributions
    for ln in lines:
        m = re.match(r'^LOAD IN COMPARTMENTS\s+(\d+)\s+(\S+)$', ln)
        if m:
            data['weights']['load_compartments'] = to_int(m.group(1))
            data['weights']['load_compartments_dist'] = m.group(2)
        m = re.match(r'^PASSENGER/CABIN BAG\s+(\d+)\s+(\S+)$', ln)
        if m:
            data['weights']['passenger_cabin_bag'] = to_int(m.group(1))
            data['weights']['passenger_cabin_bag_dist'] = m.group(2)
        if 'EFU' in ln or 'RSV' in ln:
            m_efu = re.search(r'EFU\.?.*?(\d+)', ln)
            m_rsv = re.search(r'RSV\.?.*?(\d+)', ln)
            if m_efu:
                data['weights']['efu'] = to_int(m_efu.group(1))
            if m_rsv:
                data['weights']['reserve_fuel'] = to_int(m_rsv.group(1))
        m = re.search(r'TOTAL\s+TRAFFIC\s+LOAD\s+(\d+)', ln)
        if m:
            data['weights']['total_traffic_load'] = to_int(m.group(1))
        m = re.match(r'^DRY OPERATING WEIGHT\s+(\d+)', ln)
        if m:
            data['weights']['dry_operating_weight'] = to_int(m.group(1))
        m = re.match(r'^ZERO FUEL WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
        if m:
            data['weights']['zfw_actual'] = to_int(m.group(1))
            data['weights']['zfw_max'] = to_int(m.group(2))
        m = re.search(r'TAKE\s*OFF\s*FUEL\s*(\d+)', ln)
        if m:
            data['weights']['takeoff_fuel'] = to_int(m.group(1))
        m = re.match(r'^TAKE OFF WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
        if m:
            data['weights']['tow_actual'] = to_int(m.group(1))
            data['weights']['tow_max'] = to_int(m.group(2))
        m = re.match(r'^TRIP FUEL\s+(\d+)', ln)
        if m:
            data['weights']['trip_fuel'] = to_int(m.group(1))
        m = re.match(r'^LANDING WEIGHT ACTUAL\s+(\d+)\s+MAX\s+(\d+)', ln)
        if m:
            data['weights']['ldw_actual'] = to_int(m.group(1))
            data['weights']['ldw_max'] = to_int(m.group(2))
        m = re.match(r'^UNDERLOAD BEFORE LMC\s+(\d+)(.*)$', ln)
        if m:
            data['weights']['underload_before_lmc'] = to_int(m.group(1))
            tail = m.group(2)
            m_lmc = re.search(r'LMC TOTAL\s*([+\-]?)\s*(\d+)', tail)
            if m_lmc:
                sign = -1 if m_lmc.group(1) == '-' else 1
                data['weights']['lmc_total'] = sign * to_int(m_lmc.group(2))

    # Times and CI
    for ln in lines:
        m = re.search(r'SI\s+BLOCK\s+TIME\s+(\d{2}:\d{2}).*?RESERVE\s+(\d{2}:\d{2}).*?TIME\s+TO\s+EMPTY\s+(\d{2}:\d{2}).*?CI\s+(\d+)', ln)
        if m:
            data['times']['block_time'] = m.group(1)
            data['times']['reserve'] = m.group(2)
            data['times']['time_to_empty'] = m.group(3)
            data['times']['ci'] = to_int(m.group(4))
            break

    # End line with brackets
    for ln in lines:
        if 'END LOADSHEET' in ln:
            m_all = re.search(r'\[\s*([^\]]+?)\s*\]\s*\[\s*([^\]]+?)\s*\]\s*\[\s*([^\]]+?)\s*\]', text)
            if m_all:
                data['end']['aircraft'] = m_all.group(1).strip()
                data['end']['route'] = m_all.group(2).strip()
                data['end']['date'] = m_all.group(3).strip()
            break

    return data
