"""
Forja de Impressoras — entrada unica do aplicativo.

Modos:
  python main.py                 -> desktop (janela PySide6 com a web local)
  python main.py --mode server   -> sobe o servidor local (desenvolvimento)

  A interface abre SOMENTE na janela desktop: nenhum modo abre o navegador.

CLI:
  python main.py --scan [CIDR]
  python main.py --test-ip IP
  python main.py --install IP --driver "Nome exato do driver"
  python main.py --remove-all

Rode como Administrador para instalar impressoras.
"""
import argparse
import json
import sys

from app import __version__
from app.core import driver_manager, printer_install, scanner
from app.data import paths

BASE = paths.base_dir()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def cli_scan(cidrs=None):
    from app.core.network import get_all_local_networks
    alvo = cidrs or "todas as sub-redes locais " + str(get_all_local_networks())
    print(f"Varrendo: {alvo} ...")
    printers = scanner.scan_network(
        cidrs=cidrs or None,
        progress_cb=lambda a, t, m: print(f"  [{int(a * 100 / max(t, 1))}%] {m}"))
    print(f"\nEncontradas {len(printers)} impressora(s):")
    for p in printers:
        canon = p.get("modelo_canonico") or p["modelo"]
        print(f" - {p['ip']:15} | {p['fabricante']:10} | {canon[:50]:50} | "
              f"portas={p['portas']} | SNMP={'sim' if p['snmp_ok'] else 'nao'}")
    destino = paths.scan_result_path()
    destino.write_text(json.dumps(printers, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"Salvo em {destino}")


def cli_test_ip(ip):
    r = scanner.check_single_ip(ip)
    if not r:
        print(f"{ip}: nao e impressora.")
        sys.exit(1)
    canon = r.get("modelo_canonico") or r["modelo"]
    print(f"{ip}: IMPRESSORA {r['fabricante']} {canon} "
          f"portas={r['portas']} snmp={r['snmp_ok']} conf={r.get('confianca_modelo')}")
    print("sysDescr:", r.get("sys_descr", "")[:200])


def cli_install(ip, driver, inf, nome, porta):
    if driver_manager.is_generic_name(driver or ""):
        print("ERRO: driver generico bloqueado.")
        sys.exit(2)
    if not printer_install.check_admin():
        print("AVISO: nao esta como Administrador — a instalacao provavelmente falhara.")
    ok, msgs = printer_install.full_install(ip, "", "", driver, inf_path=inf,
                                            printer_name=nome, port_number=porta,
                                            log=print)
    print(msgs)
    sys.exit(0 if ok else 1)


# --------------------------------------------------------------------------
# INTERFACE
# --------------------------------------------------------------------------
def launch_web(port=8765, mode="desktop"):
    """Sobe a interface.

    desktop -> hibrido: janela PySide6 renderizando a web local.
               NUNCA abre o navegador (politica do app).
    server  -> sobe o servidor local (desenvolvimento; abre o navegador).
    """
    if mode == "server":
        from app.presentation.server import serve
        serve(host="127.0.0.1", port=port, open_browser=True)
        return

    # hibrido desktop (padrao e unico modo de uso)
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except Exception:
        print("ERRO: PySide6/QtWebEngine nao encontrado.")
        print("Reinstale pelo instalador (ForjaDeImpressorasSetup.exe) "
              "ou rode: pip install PySide6")
        sys.exit(2)

    from app.presentation.desktop import run
    sys.exit(run(port=port))

# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="forja-de-impressoras",
        description="Forja de Impressoras — varre a rede, resolve o driver PCL "
                    "especifico e instala no Windows.")
    ap.add_argument("--version", action="version", version=f"Forja de Impressoras {__version__}")
    ap.add_argument("--scan", nargs="?", const="", default=None,
                    help="varre sub-redes locais ou CIDRs ('192.168.15.0/24, 10.0.0.0/24')")
    ap.add_argument("--test-ip", help="testa um unico IP")
    ap.add_argument("--install", help="IP da impressora a instalar (CLI)")
    ap.add_argument("--driver", help="nome exato do driver PCL (CLI)")
    ap.add_argument("--inf", help="caminho do .inf (CLI, opcional)")
    ap.add_argument("--nome", help="nome da impressora no Windows (CLI, opcional)")
    ap.add_argument("--porta", type=int, default=9100, help="porta TCP (padrao 9100)")
    ap.add_argument("--no-download", action="store_true",
                    help="nao baixa driver automaticamente")
    ap.add_argument("--remove-all", action="store_true",
                    help="remove TODAS as impressoras do computador + portas orfas")
    ap.add_argument("--include-virtual", action="store_true",
                    help="com --remove-all, remove tambem virtuais (PDF/XPS/Fax)")
    ap.add_argument("--remove-drivers", action="store_true",
                    help="com --remove-all, remove tambem drivers orfaos nao-Microsoft")
    ap.add_argument("--mode", choices=("desktop", "server"),
                    default="desktop",
                    help="desktop = janela nativa com web embarcada (padrao); "
                         "server = so o servidor local (desenvolvimento)")
    ap.add_argument("--port", type=int, default=8765,
                    help="porta do servidor web local (padrao 8765)")
    a = ap.parse_args(argv)

    if a.remove_all:
        ok, summary = printer_install.remove_all_printers(
            keep_virtual=not a.include_virtual, remove_ports=True,
            remove_drivers=a.remove_drivers, log=print)
        print(summary)
        sys.exit(0 if ok else 1)
    if a.scan is not None:
        cli_scan(a.scan or None)
    elif a.test_ip:
        cli_test_ip(a.test_ip)
    elif a.install:
        if not a.driver:
            print('Informe --driver "Nome exato do driver PCL" (nunca generico).')
            sys.exit(2)
        cli_install(a.install, a.driver, a.inf, a.nome, a.porta)
    else:
        if a.mode == "desktop":
            # Instancia unica: duas janelas brigariam pela fila de
            # impressoras e pela varredura ao mesmo tempo.
            from app.platform.instance_mutex import InstanceMutex
            mutex = InstanceMutex()
            if not mutex.acquire():
                print("Ja existe uma Forja de Impressoras em execucao.")
                print("Feche a outra janela antes de abrir outra.")
                return
        launch_web(port=a.port, mode=a.mode)


if __name__ == "__main__":
    main()
