import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _data_path() -> str:
    return os.getenv('DATA_PATH', '.')


def list_cifp_icaos(prefix: str = "", limit: int = 20) -> List[str]:
    base_cifp = os.path.join(_data_path(), 'CIFP')
    search_dir = base_cifp if os.path.isdir(base_cifp) else _data_path()
    codes: list[str] = []
    try:
        for name in os.listdir(search_dir):
            if name.lower().endswith('.dat'):
                code = os.path.splitext(name)[0]
                codes.append(code)
    except Exception:
        return []
    p = (prefix or '').strip().upper()
    if p:
        codes = [c for c in codes if c.upper().startswith(p)]
    codes.sort()
    try:
        lim = max(0, int(limit))
    except Exception:
        lim = 20
    return codes[:lim]
