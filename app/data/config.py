"""
Configuracao persistida do app (JSON em %APPDATA%\\ForjaDeImpressoras).
"""
import json

from . import paths

DEFAULTS = {
    "theme": "light",
    "auto_download": True,
    "last_cidrs": "",
    "window_geometry": "",
}

_cache = None


def load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    data = dict(DEFAULTS)
    try:
        raw = json.loads(paths.config_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update({k: v for k, v in raw.items() if k in DEFAULTS})
    except Exception:
        pass
    _cache = data
    return data


def save(cfg: dict) -> bool:
    global _cache
    data = dict(load())
    data.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    try:
        paths.config_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        _cache = data
        return True
    except Exception:
        return False


def get(key, fallback=None):
    return load().get(key, DEFAULTS.get(key, fallback))


def set_value(key, value):
    return save({key: value})
