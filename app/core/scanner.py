"""
Varredura de rede para encontrar impressoras.
Estrategia: subnet local -> ping sweep -> ARP -> checa portas de impressora
(9100 RAW, 515 LPD, 631 IPP, 161 SNMP, 80/443 HTTP) -> valida via SNMP + HTTP.
"""
import ipaddress
import socket
import platform
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.platform import process as winproc

from .snmp_client import (snmp_get, PRINTER_OIDS, OID_SYS_DESCR,
                         OID_SYS_OBJECT_ID)

PRINTER_PORTS = [9100, 515, 631, 161, 80, 443]
# 9100/515 = prova de hardware (JetDirect/LPD). 631 sozinha NAO prova nada:
# pode ser servidor com CUPS. 631 so conta junto de device-id/modelo/EWS.
RAW_PORTS = {9100, 515}

# enterprise OID -> fabricante (sysObjectID 1.3.6.1.4.1.XXXX)
ENTERPRISE_VENDOR = {
    "11": "HP",
    "2636": "Brother",   # tambem usa 2435
    "2435": "Brother",
    "1248": "Epson",
    "1602": "Canon",
    "1347": "Kyocera",
    "367": "Ricoh",
    "253": "Xerox",
    "641": "Lexmark",
    "236": "Samsung",
    "2001": "OKI",
    "10642": "Zebra",
    "4498": "Elgin",
    "22065": "Pantum",
    "10627": "Bematech",
}

KEYWORD_VENDOR = [
    ("hewlett", "HP"), ("laserjet", "HP"), ("officejet", "HP"),
    ("pagewide", "HP"), ("jetdirect", "HP"), ("designjet", "HP"), ("\bhp\b", "HP"),
    ("brother", "Brother"),
    ("epson", "Epson"), ("ecotank", "Epson"),
    ("canon", "Canon"), ("imagerunner", "Canon"), ("imageclass", "Canon"), ("pixma", "Canon"),
    ("kyocera", "Kyocera"), ("ecosys", "Kyocera"),
    ("ricoh", "Ricoh"), ("lanier", "Ricoh"), ("savin", "Ricoh"),
    ("xerox", "Xerox"), ("phaser", "Xerox"), ("versalink", "Xerox"), ("altalink", "Xerox"),
    ("lexmark", "Lexmark"),
    ("samsung", "Samsung"),
    (" oki", "OKI"), ("okidata", "OKI"),
    ("zebra", "Zebra"),
    ("pantum", "Pantum"),
    ("elgin", "Elgin"),
    ("bematech", "Bematech"),
    ("daruma", "Daruma"),
    ("epson", "Epson"),
]


def detect_vendor(sys_descr="", sys_object_id="", extra="", hostname=""):
    blob = f"{sys_descr} {extra}".lower()
    hn = (hostname or "").upper()
    # 0) hostname JetDirect/ZeroConf: NPIxxxxxx = HP, BRN/BROTHER = Brother
    if hn.startswith("NPI") or hn.startswith("HP"):
        return "HP"
    if hn.startswith("BRN") or "BROTHER" in hn:
        return "Brother"
    if hn.startswith("EPSON"):
        return "Epson"
    # 1) enterprise OID
    if sys_object_id:
        m = re.search(r"1\.3\.6\.1\.4\.1\.(\d+)", str(sys_object_id))
        if m and m.group(1) in ENTERPRISE_VENDOR:
            return ENTERPRISE_VENDOR[m.group(1)]
    # 2) keywords
    for kw, vendor in KEYWORD_VENDOR:
        if kw.startswith("\b"):
            if re.search(r"\bhp\b", blob):
                return "HP"
        elif kw in blob:
            return vendor
    return "Desconhecido"


def get_local_subnets():
    """Descobre subnets IPv4 locais a partir do hostname."""
    subnets = set()
    try:
        hostname = socket.gethostname()
        for fam, _, _, _, addr in socket.getaddrinfo(hostname, None):
            if fam == socket.AF_INET:
                ip = addr[0]
                if ip.startswith("127.") or ip.startswith("169.254."):
                    continue
                # assume /24 — sera refinado pela mascara do ipconfig se possivel
                net = ipaddress.ip_network(ip + "/24", strict=False)
                subnets.add(str(net))
    except Exception:
        pass
    if not subnets:
        subnets.add("192.168.0.0/24")
    return sorted(subnets)


def parse_arp_table():
    """Le tabela ARP do SO -> {ip: mac}."""
    out = {}
    try:
        res = winproc.run(["arp", "-a"], capture_output=True, text=True, timeout=15)
        txt = res.stdout or ""
        for m in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-:]{17})", txt):
            ip, mac = m.group(1), m.group(2).replace("-", ":").lower()
            if mac in ("ff:ff:ff:ff:ff:ff", "01:00:5e:00:00:00"):
                continue
            first = int(ip.split(".")[0])
            if first >= 224:  # multicast/reservado (224.0.0.x do ARP) nao e impressora
                continue
            out[ip] = mac
    except Exception:
        pass
    return out


def ping_host(ip, timeout_ms=800):
    system = platform.system().lower()
    if "windows" in system:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", "1", ip]
    try:
        r = winproc.run(cmd, capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def check_port(ip, port, timeout=0.9):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def probe_http_title(ip, timeout=5):
    """Retorna (titulo, modelo_ews, server_header). Usa HTTPS com cert nao-verificado
    (EWS de impressora usa cert autoassinado) e extrai o modelo exato
    da pagina (ex: <strong class="product">HP LaserJet Flow MFP E52645</strong>).
    O server_header ajuda a detectar servidor CUPS (Server: CUPS/2.x)."""
    import ssl
    ctx = ssl._create_unverified_context()
    for scheme in ("https", "http"):
        try:
            url = f"{scheme}://{ip}/"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                server = r.headers.get("Server", "")
                html = r.read(60000).decode("utf-8", errors="ignore")
                if not html.strip():
                    continue
                m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
                title = re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""
                model = ""
                for pat in (r'class="product"[^>]*>([^<]{3,80})<',
                            r'id="HomeDeviceName"[^>]*>([^<]{3,80})<',
                            r'"modelName"\s*:\s*"([^"]{3,80})"',
                            r"Product\s*Name\s*[:<][^A-Za-z0-9]{0,20}([A-Za-z0-9][^<]{2,80})"):
                    mm = re.search(pat, html, re.I)
                    if mm:
                        model = re.sub(r"\s+", " ", mm.group(1)).strip(" -:")[:100]
                        if len(model) >= 4:
                            break
                if not model:
                    low = html.lower()
                    for kw in ("laserjet", "officejet", "pagewide", "designjet",
                               "brother", "epson", "canon", "kyocera", "ricoh",
                               "xerox", "lexmark", "pantum", "elgin", "zebra",
                               "cups"):
                        if kw in low:
                            model = kw
                            break
                if title or model:
                    return title or "Pagina EWS ativa", model, server
        except Exception:
            continue
    return "", "", ""


def ipp_probe(ip, timeout=5):
    """IPP Get-Printer-Attributes (porta 631, so stdlib).
    Retorna dict com printer-make-and-model, printer-name, serial etc."""
    import struct
    out = {}

    def attr(tag, name: bytes, value: bytes) -> bytes:
        return struct.pack("!B", tag) + struct.pack("!H", len(name)) + name + \
            struct.pack("!H", len(value)) + value

    body = struct.pack("!HHi", 0x0101, 0x000B, 1)  # v1.1 Get-Printer-Attributes
    body += b"\x01"  # operation-attributes-tag
    body += attr(0x47, b"attributes-charset", b"utf-8")
    body += attr(0x48, b"attributes-natural-language", b"en")
    body += attr(0x45, b"printer-uri", f"ipp://{ip}/ipp/print".encode())
    body += attr(0x44, b"requested-attributes", b"printer-make-and-model")
    body += attr(0x44, b"", b"printer-name")
    body += attr(0x44, b"", b"printer-serial-number")
    body += attr(0x44, b"", b"printer-location")
    body += attr(0x44, b"", b"printer-device-id")
    body += attr(0x44, b"", b"printer-info")
    body += b"\x03"  # end-of-attributes
    for path in ("/ipp/print", "/ipp/printer", "/ipp", "/"):
        try:
            req = urllib.request.Request(f"http://{ip}:631{path}", data=body,
                                         headers={"Content-Type": "application/ipp",
                                                  "User-Agent": "PrinterInstaller/1.0"},
                                         method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(65535)
            # parse TLV simples
            if len(data) < 8:
                continue
            pos = 8  # pula version/op/request-id
            cur = ""
            while pos < len(data):
                tag = data[pos]
                pos += 1
                if tag in (0x00, 0x01, 0x02, 0x04, 0x05, 0x03):
                    if tag == 0x03:
                        break
                    continue
                if pos + 4 > len(data):
                    break
                nl, = struct.unpack("!H", data[pos:pos + 2])
                pos += 2
                name = data[pos:pos + nl].decode("utf-8", errors="ignore")
                pos += nl
                vl, = struct.unpack("!H", data[pos:pos + 2])
                pos += 2
                val = data[pos:pos + vl].decode("utf-8", errors="replace").strip()
                pos += vl
                if name:
                    cur = name
                if cur and val and cur not in out:
                    out[cur] = val[:200]
            if out:
                out["_ipp_path"] = path
                return out
        except Exception:
            continue
    return out


def guess_model(sys_descr="", hr_descr="", prt_name="", http_title=""):
    for cand in (prt_name, hr_descr, sys_descr, http_title):
        if cand and str(cand).strip() and str(cand).strip().lower() not in ("null", "none"):
            t = re.sub(r"\s+", " ", str(cand)).strip()
            # sysDescr costuma ser verboso: "HP LaserJet M404dn, ..." -> pega ate virgula
            if len(t) > 80:
                t = t.split(",")[0].split(";")[0].strip()
            return t[:100]
    return "Modelo nao identificado"


def scan_host(ip, communities=("public",), do_http=True):
    """Investiga um unico IP. Retorna dict ou None se nao for impressora."""
    ports_open = [p for p in PRINTER_PORTS if check_port(ip, p)]
    if not ports_open:
        return None

    snmp_data = {}
    for comm in communities:
        snmp_data = snmp_get(ip, PRINTER_OIDS, community=comm, timeout=1.2)
        if snmp_data:
            break

    sys_descr = str(snmp_data.get(OID_SYS_DESCR, "") or "")
    sys_oid = str(snmp_data.get(OID_SYS_OBJECT_ID, "") or "")
    hr_descr = str(snmp_data.get("1.3.6.1.2.1.25.3.2.1.3.1", "") or "")
    prt_name = str(snmp_data.get("1.3.6.1.2.1.43.5.1.1.16.1", "") or "")
    serial = str(snmp_data.get("1.3.6.1.2.1.43.5.1.1.17.1", "") or "")

    http_title, ews_model, http_server = ("", "", "")
    if 80 in ports_open or 443 in ports_open:
        try:
            http_title, ews_model, http_server = probe_http_title(ip)
        except Exception:
            pass

    ipp_data = {}
    if 631 in ports_open:
        try:
            ipp_data = ipp_probe(ip)
        except Exception:
            pass
    ipp_model = str(ipp_data.get("printer-make-and-model", "") or "")
    ipp_name = str(ipp_data.get("printer-name", "") or "")
    ipp_serial = str(ipp_data.get("printer-serial-number", "") or "")
    ipp_device_id = str(ipp_data.get("printer-device-id", "") or "")
    ipp_path = str(ipp_data.get("_ipp_path", "") or "")
    if ipp_serial and not serial:
        serial = ipp_serial

    try:
        hostname = socket.gethostbyaddr(ip)[0]
    except Exception:
        hostname = ""

    vendor = detect_vendor(sys_descr, sys_oid, f"{hr_descr} {prt_name} {http_title} {ews_model} {ipp_model}", hostname)
    model = guess_model(sys_descr, hr_descr, prt_name, ipp_model or ews_model or http_title)
    try:
        from .model_identifier import canonical_model
        modelo_canonico, confianca = canonical_model(
            vendor, sys_descr, hr_descr, prt_name,
            f"{ipp_model} {ipp_name} {ews_model} {http_title}")
    except Exception:
        modelo_canonico, confianca = model, "baixa"

    is_printer, reasons, _score = classify_host(
        ports_open, sys_descr, hr_descr, prt_name, vendor,
        http_title, ews_model, http_server, ipp_model,
        ipp_device_id, ipp_path, hostname, has_snmp=bool(snmp_data),
        server_ports=[p for p in (445, 135, 3389) if check_port(ip, p, timeout=0.6)]
        if (vendor == "Desconhecido" and not has_snmp_printer_like(snmp_data, sys_descr, hr_descr, prt_name))
        else [])
    if not is_printer:
        return None
    return finalize_host(ip, hostname, ports_open, vendor, model, modelo_canonico,
                         confianca, serial, sys_descr, sys_oid, http_title,
                         ews_model, ipp_model, ipp_device_id, reasons, bool(snmp_data))


def has_snmp_printer_like(snmp_data, sys_descr="", hr_descr="", prt_name=""):
    """Ha indicios de MIB de impressora nos dados SNMP?"""
    if not snmp_data:
        return False
    blob = f"{sys_descr} {hr_descr} {prt_name}".lower()
    return any(k in blob for k in ("prtmarker", "printer mib", "jetdirect", "print", "laserjet",
                                   "officejet", "brother", "epson", "canon", "kyocera", "ricoh",
                                   "xerox", "lexmark", "pantum", "zebra", "elgin"))


def classify_host(ports_open, sys_descr="", hr_descr="", prt_name="", vendor="Desconhecido",
                   http_title="", ews_model="", http_server="", ipp_model="",
                   ipp_device_id="", ipp_path="", hostname="", has_snmp=False,
                   server_ports=None):
    """Pontua evidencias. Retorna (eh_impressora, motivos, score).
    Regras:
    - 9100 = hardware (+2). 515 SOZINHA = +1 (pode ser Servidor de Impressao Windows/CUPS).
    - 631 sozinha NAO vale (pode ser CUPS).
    - precisa score >= 2 E nao parecer servidor sem evidencia de hardware."""
    score = 0
    reasons = []
    server_ports = server_ports or []
    has_9100 = 9100 in ports_open
    lpd_only = 515 in ports_open and not has_9100
    if has_9100:
        score += 2
        reasons.append("porta RAW/JetDirect 9100 aberta")
    elif lpd_only:
        score += 1
        reasons.append("somente LPD 515 (pode ser Servidor de Impressao)")
    has_snmp_printer = has_snmp and (vendor != "Desconhecido" or
        any(k in f"{sys_descr} {hr_descr} {prt_name}".lower()
            for k in ("prtmarker", "printer mib", "jetdirect", "print")))
    if has_snmp_printer:
        score += 2
        reasons.append(f"SNMP com MIB de impressora ({vendor})")
    try:
        from .model_identifier import canonical_model as _cm
        _, _ews_conf = _cm(vendor, "", "", "", ews_model)
        _, _ipp_conf = _cm(vendor, "", "", "", ipp_model)
    except Exception:
        _ews_conf, _ipp_conf = "baixa", "baixa"
    if _ews_conf in ("alta", "media"):
        score += 2
        reasons.append(f"EWS informa modelo ({ews_model[:60]})")
    if _ipp_conf in ("alta", "media") and ipp_path in ("/ipp/print", "/ipp/printer"):
        score += 2
        reasons.append(f"IPP responde modelo ({ipp_model[:60]})")
    elif _ipp_conf in ("alta", "media"):
        score += 1
        reasons.append(f"IPP cita modelo ({ipp_model[:60]})")
    if re.search(r"MFG\s*:\s*\w+\s*;\s*MDL\s*:", ipp_device_id, re.I):
        score += 2
        reasons.append("IPP device-id de hardware (MFG/MDL)")
    hn = (hostname or "").upper()
    if hn.startswith("NPI") or hn.startswith("BRN") or "BROTHER" in hn:
        score += 1
        reasons.append(f"hostname JetDirect ({hostname})")
    # --- veto: servidor (ex: CUPS, Windows Server com funcao Impressao) ---
    srv_low = f"{http_server} {http_title}".lower()
    hn_low = (hostname or "").lower()
    looks_server = ("cups" in srv_low or "squid" in srv_low or "apache" in srv_low or
                    "nginx" in srv_low or "microsoft-iis" in srv_low or "iis" in srv_low or
                    any(k in sys_descr.lower() for k in ("linux", "ubuntu", "debian", "windows server", "synology", "qnap")) or
                    bool(server_ports) or
                    any(k in hn_low for k in ("srv", "server", "servidor", "printsv", "print-sv",
                                              "dc-", "dc0", "ad-", "file", "erp", "sql", "hyper", "esx", "proxmox")))
    hardware = (has_9100 or has_snmp_printer or
                bool(re.search(r"MFG\s*:", ipp_device_id, re.I)))
    if looks_server and not hardware:
        return False, ["servidor detectado (ex: Windows Server/CUPS) sem evidencia de hardware"], score
    if score < 2:
        return False, reasons, score
    return True, reasons, score


def finalize_host(ip, hostname, ports_open, vendor, model, modelo_canonico, confianca,
                  serial, sys_descr, sys_oid, http_title, ews_model, ipp_model,
                  ipp_device_id, reasons, snmp_ok):
    return {
        "ip": ip,
        "hostname": hostname,
        "mac": "",
        "portas": ports_open,
        "fabricante": vendor,
        "modelo": model,
        "modelo_canonico": modelo_canonico,
        "confianca_modelo": confianca,
        "serial": serial if serial.lower() != "null" else "",
        "sys_descr": sys_descr[:200],
        "sys_object_id": sys_oid,
        "http_titulo": http_title,
        "ews_modelo": ews_model,
        "ipp_modelo": ipp_model,
        "ipp_device_id": ipp_device_id,
        "motivo": "; ".join(reasons),
        "snmp_ok": snmp_ok,
    }


def check_single_ip(ip, communities=("public",)):
    """Testa um IP manual (espelha HyperViewer check_single_ip)."""
    return scan_host(ip.strip(), communities=communities)


def scan_network(cidrs=None, communities=("public",), max_workers=64, progress_cb=None,
                 include_arp=True):
    """
    Varre uma ou varias sub-redes. cidrs: None (auto=todas locais), str ou lista.
    Aceita "192.168.15.0/24, 10.0.0.0/24" e hosts unicos ("192.168.1.50").
    Retorna lista de dicts de impressoras.
    progress_cb(atual, total, msg) chamado durante o scan.
    """
    from .network import parse_cidrs, expand_targets
    if isinstance(cidrs, str):
        cidrs = parse_cidrs(cidrs)
    targets, avisos = expand_targets(cidrs, include_arp=include_arp)
    arp = parse_arp_table() if include_arp else {}

    total = len(targets)

    def fire(msg):
        if progress_cb:
            try:
                progress_cb(0, total, msg)
            except Exception:
                pass

    for a in avisos:
        fire(a)
    # Etapa 1: ping sweep rapido para popular ARP (paralelo) — 0..50%
    fire(f"Ping em {total} hosts...")
    alive = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(ping_host, ip): ip for ip in targets}
        done = 0
        for f in as_completed(futs):
            done += 1
            if progress_cb:
                try:
                    progress_cb(done, total * 2, f"Ping {done}/{total}")
                except Exception:
                    pass
            try:
                if f.result():
                    alive.append(futs[f])
            except Exception:
                pass
    # inclui ARP mesmo se ping falhou (impressora pode bloquear ICMP)
    for ip in arp:
        if ip not in alive:
            alive.append(ip)

    # Etapa 2: investiga candidatos (portas + SNMP + HTTP) — 50..100%
    base = total
    fire(f"Identificando impressoras em {len(alive)} hosts ativos...")
    printers = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(scan_host, ip, communities): ip for ip in alive}
        done = 0
        for f in as_completed(futs):
            done += 1
            if progress_cb:
                try:
                    progress_cb(base + done, base + len(alive), f"Verificando {futs[f]} ({done}/{len(alive)})")
                except Exception:
                    pass
            try:
                r = f.result()
                if r:
                    r["mac"] = arp.get(r["ip"], "")
                    printers.append(r)
            except Exception:
                pass

    printers.sort(key=lambda d: ipaddress.ip_address(d["ip"]))
    return printers
