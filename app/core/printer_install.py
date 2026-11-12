"""
Instalacao da impressora no Windows:
  pnputil (stage .inf) -> Add-PrinterDriver -> Add-PrinterPort (TCP/IP) -> Add-Printer -> pagina de teste
Exige execucao como Administrador.
"""
import re

from app.platform import process as winproc

from .driver_manager import is_generic_name


def run_ps(cmd, timeout=120):
    r = winproc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def is_admin():
    try:
        rc, out = run_ps("[bool]([Security.Principal.WindowsIdentity]::GetCurrent().Groups -match 'S-1-5-32-544')")
        if rc != 0:
            return False
        return "true" in (out or "").lower()
    except Exception:
        return False


def check_admin():
    """Retorna True se admin."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def stage_inf(inf_path, timeout=180):
    rc = winproc.run(["pnputil", "/add-driver", inf_path, "/install"],
                        capture_output=True, text=True, timeout=timeout)
    out = (rc.stdout or "") + (rc.stderr or "")
    return rc.returncode == 0, out


def driver_present(driver_name, timeout=60):
    safe = (driver_name or "").replace("'", "''")
    code, out = run_ps(f"Get-PrinterDriver -Name '{safe}' 2>&1 | Out-String", timeout=timeout)
    return code == 0 and (driver_name or "").lower() in (out or "").lower()


def add_printer_driver(driver_name, inf_path=None, timeout=180):
    if is_generic_name(driver_name or ""):
        return False, "BLOQUEADO: driver generico nao permitido."
    safe = (driver_name or "").replace("'", "''")
    log = []
    # 0) stage via pnputil (precisa do pacote no DriverStore)
    if inf_path:
        ok, out = stage_inf(inf_path)
        log.append(out.strip()[:800])
    if driver_present(driver_name):
        return True, "\n".join(log) + "\nDriver ja registrado no Windows."
    # A) Add-PrinterDriver com INF (caminho padrao)
    if inf_path:
        code, out = run_ps(
            f"$inf='{inf_path}'.Replace(\"'\",\"''\"); "
            f"Add-PrinterDriver -Name '{safe}' -InfPath \"$inf\" 2>&1 | Out-String",
            timeout=timeout)
        log.append(out.strip()[:1500])
        if driver_present(driver_name):
            return True, "\n".join(log)
    # B) printui /ia (metodo classico; resolve INFs que o Add-PrinterDriver rejeita, ex: UPD -> 0x80070057)
    if inf_path:
        try:
            r = winproc.run(
                ["rundll32", "printui.dll,PrintUIEntry", "/ia",
                 "/m", driver_name, "/h", "x64", "/v", "3", "/f", inf_path, "/q"],
                capture_output=True, text=True, timeout=timeout)
            msg = (r.stdout or "") + (r.stderr or "")
            log.append(("printui /ia rc=%s " % r.returncode + msg).strip()[:800])
        except Exception as e:
            log.append(f"printui /ia excecao: {e}")
        if driver_present(driver_name):
            return True, "\n".join(log)
    # C) instalador oficial do pacote (ex: Install.exe do HP UPD com /q)
    if inf_path:
        try:
            from pathlib import Path
            root = Path(inf_path).parent
            inst = root / "Install.exe"
            if not inst.exists():
                cands = list(root.glob("Install.exe"))
                if not cands:
                    cands = [p for p in root.glob("*/Install.exe")]
                if not cands:
                    cands = [p for p in root.glob("*/*/Install.exe")]
                inst = cands[0] if cands else None
            if inst:
                r = winproc.run([str(inst), "/q"], capture_output=True, text=True,
                                   timeout=180, cwd=str(inst.parent))
                log.append(f"Install.exe /q rc={r.returncode} {(r.stdout or '')[:400]}")
                code2, out2 = run_ps(
                    f"Add-PrinterDriver -Name '{safe}' 2>&1 | Out-String", timeout=timeout)
                log.append(out2.strip()[:800])
        except Exception as e:
            log.append(f"Install.exe excecao: {e}")
        if driver_present(driver_name):
            return True, "\n".join(log)
    # D) Add-PrinterDriver pelo nome (pacote ja no store)
    code, out = run_ps(f"Add-PrinterDriver -Name '{safe}' 2>&1 | Out-String", timeout=timeout)
    log.append(out.strip()[:800])
    return driver_present(driver_name), "\n".join(log)


def ensure_tcp_port(ip, port_number=9100, timeout=60):
    pname = f"TCPIPE:{ip}"
    safe = pname.replace("'", "''")
    code, out = run_ps(
        f"$ErrorActionPreference='Stop'; try {{ $p=Get-PrinterPort -Name '{safe}' -ErrorAction SilentlyContinue; "
        f"if(-not $p){{ Add-PrinterPort -Name '{safe}' -PrinterHostAddress '{ip}' -PortNumber {port_number} }} "
        f"else {{ Set-PrinterPort -Name '{safe}' -PrinterHostAddress '{ip}' -PortNumber {port_number} }}; "
        f"$ok=Get-PrinterPort -Name '{safe}' -ErrorAction Stop; 'PORTA-OK:'+$ok.Name }} catch {{ 'PORTA-FALHA:'+$_.Exception.Message }}",
        timeout=timeout)
    ok = "PORTA-OK:" in (out or "")
    return ok, out, pname


def install_printer(printer_name, driver_name, port_name, timeout=60):
    if is_generic_name(driver_name or ""):
        return False, "BLOQUEADO: driver generico nao permitido."
    pn = printer_name.replace("'", "''")
    dn = driver_name.replace("'", "''")
    pt = port_name.replace("'", "''")
    code, out = run_ps(
        f"$ErrorActionPreference='Stop'; try {{ "
        f"$e=Get-Printer -Name '{pn}' -ErrorAction SilentlyContinue; "
        f"if($e){{ Rename-Printer -Name '{pn}' -NewName '{pn}__backup__' -ErrorAction SilentlyContinue }}; "
        f"Add-Printer -Name '{pn}' -DriverName '{dn}' -PortName '{pt}' -ErrorAction Stop; "
        f"$ok=Get-Printer -Name '{pn}' -ErrorAction Stop; "
        f"if($ok.DriverName -ne '{dn}' -or $ok.PortName -ne '{pt}'){{ throw 'verificacao pos-instalacao divergiu' }}; "
        f"if(Get-Printer -Name '{pn}__backup__' -ErrorAction SilentlyContinue){{ Remove-Printer -Name '{pn}__backup__' -Confirm:$false }}; "
        f"'INSTALACAO-OK'; Get-Printer -Name '{pn}' | Format-List Name,DriverName,PortName,PrinterStatus | Out-String }} "
        f"catch {{ if(Get-Printer -Name '{pn}__backup__' -ErrorAction SilentlyContinue){{ Rename-Printer -Name '{pn}__backup__' -NewName '{pn}' -ErrorAction SilentlyContinue }}; 'INSTALACAO-FALHA:'+$_.Exception.Message }}",
        timeout=timeout)
    txt = out or ""
    ok = "INSTALACAO-OK" in txt
    return ok, out


def print_test_page(printer_name, timeout=60):
    pn = printer_name.replace("'", "''")
    # tenta WMI PrintTestPage, fallback printui /k
    code, out = run_ps(
        f"$p=Get-CimInstance Win32_Printer -Filter \"Name='{pn}'\"; "
        f"if($p){{ $r=$p | Invoke-CimMethod -MethodName PrintTestPage; $r | Out-String }} "
        f"else {{ 'Impressora nao encontrada' }}",
        timeout=timeout)
    if code == 0 and ("ReturnValue = 0" in out or "ReturnValue: 0" in out):
        return True, out
    # fallback
    try:
        r = winproc.run(["rundll32", "printui.dll,PrintUIEntry", "/k", "/n", printer_name],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, out + f"\n{e}"


def full_install(ip, fabricante, modelo, driver_name, inf_path=None, printer_name=None,
                 port_number=9100, log=None):
    """Pipeline completo. Retorna (ok, mensagens)."""
    msgs = []

    def say(m):
        msgs.append(m)
        if log:
            try:
                log(m)
            except Exception:
                pass

    if is_generic_name(driver_name or ""):
        say("ERRO: driver generico bloqueado. Aborte.")
        return False, "\n".join(msgs)

    try:
        if not check_admin():
            say("[!] SEM privilegio de Administrador — pnputil/Add-Printer vao falhar. Use run.bat.")
    except Exception:
        pass

    if not printer_name:
        printer_name = f"{fabricante} {modelo} ({ip})".strip()
        printer_name = re.sub(r"\s+", " ", printer_name)[:80]

    say(f"[1/4] Driver: {driver_name} ({'INF: ' + inf_path if inf_path else 'inbox'})")
    ok, out = add_printer_driver(driver_name, inf_path)
    say(out.strip()[:2000])
    if not ok:
        say("FALHA ao registrar driver. Verifique o .inf (PCL6 do modelo) e rode como Administrador.")
        return False, "\n".join(msgs)

    say(f"[2/4] Porta TCP/IP: {ip}:{port_number}")
    ok, out, port_name = ensure_tcp_port(ip, port_number)
    say(out.strip()[:1500])
    if not ok:
        say("FALHA ao criar porta TCP/IP.")
        return False, "\n".join(msgs)

    say(f"[3/4] Criando impressora '{printer_name}'")
    ok, out = install_printer(printer_name, driver_name, port_name)
    say(out.strip()[:2000])
    if not ok:
        say("FALHA ao adicionar impressora.")
        return False, "\n".join(msgs)

    say("[4/4] Imprimindo pagina de teste...")
    ok, out = print_test_page(printer_name)
    say(out.strip()[:1500])
    say("OK: impressora instalada." if ok else "Instalada, mas a pagina de teste falhou (verifique papel/conexao).")
    return True, "\n".join(msgs)


# ---------------- USB ----------------
def usb_ports(timeout=60):
    """Portas USB de impressora existentes no sistema (USB001, USB002...)."""
    code, out = run_ps(
        "Get-PrinterPort | Where-Object { $_.Name -like 'USB*' } | "
        "Select-Object -ExpandProperty Name 2>&1 | Out-String", timeout=timeout)
    return [l.strip() for l in (out or "").splitlines()
            if l.strip() and not l.strip().startswith(("Get-", "Exception", "At "))]


def free_usb_port(timeout=60):
    """Primeira porta USB nao usada por nenhuma fila de impressora."""
    ports = usb_ports(timeout)
    if not ports:
        return None
    try:
        used = {p.get("port") for p in list_printers(timeout)}
    except Exception:
        used = set()
    for p in ports:
        if p not in used:
            return p
    return None


def find_printer_by_name(name, timeout=60):
    """Retorna a fila de impressora com esse nome (ou None)."""
    for p in list_printers(timeout):
        if (p.get("name") or "").lower() == (name or "").lower():
            return p
    return None


def install_usb_printer(printer_name, driver_name, inf_path=None, port_name=None,
                        log=None, timeout=300):
    """Instala uma impressora USB.

    Fluxo:
      1) pnputil /add-driver <inf> /install  -> instala o driver PnP e cria a porta USB
      2) Add-PrinterDriver -Name <driver>    -> registra o driver na fila do Windows
      3) Add-Printer -Name <nome> -DriverName <driver> -PortName USB00x
      4) pagina de teste
    Retorna (ok, mensagens)."""
    msgs = []

    def say(m):
        msgs.append(str(m))
        if log:
            try:
                log(m)
            except Exception:
                pass

    if is_generic_name(driver_name or ""):
        say("ERRO: driver generico bloqueado. Aborte.")
        return False, "\n".join(msgs)
    if not printer_name:
        printer_name = f"{driver_name} (USB)"
    safe = printer_name.replace("'", "''")
    dsafe = (driver_name or "").replace("'", "''")

    say(f"[1/4] Driver PnP USB: {driver_name}"
        + (f" (INF: {inf_path})" if inf_path else ""))

    # 1) driver PnP: pnputil cria/atualiza a porta USB do dispositivo
    if inf_path:
        try:
            ok, out = stage_inf(inf_path, timeout=timeout)
            say(("OK" if ok else "FALHA") + " pnputil /add-driver: " + out.strip()[:700])
        except Exception as e:
            say(f"ERRO pnputil: {e}")

    # 2) registrar o driver na fila de drivers do Windows
    if not driver_present(driver_name):
        ok, out = add_printer_driver(driver_name, inf_path, timeout=timeout)
        say(("OK" if ok else "FALHA") + " Add-PrinterDriver: " + out.strip()[:900])
        if not ok:
            say("FALHA ao registrar o driver USB.")
            return False, "\n".join(msgs)
    else:
        say("Driver ja registrado no Windows.")

    # 3) criar (ou reaproveitar) a fila de impressora
    existing = find_printer_by_name(printer_name)
    if existing:
        if (existing.get("driver") or "") == driver_name:
            say(f"Fila '{printer_name}' ja existe com o driver correto (porta {existing.get('port')}).")
        else:
            say(f"Fila '{printer_name}' ja existe mas com driver '{existing.get('driver')}' "
                f"(esperado '{driver_name}'). Mantida sem recriar; atualize o driver manualmente se necessario.")
    else:
        port = port_name or free_usb_port()
        if not port:
            say("ERRO: nenhuma porta USB disponivel. O Windows nao criou a porta "
                "USB — verifique o cabo / outro dispositivo na porta / reinstale o driver.")
            return False, "\n".join(msgs)
        say(f"[3/4] Criando fila '{printer_name}' na porta {port}")
        code, out = run_ps(
            f"$ErrorActionPreference='Stop'; try {{ "
            f"$e=Get-Printer -Name '{safe}' -ErrorAction SilentlyContinue; "
            f"if(-not $e){{ Add-Printer -Name '{safe}' -DriverName '{dsafe}' "
            f"-PortName '{port}' -ErrorAction Stop }}; "
            f"$ok=Get-Printer -Name '{safe}' -ErrorAction Stop; "
            f"'USB-OK:'+$ok.PortName }} catch {{ 'USB-FALHA:'+$_.Exception.Message }}",
            timeout=timeout)
        txt = (out or "")
        if "USB-OK:" not in txt:
            say("FALHA ao criar a fila USB: " + txt.strip()[:700])
            return False, "\n".join(msgs)
        say(txt.strip()[:700])

    # 4) pagina de teste
    say("[4/4] Imprimindo pagina de teste...")
    ok, out = print_test_page(printer_name)
    say(out.strip()[:700])
    say("OK: impressora USB instalada." if ok
        else "Instalada, mas a pagina de teste falhou (verifique papel/conexao).")
    return True, "\n".join(msgs)


# ---------------- REMOCAO ----------------
VIRTUAL_PRINTER_HINTS = [
    "microsoft print to pdf", "microsoft xps", "onenote", "microsoft shared fax",
    "fax", "pdf24", "adobe pdf", "remote desktop easy print",
]


def is_virtual_printer(name: str, driver: str = "", port: str = "") -> bool:
    blob = f"{name} {driver} {port}".lower()
    return any(h in blob for h in VIRTUAL_PRINTER_HINTS)


def list_printers(timeout=60):
    """Lista impressoras instaladas. Retorna [{name, driver, port, shared}]."""
    code, out = run_ps(
        "Get-Printer | Select-Object Name,DriverName,PortName,Shared | "
        "ConvertTo-Json -Compress 2>&1 | Out-String", timeout=timeout)
    import json
    try:
        txt = (out or "").strip()
        m = None
        import re as _re
        for pat in (r"\[.*\]", r"\{.*\}"):
            mm = _re.search(pat, txt, _re.S)
            if mm:
                m = mm.group(0)
                break
        if not m:
            return []
        data = json.loads(m)
        if isinstance(data, dict):
            data = [data]
        return [{"name": d.get("Name", ""), "driver": d.get("DriverName", ""),
                 "port": d.get("PortName", ""), "shared": bool(d.get("Shared"))}
                for d in data if d.get("Name")]
    except Exception:
        return []


def is_removable_port(port_name: str) -> bool:
    """So portas de REDE de impressora IP (nunca LPT/COM/USB/FILE/NUL/PORTPROMPT)."""
    n = (port_name or "").strip()
    if n.upper().startswith("TCPIPE:"):
        return True
    low = n.lower()
    if low.startswith("ip_") or low.startswith("wsd"):
        return True
    # porta IP pura criada pelo assistente do Windows: 192.168.15.91 ou 192.168.15.199_3
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}(_\d+)?$", n):
        return True
    return False


def remove_printer(name, timeout=60):
    safe = (name or "").replace("'", "''")
    code, out = run_ps(f"Remove-Printer -Name '{safe}' -Confirm:$false 2>&1 | Out-String",
                       timeout=timeout)
    return code == 0, out.strip()


def remove_printer_port(port_name, timeout=60):
    safe = (port_name or "").replace("'", "''")
    code, out = run_ps(
        f"$u=(Get-Printer | Where-Object {{$_.PortName -eq '{safe}'}}); "
        f"if($u){{ 'EM USO por: ' + ($u.Name -join ', ') }} "
        f"else {{ Remove-PrinterPort -Name '{safe}' -Confirm:$false; 'REMOVIDA' }}",
        timeout=timeout)
    txt = out.strip()
    return ("REMOVIDA" in txt, txt)


def remove_all_printers(keep_virtual=True, remove_ports=True, remove_drivers=False, log=None):
    """Remove impressoras (todas ou exceto virtuais) + portas de rede orfas + (opc) drivers orfaos.
    Retorna (ok, resumo)."""
    msgs = []

    def say(m):
        msgs.append(m)
        if log:
            try:
                log(m)
            except Exception:
                pass

    printers = list_printers()
    say(f"Impressoras encontradas: {len(printers)}")
    targets = [p for p in printers
               if not (keep_virtual and is_virtual_printer(p["name"], p["driver"], p["port"]))]
    skipped = len(printers) - len(targets)
    if skipped:
        say(f"Mantidas (virtuais do Windows): {skipped}")
    if not targets:
        say("Nada a remover.")

    used_ports = {p["port"] for p in targets if p["port"]}
    ok_n, fail = 0, []
    for p in targets:
        ok, out = remove_printer(p["name"])
        if ok:
            ok_n += 1
            say(f"Removida: {p['name']}")
        else:
            fail.append(p["name"])
            say(f"FALHOU: {p['name']} — {out[:300]}")

    ports_removed = []
    if remove_ports:
        remaining = {p["port"] for p in list_printers() if p["port"]}
        for port in sorted(used_ports):
            if not port or port in remaining:
                continue
            if not is_removable_port(port):
                say(f"Porta preservada (sistema): {port}")
                continue
            ok, out = remove_printer_port(port)
            if ok:
                ports_removed.append(port)
                say(f"Porta removida: {port}")
            else:
                say(f"Porta mantida: {port} ({out[:150]})")

    if remove_drivers:
        code, out = run_ps(
            "Get-PrinterDriver | Where-Object { $_.Name -notlike 'Microsoft*' } | "
            "ForEach-Object { $n=$_.Name; "
            "$u=(Get-Printer | Where-Object {$_.DriverName -eq $n}); "
            "if(-not $u){ Remove-PrinterDriver -Name $n -Confirm:$false; \"DRIVER REMOVIDO: $n\" } "
            "else { \"DRIVER EM USO: $n\" } } | Out-String")
        say(out.strip()[:2000])

    say(f"Resumo: {ok_n} impressora(s) removida(s), {len(fail)} falha(s), "
        f"{len(ports_removed)} porta(s) removida(s).")
    return (len(fail) == 0), "\n".join(msgs)
