"""Чтение weights.yaml без внешних зависимостей.

Формат конфига намеренно плоский (два уровня, скалярные значения), поэтому
полноценный YAML-парсер тут избыточен. Если конфиг усложнится — заменить
эту функцию на yaml.safe_load, интерфейс не изменится.
"""

from __future__ import annotations

from pathlib import Path


def _cast(v: str):
    v = v.strip()
    if v.lower() in ("true", "false"):
        return v.lower() == "true"
    try:
        return int(v) if "." not in v else float(v)
    except ValueError:
        return v


def load_config(path: Path) -> dict:
    cfg: dict = {}
    section = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indented = line[0] in " \t"
        key, _, val = line.strip().partition(":")
        key = key.strip()
        if not indented:
            section = key
            cfg[section] = _cast(val) if val.strip() else {}
        elif section is not None and isinstance(cfg.get(section), dict):
            cfg[section][key] = _cast(val)
    return cfg
