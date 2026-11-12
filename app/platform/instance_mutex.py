"""
Instancia unica: evita dois instaladores rodando ao mesmo tempo
(que brigariam pela porta local e pela fila de impressoras).
"""
import os
import sys

from app.data import paths


def _mutex_name() -> str:
    return r"Global\ForjaDeImpressorasSingleInstance"


class InstanceMutex:
    """Mutex nomeado do Windows. `acquire()` devolve False se ja existe."""

    def __init__(self, name: str = None):
        self.name = name or _mutex_name()
        self._handle = None

    def acquire(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL,
                                              wintypes.LPCWSTR]
            handle = kernel32.CreateMutexW(None, True, self.name)
            err = ctypes.get_last_error()
            if not handle:
                return True          # sem mutex: segue (nao bloqueia o app)
            if err == 183:           # ERROR_ALREADY_EXISTS
                kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        except Exception:
            return True

    def release(self):
        try:
            if self._handle:
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(
                    self._handle)
                self._handle = None
        except Exception:
            pass


def already_running() -> bool:
    """True se ja existe outra instancia em execucao."""
    m = InstanceMutex()
    ok = m.acquire()
    if ok:
        m.release()
        return False
    return True
