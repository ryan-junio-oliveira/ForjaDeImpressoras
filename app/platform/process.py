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
import threading

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


def install_readerthread_excepthook():
    """Silencia o ruido `OSError: [Errno 9] Bad file descriptor`.

    No Windows, matar um processo com timeout (ex.: ping estourado no
    ping sweep) corre contra as reader-threads internas do `subprocess`:
    `_readerthread` le/fecha um pipe ja fechado e o `threading` imprime
    o traceback no console. E inofensivo (a chamada ja retornou), mas
    assusta e esconde os logs reais. Filtra SOMENTE esse caso.
    Idempotente: pode chamar varias vezes.
    """
    prev = threading.excepthook

    def _hook(args):
        try:
            ev = getattr(args, "exc_value", None)
            if isinstance(ev, OSError) and ev.errno == 9:
                tb = getattr(args, "exc_traceback", None)
                while tb is not None:
                    code = tb.tb_frame.f_code
                    if (code.co_name == "_readerthread"
                            and code.co_filename.replace("\\", "/").endswith("subprocess.py")):
                        return
                    tb = tb.tb_next
        except Exception:
            pass
        try:
            prev(args)
        except Exception:
            pass

    _hook.__name__ = "forja_readerthread_filter"
    if getattr(prev, "__name__", "") == "forja_readerthread_filter":
        return
    threading.excepthook = _hook
