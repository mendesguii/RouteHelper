import os
import re
from typing import Tuple, List, Dict
from dotenv import load_dotenv

load_dotenv()


def _data_path() -> str:
    return os.getenv('DATA_PATH', '.')


def _read_procedure_file(name_or_path: str) -> Dict[str, List[str]]:
    """Return dict with lists: {'sids': [], 'stars': [], 'apps': [], 'rwys': []}.

    If name_or_path is a file, use it; else treat as ICAO and search:
    1) DATA_PATH/CIFP/<ICAO>.dat  2) DATA_PATH/<ICAO>.dat
    """
    sids: List[str] = []
    stars: List[str] = []
    apps: List[str] = []
    rwys: List[str] = []

    if os.path.isfile(name_or_path):
        resolved = name_or_path
    else:
        icao = os.path.basename(name_or_path).split('.')[0]
        candidate_cifp = os.path.join(_data_path(), 'CIFP', f'{icao}.dat')
        candidate_root = os.path.join(_data_path(), f'{icao}.dat')
        resolved = candidate_cifp if os.path.isfile(candidate_cifp) else candidate_root

    with open(resolved, 'r', encoding='utf-8') as f:
        for line in f:
            if 'SID:' in line:
                sids.append(line)
            elif 'STAR' in line:
                stars.append(line)
            elif 'APPCH' in line:
                apps.append(line)
            elif 'RWY' in line:
                rwys.append(line)

    return {'sids': sids, 'stars': stars, 'apps': apps, 'rwys': rwys}


def _clean_dictionary(obj_dict: Dict[str, str], proc_type: str) -> None:
    """Clean up procedure dict by merging runway-specific entries into base keys."""
    list_to_delete = []
    for i in list(obj_dict.keys()):
        split_name = i.split('-')
        if len(split_name) > 1 and 'RW' in split_name[1]:
            for x in obj_dict:
                if split_name[0] in x and 'RW' not in x:
                    list_to_delete.append(i)
                    if proc_type == "SID":
                        obj_dict[x] = f"[{split_name[1]}] {obj_dict[i].replace('  ', '')} | {obj_dict[x]}"
                    elif proc_type == "STAR":
                        obj_dict[x] = f"{obj_dict[x]} | {obj_dict[i]} [{split_name[1]}]"
    for item in set(list_to_delete):
        if item in obj_dict:
            del obj_dict[item]


def structure_data(rawdata: List[str]) -> Dict[str, str]:
    """Structure raw procedure lines into a dictionary keyed by 'procedure-start' with merged segments."""
    object_dict: Dict[str, str] = {}
    proc_type = None
    for entry in rawdata:
        current = entry.split(',')
        proc_type = current[0].split(':')[0]
        num = current[0].split(':')[1]
        procedure = current[2]
        cur_pos_start = current[3]
        cur_pos_end = current[4]

        key = f"{procedure}-{cur_pos_start}"
        value = cur_pos_end.replace('  ', '')
        if num == "010":
            object_dict[key] = value
        else:
            object_dict[key] = object_dict.get(key, '')
            if object_dict[key]:
                object_dict[key] += ' '
            object_dict[key] += value

    if rawdata and proc_type:
        _clean_dictionary(object_dict, proc_type)
    return object_dict


def search_in_dict_text(obj_dict: Dict[str, str], value: str) -> str:
    lines = [f"- Fix Search: {value}"]
    for k, v in obj_dict.items():
        if value in v or value in k:
            lines.append(f"* Chart: {k} || Route: {v}")
    return '\n'.join(lines).strip()


def infer_sid_star(origin: str, dest: str, route_list: List[str]) -> Tuple[str, str]:
    """Infer SID/STAR text based on first/last fixes of route_list."""
    sid_text = "No SID fix found."
    star_text = "No STAR fix found."
    try:
        if origin and route_list:
            data = _read_procedure_file(origin)
            sid_dict = structure_data(data['sids'])
            sid_text = search_in_dict_text(sid_dict, route_list[0]) or sid_text
    except Exception as e:
        sid_text = f"Error: {e}"
    try:
        if dest and route_list:
            data = _read_procedure_file(dest)
            star_dict = structure_data(data['stars'])
            star_text = search_in_dict_text(star_dict, route_list[-1]) or star_text
    except Exception as e:
        star_text = f"Error: {e}"
    return sid_text, star_text
