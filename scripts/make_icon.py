#!/usr/bin/env python3
"""
scripts/make_icon.py — Generate launcher/icon.ico  (Windows)
                   and launcher/LineBot.app/Contents/Resources/AppIcon.icns (macOS)

Run once from the project root:
    python scripts/make_icon.py

Auto-installs Pillow if missing.
"""
from __future__ import annotations
import io, math, struct, sys
from pathlib import Path

# ── auto-install Pillow ───────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    import subprocess
    print("Installing Pillow...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image, ImageDraw, ImageFilter

ROOT        = Path(__file__).resolve().parent.parent
OUT_ICO     = ROOT / "launcher" / "icon.ico"
OUT_ICNS    = ROOT / "launcher" / "LineBot.app" / "Contents" / "Resources" / "AppIcon.icns"
OUT_PNG     = ROOT / "launcher" / "icon.png"   # reference / debug

# ── palette ───────────────────────────────────────────────────────────────────
PINK        = (214,  58, 249)   # #D63AF9
PINK2       = (184,  46, 224)   # #B82EE0
DEEP        = ( 90,  10, 180)   # #5A0AB4
YELLOW      = (255, 215,  64)   # #FFD740 — dot colour
WHITE       = (255, 255, 255)
SHINE_ALPHA = 55                # opacity of the top highlight


# ── helper: gradient fill ─────────────────────────────────────────────────────
def _lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def _lerp_rgb(c1: tuple, c2: tuple, t: float) -> tuple:
    return (_lerp(c1[0], c2[0], t),
            _lerp(c1[1], c2[1], t),
            _lerp(c1[2], c2[2], t))


# ── draw one icon frame ───────────────────────────────────────────────────────
def make_frame(size: int) -> Image.Image:
    """Render the LINE Bot icon at `size` × `size` pixels (RGBA)."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    S    = size

    # ── 1. Rounded-square background with vertical gradient ───────────────────
    rr = max(1, round(S * 0.22))   # corner radius

    # Draw gradient line by line, then mask to rounded square
    bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    bgd = ImageDraw.Draw(bg)
    for y in range(S):
        t   = y / max(S - 1, 1)
        col = _lerp_rgb(PINK, DEEP, t)
        bgd.line([(0, y), (S - 1, y)], fill=(*col, 255))

    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1],
                                           radius=rr, fill=255)
    img.paste(bg, (0, 0), mask)
    draw = ImageDraw.Draw(img)

    # ── 2. Soft shine highlight (top-left ellipse) ────────────────────────────
    shine = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shine).ellipse(
        [round(S * 0.08), round(S * 0.04),
         round(S * 0.78), round(S * 0.34)],
        fill=(255, 255, 255, SHINE_ALPHA)
    )
    img = Image.alpha_composite(img, shine)
    draw = ImageDraw.Draw(img)

    # ── 3. Chat bubble (white rounded rectangle + tail) ───────────────────────
    bpad = round(S * 0.14)
    bx   = bpad
    by   = round(S * 0.13)
    bw   = S - 2 * bpad
    bh   = round(S * 0.52)
    br   = round(S * 0.10)

    draw.rounded_rectangle([bx, by, bx + bw, by + bh],
                           radius=br, fill=(255, 255, 255, 255))

    # Tail: triangle pointing down-left from bubble
    tw   = round(S * 0.14)
    th   = round(S * 0.14)
    tail_bx = bx + round(bw * 0.16)
    tail_by = by + bh
    draw.polygon(
        [(tail_bx,           tail_by),
         (tail_bx + tw,      tail_by),
         (tail_bx - tw * 0.3, tail_by + th)],
        fill=(255, 255, 255, 255),
    )

    # ── 4. Three dots inside bubble (typing indicator) ────────────────────────
    dr   = max(2, round(S * 0.055))   # dot radius
    dy   = by + round(bh * 0.50)
    for frac in (0.28, 0.50, 0.72):
        dx = bx + round(bw * frac)
        draw.ellipse([dx - dr, dy - dr, dx + dr, dy + dr],
                     fill=(*YELLOW, 255))

    # ── 5. Small star sparkle at top-right of bubble (AI flair) ──────────────
    if size >= 64:
        sx = bx + bw - round(S * 0.10)
        sy = by - round(S * 0.04)
        sr = max(3, round(S * 0.055))
        _draw_star4(draw, sx, sy, sr, color=(255, 255, 200, 230))

    return img


def _draw_star4(draw: ImageDraw.ImageDraw,
                cx: int, cy: int, r: int,
                color: tuple) -> None:
    """Draw a simple 4-point star (cross + diagonal cross)."""
    pts: list[tuple] = []
    for k in range(8):
        angle = math.radians(k * 45)
        radius = r if k % 2 == 0 else r * 0.38
        pts.append((cx + radius * math.cos(angle),
                    cy + radius * math.sin(angle)))
    draw.polygon(pts, fill=color)


# ── ICO writer ────────────────────────────────────────────────────────────────
def save_ico(frames: list[Image.Image], path: Path) -> None:
    sizes = [(f.width, f.height) for f in frames]
    frames[0].save(
        path,
        format="ICO",
        sizes=sizes,
        append_images=frames[1:],
    )


# ── ICNS writer (pure Python — no macOS tools needed) ────────────────────────
# Format: file header (8 B) + chunks (type 4B + size 4B + PNG data)
# PNG-format icon OSTypes:  icp4=16, icp5=32, ic07=128, ic08=256, ic09=512
_ICNS_TYPES = {16: "icp4", 32: "icp5", 64: "icp6",
               128: "ic07", 256: "ic08", 512: "ic09"}

def save_icns(frames: list[Image.Image], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunks = b""
    for f in frames:
        ostype = _ICNS_TYPES.get(f.width)
        if ostype is None:
            continue
        buf = io.BytesIO()
        f.save(buf, format="PNG")
        png = buf.getvalue()
        chunk_len = 8 + len(png)   # includes the 8-byte type+size header
        chunks += ostype.encode("ascii") + struct.pack(">I", chunk_len) + png

    total = 8 + len(chunks)
    path.write_bytes(b"icns" + struct.pack(">I", total) + chunks)


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ico_sizes  = [16, 24, 32, 48, 64, 128, 256]
    icns_sizes = [16, 32, 64, 128, 256, 512]

    print("Rendering icon frames...")
    all_sizes  = sorted(set(ico_sizes + icns_sizes))
    frames     = {s: make_frame(s) for s in all_sizes}

    # Windows ICO
    ico_frames = [frames[s] for s in ico_sizes]
    save_ico(ico_frames, OUT_ICO)
    print(f"  ✓ {OUT_ICO}")

    # macOS ICNS
    icns_frames = [frames[s] for s in icns_sizes]
    save_icns(icns_frames, OUT_ICNS)
    print(f"  ✓ {OUT_ICNS}")

    # Full-size reference PNG
    frames[256].save(OUT_PNG, format="PNG")
    print(f"  ✓ {OUT_PNG}")

    print("Done.")


if __name__ == "__main__":
    main()
