"""
Deteccao de impressoras USB conectadas ao Windows (PnP).

O Windows expoe a impressora USB como dispositivo da classe "Printer" com
InstanceID no formato  USB\\PRINTER_PROVIDER\\<MODELO>  e HardwareIDs que
identificam exatamente o modelo. Esses IDs sao a chave para casar o .inf do
fabricante correto (nunca generico).
"""
import json
import re

from app.platform import process as winproc

USB_IDS = ("USB\\PRINTER_PROVIDER\\", "USBPRINT\\", "USB\\")


def run_ps(cmd, timeout=60):
    r = winproc.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                    capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def list_usb_devices(include_non_usb=False):
    """
    Lista dispositivos PnP da classe Printer.
    Retorna lista de dicts:
      {nome, device_id, hardware_ids, fabricante, status, service, usb: bool}
    """
    ps = (
        "Get-PnpDevice -Class Printer -ErrorAction SilentlyContinue | "
        "ForEach-Object { "
        "$hw = (Get-PnpDeviceProperty -InstanceId $_.InstanceId "
        "-KeyName 'DEVPKEY_Device_HardwareIds' -ErrorAction SilentlyContinue).Data; "
        "$svc = (Get-PnpDeviceProperty -InstanceId $_.InstanceId "
        "-KeyName 'DEVPKEY_Device_Service' -ErrorAction SilentlyContinue).Data; "
        "[PSCustomObject]@{ "
        "Name=$_.FriendlyName; InstanceId=$_.InstanceId; Status=$_.Status; "
        "Manufacturer=$_.Manufacturer; Class=$_.Class; "
        "HardwareIds=(@($hw) -join ';;'); Service=$svc } } | "
        "ConvertTo-Json -Compress 2>&1 | Out-String"
    )
    try:
        _code, out = run_ps(ps, timeout=90)
    except Exception:
        return []
    txt = (out or "").strip()
    if not txt or not txt.startswith(("[", "{")):
        return []
    try:
        data = json.loads(txt)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]

    out_list = []
    for d in data:
        if not d.get("InstanceId"):
            continue
        did = str(d.get("InstanceId"))
        hws = [h for h in str(d.get("HardwareIds") or "").split(";;") if h.strip()]
        is_usb = any(did.upper().startswith(p) for p in USB_IDS) or \
            any(h.upper().startswith(p) for p in USB_IDS for h in hws)
        if not is_usb and not include_non_usb:
            continue
        out_list.append({
            "nome": _norm(d.get("Name")),
            "device_id": did,
            "hardware_ids": hws,
            "fabricante": _norm(d.get("Manufacturer")),
            "status": _norm(d.get("Status")),
            "service": _norm(d.get("Service")),
            "usb": is_usb,
        })

    if not out_list:
        try:
            ps2 = "Get-PnpDevice USBPRINT fallback"
            _c2, out2 = run_ps(
                "Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like 'USBPRINT*' } | "
                "Select-Object -First 20 FriendlyName, InstanceId, Status, Manufacturer | "
                "ConvertTo-Json -Compress 2>&1 | Out-String", timeout=60)
            txt2 = (out2 or "").strip()
            if txt2.startswith(("[", "{")):
                d2 = json.loads(txt2[txt2.find("[") if "[" in txt2 else txt2.find("{"):])
                if isinstance(d2, dict):
                    d2 = [d2]
                for dd in d2:
                    if not dd.get("InstanceId"):
                        continue
                    out_list.append({
                        "nome": _norm(dd.get("FriendlyName") or dd.get("Name")),
                        "device_id": str(dd.get("InstanceId")),
                        "hardware_ids": [],
                        "fabricante": _norm(dd.get("Manufacturer")),
                        "status": _norm(dd.get("Status")),
                        "service": "",
                        "usb": True,
                    })
        except Exception:
            pass
    return out_list


def list_usb_queues():
    """Filas de impressora ja criadas com porta USB (impressora USB instalada)."""
    ps = ("Get-Printer | Where-Object { $_.PortName -like 'USB*' } | "
          "Select-Object Name,DriverName,PortName | ConvertTo-Json -Compress 2>&1 | Out-String")
    try:
        _code, out = run_ps(ps, timeout=60)
    except Exception:
        return []
    txt = (out or "").strip()
    if not txt or not txt.startswith(("[", "{")):
        return []
    try:
        data = json.loads(txt)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    return [{"nome": d.get("Name", ""), "driver": d.get("DriverName", ""),
             "porta": d.get("PortName", "")} for d in data if d.get("Name")]


def _tokens(text):
    stop = {"printer", "impressora", "usb", "device", "class", "driver", "pnp",
            "microsoft", "ipp", "usbprint", "printer_provider", "supported"}
    return [t.lower() for t in re.split(r"[^A-Za-z0-9]+", text or "")
            if len(t) >= 3 and t.lower() not in stop]


def match_queue(device, queues):
    """Encontra a fila de impressora ja instalada para este dispositivo USB."""
    toks = _tokens(device.get("nome"))
    best, best_score = None, 0
    for q in queues:
        qt = _tokens(q.get("nome"))
        score = sum(1 for t in toks if t in qt)
        # a fila costuma ter o mesmo nome do dispositivo
        if _norm(q.get("nome")).lower() == device.get("nome", "").lower():
            score += 5
        if score > best_score:
            best, best_score = q, score
    return best if best_score >= 2 else None


def model_from_device(device):
    """Extrai o modelo exibido no nome amigavel do PnP."""
    name = device.get("nome") or ""
    # remove sufixos comuns do Windows
    name = re.sub(r"\s*\((USB|COM\d+|LPT\d+|Port)\)\s*$", "", name, flags=re.I)
    name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
    return name or device.get("nome") or "Impressora USB"


VENDOR_NORMALIZE = {
    "hewlett-packard": "HP",
    "hewlett packard": "HP",
    "hp inc": "HP",
    "hp": "HP",
    "brother industries": "Brother",
    "brother industries, ltd.": "Brother",
    "seiko epson": "Epson",
    "epson": "Epson",
    "canon": "Canon",
    "kyocera": "Kyocera",
    "kyocera document solutions": "Kyocera",
    "ricoh": "Ricoh",
    "xerox": "Xerox",
    "lexmark": "Lexmark",
    "samsung": "Samsung",
    "oki": "OKI",
    "okidata": "OKI",
    "zebra": "Zebra",
    "pantum": "Pantum",
    "elgin": "Elgin",
}


def vendor_from_device(device, model=""):
    """Fabricante a partir do campo Manufacturer ou do prefixo do nome."""
    man = (device.get("fabricante") or "").strip()
    norm = VENDOR_NORMALIZE.get(man.lower().strip())
    if norm:
        return norm
    if man and man.lower() not in ("microsoft", "desconhecido", "unknown", ""):
        return man
    blob = f"{man} {model} {device.get('device_id','')}"
    for kw, vendor in (("hewlett", "HP"), ("hp", "HP"), ("laserjet", "HP"),
                       ("brother", "Brother"), ("epson", "Epson"), ("canon", "Canon"),
                       ("kyocera", "Kyocera"), ("ricoh", "Ricoh"), ("xerox", "Xerox"),
                       ("lexmark", "Lexmark"), ("samsung", "Samsung"), ("oki", "OKI"),
                       ("pantum", "Pantum"), ("elgin", "Elgin"), ("zebra", "Zebra")):
        if kw in blob.lower():
            return vendor
    return "Desconhecido"
