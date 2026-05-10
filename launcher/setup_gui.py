#!/usr/bin/env python3
"""First-run setup window — installs packages inside a GUI, no terminal needed."""
from __future__ import annotations
import os, subprocess, sys, threading, time
from pathlib import Path
import tkinter as tk
from tkinter import ttk

PROJECT_DIR = Path(__file__).resolve().parent.parent
_W32 = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_VENV_PY  = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"    # Windows
_VENV_PYW = PROJECT_DIR / ".venv" / "Scripts" / "pythonw.exe"   # Windows no-console
_VENV_MAC = PROJECT_DIR / ".venv" / "bin" / "python"             # macOS / Linux
_FLAG     = PROJECT_DIR / ".venv" / ".setup_done"
REQ       = PROJECT_DIR / "requirements.txt"

C = dict(
    BG="#F6F0FF", CARD="#FFFFFF", CARD2="#FAF6FF",
    LOG_BG="#0D0D1A", LOG_FG="#D0D0FF",
    PINK="#D63AF9", PINK2="#B82EE0", PINK_LIGHT="#F3E6FF",
    GREEN="#00C853", RED="#FF1744", ORANGE="#FF9100",
    TEXT="#1A1A2E", TEXT2="#4A4A6A", MUTED="#9090B0",
    WHITE="#FFFFFF", BORDER="#E0D0F5",
)


def _venv_py() -> str | None:
    for p in (_VENV_PY, _VENV_MAC):
        if p.exists():
            return str(p)
    return None


def _launch_exe() -> str:
    """pythonw.exe on Windows (no console), else regular venv python."""
    if _VENV_PYW.exists():
        return str(_VENV_PYW)
    return _venv_py() or sys.executable


def _needs_setup() -> bool:
    py = _venv_py()
    if py is None:
        return True
    if _FLAG.exists():
        return False
    # Flag missing but venv exists — quick import test (e.g. after setup_mac.sh)
    try:
        r = subprocess.run(
            [py, "-c", "import fastapi, linebot, chromadb"],
            capture_output=True, timeout=10,
        )
        if r.returncode == 0:
            _FLAG.touch()  # auto-create flag for next run
            return False
    except Exception:
        pass
    return True


class SetupApp(tk.Tk):
    _W, _H           = 480, 330
    _W_LOG, _H_LOG   = 480, 580

    def __init__(self) -> None:
        super().__init__()
        self.title("LINE Bot")
        self.resizable(False, False)
        self.configure(bg=C["BG"])

        self._log_open   = False
        self._hdr_sub    = "กำลังเตรียมระบบ..."
        self._cancelled  = False

        self._build()
        self._regeom(self._W, self._H)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self.createcommand("tk::mac::Quit", self._on_close)
        except Exception:
            pass
        self.after(350, lambda: threading.Thread(target=self._worker, daemon=True).start())

    # ── geometry ─────────────────────────────────────────────────────────────
    def _regeom(self, w: int, h: int) -> None:
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _on_close(self) -> None:
        self._cancelled = True
        self.destroy()

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self) -> None:
        # Gradient header
        self._hdr_cv = tk.Canvas(self, height=72, highlightthickness=0, bd=0)
        self._hdr_cv.pack(fill="x")
        self._hdr_cv.bind("<Configure>", lambda _e: self._draw_hdr())
        self.after(10, self._draw_hdr)

        # Body
        body = tk.Frame(self, bg=C["BG"])
        body.pack(fill="x", padx=28, pady=(22, 0))

        self._icon = tk.Label(body, text="⏳", font=("", 32), bg=C["BG"])
        self._icon.pack()

        self._msg = tk.Label(body, text="กำลังเตรียมระบบ...",
                             font=("", 13, "bold"), bg=C["BG"],
                             fg=C["TEXT"], wraplength=424)
        self._msg.pack(pady=(10, 0))

        self._sub = tk.Label(body, text="กรุณารอสักครู่",
                              font=("", 10), bg=C["BG"],
                              fg=C["MUTED"], wraplength=424)
        self._sub.pack(pady=(4, 0))

        # Progress bar
        pb_wrap = tk.Frame(self, bg=C["BG"])
        pb_wrap.pack(fill="x", padx=28, pady=(18, 0))

        sty = ttk.Style()
        sty.theme_use("default")
        sty.configure("S.Horizontal.TProgressbar",
                      troughcolor=C["BORDER"], background=C["PINK"],
                      borderwidth=0, relief="flat",
                      lightcolor=C["PINK"], darkcolor=C["PINK2"])

        self._pb = ttk.Progressbar(pb_wrap, style="S.Horizontal.TProgressbar",
                                    mode="indeterminate", length=424)
        self._pb.pack(fill="x")
        self._pb.start(12)

        # Buttons row
        btn_row = tk.Frame(self, bg=C["BG"])
        btn_row.pack(fill="x", padx=28, pady=(14, 0))

        self._log_btn = tk.Button(
            btn_row, text="📋  ดู Log",
            font=("", 10), bg=C["CARD"], fg=C["TEXT2"],
            relief="flat", padx=14, pady=5, cursor="hand2",
            activebackground=C["PINK_LIGHT"],
            highlightthickness=1, highlightbackground=C["BORDER"],
            command=self._toggle_log)
        self._log_btn.pack(side="left")

        self._badge = tk.Label(btn_row, text="", font=("", 10),
                                bg=C["BG"], fg=C["MUTED"])
        self._badge.pack(side="right")

        # Log panel (hidden by default)
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

    # ── header ────────────────────────────────────────────────────────────────
    def _draw_hdr(self, _=None) -> None:
        cv = self._hdr_cv
        cv.delete("all")
        w = cv.winfo_width() or self._W
        h = 72
        for i in range(h):
            t = i / h
            r = int(0xFF + (0x8B - 0xFF) * t)
            g = int(0x6A + (0x20 - 0x6A) * t)
            b = int(0xD5 + (0xE0 - 0xD5) * t)
            cv.create_rectangle(0, i, w, i + 1,
                                 fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        cv.create_oval(w - 90, -35, w + 30, 85, fill="#EEB5F5", outline="")
        cv.create_oval(10, -20, 80, 50, fill="#D580EE", outline="")
        cv.create_text(18, h // 2 - 7, text="🌸", font=("", 20), anchor="w")
        cv.create_text(52, h // 2 - 9, text="LINE Bot",
                       fill="white", font=("", 15, "bold"), anchor="w")
        cv.create_text(54, h // 2 + 12, text=self._hdr_sub,
                       fill="#FFE0FB", font=("", 10), anchor="w")

    # ── log panel toggle ──────────────────────────────────────────────────────
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

    # ── thread-safe setters ───────────────────────────────────────────────────
    def _set_status(self, icon: str, msg: str,
                    sub: str = "", hdr: str = "") -> None:
        def _u() -> None:
            self._icon.config(text=icon)
            self._msg.config(text=msg)
            self._sub.config(text=sub)
            if hdr:
                self._hdr_sub = hdr
                self._draw_hdr()
        self.after(0, _u)

    def _set_sub(self, text: str) -> None:
        self.after(0, lambda: self._sub.config(text=text))

    def _set_badge(self, text: str) -> None:
        self.after(0, lambda: self._badge.config(text=text))

    def _log(self, text: str) -> None:
        def _u() -> None:
            self._log_w.config(state="normal")
            self._log_w.insert("end", text)
            self._log_w.see("end")
            self._log_w.config(state="disabled")
        self.after(0, _u)

    # ── worker ────────────────────────────────────────────────────────────────
    def _worker(self) -> None:
        py = _venv_py()

        # ── Step 1: create venv if missing ───────────────────────────────
        if py is None:
            self._set_status("⚙️", "สร้าง virtual environment...",
                              "", "สร้าง venv...")
            self._log("$ python -m venv .venv\n")
            r = subprocess.run(
                [sys.executable, "-m", "venv", str(PROJECT_DIR / ".venv")],
                capture_output=True, text=True, cwd=str(PROJECT_DIR),
                creationflags=_W32,
            )
            self._log(r.stdout or "")
            if r.returncode != 0:
                self._log(f"\n[ERROR]\n{r.stderr}\n")
                self._set_status(
                    "❌", "สร้าง virtual environment ไม่สำเร็จ",
                    "กด 'ดู Log' เพื่อดูรายละเอียด", "ล้มเหลว")
                self.after(0, self._pb.stop)
                return
            self._log("✓ Done\n")
            py = _venv_py()

        if self._cancelled:
            return

        # ── Step 2: pip install ───────────────────────────────────────────
        self._set_status("📦", "กำลังติดตั้ง packages...",
                          "ครั้งแรกอาจใช้เวลา 1–3 นาที",
                          "ติดตั้ง packages...")
        self._log(f"\n$ pip install -r requirements.txt\n\n")

        try:
            proc = subprocess.Popen(
                [py, "-m", "pip", "install", "-r", str(REQ),
                 "--no-warn-script-location"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                cwd=str(PROJECT_DIR), bufsize=1,
                creationflags=_W32,
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
                    self._set_sub("กำลังติดตั้ง...")
            proc.wait()

            if proc.returncode != 0:
                self._set_status(
                    "❌", "ติดตั้ง packages ไม่สำเร็จ",
                    "กด 'ดู Log' เพื่อดูรายละเอียด", "ล้มเหลว")
                self.after(0, self._pb.stop)
                return

        except Exception as exc:
            self._log(f"\n[EXCEPTION] {exc}\n")
            self._set_status("❌", "เกิดข้อผิดพลาด",
                              str(exc)[:100], "ล้มเหลว")
            self.after(0, self._pb.stop)
            return

        # ── Mark done ────────────────────────────────────────────────────
        try:
            _FLAG.touch()
        except Exception:
            pass

        self._set_status("🎉", "ติดตั้งเสร็จแล้ว!",
                          "กำลังเปิดแอพ...", "เปิดแอพ!")
        self._set_badge("✅  เสร็จแล้ว")

        def _finish_pb() -> None:
            self._pb.stop()
            self._pb.config(mode="determinate", value=100)
        self.after(0, _finish_pb)

        self._log("\n✓ Setup complete — launching LINE Bot\n")
        time.sleep(1.2)
        self._launch()

    def _launch(self) -> None:
        try:
            exe = _launch_exe()
            subprocess.Popen(
                [exe, str(PROJECT_DIR / "launcher" / "launcher.py")],
                cwd=str(PROJECT_DIR),
                creationflags=_W32,
            )
        except Exception as exc:
            self._set_status("❌", "เปิดแอพไม่สำเร็จ",
                              str(exc)[:100], "ล้มเหลว")
            return
        self.after(700, self.destroy)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not _needs_setup():
        # Packages already installed → jump straight to launcher (no window)
        subprocess.Popen(
            [_launch_exe(), str(PROJECT_DIR / "launcher" / "launcher.py")],
            cwd=str(PROJECT_DIR),
            creationflags=_W32,
        )
    else:
        SetupApp().mainloop()
