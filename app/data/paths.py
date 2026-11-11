"""
Caminhos do sistema.

Distingue duas raizes:
  - recursos somente-leitura (embutidos no executavel): driver_packs.json,
    drivers_catalog.json, app/resources, interface web
  - pasta gravavel (onde o app roda): drivers/ (inf do TI), logs/, config
"""
import os
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent      # app/
ROOT = APP_DIR.parent                                  # raiz do projeto (dev)

# --- recursos somente-leitura (funcionam empacotado ou em dev) ---
RESOURCES_DIR = APP_DIR / "resources"
STATIC_DIR = APP_DIR / "presentation" / "static"
PACKS_JSON = APP_DIR / "data" / "driver_packs.json"
CATALOG_JSON = APP_DIR / "data" / "drivers_catalog.json"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Pasta gravavel onde o app roda (raiz do projeto em dev, pasta do .exe)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return ROOT


def _writable(path: Path) -> bool:
    """True se da para criar/usar a pasta."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def drivers_dir() -> Path:
    """Pasta dos .inf do TI + cache de downloads.

    Se a pasta de instalacao nao for gravavel (ex.: Program Files sem
    privilegio), cai para %LOCALAPPDATA% em vez de quebrar o app.
    """
    if is_frozen():
        preferida = base_dir() / "drivers"
        if _writable(preferida):
            return preferida
        alternativa = (Path(os.environ.get("LOCALAPPDATA", base_dir()))
                       / "ForjaDeImpressoras" / "drivers")
        alternativa.mkdir(parents=True, exist_ok=True)
        return alternativa
    d = base_dir() / "drivers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def downloads_dir() -> Path:
    d = drivers_dir() / "_downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    """Logs de execucao (sempre gravavel)."""
    if is_frozen():
        d = Path(os.environ.get("LOCALAPPDATA", base_dir())) / "ForjaDeImpressoras" / "logs"
    else:
        d = base_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    d = Path(os.environ.get("APPDATA", base_dir())) / "ForjaDeImpressoras"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.json"


def writable_dir() -> Path:
    """Pasta gravavel para dados de execucao (resultado de scan, etc.).

    Em dev e em instalacao portatil usa a propria pasta do app; se ela nao
    for gravavel (Program Files sem privilegio), cai para %LOCALAPPDATA%.
    """
    d = base_dir()
    if _writable(d):
        return d
    alt = Path(os.environ.get("LOCALAPPDATA", d)) / "ForjaDeImpressoras"
    alt.mkdir(parents=True, exist_ok=True)
    return alt


def scan_result_path() -> Path:
    """Arquivo JSON com o resultado da ultima varredura."""
    return writable_dir() / "ultimo_scan.json"


def install_log_path(stem: str) -> Path:
    return logs_dir() / f"instalacao_{stem}.log"
