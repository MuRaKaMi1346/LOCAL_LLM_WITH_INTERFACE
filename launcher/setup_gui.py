#!/usr/bin/env python3
"""First-run setup window — circular spinner with flame animation, retry support.

DPI-aware on Windows. Works on macOS Retina and standard monitors.
"""
from __future__ import annotations
import math, os, subprocess, sys, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk

# ── Windows: declare DPI-aware before Tk initialises (sharp rendering) ────────
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

PROJECT_DIR = Path(__file__).resolve().parent.parent
_W32      = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_VENV_PY  = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
_VENV_PYW = PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"
_VENV_MAC = PROJECT_DIR / ".venv" / "bin" / "python"
_FLAG     = PROJECT_DIR / ".venv" / ".setup_done"
REQ       = PROJECT_DIR / "requirements.txt"

C = dict(
    BG="#F6F0FF", CARD="#FFFFFF", CARD2="#FAF6FF",
    LOG_BG="#0D0D1A", LOG_FG="#D0D0FF",
    PINK="#D63AF9", PINK2="#B82EE0", PINK_LIGHT="#F3E6FF",
    GREEN="#00C853", RED="#FF1744", ORANGE="#FF9100",
    YELLOW="#FFD740",
    TEXT="#1A1A2E", TEXT2="#4A4A6A", MUTED="#9090B0",
    WHITE="#FFFFFF", BORDER="#E0D0F5",
)

_STEPS = [
    ("venv", "Python Environment"),
    ("pip",  "Package Installation"),
    ("done", "Launching App"),
]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _venv_py() -> str | None:
    for p in (_VENV_PY, _VENV_MAC):
        if p.exists():
            return str(p)
    return None


def _launch_exe() -> str:
    if _VENV_PYW.exists():
        return str(_VENV_PYW)
    return _venv_py() or sys.executable


def _needs_setup() -> bool:
    py = _venv_py()
    if py is None:
        return True
    if _FLAG.exists():
        return False
    try:
        r = subprocess.run(
            [py, "-c", "import fastapi, linebot, chromadb"],
            capture_output=True, timeout=10,
        )
        if r.returncode == 0:
            _FLAG.touch()
            return False
    except Exception:
        pass
    return True


# ── Circular spinner with rotating flame effect ───────────────────────────────
class CircleLoader(tk.Canvas):
    """
    Indeterminate spinner:
      • Gray track ring
      • Gradient sweeping arc  (tail=dim-lavender → head=bright-pink)
      • Flame spark particles trailing the head (white→yellow→orange→red)
      • Bright white comet-tip at arc head

    States: "spin" | "ok" (green fill + checkmark) | "error" (red ring + X)
    """

    # Spark colours — index 0 = head (white), last = tail (deep red)
    _SPARK = ["#FFFFFF", "#FFE57F", "#FFD740", "#FFAB40",
              "#FF9100", "#FF6D00", "#FF3D00", "#FF1744"]
    # Glow arc colours — index 0 = tail (dim), last = head (bright)
    _GLOWS = ["#EDD8FF", "#C878F0", "#C040E0", "#D63AF9"]

    def __init__(self, parent: tk.Widget, size: int = 130,
                 bg: str = C["BG"], **kw):
        super().__init__(parent, width=size, height=size,
                         highlightthickness=0, bd=0, bg=bg, **kw)
        self._sz      = size
        self._cx      = size / 2
        self._cy      = size / 2
        self._r       = size * 0.355
        self._sw      = max(5, size // 19)
        self._ang     = 90.0        # head angle, degrees, tkinter convention (0=right, CCW+)
        self._spd     = 3.5         # degrees per frame (CW: decrease angle)
        self._swe     = 215         # arc sweep in degrees
        self._state   = "spin"
        self._ok_pct  = 0.0
        self._running = False

    # ── Public API ────────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._state   = "spin"
        self._running = True
        self._tick()

    def stop(self) -> None:
        self._running = False

    def set_ok(self) -> None:
        """Switch to green-fill animation; existing tick loop picks up new state."""
        self._state  = "ok"
        self._ok_pct = 0.0

    def set_error(self) -> None:
        self._state   = "error"
        self._running = False
        self._draw()

    # ── Animation loop ────────────────────────────────────────────────────────
    def _tick(self) -> None:
        if not self._running:
            return
        if self._state == "spin":
            self._ang = (self._ang - self._spd) % 360   # CW on screen
        elif self._state == "ok":
            self._ok_pct = min(1.0, self._ok_pct + 0.032)
            if self._ok_pct >= 1.0:
                self._running = False
        self._draw()
        if self._running:
            self.after(16, self._tick)   # ≈60 fps

    # ── Drawing dispatcher ────────────────────────────────────────────────────
    def _draw(self) -> None:
        self.delete("all")
        cx, cy, r, sw = self._cx, self._cy, self._r, self._sw
        if   self._state == "ok":    self._draw_ok(cx, cy, r, sw)
        elif self._state == "error": self._draw_error(cx, cy, r, sw)
        else:                         self._draw_spin(cx, cy, r, sw)

    def _draw_spin(self, cx: float, cy: float, r: float, sw: int) -> None:
        head = self._ang
        swe  = self._swe

        # 1. Track ring
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                         outline="#DEC8F8", width=sw)

        # 2. Gradient glow arcs — drawn tail-first so head layers on top.
        #    Each arc starts at 'head' and extends CCW by 'ext' degrees.
        #    Shorter arcs (drawn later) cover the head portion with brighter colour.
        ng = len(self._GLOWS)
        for i, col in enumerate(self._GLOWS):
            frac = i / (ng - 1)                              # 0=tail, 1=head
            ext  = swe * (1.0 - 0.72 * frac)                # long at tail → short at head
            w    = max(1, int(sw * (1.35 - 0.55 * frac)))   # thicker at tail (glow bloom)
            self.create_arc(cx-r, cy-r, cx+r, cy+r,
                            start=head, extent=ext,
                            style="arc", outline=col, width=w)

        # 3. Flame spark particles: index 0 = head (white), n-1 = tail (red).
        #    Angles increase CCW from head toward tail (arc goes CCW from head).
        n = len(self._SPARK)
        for i in range(n):
            frac = i / (n - 1)
            ang_deg = head + frac * swe * 0.91   # CCW from head
            ang_rad = math.radians(ang_deg)
            # Outward bulge near head to simulate fire leaping off the ring
            wave = math.sin(frac * math.pi)
            rr   = r * (1.0 + 0.20 * (1 - frac) * wave)
            px   = cx + rr * math.cos(ang_rad)
            py   = cy - rr * math.sin(ang_rad)    # minus: canvas y flipped
            sz   = max(1.0, sw * (0.82 - 0.62 * frac))
            self.create_oval(px-sz, py-sz, px+sz, py+sz,
                             fill=self._SPARK[i], outline="")

        # 4. Comet tip: soft pink halo + white core at the arc head
        tip_a = math.radians(head)
        tx    = cx + r * math.cos(tip_a)
        ty    = cy - r * math.sin(tip_a)
        tr    = sw * 0.72
        self.create_oval(tx-tr*1.9, ty-tr*1.9, tx+tr*1.9, ty+tr*1.9,
                         fill="#ECC8FF", outline="")
        self.create_oval(tx-tr, ty-tr, tx+tr, ty+tr,
                         fill="#FFFFFF", outline="")

    def _draw_ok(self, cx: float, cy: float, r: float, sw: int) -> None:
        p = self._ok_pct
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                         outline="#C8EDD8", width=sw)
        if p > 0:
            self.create_arc(cx-r, cy-r, cx+r, cy+r,
                            start=90, extent=p * 360,
                            style="arc", outline=C["GREEN"], width=sw)
        if p > 0.80:
            ck = r * 0.42
            self.create_line(
                cx - ck*0.60, cy + ck*0.05,
                cx - ck*0.05, cy + ck*0.52,
                cx + ck*0.65, cy - ck*0.48,
                fill=C["GREEN"], width=max(2, sw // 2),
                smooth=True, joinstyle="round", capstyle="round",
            )

    def _draw_error(self, cx: float, cy: float, r: float, sw: int) -> None:
        self.create_oval(cx-r, cy-r, cx+r, cy+r,
                         outline=C["RED"], width=sw)
        ck = r * 0.38
        kw = dict(fill=C["RED"], width=max(2, sw // 2),
                  capstyle="round", joinstyle="round")
        self.create_line(cx-ck, cy-ck, cx+ck, cy+ck, **kw)
        self.create_line(cx+ck, cy-ck, cx-ck, cy+ck, **kw)


# ── Step row ──────────────────────────────────────────────────────────────────
class StepRow(tk.Frame):
    _ICONS  = {"wait": "○", "active": "⟳", "done": "✓", "error": "✗"}
    _COLORS = {
        "wait":   (C["MUTED"],  C["MUTED"]),
        "active": (C["PINK"],   C["TEXT"]),
        "done":   (C["GREEN"],  C["TEXT2"]),
        "error":  (C["RED"],    C["RED"]),
    }

    def __init__(self, parent: tk.Widget, label: str, bg: str = C["BG"]):
        super().__init__(parent, bg=bg)
        self._icon = tk.Label(self, text="○", width=2, font=("", 12),
                              bg=bg, fg=C["MUTED"], anchor="center")
        self._icon.pack(side="left")
        self._name = tk.Label(self, text=label, font=("", 10, "bold"),
                              bg=bg, fg=C["MUTED"], width=22, anchor="w")
        self._name.pack(side="left", padx=(4, 0))
        self._detail = tk.Label(self, text="", font=("", 9),
                                bg=bg, fg=C["MUTED"], anchor="w")
        self._detail.pack(side="left", fill="x", expand=True)

    def set_state(self, state: str, detail: str = "") -> None:
        ic, nc = self._COLORS.get(state, self._COLORS["wait"])
        self._icon.config(text=self._ICONS.get(state, "○"), fg=ic)
        self._name.config(fg=nc)
        self._detail.config(text=detail, fg=ic)


# ── Main window ───────────────────────────────────────────────────────────────
class SetupApp(tk.Tk):
    _W, _H         = 460, 430
    _W_LOG, _H_LOG = 460, 690

    def __init__(self) -> None:
        super().__init__()
        self.title("LINE Bot — Setup")
        self.resizable(False, False)
        self.configure(bg=C["BG"])
        self._log_open  = False
        self._cancelled = False
        self._hdr_sub   = "กำลังเตรียมระบบ..."
        self._build()
        self._regeom(self._W, self._H)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.createcommand("tk::mac::Quit", self._on_close)
        except Exception:
            pass
        self.after(350, self._start_worker)

    # ── Geometry ──────────────────────────────────────────────────────────────
    def _regeom(self, w: int, h: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _on_close(self) -> None:
        self._cancelled = True
        self.destroy()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # Gradient header
        self._hdr_cv = tk.Canvas(self, height=72, highlightthickness=0, bd=0)
        self._hdr_cv.pack(fill="x")
        self._hdr_cv.bind("<Configure>", lambda _: self._draw_hdr())
        self.after(10, self._draw_hdr)

        # ── Centre: spinner (left) + messages (right) ─────────────────────────
        centre = tk.Frame(self, bg=C["BG"])
        centre.pack(fill="x", padx=28, pady=(20, 0))

        self._loader = CircleLoader(centre, size=128, bg=C["BG"])
        self._loader.pack(side="left", padx=(0, 18))
        self._loader.start()

        msg_col = tk.Frame(centre, bg=C["BG"])
        msg_col.pack(side="left", fill="x", expand=True)

        self._msg = tk.Label(msg_col, text="กำลังเตรียมระบบ...",
                             font=("", 13, "bold"), bg=C["BG"],
                             fg=C["TEXT"], wraplength=265, justify="left")
        self._msg.pack(anchor="w")

        self._sub = tk.Label(msg_col, text="กรุณารอสักครู่",
                             font=("", 10), bg=C["BG"],
                             fg=C["MUTED"], wraplength=265, justify="left")
        self._sub.pack(anchor="w", pady=(4, 0))

        self._badge = tk.Label(msg_col, text="", font=("", 9),
                               bg=C["BG"], fg=C["PINK"])
        self._badge.pack(anchor="w", pady=(3, 0))

        # ── Step tracker ──────────────────────────────────────────────────────
        steps_f = tk.Frame(self, bg=C["BG"])
        steps_f.pack(fill="x", padx=28, pady=(16, 0))
        self._step_rows: dict[str, StepRow] = {}
        for key, label in _STEPS:
            row = StepRow(steps_f, label, bg=C["BG"])
            row.pack(fill="x", pady=2)
            self._step_rows[key] = row

        # ── Error / retry area (hidden until needed) ──────────────────────────
        self._retry_frame = tk.Frame(self, bg=C["BG"])
        self._retry_frame.pack(fill="x", padx=28, pady=(10, 0))
        self._err_lbl = tk.Label(
            self._retry_frame, text="", font=("", 9),
            bg=C["BG"], fg=C["RED"], wraplength=400, justify="left",
        )
        self._btn_retry = tk.Button(
            self._retry_frame, text="🔄  Retry",
            font=("", 11, "bold"), bg=C["PINK"], fg="white",
            relief="flat", padx=18, pady=6, cursor="hand2",
            activebackground=C["PINK2"], activeforeground="white",
            command=self._retry,
        )
        self._retry_visible = False

        # ── Log toggle + log panel ────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=C["BG"])
        btn_row.pack(fill="x", padx=28, pady=(14, 0))
        self._log_btn = tk.Button(
            btn_row, text="📋  ดู Log",
            font=("", 10), bg=C["CARD"], fg=C["TEXT2"],
            relief="flat", padx=14, pady=5, cursor="hand2",
            activebackground=C["PINK_LIGHT"],
            highlightthickness=1, highlightbackground=C["BORDER"],
            command=self._toggle_log,
        )
        self._log_btn.pack(side="left")

        self._log_frame = tk.Frame(self, bg=C["LOG_BG"])
        _sb = ttk.Scrollbar(self._log_frame)
        _sb.pack(side="right", fill="y")
        self._log_w = tk.Text(
            self._log_frame,
            bg=C["LOG_BG"], fg=C["LOG_FG"],
            font=("Consolas" if sys.platform == "win32" else "Menlo", 9),
            relief="flat", state="disabled", bd=0,
            padx=8, pady=6, yscrollcommand=_sb.set,
        )
        self._log_w.pack(side="left", fill="both", expand=True)
        _sb.config(command=self._log_w.yview)

    # ── Header ────────────────────────────────────────────────────────────────
    def _draw_hdr(self) -> None:
        cv = self._hdr_cv
        cv.delete("all")
        w = cv.winfo_width() or self._W
        h = 72
        for i in range(h):
            t = i / h
            r = int(0xFF + (0x8B - 0xFF) * t)
            g = int(0x6A + (0x20 - 0x6A) * t)
            b = int(0xD5 + (0xE0 - 0xD5) * t)
            cv.create_rectangle(0, i, w, i+1,
                                 fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        cv.create_oval(w-90, -35, w+30, 85, fill="#EEB5F5", outline="")
        cv.create_oval(10, -20, 80, 50, fill="#D580EE", outline="")
        cv.create_text(18, h//2-7,  text="🌸", font=("", 20), anchor="w")
        cv.create_text(52, h//2-9,  text="LINE Bot",
                       fill="white", font=("", 15, "bold"), anchor="w")
        cv.create_text(54, h//2+12, text=self._hdr_sub,
                       fill="#FFE0FB", font=("", 10), anchor="w")

    # ── Log panel toggle ──────────────────────────────────────────────────────
    def _toggle_log(self) -> None:
        self._log_open = not self._log_open
        if self._log_open:
            self._log_frame.pack(fill="both", expand=True, pady=(10, 0))
            self._log_btn.config(text="🙈  ซ่อน Log")
            self.resizable(True, True)
            self._regeom(self._W_LOG,
                         min(self._H_LOG, self.winfo_screenheight() - 80))
        else:
            self._log_frame.pack_forget()
            self._log_btn.config(text="📋  ดู Log")
            self.resizable(False, False)
            self._regeom(self._W, self._H)

    # ── Thread-safe helpers ───────────────────────────────────────────────────
    def _ui(self, fn) -> None:
        """Schedule fn() on the main thread."""
        self.after(0, fn)

    def _set_msg(self, msg: str, sub: str = "", hdr: str = "") -> None:
        def _u():
            self._msg.config(text=msg)
            self._sub.config(text=sub)
            if hdr:
                self._hdr_sub = hdr
                self._draw_hdr()
        self._ui(_u)

    def _set_sub(self, text: str) -> None:
        self._ui(lambda: self._sub.config(text=text))

    def _set_badge(self, text: str) -> None:
        self._ui(lambda: self._badge.config(text=text))

    def _set_step(self, key: str, state: str, detail: str = "") -> None:
        def _u():
            row = self._step_rows.get(key)
            if row:
                row.set_state(state, detail)
        self._ui(_u)

    def _log(self, text: str) -> None:
        def _u():
            self._log_w.config(state="normal")
            self._log_w.insert("end", text)
            self._log_w.see("end")
            self._log_w.config(state="disabled")
        self._ui(_u)

    def _show_error(self, msg: str) -> None:
        def _u():
            self._loader.set_error()
            self._err_lbl.config(text=f"⚠  {msg}")
            if not self._retry_visible:
                self._err_lbl.pack(anchor="w", pady=(0, 6))
                self._btn_retry.pack(side="left")
                self._retry_visible = True
            self._hdr_sub = "ติดตั้งไม่สำเร็จ"
            self._draw_hdr()
        self._ui(_u)

    def _hide_error(self) -> None:
        def _u():
            self._err_lbl.pack_forget()
            self._btn_retry.pack_forget()
            self._retry_visible = False
        self._ui(_u)

    # ── Worker management ─────────────────────────────────────────────────────
    def _start_worker(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _retry(self) -> None:
        self._cancelled = False
        for key, _ in _STEPS:
            self._set_step(key, "wait")
        self._hide_error()
        self._ui(lambda: self._loader.start())
        self._set_msg("กำลังลองใหม่...", "กรุณารอสักครู่", "กำลังเตรียมระบบ...")
        self._start_worker()

    # ── Worker (runs on background thread) ───────────────────────────────────
    def _worker(self) -> None:
        py = _venv_py()

        # Step 1 — create venv ────────────────────────────────────────────────
        if py is None:
            self._set_step("venv", "active", "กำลังสร้าง...")
            self._set_msg("สร้าง Python Environment",
                          "ครั้งแรกอาจใช้เวลา 20–30 วินาที", "สร้าง venv...")
            self._log("$ python -m venv .venv\n")
            r = subprocess.run(
                [sys.executable, "-m", "venv", str(PROJECT_DIR / ".venv")],
                capture_output=True, text=True,
                cwd=str(PROJECT_DIR), creationflags=_W32,
            )
            self._log(r.stdout or "")
            if r.returncode != 0 and "ensurepip" in (r.stderr or ""):
                self._log("[retry] --without-pip\n")
                import shutil as _sh
                _sh.rmtree(str(PROJECT_DIR / ".venv"), ignore_errors=True)
                r = subprocess.run(
                    [sys.executable, "-m", "venv", "--without-pip",
                     str(PROJECT_DIR / ".venv")],
                    capture_output=True, text=True,
                    cwd=str(PROJECT_DIR), creationflags=_W32,
                )
                self._log(r.stdout or "")
            if r.returncode != 0:
                self._log(f"\n[ERROR]\n{r.stderr}\n")
                self._set_step("venv", "error", "ล้มเหลว")
                self._set_msg("สร้าง Environment ไม่สำเร็จ",
                              "กด 'ดู Log' เพื่อดูรายละเอียด", "ล้มเหลว")
                self._show_error("สร้าง virtual environment ไม่สำเร็จ — อาจขาด Python หรือ ensurepip")
                return
            self._set_step("venv", "done", "สำเร็จ")
            self._log("✓ Done\n")
            py = _venv_py()
        else:
            self._set_step("venv", "done", "มีอยู่แล้ว")

        if self._cancelled:
            return

        # Step 2 — pip install ────────────────────────────────────────────────
        self._set_step("pip", "active", "กำลังติดตั้ง...")
        self._set_msg("กำลังติดตั้ง Packages",
                      "ครั้งแรกอาจใช้เวลา 1–3 นาที", "ติดตั้ง packages...")
        self._log("\n$ pip install -r requirements.txt\n\n")

        try:
            proc = subprocess.Popen(
                [py, "-m", "pip", "install", "-r", str(REQ),
                 "--no-warn-script-location"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(PROJECT_DIR), bufsize=1, creationflags=_W32,
            )
            for line in proc.stdout:
                if self._cancelled:
                    proc.kill()
                    return
                self._log(line)
                ls = line.strip()
                if ls.startswith("Collecting"):
                    pkg = ls.split()[1] if len(ls.split()) > 1 else ""
                    self._set_badge(f"⬇  {pkg}")
                    self._set_sub(f"กำลังโหลด: {pkg}")
                elif ls.startswith("Installing collected"):
                    self._set_badge("🔧  กำลังติดตั้ง...")
                    self._set_sub("กำลังติดตั้ง packages...")
            proc.wait()

            if proc.returncode != 0:
                self._set_step("pip", "error", "ล้มเหลว")
                self._set_msg("ติดตั้ง Packages ไม่สำเร็จ",
                              "ตรวจสอบการเชื่อมต่ออินเทอร์เน็ต แล้วกด Retry",
                              "ล้มเหลว")
                self._show_error("pip install ล้มเหลว — ตรวจสอบ internet แล้วกด Retry")
                return

        except Exception as exc:
            self._log(f"\n[EXCEPTION] {exc}\n")
            self._set_step("pip", "error", str(exc)[:50])
            self._set_msg("เกิดข้อผิดพลาด", str(exc)[:80], "ล้มเหลว")
            self._show_error(str(exc)[:120])
            return

        # Mark done ───────────────────────────────────────────────────────────
        try:
            _FLAG.touch()
        except Exception:
            pass

        self._set_step("pip", "done", "สำเร็จ")
        self._set_step("done", "active", "กำลังเปิด...")
        self._set_msg("ติดตั้งเสร็จแล้ว!", "กำลังเปิดแอพ...", "เปิดแอพ!")
        self._set_badge("✅  เสร็จแล้ว")
        self._ui(lambda: self._loader.set_ok())
        self._log("\n✓ Setup complete — launching LINE Bot\n")
        time.sleep(1.5)
        self._launch()

    def _launch(self) -> None:
        try:
            exe = _launch_exe()
            subprocess.Popen(
                [exe, str(PROJECT_DIR / "launcher" / "launcher.py")],
                cwd=str(PROJECT_DIR), creationflags=_W32,
            )
        except Exception as exc:
            self._set_step("done", "error", "เปิดไม่ได้")
            self._set_msg("เปิดแอพไม่สำเร็จ", str(exc)[:80], "ล้มเหลว")
            self._show_error(f"เปิด launcher ไม่ได้: {exc}")
            return
        self.after(800, self.destroy)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not _needs_setup():
        subprocess.Popen(
            [_launch_exe(), str(PROJECT_DIR / "launcher" / "launcher.py")],
            cwd=str(PROJECT_DIR),
            creationflags=_W32,
        )
    else:
        SetupApp().mainloop()
