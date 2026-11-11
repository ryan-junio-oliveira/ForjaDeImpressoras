"""
Forja de Impressoras — aplicativo de instalacao de impressoras.

Organizacao (padrao do HyperViewerTotem / HyperViewerDesktop):

  app/core          motor: varredura de rede, USB, drivers, instalacao
  app/data          dados e caminhos (packs de driver, config, paths)
  app/platform      integracao com o Windows (elevacao, instancia unica)
  app/presentation  interface (web local + janela desktop)
  app/resources     icone e outros recursos binarios
"""
from pathlib import Path


def _read_version() -> str:
    """Versao do app — fonte unica: arquivo VERSION na raiz."""
    try:
        raw = (Path(__file__).resolve().parent.parent / "VERSION").read_text(
            encoding="utf-8").strip()
        if raw:
            return raw
    except Exception:
        pass
    return "0.0.0-dev"


__version__ = _read_version()
__all__ = ["__version__"]
