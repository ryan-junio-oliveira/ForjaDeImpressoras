"""
Execucao de processos no Windows sem abrir janelas de console.

A interface e um app *windowed* (sem console proprio). Quando ele chama
`subprocess.run`, o Windows cria um console VISIVEL para cada filho — no
ping sweep de uma /24 isso sao centenas de janelas piscando na tela.

`CREATE_NO_WINDOW` resolve: o filho roda sem console, e a saida continua
sendo capturada por pipes normalmente.
"""
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def run(*args, **kwargs):
    """Equivalente a `subprocess.run`, sem criar janela de console."""
    if sys.platform == "win32":
        flags = int(kwargs.get("creationflags") or 0)
        kwargs["creationflags"] = flags | CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)


def popen(*args, **kwargs):
    """Equivalente a `subprocess.Popen`, sem criar janela de console."""
    if sys.platform == "win32":
        flags = int(kwargs.get("creationflags") or 0)
        kwargs["creationflags"] = flags | CREATE_NO_WINDOW
    return subprocess.Popen(*args, **kwargs)
