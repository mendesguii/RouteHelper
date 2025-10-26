from typing import Tuple, List, Dict
from sqlalchemy.orm import Session
from app.utils.dbnav import get_procedure_texts_db


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


def infer_sid_star(db: Session, origin: str, dest: str, route_list: List[str]) -> Tuple[str, str]:
    """Infer SID/STAR text based on first/last fixes of route_list using DB procedures."""
    sid_text = "No SID fix found."
    star_text = "No STAR fix found."
    try:
        if origin and route_list:
            sid_dict = get_procedure_texts_db(db, origin, kind='SID')
            sid_text = search_in_dict_text(sid_dict, route_list[0]) or sid_text
    except Exception as e:
        sid_text = f"Error: {e}"
    try:
        if dest and route_list:
            star_dict = get_procedure_texts_db(db, dest, kind='STAR')
            star_text = search_in_dict_text(star_dict, route_list[-1]) or star_text
    except Exception as e:
        star_text = f"Error: {e}"
    return sid_text, star_text
