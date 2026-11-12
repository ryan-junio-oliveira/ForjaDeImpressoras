"""
Deteccao de sub-redes locais — espelhado no HyperViewerDesktop
(app/data/network_scanner.py: _get_local_ip via UDP + _get_subnet_ips /24,
scan em lotes com progresso 0-100, check_single_ip).

Diferencas/adaptacoes para impressoras:
- detecta TODAS as interfaces IPv4 com suas mascaras reais (via ipconfig),
  nao assume /24;
- aceita multiplos CIDRs ("192.168.15.0/24, 10.0.0.0/24");
- inclui sempre a tabela ARP (impressora pode bloquear ping).
"""
import ipaddress
import re
import socket

from app.platform import process as winproc


def get_local_ip() -> str | None:
    """IP da interface de rota padrao (truque UDP, igual ao HyperViewer).
    connect() em UDP nao envia pacote — so seleciona a interface."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for fam, _, _, _, addr in socket.getaddrinfo(hostname, None):
            if fam == socket.AF_INET and not addr[0].startswith("127."):
                return addr[0]
    except Exception:
        pass
    return None


def get_all_local_networks() -> list[str]:
    """Lista CIDRs reais das interfaces IPv4 (via ipconfig). Ex: ['192.168.15.0/24']."""
    nets: dict[str, None] = {}
    try:
        res = winproc.run(["ipconfig"], capture_output=True, text=True, timeout=15,
                             encoding="utf-8", errors="ignore")
        txt = res.stdout or ""
        # pares IPv4 + mascara (ordem do ipconfig: IP vem antes da mascara)
        ips = re.findall(r"Endereço IPv4[^\d]*(\d+\.\d+\.\d+\.\d+)", txt)
        masks = re.findall(r"Máscara de Sub-rede[^\d]*(\d+\.\d+\.\d+\.\d+)", txt)
        # fallback: locale ingles
        if not ips:
            ips = re.findall(r"IPv4 Address[^\d]*(\d+\.\d+\.\d+\.\d+)", txt)
            masks = re.findall(r"Subnet Mask[^\d]*(\d+\.\d+\.\d+\.\d+)", txt)
        for i, ip in enumerate(ips):
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            mask = masks[i] if i < len(masks) else "255.255.255.0"
            try:
                net = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
                nets[str(net)] = None
            except Exception:
                continue
    except Exception:
        pass
    if not nets:
        lip = get_local_ip()
        if lip:
            try:
                nets[str(ipaddress.ip_network(f"{lip}/24", strict=False))] = None
            except Exception:
                pass
    if not nets:
        nets["192.168.0.0/24"] = None
    return sorted(nets)


def parse_cidrs(text: str | None) -> list[str]:
    """'192.168.15.0/24, 10.0.0.0/24' -> lista validada. IP puro vira host unico."""
    valid, _invalid = validate_cidrs(text)
    return valid


def validate_cidrs(text: str | None) -> tuple[list[str], list[str]]:
    out = []
    invalid = []
    if not text:
        return out, invalid
    for part in re.split(r"[;,\s]+", text.strip()):
        if not part:
            continue
        try:
            if "/" not in part:
                ipaddress.ip_address(part)  # valida host unico
                out.append(part)
            else:
                out.append(str(ipaddress.ip_network(part, strict=False)))
        except Exception:
            invalid.append(part)
    return out, invalid


def expand_targets(cidrs: list[str] | None = None, include_arp: bool = True,
                   max_hosts: int = 2048) -> tuple[list[str], list[str]]:
    """Expande CIDRs (ou sub-redes locais) em lista de IPs.
    Retorna (targets, avisos). Redes > max_hosts entram via ARP apenas."""
    from .scanner import parse_arp_table
    avisos: list[str] = []
    if not cidrs:
        cidrs = get_all_local_networks()
    targets: list[str] = []
    for c in cidrs:
        try:
            if "/" not in c:  # host unico (IP manual)
                try:
                    a = ipaddress.ip_address(c)
                    if a.is_multicast or a.is_reserved or a.is_loopback \
                            or a.is_unspecified:
                        avisos.append(f"IP ignorado (nao varrivel): {c}")
                        continue
                except Exception:
                    avisos.append(f"Rede invalida ignorada: {c}")
                    continue
                targets.append(c)
                continue
            net = ipaddress.ip_network(c, strict=False)
            if net.num_addresses - 2 > max_hosts:
                avisos.append(f"{c} grande demais ({net.num_addresses} IPs) — usando ARP+tabela local.")
                continue
            targets.extend(str(ip) for ip in net.hosts())
        except Exception:
            avisos.append(f"Rede invalida ignorada: {c}")
    if include_arp:
        try:
            for ip in parse_arp_table():
                if ip not in targets:
                    targets.append(ip)
        except Exception:
            pass
    return sorted(set(targets)), avisos
