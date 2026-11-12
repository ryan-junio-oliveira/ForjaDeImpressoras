"""
Configuracao persistida do app (JSON em %APPDATA%\\ForjaDeImpressoras).
"""
import json
import os
import tempfile
import threading

from . import paths

DEFAULTS = {
    "theme": "light",
    "auto_download": True,
    "last_cidrs": "",
    "window_geometry": "",
}

_cache = None
_lock = threading.Lock()


def load() -> dict:
    global _cache
    with _lock:
        if _cache is not None:
            return dict(_cache)
    data = dict(DEFAULTS)
    try:
        raw = json.loads(paths.config_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update({k: v for k, v in raw.items() if k in DEFAULTS})
    except Exception:
        pass
    with _lock:
        _cache = data
        return dict(data)


def save(cfg: dict) -> bool:
    global _cache
    with _lock:
        base = dict(_cache) if isinstance(_cache, dict) else dict(DEFAULTS)
    base.update({k: v for k, v in (cfg or {}).items() if k in DEFAULTS})
    try:
        dest = paths.config_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(base, ensure_ascii=False, indent=2))
            os.replace(tmp, dest)
        finally:
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass
        with _lock:
            _cache = base
        return True
    except Exception:
        return False


def get(key, fallback=None):
    return load().get(key, DEFAULTS.get(key, fallback))


def set_value(key, value):
    return save({key: value})
