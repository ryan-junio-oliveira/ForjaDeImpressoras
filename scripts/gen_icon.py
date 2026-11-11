"""
Gera app/resources/icon.ico (multi-resolucao) sem dependencias externas.

Desenha o icone do app em PNG puro (zlib + struct) e empacota as entradas
num container ICO. Uso:
    python scripts/gen_icon.py
"""
import math
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "resources" / "icon.ico"

SIZES = (16, 24, 32, 48, 64, 128, 256)

PURPLE = (124, 58, 237)     # #7C3AED
BLUE = (37, 99, 235)        # #2563EB
WHITE = (255, 255, 255)
GOLD = (245, 158, 11)       # #F59E0B


def _rounded(x, y, w, h, r, px, py):
    """True se (px,py) esta dentro do retangulo arredondado."""
    if px < x or px > x + w or py < y or py > y + h:
        return False
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def render(size):
    """Desenha o icone e devolve os pixels RGBA (bytes)."""
    s = size
    px = bytearray(s * s * 4)
    u = s / 64.0          # unidade de desenho (base 64)

    for y in range(s):
        for x in range(s):
            r, g, b, a = 0, 0, 0, 0
            # fundo: retangulo arredondado com gradiente diagonal
            if _rounded(0, 0, s - 1, s - 1, 13 * u, x, y):
                t = (x + y) / (2.0 * (s - 1))
                r = int(PURPLE[0] + (BLUE[0] - PURPLE[0]) * t)
                g = int(PURPLE[1] + (BLUE[1] - PURPLE[1]) * t)
                b = int(PURPLE[2] + (BLUE[2] - PURPLE[2]) * t)
                a = 255
            # impressora: bandeja de papel
            if _rounded(20 * u, 11 * u, 24 * u, 12 * u, 3 * u, x, y):
                r, g, b, a = WHITE + (255,)
            # corpo
            if _rounded(13 * u, 21 * u, 38 * u, 21 * u, 4 * u, x, y):
                r, g, b, a = WHITE + (255,)
            # papel saindo
            if _rounded(19 * u, 41 * u, 26 * u, 13 * u, 3 * u, x, y):
                r, g, b, a = WHITE + (255,)
            # visor
            if _rounded(40 * u, 26 * u, 7 * u, 5 * u, 2 * u, x, y):
                r, g, b, a = GOLD + (255,)
            i = (y * s + x) * 4
            px[i:i + 4] = bytes((r, g, b, a))
    return bytes(px)


def png_bytes(size, raw):
    """Empacota os pixels RGBA em PNG."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw_rows = b"".join(b"\x00" + raw[y * size * 4:(y + 1) * size * 4]
                         for y in range(size))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw_rows, 9))
            + chunk(b"IEND", b""))


def build_ico(images):
    """Monta o container ICO com entradas PNG."""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    entries, blobs = b"", b""
    for size, data in images:
        w = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


def main():
    print("[INFO] Gerando o icone do app...")
    images = []
    for size in SIZES:
        images.append((size, png_bytes(size, render(size))))
        print(f"       {size}x{size}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_ico(images))
    print(f"[OK] {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
