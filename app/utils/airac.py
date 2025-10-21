import os
import json
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

# Load .env so DATA_PATH is available
load_dotenv()


def _data_path() -> str:
    return os.getenv('DATA_PATH', '.')


def read_cycle_json() -> Optional[dict]:
    path = os.path.join(_data_path(), 'cycle.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def expected_cycle_str() -> str:
    now = datetime.now()
    return f"{now.year % 100:02d}{now.month:02d}"


def is_cycle_current(cycle_str: str) -> bool:
    return (cycle_str or '').strip() == expected_cycle_str()


def get_airac_info() -> dict:
    data = read_cycle_json()
    if not data:
        return {'cycle': None, 'name': None, 'revision': None, 'source': 'missing', 'is_current': False}
    cycle = str(data.get('cycle', '')).strip() or None
    return {
        'cycle': cycle,
        'name': data.get('name'),
        'revision': str(data.get('revision')) if data.get('revision') is not None else None,
        'source': 'json',
        'is_current': is_cycle_current(cycle or ''),
    }


def get_cycle() -> int:
    data = read_cycle_json()
    if not data:
        raise FileNotFoundError("cycle.json not found under DATA_PATH")
    try:
        return int(str(data.get('cycle', '')).strip())
    except Exception as e:
        raise ValueError("Invalid cycle value in cycle.json") from e
