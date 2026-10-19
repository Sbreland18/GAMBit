"""Rebuild assets/gambit.ico so Windows shows it everywhere (taskbar, Alt+Tab, title bar).

Windows reads PNG-compressed icon images reliably only at 256×256; the small sizes it uses
for the taskbar and title bar must be classic 32-bit bitmaps, or it shows a broken icon.
Run:  python tools/make_ico.py [source.png|source.ico]
"""

import io
import os
import struct
import sys

from PIL import Image

SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _frame(src: Image.Image, size: int) -> Image.Image:
    if isinstance(getattr(src, "ico", None), object) and hasattr(src, "ico"):
        try:  # use the hand-drawn size from an existing .ico when it has one
            return src.ico.getimage((size, size)).convert("RGBA")
        except (KeyError, ValueError):
            pass
    return src.convert("RGBA").resize((size, size), Image.LANCZOS)


def _bmp(im: Image.Image) -> bytes:
    w, h = im.size
    header = struct.pack("<IiiHHIIiiII", 40, w, h * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    px = im.tobytes("raw", "BGRA")
    rows = [px[y * w * 4:(y + 1) * w * 4] for y in range(h)][::-1]     # bottom-up
    mask_row = ((w + 31) // 32) * 4
    mask = b"\x00" * (mask_row * h)          # transparency comes from the alpha channel
    return header + b"".join(rows) + mask


def build(src_path: str, out_path: str):
    src = Image.open(src_path)
    if hasattr(src, "ico"):
        big = max(src.ico.sizes())
        base = src.ico.getimage(big).convert("RGBA")
    else:
        base = src.convert("RGBA")
    blobs = []
    for s in SIZES:
        im = _frame(src, s) if hasattr(src, "ico") and (s, s) in src.ico.sizes() else \
            base.resize((s, s), Image.LANCZOS)
        if s >= 256:
            buf = io.BytesIO()
            im.save(buf, "PNG")
            blobs.append((s, buf.getvalue()))
        else:
            blobs.append((s, _bmp(im)))
    out = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    for s, data in blobs:
        b = 0 if s >= 256 else s
        out += struct.pack("<BBBBHHII", b, b, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(d for _s, d in blobs)
    with open(out_path, "wb") as fh:
        fh.write(out)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "assets", "gambit.png")
    build(src, os.path.join(HERE, "assets", "gambit.ico"))
    print("Wrote assets/gambit.ico")
