#!/usr/bin/env python3
from __future__ import annotations
import os
import re
import sys
import shutil
import signal
import subprocess
import threading
import webbrowser
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).resolve().parent.parent   # launcher/ → project root
CONFIG_JSON  = PROJECT_DIR / "config.json"
ENV_FILE     = PROJECT_DIR / ".env"
ADMIN_URL    = "http://localhost:8000/admin"
HEALTH_URL   = "http://localhost:8000/health"

# Use venv's python.exe (not pythonw) so the server process has stdout/stderr
_venv_py_win = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
_venv_py_mac = PROJECT_DIR / ".venv" / "bin" / "python"
SERVER_PYTHON = str(
    _venv_py_win if _venv_py_win.exists() else
    _venv_py_mac if _venv_py_mac.exists() else
    sys.executable
)

REQUIRED = ("line_channel_access_token", "line_channel_secret")

# ── Palette ───────────────────────────────────────────────────────────────────
C = dict(
    PINK="#FF6AD5", PINK2="#C774E8", PINK_LIGHT="#FFF0F8",
    BG="#FFFFFF", CARD="#FFF5FB",
    GREEN="#00C853", RED="#FF1744", ORANGE="#FF9100",
    TEXT="#1A1A2E", MUTED="#888899", BORDER="#F0D0EC",
    WHITE="#FFFFFF",
)


# ── Process killer (full tree) ────────────────────────────────────────────────

def _kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, timeout=5,
            )
        else:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


# ── config.json helpers ───────────────────────────────────────────────────────

def read_config() -> dict:
    if not CONFIG_JSON.exists():
        return {}
    try:
        import json
        return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(updates: dict):
    import json
    cfg = read_config()
    cfg.update(updates)
    CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def read_env() -> dict:
    if not ENV_FILE.exists():
        return {}
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def env_is_complete() -> bool:
    cfg = read_config()
    return all(cfg.get(k, "").strip() for k in REQUIRED)


# ── Widget helpers ────────────────────────────────────────────────────────────

def make_header(parent, title: str, subtitle: str = "") -> tk.Canvas:
    c = tk.Canvas(parent, height=80, highlightthickness=0)
    c.pack(fill="x")

    def _draw(event=None):
        c.delete("all")
        w = c.winfo_width() or 500
        # Gradient strips (fake)
        steps = 80
        for i in range(steps):
            t = i / steps
            r = int(0xFF + (0xC7 - 0xFF) * t)
            g = int(0x6A + (0x74 - 0x6A) * t)
            b = int(0xD5 + (0xE8 - 0xD5) * t)
            col = f"#{r:02x}{g:02x}{b:02x}"
            c.create_rectangle(0, i, w, i + 1, fill=col, outline="")
        c.create_text(20, 26, text="🌸", font=("", 22), anchor="w")
        c.create_text(50, 22, text=title, fill="white", font=("", 15, "bold"), anchor="w")
        if subtitle:
            c.create_text(50, 44, text=subtitle, fill="#FFE8F8",
                          font=("", 11), anchor="w", tags="sub")
            c.itemconfig("sub", fill="#FFECF8")

    c.bind("<Configure>", _draw)
    c.after(10, _draw)
    return c


def labeled_entry(parent, label: str, var: tk.StringVar, show="", hint="") -> ttk.Frame:
    f = ttk.Frame(parent)
    f.pack(fill="x", pady=5)
    ttk.Label(f, text=label, font=("", 12, "bold")).pack(anchor="w")
    e = ttk.Entry(f, textvariable=var, show=show, font=("", 12))
    e.pack(fill="x", ipady=4, pady=(2, 0))
    if hint:
        ttk.Label(f, text=hint, font=("", 10), foreground=C["MUTED"]).pack(anchor="w", pady=(2, 0))
    return f


# ═════════════════════════════════════════════════════════════════════════════
# WIZARD
# ═════════════════════════════════════════════════════════════════════════════

class SetupWizard(tk.Toplevel):
    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done = on_done
        self.title("LINE Bot — Setup")
        self.resizable(False, False)
        self._data = {}
        self._pages = []
        self._idx = 0

        # Center window
        self.geometry("520x540")
        self.after(10, lambda: self._center(520, 540))

        self._build()
        self._show_page(0)

    def _center(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build(self):
        cfg = read_config()

        # Pages
        self._container = tk.Frame(self, bg=C["BG"])
        self._container.pack(fill="both", expand=True)

        self._pages = [
            WelcomePage(self._container, self),
            LineCredPage(self._container, self, cfg),
            BotIdentityPage(self._container, self, cfg),
            OllamaPage(self._container, self, cfg),
            ReviewPage(self._container, self),
        ]

        # Step dots
        dots_f = tk.Frame(self, bg=C["BG"], pady=6)
        dots_f.pack(fill="x")
        self._dots = []
        for i in range(len(self._pages)):
            d = tk.Label(dots_f, text="●", font=("", 14), bg=C["BG"])
            d.pack(side="left", padx=4)
            self._dots.append(d)
        # center dots
        dots_f.pack_configure(padx=(520 - len(self._pages) * 24) // 2)

        # Nav buttons
        nav = tk.Frame(self, bg=C["BORDER"], pady=1)
        nav.pack(fill="x", side="bottom")
        nav_inner = tk.Frame(nav, bg=C["BG"])
        nav_inner.pack(fill="x")
        self._btn_back = tk.Button(nav_inner, text="◀ ย้อนกลับ", command=self._prev,
                                   font=("", 12), bg=C["BG"], relief="flat", padx=16, pady=8)
        self._btn_back.pack(side="left", padx=10, pady=8)
        self._btn_next = tk.Button(nav_inner, text="ถัดไป ▶", command=self._next,
                                   font=("", 12, "bold"), bg=C["PINK"], fg="white",
                                   relief="flat", padx=20, pady=8, cursor="hand2",
                                   activebackground=C["PINK2"], activeforeground="white")
        self._btn_next.pack(side="right", padx=10, pady=8)

    def _show_page(self, idx):
        for p in self._pages:
            p.pack_forget()
        self._pages[idx].pack(fill="both", expand=True)
        self._idx = idx
        # Dots
        for i, d in enumerate(self._dots):
            d.config(foreground=C["PINK"] if i == idx else C["MUTED"])
        # Nav labels
        self._btn_back.config(state="normal" if idx > 0 else "disabled")
        if idx == len(self._pages) - 1:
            self._btn_next.config(text="✦ เริ่มใช้งาน!", bg=C["GREEN"])
        else:
            self._btn_next.config(text="ถัดไป ▶", bg=C["PINK"])

    def _next(self):
        page = self._pages[self._idx]
        if hasattr(page, "validate") and not page.validate():
            return
        if hasattr(page, "collect"):
            self._data.update(page.collect())
        if self._idx < len(self._pages) - 1:
            self._show_page(self._idx + 1)
        else:
            self._finish()

    def _prev(self):
        if self._idx > 0:
            self._show_page(self._idx - 1)

    def _finish(self):
        write_config(self._data)
        self.destroy()
        self.on_done()


# ── Wizard Pages ──────────────────────────────────────────────────────────────

class WelcomePage(tk.Frame):
    def __init__(self, parent, wizard):
        super().__init__(parent, bg=C["BG"])
        make_header(self, "ยินดีต้อนรับสู่ LINE Bot", "ตั้งค่าครั้งแรก — ใช้เวลาแค่ 2 นาที")
        body = tk.Frame(self, bg=C["BG"], padx=28, pady=16)
        body.pack(fill="both", expand=True)
        tk.Label(body, text="สิ่งที่ต้องเตรียม:", font=("", 13, "bold"), bg=C["BG"],
                 fg=C["TEXT"]).pack(anchor="w", pady=(0, 10))
        items = [
            ("🔑", "LINE Channel Access Token + Secret", "จาก LINE Developers Console"),
            ("🏫", "ชื่อคณะ / มหาวิทยาลัย", "สำหรับบุคลิกของบอท"),
            ("🦙", "Ollama รันอยู่", "สำหรับ AI model (llama3.2 แนะนำ)"),
        ]
        for icon, title, sub in items:
            row = tk.Frame(body, bg=C["CARD"], pady=10, padx=14, relief="flat")
            row.pack(fill="x", pady=4)
            tk.Label(row, text=icon, font=("", 20), bg=C["CARD"]).pack(side="left", padx=(0, 12))
            info = tk.Frame(row, bg=C["CARD"])
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=title, font=("", 12, "bold"), bg=C["CARD"], fg=C["TEXT"],
                     anchor="w").pack(fill="x")
            tk.Label(info, text=sub, font=("", 10), bg=C["CARD"], fg=C["MUTED"],
                     anchor="w").pack(fill="x")


class LineCredPage(tk.Frame):
    def __init__(self, parent, wizard, cfg: dict):
        super().__init__(parent, bg=C["BG"])
        make_header(self, "LINE Credentials 🔑", "ขั้นตอน 1/3")
        body = tk.Frame(self, bg=C["BG"], padx=28, pady=16)
        body.pack(fill="both", expand=True)

        info = tk.Label(body,
            text="หาได้ที่ developers.line.biz → เลือก Channel → Messaging API",
            font=("", 10), bg=C["BG"], fg=C["MUTED"], wraplength=440, justify="left")
        info.pack(anchor="w", pady=(0, 14))

        def open_line(_=None):
            webbrowser.open("https://developers.line.biz/console/")
        link = tk.Label(body, text="🌐 เปิด LINE Developers Console", font=("", 10, "underline"),
                        fg=C["PINK"], bg=C["BG"], cursor="hand2")
        link.bind("<Button-1>", open_line)
        link.pack(anchor="w", pady=(0, 12))

        self.token_var = tk.StringVar(value=cfg.get("line_channel_access_token", ""))
        self.secret_var = tk.StringVar(value=cfg.get("line_channel_secret", ""))

        labeled_entry(body, "Channel Access Token *", self.token_var,
                      hint="ยาวมาก (ขึ้นต้นด้วย eyJ...)")
        labeled_entry(body, "Channel Secret *", self.secret_var, show="•",
                      hint="สั้นกว่า — ดูในแท็บ Basic settings")

    def validate(self):
        if not self.token_var.get().strip():
            messagebox.showerror("กรุณาใส่", "Channel Access Token ห้ามว่าง", parent=self.winfo_toplevel())
            return False
        if not self.secret_var.get().strip():
            messagebox.showerror("กรุณาใส่", "Channel Secret ห้ามว่าง", parent=self.winfo_toplevel())
            return False
        return True

    def collect(self):
        return {
            "line_channel_access_token": self.token_var.get().strip(),
            "line_channel_secret": self.secret_var.get().strip(),
        }


class BotIdentityPage(tk.Frame):
    def __init__(self, parent, wizard, cfg: dict):
        super().__init__(parent, bg=C["BG"])
        make_header(self, "ตัวตนของบอท 🤖", "ขั้นตอน 2/3")
        body = tk.Frame(self, bg=C["BG"], padx=28, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="บอทจะแนะนำตัวเองตามข้อมูลนี้ใน LINE",
                 font=("", 10), bg=C["BG"], fg=C["MUTED"]).pack(anchor="w", pady=(0, 14))

        self.faculty_var = tk.StringVar(value=cfg.get("faculty_name", ""))
        self.uni_var = tk.StringVar(value=cfg.get("university_name", "มหาวิทยาลัยตัวอย่าง"))

        labeled_entry(body, "ชื่อคณะ / หน่วยงาน", self.faculty_var,
                      hint="เช่น คณะวิทยาศาสตร์, งานทะเบียน, สำนักงานอธิการบดี")
        labeled_entry(body, "ชื่อมหาวิทยาลัย / องค์กร", self.uni_var)

        # Preview box
        prev_f = tk.Frame(body, bg=C["CARD"], padx=14, pady=12, relief="flat")
        prev_f.pack(fill="x", pady=(20, 0))
        tk.Label(prev_f, text="ตัวอย่างข้อความต้อนรับ:", font=("", 10, "bold"),
                 bg=C["CARD"], fg=C["MUTED"]).pack(anchor="w")
        self._prev_label = tk.Label(prev_f, text="", font=("", 11),
                                    bg=C["CARD"], fg=C["TEXT"], wraplength=400, justify="left")
        self._prev_label.pack(anchor="w", pady=(4, 0))

        def _update(*_):
            self._prev_label.config(
                text=f"สวัสดีครับ/ค่ะ 👋\nผมคือผู้ช่วยของ{self.faculty_var.get()} {self.uni_var.get()}"
            )
        self.faculty_var.trace_add("write", _update)
        self.uni_var.trace_add("write", _update)
        _update()

    def collect(self):
        return {
            "faculty_name": self.faculty_var.get().strip() or "หน่วยงานของคุณ",
            "university_name": self.uni_var.get().strip() or "มหาวิทยาลัยตัวอย่าง",
        }


class OllamaPage(tk.Frame):
    def __init__(self, parent, wizard, cfg: dict):
        super().__init__(parent, bg=C["BG"])
        make_header(self, "Ollama Settings 🦙", "ขั้นตอน 3/3")
        body = tk.Frame(self, bg=C["BG"], padx=28, pady=16)
        body.pack(fill="both", expand=True)

        def open_ollama(_=None):
            webbrowser.open("https://ollama.com/download")
        link = tk.Label(body, text="🌐 ดาวน์โหลด Ollama (ถ้ายังไม่มี)",
                        font=("", 10, "underline"), fg=C["PINK"], bg=C["BG"], cursor="hand2")
        link.bind("<Button-1>", open_ollama)
        link.pack(anchor="w", pady=(0, 10))

        self.url_var = tk.StringVar(value=cfg.get("ollama_base_url", "http://localhost:11434"))
        self.chat_var = tk.StringVar(value=cfg.get("ollama_chat_model", "llama3.2"))
        self.embed_var = tk.StringVar(value=cfg.get("ollama_embed_model", "nomic-embed-text"))

        labeled_entry(body, "Ollama URL", self.url_var)
        labeled_entry(body, "Chat Model", self.chat_var,
                      hint="แนะนำ: llama3.2, typhoon2-8b-instruct (ภาษาไทยดีกว่า)")
        labeled_entry(body, "Embed Model", self.embed_var,
                      hint="แนะนำ: nomic-embed-text")

        # Status row
        status_f = tk.Frame(body, bg=C["BG"])
        status_f.pack(fill="x", pady=(14, 0))
        self._status = tk.Label(status_f, text="", font=("", 11), bg=C["BG"])
        self._status.pack(side="left")
        tk.Button(status_f, text="ทดสอบเชื่อมต่อ", command=self._check,
                  font=("", 11), bg=C["PINK"], fg="white", relief="flat",
                  padx=12, pady=4, cursor="hand2").pack(side="right")

    def _check(self):
        self._status.config(text="⏳ กำลังตรวจสอบ...", fg=C["ORANGE"])
        self.after(10, self._do_check)

    def _do_check(self):
        def _run():
            try:
                import httpx
                r = httpx.get(self.url_var.get().rstrip("/") + "/api/tags", timeout=4)
                models = [m["name"] for m in r.json().get("models", [])]
                msg = f"✓ เชื่อมต่อได้! พบ {len(models)} models"
                self.after(0, lambda: self._status.config(text=msg, fg=C["GREEN"]))
            except Exception:
                msg = "✗ ไม่สามารถเชื่อมต่อ — ตรวจสอบว่า Ollama รันอยู่"
                self.after(0, lambda: self._status.config(text=msg, fg=C["RED"]))
        threading.Thread(target=_run, daemon=True).start()

    def collect(self):
        return {
            "ollama_base_url": self.url_var.get().strip(),
            "ollama_chat_model": self.chat_var.get().strip(),
            "ollama_embed_model": self.embed_var.get().strip(),
        }


class ReviewPage(tk.Frame):
    def __init__(self, parent, wizard):
        super().__init__(parent, bg=C["BG"])
        self.wizard = wizard
        make_header(self, "พร้อมแล้ว! 🎉", "ตรวจสอบการตั้งค่า")
        body = tk.Frame(self, bg=C["BG"], padx=28, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="สรุปการตั้งค่า:", font=("", 13, "bold"),
                 bg=C["BG"], fg=C["TEXT"]).pack(anchor="w", pady=(0, 8))

        self._summary = tk.Text(body, height=8, font=("Menlo", 11), bg=C["CARD"],
                                fg=C["TEXT"], relief="flat", wrap="word",
                                state="disabled", bd=0, padx=10, pady=8)
        self._summary.pack(fill="x")

        tk.Label(body, text="หลังจากนี้ตั้งค่าเพิ่มเติมได้ที่ Admin Panel ✦",
                 font=("", 10), bg=C["BG"], fg=C["MUTED"]).pack(anchor="w", pady=(12, 0))

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self._refresh()

    def pack(self, **kwargs):
        self._refresh()
        super().pack(**kwargs)

    def _refresh(self):
        d = self.wizard._data
        token = d.get('line_channel_access_token', '')
        lines = [
            f"✓ LINE Token   : {token[:16]}..." if token else "✗ LINE Token   : (ยังไม่ได้ใส่)",
            f"✓ LINE Secret  : {'•'*8}",
            f"✓ คณะ          : {d.get('faculty_name','')}",
            f"✓ มหาวิทยาลัย  : {d.get('university_name','')}",
            f"✓ Ollama URL   : {d.get('ollama_base_url','')}",
            f"✓ Chat Model   : {d.get('ollama_chat_model','')}",
        ]
        self._summary.config(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("end", "\n".join(lines))
        self._summary.config(state="disabled")


# ═════════════════════════════════════════════════════════════════════════════
# CONTROL PANEL
# ═════════════════════════════════════════════════════════════════════════════

class ControlPanel(tk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, bg=C["BG"])
        self.pack(fill="both", expand=True)
        self._proc: subprocess.Popen | None = None
        self._ngrok_proc: subprocess.Popen | None = None
        self._running = False
        self._ngrok_url = ""
        self._opened_admin = False

        make_header(self, "LINE Bot", "Control Panel")

        # Status area
        status_outer = tk.Frame(self, bg=C["CARD"], padx=18, pady=12)
        status_outer.pack(fill="x", padx=16, pady=(12, 4))
        self._st_server = self._stat_row(status_outer, "Server")
        self._st_ollama = self._stat_row(status_outer, "Ollama")
        self._st_rag    = self._stat_row(status_outer, "RAG Index")
        self._st_ngrok  = self._stat_row(status_outer, "ngrok")

        # ngrok URL bar
        url_f = tk.Frame(self, bg=C["CARD"], padx=18, pady=8)
        url_f.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(url_f, text="Webhook URL:", font=("", 10, "bold"),
                 bg=C["CARD"], fg=C["MUTED"], width=13, anchor="w").pack(side="left")
        self._url_label = tk.Label(url_f, text="— รอ ngrok —",
                                   font=("Menlo", 10), bg=C["CARD"], fg=C["MUTED"],
                                   anchor="w", cursor="hand2")
        self._url_label.pack(side="left", fill="x", expand=True)
        self._btn_copy = tk.Button(url_f, text="Copy", font=("", 10),
                                   command=self._copy_url,
                                   bg=C["PINK"], fg="white", relief="flat",
                                   padx=10, pady=4, cursor="hand2", state="disabled",
                                   activebackground=C["PINK2"], activeforeground="white")
        self._btn_copy.pack(side="right")

        # Main buttons
        btn_f = tk.Frame(self, bg=C["BG"])
        btn_f.pack(fill="x", padx=16, pady=4)

        self._btn_start = tk.Button(btn_f, text="▶  Start",
                                    command=self.start, font=("", 13, "bold"),
                                    bg=C["GREEN"], fg="white", relief="flat",
                                    padx=22, pady=10, cursor="hand2",
                                    activebackground="#009624", activeforeground="white")
        self._btn_start.pack(side="left", padx=(0, 8))

        self._btn_stop = tk.Button(btn_f, text="■  Stop",
                                   command=self.stop, font=("", 13, "bold"),
                                   bg=C["MUTED"], fg="white", relief="flat",
                                   padx=22, pady=10, cursor="hand2", state="disabled")
        self._btn_stop.pack(side="left", padx=(0, 8))

        # Log area
        log_f = tk.Frame(self, bg=C["BG"])
        log_f.pack(fill="both", expand=True, padx=16, pady=(8, 0))
        tk.Label(log_f, text="Server Logs", font=("", 11, "bold"),
                 bg=C["BG"], fg=C["MUTED"]).pack(anchor="w")
        sb = ttk.Scrollbar(log_f)
        sb.pack(side="right", fill="y", pady=(4, 0))
        self._log = tk.Text(log_f, bg="#1A1A2E", fg="#E0E0FF",
                            font=("Menlo", 10), relief="flat",
                            wrap="word", state="disabled", bd=0,
                            yscrollcommand=sb.set)
        self._log.pack(side="left", fill="both", expand=True, pady=(4, 0))
        sb.config(command=self._log.yview)
        self._log.config(yscrollcommand=sb.set)
        # Color tags
        self._log.tag_config("ERROR", foreground="#FF6B6B")
        self._log.tag_config("WARNING", foreground="#FFD700")
        self._log.tag_config("INFO", foreground="#A0E0FF")
        self._log.tag_config("OK", foreground="#00FF94")
        self._log.tag_config("DIM", foreground="#666688")

        # Bottom bar
        bot_f = tk.Frame(self, bg=C["CARD"], pady=6)
        bot_f.pack(fill="x")
        tk.Button(bot_f, text="⚙ ตั้งค่าใหม่", command=self._open_settings,
                  font=("", 10), bg=C["CARD"], relief="flat",
                  fg=C["MUTED"], cursor="hand2").pack(side="left", padx=12)
        tk.Button(bot_f, text="🌐 Admin", command=self.open_admin,
                  font=("", 10), bg=C["CARD"], relief="flat",
                  fg=C["PINK"], cursor="hand2").pack(side="left", padx=4)
        tk.Label(bot_f, text="LINE Bot + Ollama + RAG", font=("", 10),
                 bg=C["CARD"], fg=C["MUTED"]).pack(side="right", padx=12)

        _ngrok_installed = bool(shutil.which("ngrok"))
        self._set_status(self._st_server, "●", C["MUTED"], "ยังไม่ได้เริ่ม")
        self._set_status(self._st_ollama, "●", C["MUTED"], "รอ...")
        self._set_status(self._st_rag,    "●", C["MUTED"], "รอ...")
        self._set_status(self._st_ngrok,  "●",
                         C["MUTED"] if _ngrok_installed else C["RED"],
                         "รอ..." if _ngrok_installed else "ไม่ได้ติดตั้ง ngrok")

    def _stat_row(self, parent, label: str) -> tk.Label:
        f = tk.Frame(parent, bg=C["CARD"])
        f.pack(fill="x", pady=2)
        tk.Label(f, text=f"{label}:", font=("", 11), bg=C["CARD"],
                 fg=C["TEXT"], width=12, anchor="w").pack(side="left")
        val = tk.Label(f, text="", font=("", 11, "bold"), bg=C["CARD"])
        val.pack(side="left")
        return val

    def _set_status(self, lbl: tk.Label, dot: str, color: str, text: str):
        lbl.config(text=f"{dot} {text}", fg=color)

    def _log_write(self, text: str, tag: str = "INFO"):
        self._log.config(state="normal")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _classify_log(self, line: str) -> str:
        if "[ERROR]" in line:
            return "ERROR"
        if "[WARNING]" in line or "[WARN]" in line:
            return "WARNING"
        if "OK" in line or "ready" in line.lower() or "started" in line.lower():
            return "OK"
        return "DIM"

    def start(self):
        if self._running:
            return
        self._log_write("▶ Starting server...\n", "INFO")
        self._set_status(self._st_server, "⏳", C["ORANGE"], "กำลังเริ่ม...")
        self._btn_start.config(state="disabled", bg=C["MUTED"])
        self._btn_stop.config(state="normal", bg=C["RED"])

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        self._proc = subprocess.Popen(
            [SERVER_PYTHON, "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
            start_new_session=True,
        )
        self._running = True

        threading.Thread(target=self._stream_logs, daemon=True).start()
        self.after(3000, self._poll_status)

        # Start ngrok alongside server
        if shutil.which("ngrok"):
            threading.Thread(target=self._start_ngrok, daemon=True).start()

    def stop(self):
        _kill_proc(self._proc)
        _kill_proc(self._ngrok_proc)
        self._running = False
        self._proc = None
        self._ngrok_proc = None
        self._ngrok_url = ""
        self._opened_admin = False
        self._set_status(self._st_server, "●", C["RED"], "หยุดแล้ว")
        self._set_status(self._st_ollama, "●", C["MUTED"], "รอ...")
        self._set_status(self._st_rag,    "●", C["MUTED"], "รอ...")
        self._set_status(self._st_ngrok,  "●", C["MUTED"], "หยุดแล้ว")
        self._url_label.config(text="— รอ ngrok —", fg=C["MUTED"])
        self._btn_copy.config(state="disabled")
        self._btn_start.config(state="normal", bg=C["GREEN"])
        self._btn_stop.config(state="disabled", bg=C["MUTED"])
        self._log_write("■ Server stopped.\n", "WARNING")

    def _stream_logs(self):
        try:
            for line in self._proc.stdout:
                tag = self._classify_log(line)
                self.after(0, self._log_write, line, tag)
        except Exception:
            pass

    def _poll_status(self):
        if not self._running:
            return
        threading.Thread(target=self._fetch_health, daemon=True).start()
        self.after(5000, self._poll_status)

    def _fetch_health(self):
        try:
            import httpx
            r = httpx.get(HEALTH_URL, timeout=3)
            data = r.json()
            def _upd():
                self._set_status(self._st_server, "●", C["GREEN"], "Online ✓")
                if not self._opened_admin:
                    self._opened_admin = True
                    threading.Thread(
                        target=lambda: webbrowser.open(ADMIN_URL), daemon=True
                    ).start()
                if data.get("ollama", {}).get("healthy"):
                    model = data["ollama"].get("model", "")
                    self._set_status(self._st_ollama, "●", C["GREEN"], f"Online · {model}")
                else:
                    self._set_status(self._st_ollama, "●", C["RED"], "Offline")
                rag = data.get("rag", {})
                if rag.get("ready"):
                    self._set_status(self._st_rag, "●", C["GREEN"], f"{rag.get('chunks', 0)} chunks")
                else:
                    self._set_status(self._st_rag, "●", C["ORANGE"], "ยังไม่พร้อม")
            self.after(0, _upd)
        except Exception:
            self.after(0, lambda: self._set_status(self._st_server, "⏳", C["ORANGE"], "กำลังเริ่ม..."))

    def _start_ngrok(self):
        env = read_env()
        token = env.get("NGROK_AUTH_TOKEN", "").strip()
        if token:
            subprocess.run(["ngrok", "config", "add-authtoken", token],
                           capture_output=True)
        self.after(0, lambda: self._set_status(
            self._st_ngrok, "⏳", C["ORANGE"], "กำลังเชื่อมต่อ..."))
        try:
            self._ngrok_proc = subprocess.Popen(
                ["ngrok", "http", "8000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Give ngrok time to start, then poll for URL
            time.sleep(2)
            self.after(0, self._poll_ngrok_url)
        except Exception as e:
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "●", C["RED"], f"Error: {e}"))

    def _poll_ngrok_url(self):
        if not self._running:
            return
        threading.Thread(target=self._fetch_ngrok_url, daemon=True).start()
        self.after(8000, self._poll_ngrok_url)

    def _fetch_ngrok_url(self):
        try:
            import httpx
            r = httpx.get("http://localhost:4040/api/tunnels", timeout=3)
            tunnels = r.json().get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    url = t["public_url"]
                    webhook = url + "/webhook"
                    def _upd(u=url, w=webhook):
                        self._ngrok_url = w
                        self._set_status(self._st_ngrok, "●", C["GREEN"],
                                         u.replace("https://", ""))
                        self._url_label.config(text=w, fg=C["GREEN"])
                        self._btn_copy.config(state="normal")
                    self.after(0, _upd)
                    return
            # No HTTPS tunnel yet
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "⏳", C["ORANGE"], "รอ tunnel..."))
        except Exception:
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "⏳", C["ORANGE"], "กำลังเชื่อมต่อ..."))

    def _copy_url(self):
        if self._ngrok_url:
            self.clipboard_clear()
            self.clipboard_append(self._ngrok_url)
            self._btn_copy.config(text="Copied!")
            self.after(2000, lambda: self._btn_copy.config(text="Copy"))

    def open_admin(self):
        webbrowser.open(ADMIN_URL)

    def _open_settings(self):
        wizard = SetupWizard(self.winfo_toplevel(), on_done=lambda: None)
        wizard.grab_set()


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LINE Bot — Control Panel")
        self.resizable(False, False)
        self._width, self._height = 520, 540
        self.geometry(f"{self._width}x{self._height}")
        self.after(10, self._center)

        # macOS dock icon / quit handler
        try:
            self.createcommand("tk::mac::Quit", self._on_quit)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

        self._panel: ControlPanel | None = None

        self._show_control()

    def _center(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{self._width}x{self._height}+{(sw-self._width)//2}+{(sh-self._height)//2}")

    def _show_wizard(self):
        SetupWizard(self, on_done=self._after_wizard)
        # Keep main window but smaller during wizard
        self.geometry("420x300")
        self._show_placeholder()

    def _show_placeholder(self):
        for w in self.winfo_children():
            w.destroy()
        f = tk.Frame(self, bg=C["BG"])
        f.pack(fill="both", expand=True)
        make_header(f, "LINE Bot", "กำลังตั้งค่า...")
        tk.Label(f, text="โปรดทำตาม Setup Wizard ที่เปิดขึ้นมา",
                 font=("", 12), bg=C["BG"], fg=C["MUTED"]).pack(pady=30)

    def _after_wizard(self):
        self._show_control()

    def _show_control(self):
        for w in self.winfo_children():
            w.destroy()
        self._width, self._height = 540, 680
        self.geometry(f"{self._width}x{self._height}")
        self.after(10, self._center)
        self._panel = ControlPanel(self)

    def _on_quit(self):
        if self._panel:
            _kill_proc(self._panel._proc)
            _kill_proc(self._panel._ngrok_proc)
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
