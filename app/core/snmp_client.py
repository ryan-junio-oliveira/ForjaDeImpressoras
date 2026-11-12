"""
Cliente SNMP v1/v2c minimo (sem dependencias externas).
Usado para identificar impressoras na rede via sysDescr, modelo e fabricante.
"""
import socket
import struct
import random


def _enc_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _enc_int(n: int) -> bytes:
    if n == 0:
        body = b"\x00"
    else:
        body = n.to_bytes((n.bit_length() + 8) // 8, "big", signed=True)
        # remove redundancia de sinal
        while len(body) > 1 and ((body[0] == 0x00 and body[1] < 0x80) or (body[0] == 0xFF and body[1] >= 0x80)):
            body = body[1:]
    return b"\x02" + _enc_len(len(body)) + body


def _enc_octets(b: bytes) -> bytes:
    return b"\x04" + _enc_len(len(b)) + b


def _enc_null() -> bytes:
    return b"\x05\x00"


def _enc_oid(oid: str) -> bytes:
    parts = [int(x) for x in oid.strip().split(".")]
    if len(parts) < 2:
        raise ValueError("OID invalida: " + oid)
    body = bytes([parts[0] * 40 + parts[1]])
    for p in parts[2:]:
        tmp = [p & 0x7F]
        p >>= 7
        while p:
            tmp.append(0x80 | (p & 0x7F))
            p >>= 7
        body += bytes(reversed(tmp))
    return b"\x06" + _enc_len(len(body)) + body


def _enc_seq(body: bytes) -> bytes:
    return b"\x30" + _enc_len(len(body)) + body


def build_get(community: str, oid_list, request_id=None, version=0) -> bytes:
    """Monta pacote SNMP GET. version: 0=v1, 1=v2c."""
    if request_id is None:
        request_id = random.randint(1, 2_147_483_647)
    varbinds = b""
    for oid in oid_list:
        vb = _enc_seq(_enc_oid(oid) + _enc_null())
        varbinds += vb
    pdu_body = _enc_int(request_id) + _enc_int(0) + _enc_int(0) + _enc_seq(varbinds)
    pdu = b"\xA0" + _enc_len(len(pdu_body)) + pdu_body  # GETREQUEST
    msg = _enc_seq(_enc_int(version) + _enc_octets(community.encode()) + pdu)
    return msg


def _read_tlv(buf: bytes, off: int):
    if off >= len(buf):
        raise ValueError("buffer curto")
    tag = buf[off]
    off += 1
    ln = buf[off]
    off += 1
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(buf[off:off + n], "big")
        off += n
    val = buf[off:off + ln]
    return tag, val, off + ln


def _parse_oid(val: bytes) -> str:
    if not val:
        return ""
    out = [str(val[0] // 40), str(val[0] % 40)]
    i = 1
    while i < len(val):
        n = 0
        while True:
            n = (n << 7) | (val[i] & 0x7F)
            done = not (val[i] & 0x80)
            i += 1
            if done:
                break
        out.append(str(n))
    return ".".join(out)


def _parse_value(tag: int, val: bytes):
    if tag == 0x04:  # octet string
        try:
            return val.decode("utf-8", errors="replace").strip()
        except Exception:
            return val.hex()
    if tag == 0x02:  # integer
        return int.from_bytes(val, "big", signed=True)
    if tag == 0x06:  # oid
        return _parse_oid(val)
    if tag == 0x05:  # null
        return None
    if tag == 0x40:  # IpAddress
        return ".".join(str(b) for b in val)
    if tag == 0x41:  # Counter32
        return int.from_bytes(val, "big")
    if tag == 0x42:  # Gauge32
        return int.from_bytes(val, "big")
    if tag == 0x43:  # TimeTicks
        return int.from_bytes(val, "big")
    if tag in (0x80, 0x81, 0x82):
        return None
    # tenta texto
    try:
        t = val.decode("utf-8", errors="strict").strip()
        if t and all(32 <= ord(c) < 127 or c in "\r\n\t" for c in t):
            return t
    except Exception:
        pass
    return val.hex() if isinstance(val, bytes) else val


def parse_response(buf: bytes):
    """Retorna dict {oid: valor} do GET-RESPONSE."""
    result = {}
    try:
        tag, msg, off = _read_tlv(buf, 0)
        if tag != 0x30:
            return result
        # version
        _, _, off = _read_tlv(buf, off)
        # community
        _, _, off = _read_tlv(buf, off)
        # PDU (0xA2 = response)
        ptag, pdu, _ = _read_tlv(buf, off)
        poff = 0
        _, _, poff = _read_tlv(pdu, poff)  # request-id
        _, err, poff = _read_tlv(pdu, poff)  # error-status
        _, _, poff = _read_tlv(pdu, poff)  # error-index
        try:
            err_code = int.from_bytes(err, "big", signed=True)
        except Exception:
            err_code = 0
        if err_code != 0:
            return {}
        _, vblist, _ = _read_tlv(pdu, poff)
        voff = 0
        while voff < len(vblist):
            _, vb, voff = _read_tlv(vblist, voff)
            ioff = 0
            otag, oval, ioff = _read_tlv(vb, ioff)
            oid = _parse_oid(oval)
            vtag, vval, _ = _read_tlv(vb, ioff)
            val = _parse_value(vtag, vval)
            if val is None:
                continue
            result[oid] = val
    except Exception:
        pass
    return result


def snmp_get(ip: str, oids, community="public", timeout=1.5, retries=1, port=161):
    """Faz SNMP GET (v1, tenta v2c em fallback). Retorna dict ou {}."""
    if isinstance(oids, str):
        oids = [oids]
    for version in (0, 1):
        pkt = build_get(community, oids, version=version)
        for _ in range(retries + 1):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(timeout)
            try:
                s.sendto(pkt, (ip, port))
                data, _ = s.recvfrom(65535)
                out = parse_response(data)
                if out:
                    return out
            except socket.timeout:
                continue
            except Exception:
                break
            finally:
                s.close()
    return {}


# OIDs uteis para impressoras
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_HR_DEVICE_DESCR = "1.3.6.1.2.1.25.3.2.1.3.1"
OID_PRT_GENERAL_PRINTER_NAME = "1.3.6.1.2.1.43.5.1.1.16.1"
OID_PRT_GENERAL_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
OID_JETDIRECT_MODEL = "1.3.6.1.4.1.11.2.3.9.1.1.7.0"

PRINTER_OIDS = [
    OID_SYS_DESCR,
    OID_SYS_OBJECT_ID,
    OID_SYS_NAME,
    OID_HR_DEVICE_DESCR,
    OID_PRT_GENERAL_PRINTER_NAME,
    OID_PRT_GENERAL_SERIAL,
]
