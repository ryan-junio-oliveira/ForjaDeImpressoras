"""
Identificacao canonica do MODELO exato da impressora.
Ex: "HP LaserJet MFP E52645", "Brother HL-L5100DN", "Epson EcoTank L5590".

Combina sysDescr + hrDeviceDescr + prtGeneralPrinterName + titulo HTTP
e aplica regex por fabricante. Sem match -> devolve o texto mais util.
"""
import re


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip(" ,;-\t"))


def _first(*vals: str) -> str:
    for v in vals:
        v = _clean(v or "")
        if v and v.lower() not in ("null", "none", "unknown", "-"):
            return v
    return ""


def canonical_model(vendor: str, sys_descr="", hr_descr="", prt_name="", http_title=""):
    """Retorna (modelo_canonico, confianca). confianca: alta|media|baixa."""
    v = (vendor or "").lower()
    blob = " | ".join(x for x in (sys_descr, hr_descr, prt_name, http_title) if x)

    def hp():
        m = re.search(
            r"(Color\s+)?(LaserJet|OfficeJet|PageWide|DesignJet|DeskJet)\s+"
            r"(Managed\s+)?(Flow\s+)?(MFP\s+)?([A-Z]{0,3}\d{3,5}[A-Za-z]{0,4}(?:dn|dw|n|dn)?)",
            blob, re.I)
        if m:
            color = (m.group(1) or "").strip()
            fam = m.group(2)
            managed = (m.group(3) or "").strip()
            flow = (m.group(4) or "").strip()
            mfp = (m.group(5) or "").strip()
            cod = m.group(6)
            parts = ["HP"]
            if color:
                parts.append(color)
            parts.append(fam)
            if managed:
                parts.append(managed)
            if flow:
                parts.append(flow)
            if mfp:
                parts.append(mfp)
            parts.append(cod)
            return _clean(" ".join(parts)), "alta"
        # JetDirect sozinho: "HP ETHERNET MULTI-ENVIRONMENT" -> tenta codigo solto
        m2 = re.search(r"\b(E\d{4,5}[A-Za-z]{0,3}|M\d{3,4}[a-z]{0,3}|P\d{4}[a-z]{0,3})\b", blob)
        if m2 and "hp" in blob.lower():
            return f"HP LaserJet {m2.group(1)}", "media"
        return None

    def brother():
        m = re.search(r"\b((?:HL|DCP|MFC|ADS|FAX)-[A-Z0-9]+)\b", blob, re.I)
        if m:
            return f"Brother {m.group(1).upper()}", "alta"
        return None

    def epson():
        m = re.search(r"\b(EcoTank|WorkForce|WorkForce Pro|Expression|SureColor|Stylus)\s+([A-Z0-9][A-Z0-9\-]+)",
                      blob, re.I)
        if m:
            return f"Epson {m.group(1)} {m.group(2)}", "alta"
        m2 = re.search(r"\b(ET-\d+|L\d{3,4}|WF-\d+|XP-\d+)\b", blob, re.I)
        if m2:
            return f"Epson {m2.group(1).upper()}", "media"
        return None

    def canon():
        m = re.search(r"\b(imageRUNNER|imageCLASS|imageFORMULA|PIXMA|MAXIFY|SELPHY)\s+([A-Z0-9][A-Z0-9\-]+)",
                      blob, re.I)
        if m:
            return f"Canon {m.group(1)} {m.group(2)}", "alta"
        return None

    def kyocera():
        m = re.search(r"\b(ECOSYS|TASKalfa)\s+([A-Z0-9][A-Z0-9\- ]{1,12})", blob, re.I)
        if m:
            return f"Kyocera {m.group(1)} {_clean(m.group(2))}", "alta"
        return None

    def ricoh():
        m = re.search(r"\b(MP|SP|IM)\s*([A-Z]?\s?\d{3,4}[A-Z]*)", blob, re.I)
        if m:
            return f"Ricoh {_clean(m.group(1) + ' ' + m.group(2)).upper()}", "alta"
        return None

    def xerox():
        m = re.search(r"\b(VersaLink|AltaLink|Phaser|WorkCentre|PrimeLink)\s+([A-Z0-9][A-Z0-9\-]+)", blob, re.I)
        if m:
            return f"Xerox {m.group(1)} {m.group(2)}", "alta"
        return None

    def lexmark():
        m = re.search(r"\b(M[CSX]\d{3,4}[a-z]*|CX\d{3,4}[a-z]*|XC\d{3,4}[a-z]*|B\d{4}[a-z]*)\b", blob, re.I)
        if m:
            return f"Lexmark {m.group(1)}", "media"
        return None

    def samsung():
        m = re.search(r"\b(ML|SL|CLP|CLX|SCX|SF|ProXpress)[-\s]?([A-Z0-9][A-Z0-9\-]*)", blob, re.I)
        if m:
            return f"Samsung {m.group(1)}-{m.group(2)}", "media"
        return None

    def oki():
        m = re.search(r"\b(MB|MC|C|B|ES)\d{3,4}[a-z]{0,3}\b", blob, re.I)
        if m:
            return f"OKI {m.group(0).upper()}", "media"
        return None

    def zebra():
        m = re.search(r"\b(ZD|ZT|GK|GX|ZM|ZQ)\d{3,4}[a-z]?\b", blob, re.I)
        if m:
            return f"Zebra {m.group(0).upper()}", "media"
        return None

    def pantum():
        m = re.search(r"\b([PM]\d{4}[A-Z]*)\b", blob, re.I)
        if m:
            return f"Pantum {m.group(1).upper()}", "media"
        return None

    fn = {"hp": hp, "hewlett": hp, "brother": brother, "epson": epson,
          "canon": canon, "kyocera": kyocera, "ricoh": ricoh, "xerox": xerox,
          "lexmark": lexmark, "samsung": samsung, "oki": oki, "zebra": zebra,
          "pantum": pantum}.get(v)
    if fn:
        r = fn()
        if r:
            return r
    # tenta todos os padroes quando fabricante e desconhecido
    for fn2 in (hp, brother, epson, canon, kyocera, ricoh, xerox, lexmark, samsung, oki, zebra, pantum):
        try:
            r = fn2()
            if r:
                return r[0], "media"
        except Exception:
            pass
    # fallback: texto mais util (prtName > hrDescr > sysDescr resumido)
    fb = _first(prt_name, hr_descr,
                (sys_descr.split(",")[0].split(";")[0] if sys_descr else ""))
    if fb:
        return _clean(fb)[:100], "baixa"
    return "Modelo nao identificado", "baixa"


def model_tokens(modelo_canonico: str) -> list[str]:
    """Tokens uteis para casar driver: ['hp','laserjet','mfp','e52645']."""
    stop = {"managed", "series", "serie", "printer", "impressora"}
    toks = [t.lower() for t in re.split(r"[^A-Za-z0-9]+", modelo_canonico or "") if len(t) >= 2]
    return [t for t in toks if t not in stop]
