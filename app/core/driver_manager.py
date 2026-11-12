"""
Gerencia drivers PCL ESPECIFICOS (nunca genericos).
Ordem de busca:
  1) ./drivers/**/*.inf (pacotes extraidos pelo TI)
  2) drivers inbox do Windows filtrados (fabricante + PCL, sem 'Generic')
  3) catalogo (orienta download oficial)
"""
import os
import re
import json
import zipfile
import urllib.request
import shutil
from pathlib import Path

from app.data import paths
from app.platform import process as winproc

BASE = paths.base_dir()
DRIVERS_DIR = paths.drivers_dir()

# Nomes que JAMAIS podem ser usados (genericos do SO, virtuais, fax/pdf)
GENERIC_BLOCK = [
    "generic", "generico", "text only", "texto",
    "microsoft",  # tudo da MS: IPP Class, XPS, Print to PDF, PnP, etc.
    "class driver", "xps", "onenote", "print to pdf", "pdf24",
    "fax driver", "easy print", "virtual print",
    "ms publisher",
]

# inf deve conter indicios de PCL/PS especifico
PCL_HINTS = ["pcl6", "pcl5", "pcl 6", "pcl 5", "pclxl", "postscript", "ps ", " kx", "upld", "pcl"]


def is_generic_name(name: str) -> bool:
    n = (name or "").lower()
    return any(g in n for g in GENERIC_BLOCK)


def parse_inf_driver_names(inf_path: Path):
    """Extrai nomes de driver provaveis de um .inf (secao [Strings] + linhas de modelo)."""
    names = []
    JUNK = ("%", "\\", "HKLM", "HKR", "0x", "REG_", "rundll", ".dll", ".exe", ",,")
    try:
        raw = inf_path.read_bytes()
        text = None
        for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw.decode(enc)
                if "[Version]" in text or "[Manufacturer]" in text:
                    break
            except Exception:
                continue
        if not text:
            return names
        # 1) disk names / driver names entre aspas em secoes de modelo
        # formato tipico: "HP LaserJet M404 PCL6" = InstSec, ...
        for m in re.finditer(r'"([^"]*(?:PCL[^"]*|LaserJet[^"]*|Brother[^"]*|Epson[^"]*|Canon[^"]*|Kyocera[^"]*|Ricoh[^"]*|Xerox[^"]*|Lexmark[^"]*|Samsung[^"]*|Pantum[^"]*|Elgin[^"]*|Zebra[^"]*|OKI[^"]*|ECOSYS[^"]*|TASKalfa[^"]*|KX[^"]*|Universal[^"]*|VersaLink[^"]*|AltaLink[^"]*|Phaser[^"]*|WorkCentre[^"]*|ImageRunner[^"]*|imageCLASS[^"]*|OfficeJet[^"]*|PageWide[^"]*|DesignJet[^"]*|MFP[^"]*|WorkForce[^"]*|EcoTank[^"]*|HL-[^"]*|DCP[^"]*|MFC[^"]*))"', text, re.I):
            cand = m.group(1).strip()
            if 4 < len(cand) < 120 and not is_generic_name(cand) \
                    and not any(j in cand for j in JUNK):
                names.append(cand)
        # 2) chaves em [Strings]
        sec = re.search(r"\[Strings\](.*?)(^\[|\Z)", text, re.I | re.M | re.S)
        if sec:
            for m in re.finditer(r'^\s*\w+\s*=\s*"([^"]+)"', sec.group(1), re.M):
                cand = m.group(1).strip()
                if any(k in cand for k in ("HP", "Brother", "Epson", "Canon", "Kyocera", "Ricoh", "Xerox", "Lexmark", "Samsung", "Pantum", "OKI", "Elgin", "Zebra", "PCL", "LaserJet", "ECOSYS", "TASKalfa", "KX", "Universal", "VersaLink", "Phaser")):
                    if not is_generic_name(cand) and len(cand) < 120 \
                            and not any(j in cand for j in JUNK):
                        names.append(cand)
    except Exception:
        pass
    # dedup mantendo ordem
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:20]


def find_local_inf(fabricante="", modelo=""):
    """Procura .inf local compativel APENAS em ./drivers
    (ignora o cache de downloads automaticos ./drivers/_downloads, que e
    tratado pelo fluxo de download com escopo de fabricante).
    Retorna lista [(inf_path, score, driver_names)]."""
    from pathlib import Path as _P
    import json as _json
    results = []
    if not DRIVERS_DIR.exists():
        return results
    try:
        cache = (DRIVERS_DIR / "_downloads").resolve()
    except Exception:
        cache = DRIVERS_DIR / "_downloads"
    fab = (fabricante or "").lower().strip()
    unknown_fab = fab in ("", "desconhecido", "unknown", "null")
    stop = {"modelo", "model", "series", "serie", "printer", "impressora",
            "driver", "nao", "identificado", "unknown", "desconhecido"}
    toks = [t for t in re.split(r"[^A-Za-z0-9]+", f"{fabricante} {modelo}".lower())
            if len(t) >= 2 and t not in stop]
    for inf in DRIVERS_DIR.rglob("*.inf"):
        try:
            if cache in _P(inf).resolve().parents:
                continue  # cache de download: nao e pacote do TI
        except Exception:
            if "_downloads" in str(inf).lower():
                continue
        try:
            raw = inf.read_bytes()[:60000]
            text = None
            for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
                try:
                    t = raw.decode(enc)
                    if "[Version]" in t or "[Manufacturer]" in t:
                        text = t.lower()
                        break
                except Exception:
                    continue
            if text is None:
                text = raw.decode("utf-8", errors="ignore").lower()
        except Exception:
            continue
        if not unknown_fab and fab not in text and fab not in str(inf).lower():
            continue  # fabricante conhecido: .inf precisa ser do fabricante
        score = 0
        for t in toks:
            if t in text or t in str(inf).lower():
                score += 4 if len(t) >= 4 else 1
        if unknown_fab and not any(len(t) >= 4 and t in text for t in toks):
            continue  # sem fabricante e sem token forte do modelo: nao arrisca
        # bonus se menciona pcl
        if any(h in text for h in PCL_HINTS):
            score += 3
        # bonus se pasta do fabricante bate
        if fabricante and fabricante.lower() in str(inf).lower():
            score += 5
        if score > 0:
            names = parse_inf_driver_names(inf)
            if names and all(is_generic_name(n) for n in names):
                continue  # so nomes genericos: descarta o .inf
            results.append((inf, score, names))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def list_inbox_drivers():
    """Lista drivers ja disponiveis no Windows (inbox / instalados)."""
    try:
        ps = 'Get-PrinterDriver | Select-Object -ExpandProperty Name'
        r = winproc.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=30)
        names = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        return names
    except Exception:
        return []


def pick_inbox_driver(fabricante, modelo):
    """Escolhe driver inbox ESPECIFICO do fabricante com PCL. Nunca generico."""
    names = list_inbox_drivers()
    fab = (fabricante or "").lower().strip()
    unknown_fab = fab in ("", "desconhecido", "unknown", "null")
    mod_toks = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", modelo or "") if len(t) >= 2]

    def ok(n):
        if is_generic_name(n):
            return False
        nl = n.lower()
        if unknown_fab:
            return False  # sem fabricante confirmado, nao arrisca driver errado
        if fab and fab not in nl and "hewlett" not in nl and "hp " not in nl:
            # permite "HP" abreviado
            if fab == "hp" and ("hp" not in nl and "hewlett" not in nl):
                return False
            if fab not in ("hp",) and fab not in nl:
                return False
        return True

    cands = [n for n in names if ok(n)]
    # prefere os que citam PCL e/ou tokens do modelo
    def score(n):
        nl = n.lower()
        s = 0
        if "pcl6" in nl or "pcl 6" in nl:
            s += 10
        if "pcl5" in nl or "pcl 5" in nl:
            s += 6
        if "ps" in nl or "postscript" in nl:
            s += 4
        for t in mod_toks:
            if t in nl:
                s += 5 if len(t) > 3 else 1
        # penaliza universais genericos de fabricante? aceita como ultimo recurso do FABRICANTE
        if "universal" in nl:
            s -= 2
        return s
    cands.sort(key=score, reverse=True)
    # remove score 0 (sem relacao)
    cands = [c for c in cands if score(c) > 0]
    return cands[0] if cands else None


def download_and_extract(url, dest_dir: Path):
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = url.split("/")[-1].split("?")[0] or "driver.bin"
    fname = "".join(c for c in fname if c.isalnum() or c in (".-_")).strip(".") or "driver.bin"
    fpath = dest_dir / fname
    req = urllib.request.Request(url, headers={"User-Agent": "PrinterInstaller/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(fpath, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1024 * 256)
            if not chunk:
                break
            total += len(chunk)
            if total > 1024 * 1024 * 1024:
                raise ValueError("Arquivo excede 1GB — abortado.")
            f.write(chunk)
    # extrai se zip
    if zipfile.is_zipfile(fpath):
        with zipfile.ZipFile(fpath) as z:
            for m in z.namelist():
                p = (dest_dir / m).resolve()
                if dest_dir.resolve() not in p.parents and p != dest_dir.resolve():
                    continue
            z.extractall(dest_dir)
        return dest_dir
    return fpath


def driver_matches_model(driver_name: str, modelo_canonico: str) -> bool:
    """True se o nome do driver cita tokens fortes do modelo (ex: E52645, M404)."""
    nl = (driver_name or "").lower()
    toks = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", modelo_canonico or "") if len(t) >= 2]
    stop = {"laserjet", "officejet", "pagewide", "designjet", "deskjet", "mfp", "color",
            "brother", "epson", "canon", "kyocera", "ricoh", "xerox", "lexmark",
            "samsung", "ecosys", "pantum", "elgin", "zebra", "pro"}
    strong = {t for t in toks if len(t) >= 4 and t not in stop}
    # variantes sem sufixo de configuracao: m404dn->m404, e52645dn->e52645
    for t in list(strong):
        m = re.match(r"^([a-z]*\d+)[a-z]+$", t)
        if m and len(m.group(1)) >= 3:
            strong.add(m.group(1))
    return any(t in nl for t in strong)


def find_inf_by_hardware(hardware_ids=None, device_id="", modelo="", fabricante=""):
    """Procura um .inf que case com os HardwareIDs do dispositivo USB.

    Os IDs do PnP aparecem literalmente na secao [Models] do .inf, em duas
    formas possiveis:
      USBPRINT\\Hewlett-PackardHP_LaAE38   (ID do fabricante, o que casa)
      USB\\PRINTER_PROVIDER\\HP LaserJet M404 MFP (nome legivel, as vezes ausente)
    Quando nenhum ID casa, usa o nome do modelo como sinal fraco.
    Retorna (inf, score, driver_names) ou (None, 0, [])."""
    ids = [str(h).lower() for h in (hardware_ids or []) if h]
    if device_id:
        ids.append(str(device_id).lower())
    ids = [i for i in ids if i and i not in ("none", "null")]
    # a forma legivel (USB\PRINTER_PROVIDER\Model) raramente esta no .inf,
    # mas o nome do modelo ainda pode servir de sinal fraco
    modelo_toks = [t for t in re.split(r"[^A-Za-z0-9]+", (modelo or "").lower())
                   if len(t) >= 4 and t not in ("laserjet", "officejet", "pagewide",
                                               "designjet", "printer", "impressora",
                                               "brother", "epson", "canon", "kyocera")]
    fab = (fabricante or "").lower().strip()
    fab_alias = {"hewlett-packard": "hp", "hewlett packard": "hp", "hp inc": "hp",
                 "brother industries": "brother", "seiko epson": "epson"}
    fab = fab_alias.get(fab, fab)
    results = []
    for inf in DRIVERS_DIR.rglob("*.inf"):
        try:
            raw = inf.read_bytes()[:400000]
            text = None
            for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
                try:
                    t = raw.decode(enc)
                    if "[Version]" in t or "[Manufacturer]" in t:
                        text = t.lower()
                        break
                except Exception:
                    continue
            if text is None:
                text = raw.decode("utf-8", errors="ignore").lower()
        except Exception:
            continue
        if fab and fab not in ("desconhecido", "unknown", ""):
            if fab not in text and fab not in str(inf).lower():
                continue
        score = 0
        for h in ids:
            if h and h in text:
                score += 20
        if score == 0 and modelo_toks:
            # sinal fraco: o .inf menciona o modelo E tem ids USB
            if "usbprint" in text or "usb\\printer_provider" in text:
                hits = sum(1 for t in modelo_toks if t in text)
                if hits:
                    score += 2 * hits
        if score == 0:
            continue
        if any(x in text for x in ("pcl6", "pcl 6", "pclxl")):
            score += 3
        names = parse_inf_driver_names(inf)
        if not names:
            score -= 4
        elif all(is_generic_name(n) for n in names):
            continue
        results.append((inf, score, names))
    results.sort(key=lambda x: -x[1])
    return results[0] if results else (None, 0, [])


def resolve_usb_driver(device, allow_download=True, log=None):
    """Resolve o driver PCL de uma impressora USB.

    device: {nome, device_id, hardware_ids, fabricante, modelo, fila}
    Retorna dict {origem, inf, driver_name, detalhe}
    Ordem:
      1) fila ja instalada no Windows (driver em uso)
      2) .inf local que casa com os HardwareIDs
      3) download do pack do fabricante -> .inf que casa com os HardwareIDs
      4) driver inbox do fabricante (PCL, nunca generico)
      5) pendente (orienta) — NUNCA driver generico
    """
    modelo = device.get("modelo") or device.get("nome") or ""
    fab = device.get("fabricante") or ""
    # 1) fila existente
    fila = device.get("fila") or {}
    if fila.get("driver") and not is_generic_name(fila["driver"]):
        return {"origem": "instalado", "inf": None, "driver_name": fila["driver"],
                "detalhe": f"impressora USB ja instalada no Windows "
                           f"(porta {fila.get('porta') or 'USB'})"}
    # 2) .inf local pelo hardware id
    inf, score, names = find_inf_by_hardware(device.get("hardware_ids"),
                                              device.get("device_id"), modelo,
                                              device.get("fabricante"))
    if inf and names:
        dname = names[0]
        if not is_generic_name(dname):
            return {"origem": "local", "inf": str(inf), "driver_name": dname,
                    "detalhe": f".inf local casando com o hardware USB ({inf.name})"}
    # 3) download do pack do fabricante
    if allow_download and fab and fab.lower() not in ("", "desconhecido", "unknown"):
        try:
            from .driver_download import ensure_driver_pack
            got = ensure_driver_pack(fab, modelo, log=log,
                                     hardware_ids=device.get("hardware_ids"),
                                     device_id=device.get("device_id"))
            if got:
                p_inf, dname, pack_id = got
                if dname and not is_generic_name(dname):
                    return {"origem": "download", "inf": str(p_inf),
                            "driver_name": dname,
                            "detalhe": f"baixado do fabricante ({pack_id}): {p_inf.name}"}
        except Exception as e:
            if log:
                try:
                    log(f"Download do driver USB falhou: {e}")
                except Exception:
                    pass
    # 4) inbox do fabricante
    inbox = pick_inbox_driver(fab, modelo) if fab else None
    if inbox:
        return {"origem": "inbox", "inf": None, "driver_name": inbox,
                "detalhe": "driver PCL do fabricante ja presente no Windows"}
    # 5) pendente
    return {"origem": "pendente", "inf": None, "driver_name": None,
            "detalhe": (f"Sem driver PCL para a impressora USB {modelo}: "
                        f"nem .inf local, nem download, nem Windows. "
                        f"Baixe o driver do modelo no site do fabricante e extraia o "
                        f".inf em ./drivers/{fab or 'FABRICANTE'}/. "
                        f"NENHUM driver generico sera usado.")}


def resolve_driver(fabricante, modelo, modelo_canonico=None, allow_download=True, log=None):
    """
    Resolve o melhor driver ESPECIFICO (nunca generico).
    Ordem:
      1) .inf local em ./drivers/ (pacote do modelo extraido pelo TI)
      2) driver inbox do Windows que case com o MODELO EXATO (ex: 'HP LaserJet MFP E52645 PCL-6 (V4)')
      3) download automatico do pack PCL do fabricante (driver_packs.json) -> .inf do fabricante
      4) driver inbox do fabricante (PCL, ex: UPD) como fallback vendor
      5) pendente (orienta, sem instalar nada generico)
    Retorna dict: {origem, inf, driver_name, detalhe}
    """
    canon = modelo_canonico or modelo
    # 1) local (pacote do TI: ./drivers + pastas extras de drivers_config.json)
    locais = find_local_inf(fabricante, canon)
    if locais:
        inf, score, dnames = locais[0]
        dname = dnames[0] if dnames else None
        if dname and not is_generic_name(dname):
            if not driver_matches_model(dname, canon):
                warn = (f"AVISO: o .inf local '{dname}' nao cita o modelo {canon} — "
                        f"usando mesmo assim por ser pacote do TI ({inf}).")
                if log:
                    try:
                        log(warn)
                    except Exception:
                        pass
            else:
                warn = ""
            detalhe = f".inf local ({inf}) score={score}"
            if warn:
                detalhe += " | " + warn
            return {"origem": "local", "inf": str(inf), "driver_name": dname,
                    "detalhe": detalhe}
        # .inf local sem nome utilizavel: continua para download/inbox
        if log:
            try:
                log(f".inf local {inf} sem nome de driver valido — tentando download/inbox.")
            except Exception:
                pass
    # 2) inbox que case com o MODELO EXATO
    inbox = pick_inbox_driver(fabricante, canon)
    if inbox and driver_matches_model(inbox, canon):
        return {"origem": "inbox-exato", "inf": None, "driver_name": inbox,
                "detalhe": f"driver exato do modelo ja presente no Windows ({inbox})"}
    # 3) download automatico do fabricante
    if allow_download and (fabricante or "").lower() not in ("", "desconhecido"):
        try:
            from .driver_download import ensure_driver_pack
            got = ensure_driver_pack(fabricante, canon, log=log)
            if got:
                inf, dname, pack_id = got
                if dname and not is_generic_name(dname):
                    return {"origem": "download", "inf": str(inf), "driver_name": dname,
                            "detalhe": f"baixado do fabricante ({pack_id}): {inf.name}"}
        except Exception as e:
            if log:
                try:
                    log(f"Download do driver falhou: {e}")
                except Exception:
                    pass
    # 4) inbox do fabricante (PCL vendor, nunca generico do SO)
    if inbox:
        return {"origem": "inbox", "inf": None, "driver_name": inbox,
                "detalhe": "driver PCL do fabricante ja presente no Windows (nao-generico)"}
    # 5) pendente: orienta
    return {"origem": "pendente", "inf": None, "driver_name": None,
            "detalhe": (f"Sem driver PCL para {fabricante} {canon}: nem ./drivers/, nem download, nem Windows. "
                        f"Baixe o driver PCL6 do modelo no site do fabricante e extraia o .inf em "
                        f"./drivers/{fabricante or 'FABRICANTE'}/. NENHUM driver generico sera usado.")}
