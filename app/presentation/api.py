"""
Camada de negocio do frontend web: liga a API HTTP ao backend existente
(scanner / driver_manager / printer_install) e publica eventos ao vivo
(log, progresso, lista de impressoras) via SSE.
"""
import datetime
import json
import queue
import threading
from pathlib import Path

from app.core import driver_manager, printer_install, scanner
from app.data import paths

BASE = paths.base_dir()


# --------------------------------------------------------------------------
# BUSCA DE EVENTOS (SSE)
# --------------------------------------------------------------------------
class EventBus:
    def __init__(self):
        self._subs = []
        self._lock = threading.Lock()
        self.history = []

    def subscribe(self):
        q = queue.Queue(maxsize=4000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, etype, payload):
        msg = {"type": etype, "data": payload}
        with self._lock:
            self.history.append(msg)
            if len(self.history) > 800:
                del self.history[:400]
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def snapshot(self):
        with self._lock:
            return list(self.history)


# --------------------------------------------------------------------------
# ESTADO
# --------------------------------------------------------------------------
class State:
    def __init__(self):
        self.bus = EventBus()
        self.printers = []
        self.checked = set()
        self.busy = None
        try:
            from app.data import config as _cfg
            self.auto_download = bool(_cfg.get("auto_download", True))
        except Exception:
            self.auto_download = True
        self.last_error = None
        self._load_last_scan()

    def _load_last_scan(self):
        scan_file = paths.scan_result_path()
        if scan_file.is_file():
            try:
                data = json.loads(scan_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    for p in data:
                        p.setdefault("uid", p.get("ip", ""))
                        p.setdefault("conexao", "rede")
                        # Re-resolve COM download permitido: o pack pode ja
                        # estar em cache (./drivers/_downloads) e o usuario
                        # espera ver o driver resolvido ao abrir o app —
                        # nao um falso "pendente".
                        if "_drv" not in p or not (p.get("_drv") or {}).get("driver_name"):
                            try:
                                if p.get("conexao") == "usb":
                                    from app.core import usb_scanner as _u
                                    p["_drv"] = driver_manager.resolve_usb_driver(
                                        {"nome": p.get("modelo_canonico") or p.get("modelo", ""),
                                         "device_id": p.get("usb_device_id"),
                                         "hardware_ids": p.get("usb_hardware_ids"),
                                         "fabricante": p.get("fabricante"),
                                         "modelo": p.get("modelo_canonico") or p.get("modelo", ""),
                                         "fila": {}},
                                        allow_download=self.auto_download)
                                else:
                                    p["_drv"] = driver_manager.resolve_driver(
                                        p.get("fabricante", ""), p.get("modelo", ""),
                                        p.get("modelo_canonico"),
                                        allow_download=self.auto_download)
                            except Exception:
                                p["_drv"] = {"origem": "pendente", "driver_name": None}
                    self.printers = data
                    self.checked = {p.get("uid") or p.get("ip") for p in data}
            except Exception:
                pass


STATE = State()


# --------------------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------------------
def level_of(msg):
    m = str(msg).strip()
    if m.startswith(("ERRO", "FALH", "BLOQUEAD", "PULADA")):
        return "err"
    if m.startswith("===") or "impressora" in m.lower()[:40]:
        return "hl"
    if m.startswith(("OK", "Removida", "Porta removida", "DRIVER REMOVIDO",
                     "pagina de teste ENVIADA", "Concluido", "Resumo")):
        return "ok"
    if m.startswith(("AVISO", "FALTA", "Porta mantida", "Preservada", "Mantida")):
        return "warn"
    return None


def log(msg, level=None):
    STATE.bus.publish("log", {"text": str(msg), "level": level or level_of(msg)})


def status(msg, a=0, t=1):
    pct = int(a * 100 / max(t, 1))
    STATE.bus.publish("status", {"text": str(msg), "pct": pct})


def _public(p):
    """Serializa uma impressora para o frontend."""
    drv = p.get("_drv") or {}
    return {
        "uid": p.get("uid") or p.get("ip", ""),
        "conexao": p.get("conexao", "rede"),
        "ip": p.get("ip", ""),
        "hostname": p.get("hostname", ""),
        "mac": p.get("mac", ""),
        "portas": p.get("portas", []),
        "fabricante": p.get("fabricante", ""),
        "modelo": p.get("modelo", ""),
        "modelo_canonico": p.get("modelo_canonico") or p.get("modelo", ""),
        "confianca_modelo": p.get("confianca_modelo", "baixa"),
        "serial": p.get("serial", ""),
        "snmp_ok": bool(p.get("snmp_ok")),
        "ews_modelo": p.get("ews_modelo", ""),
        "ipp_modelo": p.get("ipp_modelo", ""),
        "motivo": p.get("motivo", ""),
        "sys_descr": p.get("sys_descr", ""),
        "usb_device_id": p.get("usb_device_id", ""),
        "usb_hardware_ids": p.get("usb_hardware_ids", []),
        "usb_port": p.get("usb_port", ""),
        "usb_instalada": bool(p.get("usb_instalada")),
        "driver": {
            "origem": drv.get("origem", "pendente"),
            "driver_name": drv.get("driver_name"),
            "detalhe": drv.get("detalhe", ""),
            "inf": drv.get("inf"),
        },
    }


def publish_printers():
    STATE.bus.publish("printers", {
        "printers": [_public(p) for p in STATE.printers],
        "checked": sorted(STATE.checked),
    })


def publish_printer(p):
    STATE.bus.publish("printer", _public(p))


def publish_busy():
    STATE.bus.publish("busy", {"busy": STATE.busy})


def find_printer(ip):
    for p in STATE.printers:
        if (p.get("uid") or p.get("ip")) == ip:
            return p
    return None


def build_usb_printers(allow_download=True):
    """Monta as impressoras USB conectadas (PnP classe Printer)."""
    try:
        from app.core import usb_scanner
    except Exception:
        return []
    try:
        devices = usb_scanner.list_usb_devices()
        queues = usb_scanner.list_usb_queues()
    except Exception as e:
        log(f"ERRO ao detectar impressoras USB: {e}")
        return []

    out = []
    for d in devices:
        modelo = usb_scanner.model_from_device(d)
        fab = usb_scanner.vendor_from_device(d, modelo)
        fila = usb_scanner.match_queue(d, queues)
        dev = {
            "nome": d.get("nome", ""),
            "device_id": d.get("device_id", ""),
            "hardware_ids": d.get("hardware_ids", []),
            "fabricante": fab,
            "modelo": modelo,
            "fila": fila or {},
        }
        try:
            info = driver_manager.resolve_usb_driver(
                dev, allow_download=allow_download, log=log)
        except Exception as e:
            info = {"origem": "pendente", "driver_name": None,
                    "detalhe": str(e), "inf": None}
        motivo = f"dispositivo USB PnP detectado ({d.get('device_id','')})"
        if fila:
            motivo += f" | fila já instalada: {fila.get('nome')} (porta {fila.get('porta')})"
        out.append({
            "uid": "usb:" + d.get("device_id", ""),
            "conexao": "usb",
            "ip": "",
            "hostname": "",
            "mac": "",
            "portas": [],
            "fabricante": fab,
            "modelo": modelo,
            "modelo_canonico": modelo,
            "confianca_modelo": "alta" if fila else "media",
            "serial": "",
            "snmp_ok": False,
            "ews_modelo": "",
            "ipp_modelo": "",
            "motivo": motivo,
            "usb_device_id": d.get("device_id", ""),
            "usb_hardware_ids": d.get("hardware_ids", []),
            "usb_port": (fila or {}).get("porta", ""),
            "usb_instalada": bool(fila),
            "_drv": info,
        })
    return out


def local_networks():
    try:
        from app.core.network import get_all_local_networks
        return get_all_local_networks()
    except Exception:
        return []


def is_admin():
    try:
        return bool(printer_install.check_admin())
    except Exception:
        return False


def snapshot():
    return {
        "printers": [_public(p) for p in STATE.printers],
        "checked": sorted(STATE.checked),
        "busy": STATE.busy,
        "admin": is_admin(),
        "auto_download": STATE.auto_download,
        "networks": local_networks(),
    }


def set_auto_download(value: bool):
    """Aplica e persiste a preferencia de download automatico."""
    STATE.auto_download = bool(value)
    try:
        from app.data import config as _cfg
        _cfg.set_value("auto_download", STATE.auto_download)
    except Exception:
        pass
    return STATE.auto_download


# --------------------------------------------------------------------------
# ACOES
# --------------------------------------------------------------------------
def start_scan(cidrs=None):
    if STATE.busy:
        return {"ok": False, "error": "Já existe uma operação em andamento."}
    STATE.busy = "scan"
    publish_busy()
    threading.Thread(target=_scan_worker, args=(cidrs,), daemon=True).start()
    return {"ok": True}


def _scan_worker(cidrs):
    alvo = cidrs or "todas as sub-redes locais"
    log(f"Varrendo {alvo} ...", "hl")

    def cb(a, t, m):
        status(m, a, t)

    try:
        printers = scanner.scan_network(cidrs=cidrs or None, progress_cb=cb)
    except Exception as e:
        log(f"ERRO no scan: {e}", "err")
        printers = []

    for p in printers:
        p.setdefault("uid", p.get("ip", ""))
        p.setdefault("conexao", "rede")

    # impressoras USB conectadas (PnP) — mesma lista, outra conexao
    status("Verificando impressoras USB conectadas...", 0, 1)
    try:
        usb = build_usb_printers(allow_download=STATE.auto_download)
    except Exception as e:
        log(f"ERRO ao detectar impressoras USB: {e}", "err")
        usb = []
    printers.extend(usb)
    if usb:
        log(f"{len(usb)} impressora(s) USB detectada(s) via PnP.", "hl")

    try:
        paths.scan_result_path().write_text(
            json.dumps(printers, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    STATE.printers = printers
    STATE.checked = {(p.get("uid") or p.get("ip")) for p in printers}
    publish_printers()

    if not printers:
        log("Nenhuma impressora encontrada.", "warn")
        status("Nenhuma impressora encontrada. Verifique rede/VLAN e SNMP.", 1, 1)
        STATE.busy = None
        publish_busy()
        return

    log(f"Encontradas {len(printers)} impressora(s). Resolvendo drivers PCL...", "hl")
    status("Resolvendo drivers PCL específicos...", 0, len(printers))
    for i, p in enumerate(printers):
        rotulo = p.get("ip") or p.get("modelo_canonico") or p.get("modelo", "")
        if p.get("conexao") == "usb":
            # USB ja chega com o driver resolvido por HardwareID — nao
            # sobrescreve com o caminho de rede (que nao entende PnP).
            info = p.get("_drv") or {"origem": "pendente", "driver_name": None,
                                     "detalhe": "sem driver", "inf": None}
        else:
            try:
                info = driver_manager.resolve_driver(
                    p["fabricante"], p["modelo"], p.get("modelo_canonico"),
                    allow_download=STATE.auto_download, log=log)
            except Exception as e:
                log(f"ERRO ao resolver driver de {rotulo}: {e}", "err")
                info = {"origem": "pendente", "driver_name": None,
                        "detalhe": str(e), "inf": None}
        p["_drv"] = info
        canon = p.get("modelo_canonico") or p["modelo"]
        log(f"{rotulo}  {canon[:70]}  ->  [{info.get('origem')}] "
            f"{info.get('driver_name') or (info.get('detalhe') or '')[:100]}")
        publish_printer(p)
        status(f"Resolvendo drivers ({i + 1}/{len(printers)})", i + 1, len(printers))

    status(f"{len(printers)} impressora(s) pronta(s). Marque as desejadas e clique em Instalar.",
           1, 1)
    # Salva DE NOVO apos a resolucao: o arquivo passa a conter o _drv e a
    # proxima abertura mostra o driver certo imediatamente (sem re-resolver).
    try:
        paths.scan_result_path().write_text(
            json.dumps(printers, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    STATE.busy = None
    publish_busy()


def start_test_ip(ip):
    ip = (ip or "").strip()
    if not ip:
        return {"ok": False, "error": "Informe um IP."}

    def worker():
        log(f"Testando IP manual {ip} ...", "hl")
        try:
            r = scanner.check_single_ip(ip)
        except Exception as e:
            log(f"ERRO ao testar {ip}: {e}", "err")
            r = None
        if not r:
            log(f"{ip}: NAO e impressora (sem portas/assinatura de impressao).", "warn")
            status(f"{ip} nao e impressora.", 1, 1)
            return
        log(f"{ip}: IMPRESSORA {r['fabricante']} "
            f"{r.get('modelo_canonico') or r['modelo']}", "ok")
        r.setdefault("uid", r.get("ip", ip))
        r.setdefault("conexao", "rede")
        if not find_printer(ip):
            STATE.printers.append(r)
            STATE.checked.add(r.get("uid") or r.get("ip"))
        try:
            info = driver_manager.resolve_driver(
                r["fabricante"], r["modelo"], r.get("modelo_canonico"),
                allow_download=STATE.auto_download, log=log)
        except Exception as e:
            info = {"origem": "pendente", "driver_name": None,
                    "detalhe": str(e), "inf": None}
        r["_drv"] = info
        publish_printers()
        publish_printer(r)
        status(f"{ip} adicionada a lista.", 1, 1)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def start_resolve():
    if not STATE.printers:
        return {"ok": False, "error": "Rode uma varredura antes."}

    def worker():
        log("Re-resolvendo drivers PCL...", "hl")
        for i, p in enumerate(STATE.printers):
            if p.get("conexao") == "usb":
                try:
                    info = driver_manager.resolve_usb_driver(
                        {"nome": p.get("modelo_canonico") or p.get("modelo", ""),
                         "device_id": p.get("usb_device_id"),
                         "hardware_ids": p.get("usb_hardware_ids"),
                         "fabricante": p.get("fabricante"),
                         "modelo": p.get("modelo_canonico") or p.get("modelo", ""),
                         "fila": {}},
                        allow_download=STATE.auto_download, log=log)
                except Exception as e:
                    info = {"origem": "pendente", "driver_name": None,
                            "detalhe": str(e), "inf": None}
            else:
                try:
                    info = driver_manager.resolve_driver(
                        p["fabricante"], p["modelo"], p.get("modelo_canonico"),
                        allow_download=STATE.auto_download, log=log)
                except Exception as e:
                    info = {"origem": "pendente", "driver_name": None,
                            "detalhe": str(e), "inf": None}
            p["_drv"] = info
            publish_printer(p)
            status(f"Re-resolvendo ({i + 1}/{len(STATE.printers)})",
                   i + 1, len(STATE.printers))
        publish_printers()
        status("Drivers re-resolvidos.", 1, 1)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def start_install(uids):
    if not uids:
        return {"ok": False, "error": "Nenhuma impressora marcada."}
    if not is_admin():
        return {"ok": False, "error": "Sem Administrador: use run.bat para elevar."}
    if STATE.busy:
        return {"ok": False, "error": "Já existe uma operação em andamento."}
    STATE.busy = "install"
    publish_busy()
    threading.Thread(target=_install_worker, args=(list(uids),), daemon=True).start()
    return {"ok": True}


def _install_worker(uids):
    oks, fails = 0, []
    total = len(uids)
    for i, uid in enumerate(uids):
        p = find_printer(uid)
        if not p:
            continue
        canon = p.get("modelo_canonico") or p["modelo"]
        info = p.get("_drv") or {}
        if not info.get("driver_name"):
            try:
                if p.get("conexao") == "usb":
                    info = driver_manager.resolve_usb_driver(
                        {"nome": canon, "device_id": p.get("usb_device_id"),
                         "hardware_ids": p.get("usb_hardware_ids"),
                         "fabricante": p.get("fabricante"), "modelo": canon},
                        allow_download=STATE.auto_download, log=log)
                else:
                    info = driver_manager.resolve_driver(
                        p["fabricante"], p["modelo"], canon,
                        allow_download=STATE.auto_download, log=log)
                p["_drv"] = info
            except Exception as e:
                info = {"origem": "pendente", "driver_name": None,
                        "detalhe": str(e), "inf": None}
        drv = info.get("driver_name")
        inf = info.get("inf")
        usb = p.get("conexao") == "usb"
        rotulo = p.get("ip") or canon
        log("")
        log(f"=== {rotulo}  {canon} ===", "hl")
        status(f"Instalando {rotulo} ({i + 1}/{total})", i, total)

        if info.get("origem") == "pendente" or not drv:
            log("PULADA: " + (info.get("detalhe") or ""), "err")
            fails.append(uid)
            continue
        if driver_manager.is_generic_name(drv):
            log(f"BLOQUEADA (generico): {drv}", "err")
            fails.append(uid)
            continue

        if usb:
            ok, msgs = printer_install.install_usb_printer(
                f"{canon} (USB)", drv, inf_path=inf,
                log=lambda m: log("  " + m))
        else:
            portas = p.get("portas", [])
            porta = 9100 if 9100 in portas else (515 if 515 in portas else 9100)
            ok, msgs = printer_install.full_install(
                p["ip"], p["fabricante"], canon, drv, inf_path=inf,
                log=lambda m: log("  " + m))
        try:
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            arquivo = (p.get("ip") or "usb").replace(".", "_").replace(":", "_")
            paths.install_log_path(f"{arquivo}_{stamp}").write_text(
                f"Conexao: {'USB' if usb else 'Rede'}\n"
                f"IP: {p.get('ip') or '-'}\nModelo: {canon}\n"
                f"Driver [{info.get('origem')}]: {drv}\nINF: {inf}\n\n{msgs}",
                encoding="utf-8")
        except Exception:
            pass
        if ok:
            oks += 1
        else:
            fails.append(uid)

    resumo = f"Concluido: {oks} instalada(s), {len(fails)} falha(s)"
    if fails:
        resumo += " (" + ", ".join(fails) + ")"
    log(resumo, "ok" if not fails else "err")
    if fails:
        log("Veja o arquivo instalacao_<IP>_<data>.log na pasta do app.", "warn")
    status(resumo, 1, 1)
    STATE.busy = None
    publish_busy()
    STATE.bus.publish("done", {"action": "install", "ok": oks, "fail": len(fails)})


def start_test_page(uids):
    if not uids:
        return {"ok": False, "error": "Nenhuma impressora marcada."}

    def worker():
        import re
        for uid in uids:
            p = find_printer(uid)
            if not p:
                continue
            ip = p.get("ip") or ""
            guess = re.sub(r"\s+", " ",
                           f"{p['fabricante']} "
                           f"{p.get('modelo_canonico') or p.get('modelo', '')} "
                           f"({ip})".strip())[:80]
            _code, lst = printer_install.run_ps(
                "Get-Printer | Select-Object -ExpandProperty Name")
            candidates = [c.strip() for c in (lst or "").splitlines() if c.strip()]
            target = next((c for c in candidates if ip and ip in c),
                          guess if guess in candidates else None)
            if not target:
                log(f"{ip or p.get('modelo')}: impressora ainda nao instalada. "
                    "Instale primeiro.", "warn")
                continue
            ok, _msg = printer_install.print_test_page(target)
            log(f"{target}: pagina de teste {'ENVIADA' if ok else 'FALHOU'}",
                "ok" if ok else "err")
        status("Teste concluido. Veja o log.", 1, 1)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True}


def open_drivers_folder():
    """Abre a pasta de drivers no Explorer (sem janela de console)."""
    import os
    d = paths.drivers_dir()
    os.startfile(str(d))
    return {"ok": True}


def list_installed():
    try:
        printers = printer_install.list_printers()
    except Exception:
        printers = []
    out = []
    for p in printers:
        out.append({
            "name": p.get("name", ""),
            "driver": p.get("driver", ""),
            "port": p.get("port", ""),
            "shared": bool(p.get("shared")),
            "virtual": bool(printer_install.is_virtual_printer(
                p.get("name", ""), p.get("driver", ""), p.get("port", ""))),
        })
    return out


def start_remove(names, keep_virtual=True, remove_ports=True, remove_drivers=False):
    if not names:
        return {"ok": False, "error": "Nada selecionado."}
    if STATE.busy:
        return {"ok": False, "error": "Já existe uma operação em andamento."}
    STATE.busy = "remove"
    publish_busy()
    threading.Thread(target=_remove_worker,
                     args=(list(names), bool(keep_virtual), bool(remove_ports),
                           bool(remove_drivers)), daemon=True).start()
    return {"ok": True}


def _remove_worker(names, keep_virtual, remove_ports, remove_drivers):
    installed = {p["name"]: p for p in list_installed()}
    targets = []
    for n in names:
        info = installed.get(n)
        if info is None:
            continue
        if keep_virtual and info["virtual"]:
            log(f"Preservada (virtual): {n}", "warn")
            continue
        targets.append(info)

    if not targets:
        log("Nada a remover.", "warn")
        status("Nada a remover.", 1, 1)
        STATE.busy = None
        publish_busy()
        return

    ok_n = 0
    used_ports = {t["port"] for t in targets if t.get("port")}
    for i, t in enumerate(targets):
        status(f"Removendo {t['name']} ({i + 1}/{len(targets)})", i, len(targets))
        ok, _ = printer_install.remove_printer(t["name"])
        log(f"{'Removida' if ok else 'FALHOU'}: {t['name']}", "ok" if ok else "err")
        ok_n += 1 if ok else 0

    ports_rm = 0
    if remove_ports:
        remaining = {p["port"] for p in list_installed() if p.get("port")}
        for port in sorted(used_ports):
            if not port or port in remaining:
                continue
            if not printer_install.is_removable_port(port):
                log(f"Porta preservada (sistema): {port}", "warn")
                continue
            ok, _ = printer_install.remove_printer_port(port)
            log(f"{'Porta removida' if ok else 'Porta mantida'}: {port}",
                "ok" if ok else "warn")
            ports_rm += 1 if ok else 0

    if remove_drivers:
        _ok, summary = printer_install.remove_all_printers(
            keep_virtual=True, remove_ports=False, remove_drivers=True)
        for line in summary.splitlines():
            log(line)

    log(f"Resumo: {ok_n} impressora(s) removida(s), {ports_rm} porta(s).", "ok")
    status(f"Remocao: {ok_n}/{len(targets)} impressoras, {ports_rm} portas.", 1, 1)
    STATE.busy = None
    publish_busy()
    STATE.bus.publish("done", {"action": "remove", "ok": ok_n, "fail": 0})
