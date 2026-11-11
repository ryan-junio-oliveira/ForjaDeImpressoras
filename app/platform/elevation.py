"""
Elevacao de privilegio: instalar impressora exige Administrador.
"""
import ctypes
import os
import sys


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Relanca o processo atual como Administrador. True se conseguiu."""
    if is_admin():
        return False
    try:
        params = " ".join(f'"{a}"' for a in sys.argv[1:])
        exe = sys.executable
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join(f'"{a}"' for a in sys.argv[1:])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, params, None, 1)
        return int(result) > 32
    except Exception:
        return False


def ensure_admin(interactive=True) -> bool:
    """Garante privilegio de administrador. Devolve True se ok."""
    if is_admin():
        return True
    if not interactive:
        return False
    if relaunch_as_admin():
        sys.exit(0)
    return False
