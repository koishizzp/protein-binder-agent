import json
from pathlib import Path

import yaml


def read_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text())


def write_yaml(path: str, data: dict) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return str(p)


def write_json(path: str, data: dict) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return str(p)
