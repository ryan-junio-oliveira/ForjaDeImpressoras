"""
Download automatico do driver PCL correto do FABRICANTE.
- Le driver_packs.json (urls diretas verificadas por fabricante);
- baixa (com progresso), confere sha256 quando informado;
- extrai (zip) para ./drivers/_downloads/<id>/;
- localiza o .inf que casa com o MODELO exato e devolve (inf, driver_name).

Nunca retorna driver generico: o .inf baixado e sempre do fabricante,
e o nome instalado vem de dentro do proprio .inf.
"""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

from app.data import paths
from app.platform import process as winproc

BASE = paths.base_dir()
PACKS_JSON = paths.PACKS_JSON
DOWNLOAD_DIR = paths.downloads_dir()


def load_packs() -> list[dict]:
    try:
        data = json.loads(PACKS_JSON.read_text(encoding="utf-8"))
        return [p for p in data.get("packs", []) if p.get("url")]
    except Exception:
        return []


def packs_for_vendor(vendor: str, modelo_canonico: str = "") -> list[dict]:
    """Packs do fabricante; packs com model_match so valem para o modelo casado."""
    import re as _re
    v = (vendor or "").lower()
    out = []
    for p in load_packs():
        if p.get("vendor", "").lower() != v:
            continue
        mm = (p.get("model_match") or "").strip()
        if mm and modelo_canonico:
            if not _re.search(mm, modelo_canonico, _re.I):
                continue
        out.append(p)
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def download_pack(pack: dict, log=None, progress_cb=None, cancel_event=None) -> Path:
    """Baixa o pacote. Retorna o caminho do arquivo. Confere sha256 se informado."""
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    url = pack["url"]
    fname = url.split("/")[-1].split("?")[0] or (pack["id"] + ".zip")
    dest = DOWNLOAD_DIR / fname
    expected = (pack.get("sha256") or "").upper()

    def _valid_file(p: Path) -> bool:
        try:
            if not p.exists() or p.stat().st_size < 200_000:
                return False
            with open(p, "rb") as f:
                magic = f.read(4)
            if fname.lower().endswith(".zip") and magic[:2] != b"PK":
                return False
            if fname.lower().endswith(".exe") and magic[:2] != b"MZ":
                return False
            return True
        except Exception:
            return False

    if dest.exists() and dest.stat().st_size > 1_000_000:
        if expected:
            try:
                if _sha256_file(dest) == expected:
                    if log:
                        log(f"Pacote em cache: {fname}")
                    return dest
                dest.unlink(missing_ok=True)
            except Exception:
                dest.unlink(missing_ok=True)
        elif _valid_file(dest):
            if log:
                log(f"Pacote em cache (sem checksum, formato valido): {fname}")
            return dest
        else:
            dest.unlink(missing_ok=True)

    def report(blocks, block_size, total):
        if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
            raise CancelledError("Download cancelado pelo usuario.")
        if progress_cb and total and total > 0:
            try:
                progress_cb(min(100, int(blocks * block_size * 100 / total)))
            except CancelledError:
                raise
            except Exception:
                pass

    if log:
        log(f"Baixando {pack['id']} ({url}) ...")
    import urllib.error as _uerr
    for attempt in range(3):
        try:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                raise CancelledError("Download cancelado pelo usuario.")
            req = urllib.request.Request(url, headers={"User-Agent": "PrinterInstaller/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
                ctype = (r.headers.get("Content-Type") or "").lower()
                if "text/html" in ctype:
                    raise ValueError(f"URL retornou HTML ({ctype}) — link expirado?")
                total = 0
                while True:
                    if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                        raise CancelledError("Download cancelado pelo usuario.")
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > 1024 * 1024 * 1024:
                        raise ValueError("Arquivo excede 1GB — abortado.")
                    f.write(chunk)
                    if progress_cb:
                        try:
                            progress_cb(-1)
                        except Exception:
                            pass
            break
        except CancelledError:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        except Exception as e:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            if attempt == 2:
                raise ValueError(f"Falha ao baixar {pack['id']} apos 3 tentativas: {e}")
    if expected:
        got = _sha256_file(dest)
        if got != expected:
            dest.unlink(missing_ok=True)
            raise ValueError(f"Checksum divergente em {fname}. Download descartado.")
        if log:
            log("Checksum sha256 OK.")
    elif not _valid_file(dest):
        dest.unlink(missing_ok=True)
        raise ValueError(f"Arquivo baixado invalido em {fname}.")
    return dest


class CancelledError(RuntimeError):
    pass


def find_7z():
    import shutil
    for cand in (shutil.which("7z"), shutil.which("7za"),
                 r"C:\Program Files\7-Zip\7z.exe",
                 r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if cand:
            try:
                from pathlib import Path as _P
                if _P(cand).exists():
                    return cand
            except Exception:
                continue
    return None


def extract_pack(archive: Path, pack_id: str, log=None, cancel_event=None) -> Path:
    """Extrai para ./drivers/_downloads/<pack_id>/ e retorna a pasta."""
    import subprocess
    out = DOWNLOAD_DIR / pack_id
    out.mkdir(parents=True, exist_ok=True)
    # ja extraido (existe .inf do fabricante) -> reaproveita, nao re-extrai
    try:
        if list(out.rglob("*.inf")):
            try:
                if archive.exists() and archive.stat().st_mtime > max(
                        p.stat().st_mtime for p in out.rglob("*.inf")):
                    pass  # archive mais novo: re-extrai abaixo
                else:
                    if log:
                        log(f"Pacote ja extraido em {out}")
                    return out
            except Exception:
                if log:
                    log(f"Pacote ja extraido em {out}")
                return out
    except Exception:
        pass
    if archive.suffix.lower() == ".zip" and zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for m in z.namelist():
                if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                    raise CancelledError("Extracao cancelada.")
                p = (out / m).resolve()
                try:
                    if out.resolve() not in p.parents and p != out.resolve():
                        continue
                except Exception:
                    continue
            z.extractall(out)
        if log:
            log(f"Extraido em {out}")
        return out
    # .exe auto-extraivel (HP InstallShield / Brother hostm).
    # Tenta o 7-Zip (silencioso). Só depois disso, o proprio instalador —
    # e no máximo 2 conjuntos de switches: um instalador GUI mal
    # parametrizado abre janelas de erro na tela do usuario.
    if archive.suffix.lower() == ".exe":
        z7 = find_7z()
        if z7:
            try:
                winproc.run([z7, "x", "-aoa", f"-o{out}", str(archive), "-y"],
                            timeout=180, capture_output=True)
                if list(out.rglob("*.inf")):
                    if log:
                        log(f"Extraido com 7-Zip em {out}")
                    return out
            except Exception:
                pass
        silenciosos = (["/extract", str(out)], ["/s", f"/f{out}"])
        for args in silenciosos:
            try:
                winproc.run([str(archive)] + args, timeout=180, capture_output=True)
                if list(out.rglob("*.inf")):
                    if log:
                        log(f"Extraido em {out}")
                    return out
            except Exception:
                continue
        if log:
            log(f"Extracao automatica de {archive.name} nao suportada — "
                f"extraia manualmente em {out}")
    return out


def find_inf_for_model(root: Path, vendor: str, modelo_canonico: str, inf_hint: str = "",
                       hardware_ids=None, device_id: str = ""):
    """Acha o .inf no pacote que casa com o modelo. Retorna (inf, score, driver_names)."""
    from .driver_manager import parse_inf_driver_names
    from .model_identifier import model_tokens
    toks = model_tokens(modelo_canonico)
    hw = [str(h).lower() for h in (hardware_ids or []) if h]
    if device_id:
        hw.append(str(device_id).lower())
    fab = (vendor or "").lower()
    best = None
    for inf in root.rglob("*.inf"):
        try:
            raw = inf.read_bytes()[:80000]
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
        score = 0
        if fab and fab in text:
            score += 5
        for t in toks:
            if t in text:
                score += 4 if len(t) > 3 else 1
        # casamento exato do hardware USB (prioridade maxima)
        for h in hw:
            if h and h in text:
                score += 25
        if any(h in text for h in ("pcl6", "pcl 6", "pclxl")):
            score += 4
        elif "pcl" in text:
            score += 2
        if inf_hint and inf.name.lower() == inf_hint.lower():
            score += 6
        dnames = parse_inf_driver_names(inf)
        if not dnames:
            score -= 5
        elif all((__import__("app.core.driver_manager", fromlist=["is_generic_name"]).is_generic_name(n) for n in dnames)):
            continue
        if best is None or score > best[1]:
            best = (inf, score, dnames)
    if best is not None and best[1] < 4:
        return None
    return best


def ensure_driver_pack(vendor: str, modelo_canonico: str, log=None, progress_cb=None,
                        hardware_ids=None, device_id: str = "", cancel_event=None):
    """Baixa+extrai o pack do fabricante e retorna (inf, driver_name, pack_id) ou None."""
    packs = packs_for_vendor(vendor, modelo_canonico)
    if not packs:
        if log:
            try:
                log(f"Sem packs cadastrados para {vendor} {modelo_canonico}.")
            except Exception:
                pass
        return None
    for pack in packs:
        try:
            if cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)():
                from .driver_download import CancelledError as _C
                raise _C("Operacao cancelada.")
            archive = download_pack(pack, log=log, progress_cb=progress_cb, cancel_event=cancel_event)
            root = extract_pack(archive, pack["id"], log=log, cancel_event=cancel_event)
            found = find_inf_for_model(root, vendor, modelo_canonico, pack.get("inf_hint", ""),
                                       hardware_ids=hardware_ids, device_id=device_id)
            if found:
                inf, score, dnames = found
                if log:
                    log(f"Pack {pack['id']}: {inf.name} score={score}")
                if dnames:
                    # prefere entrada com PCL no nome
                    dnames_sorted = sorted(dnames, key=lambda n: ("pcl" not in n.lower(), len(n)))
                    return inf, dnames_sorted[0], pack["id"]
                return inf, None, pack["id"]
        except Exception as e:
            if log:
                log(f"Pack {pack['id']} falhou: {e}")
            continue
    return None
