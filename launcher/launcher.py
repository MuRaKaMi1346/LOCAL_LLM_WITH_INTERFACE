#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, sys, shutil, signal, subprocess, threading, webbrowser, time, re
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# ─── Paths ────────────────────────────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).resolve().parent.parent
CONFIG_JSON  = PROJECT_DIR / "config.json"
ENV_FILE     = PROJECT_DIR / ".env"
ADMIN_URL    = "http://localhost:8000/admin"
HEALTH_URL   = "http://localhost:8000/health"
APP_VERSION  = "2.1.0"

# updater.py lives in project root — add to path so we can import it
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

_venv_py_win = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
_venv_py_mac = PROJECT_DIR / ".venv" / "bin" / "python"
SERVER_PYTHON = str(
    _venv_py_win if _venv_py_win.exists() else
    _venv_py_mac if _venv_py_mac.exists() else
    sys.executable
)
REQUIRED = ("line_channel_access_token", "line_channel_secret")

# ─── Palette ──────────────────────────────────────────────────────────────────
C = dict(
    BG="#F6F0FF", CARD="#FFFFFF", CARD2="#FAF6FF",
    LOG_BG="#0D0D1A", LOG_FG="#D0D0FF",
    PINK="#D63AF9", PINK2="#B82EE0", PINK_LIGHT="#F3E6FF",
    GREEN="#00C853", RED="#FF1744", ORANGE="#FF9100",
    YELLOW="#FFD740", CYAN="#00BCD4",
    TEXT="#1A1A2E", TEXT2="#4A4A6A", MUTED="#9090B0",
    WHITE="#FFFFFF", BORDER="#E0D0F5", BORDER2="#C4A8E4",
    BTN_HOVER="#C030E8",
)


# ─── Process helpers ──────────────────────────────────────────────────────────
def _kill_proc(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=5)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


# ─── Config helpers ───────────────────────────────────────────────────────────
def read_config() -> dict:
    if not CONFIG_JSON.exists():
        return {}
    try:
        return json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_config(updates: dict) -> None:
    cfg = read_config()
    cfg.update(updates)
    CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def read_env() -> dict:
    if not ENV_FILE.exists():
        return {}
    out: dict = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def write_env_key(key: str, val: str) -> None:
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    pat = rf"^{re.escape(key)}=.*$"
    if re.search(pat, text, re.MULTILINE):
        text = re.sub(pat, f"{key}={val}", text, flags=re.MULTILINE)
    else:
        text = text.rstrip("\n") + f"\n{key}={val}\n"
    ENV_FILE.write_text(text, encoding="utf-8")


def is_configured() -> bool:
    cfg = read_config()
    return all(cfg.get(k, "").strip() for k in REQUIRED)


# ─── Gradient header ──────────────────────────────────────────────────────────
def make_header(parent: tk.Widget, title: str, subtitle: str = "",
                height: int = 72) -> tk.Canvas:
    cv = tk.Canvas(parent, height=height, highlightthickness=0, bd=0)
    cv.pack(fill="x")

    def _draw(e=None):
        cv.delete("all")
        w = cv.winfo_width() or 560
        for i in range(height):
            t = i / height
            r = int(0xFF + (0x8B - 0xFF) * t)
            g = int(0x6A + (0x20 - 0x6A) * t)
            b = int(0xD5 + (0xE0 - 0xD5) * t)
            cv.create_rectangle(0, i, w, i + 1, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        cv.create_oval(w - 90, -35, w + 30, 85, fill="#EEB5F5", outline="")
        cv.create_oval(w - 35,  25, w + 65, 125, fill="#C97EE8", outline="")
        cv.create_oval(10, -20, 80, 50, fill="#D580EE", outline="")
        # Content
        cv.create_text(18, height // 2 - 7, text="🌸", font=("", 20), anchor="w")
        cv.create_text(52, height // 2 - (9 if subtitle else 0),
                       text=title, fill="white", font=("", 15, "bold"), anchor="w")
        if subtitle:
            cv.create_text(54, height // 2 + 12, text=subtitle,
                           fill="#FFE0FB", font=("", 10), anchor="w")

    cv.bind("<Configure>", _draw)
    cv.after(10, _draw)
    return cv


# ─── Pulsing dot ─────────────────────────────────────────────────────────────
class PulseDot(tk.Canvas):
    _COLORS = {
        "online":   ("#00C853", "#69F0AE"),
        "starting": ("#FF9100", "#FFD740"),
        "offline":  ("#9090B0", "#9090B0"),
        "error":    ("#FF1744", "#FF6D00"),
    }

    def __init__(self, parent: tk.Widget, size: int = 13, bg: str = C["CARD"], **kw):
        super().__init__(parent, width=size, height=size,
                         highlightthickness=0, bd=0, bg=bg, **kw)
        self._size = size
        self._state = "offline"
        self._phase = 0.0
        self._oval = self.create_oval(2, 2, size - 2, size - 2,
                                      fill=C["MUTED"], outline="")
        self._running = True
        self._tick()

    def set_state(self, state: str) -> None:
        self._state = state

    def destroy(self) -> None:
        self._running = False
        super().destroy()

    def _tick(self) -> None:
        if not self._running:
            return
        colors = self._COLORS.get(self._state, self._COLORS["offline"])
        if self._state in ("online", "starting"):
            t = (1 + math.sin(self._phase)) / 2
            def _lerp(h1: str, h2: str, t: float) -> str:
                r = int(int(h1[1:3], 16) * (1 - t) + int(h2[1:3], 16) * t)
                g = int(int(h1[3:5], 16) * (1 - t) + int(h2[3:5], 16) * t)
                b = int(int(h1[5:7], 16) * (1 - t) + int(h2[5:7], 16) * t)
                return f"#{r:02x}{g:02x}{b:02x}"
            col = _lerp(colors[0], colors[1], t)
            self._phase += 0.12
        else:
            col = colors[0]
            self._phase = 0.0
        try:
            self.itemconfig(self._oval, fill=col)
        except Exception:
            return
        self.after(60, self._tick)


# ─── Labelled entry with show/hide ────────────────────────────────────────────
class SecretEntry(tk.Frame):
    def __init__(self, parent: tk.Widget, label: str, var: tk.StringVar,
                 secret: bool = True, hint: str = "", bg: str = C["CARD"]):
        super().__init__(parent, bg=bg)
        self.pack(fill="x", pady=4)
        self._secret = secret
        self._shown = not secret

        tk.Label(self, text=label, font=("", 11, "bold"),
                 bg=bg, fg=C["TEXT"]).pack(anchor="w")

        row = tk.Frame(self, bg=bg)
        row.pack(fill="x", pady=(2, 0))

        self._entry = tk.Entry(row, textvariable=var,
                               font=("Menlo" if sys.platform == "darwin" else "Consolas", 11),
                               show="•" if secret else "", relief="flat",
                               bg=C["CARD2"], fg=C["TEXT"],
                               insertbackground=C["PINK"],
                               highlightthickness=1,
                               highlightbackground=C["BORDER"],
                               highlightcolor=C["PINK"])
        self._entry.pack(side="left", fill="x", expand=True, ipady=5)

        if secret:
            self._btn = tk.Button(row, text="👁", font=("", 11),
                                  command=self._toggle,
                                  bg=C["CARD2"], fg=C["MUTED"],
                                  relief="flat", padx=6, cursor="hand2",
                                  bd=0, highlightthickness=0)
            self._btn.pack(side="left", padx=(2, 0))

        if hint:
            tk.Label(self, text=hint, font=("", 9), bg=bg,
                     fg=C["MUTED"]).pack(anchor="w", pady=(2, 0))

    def _toggle(self) -> None:
        self._shown = not self._shown
        self._entry.config(show="" if self._shown else "•")


# ═════════════════════════════════════════════════════════════════════════════
# CONTROL TAB
# ═════════════════════════════════════════════════════════════════════════════
class ControlTab(tk.Frame):
    def __init__(self, master: tk.Widget, app: "App"):
        super().__init__(master, bg=C["BG"])
        self._app = app
        self._proc: subprocess.Popen | None = None
        self._ngrok_proc: subprocess.Popen | None = None
        self._running = False
        self._ngrok_url = ""
        self._opened_admin = False
        self._msg_count = 0

        self._build()

    def _build(self) -> None:
        # ── Warning banner (shown when unconfigured) ──────────────────────────
        self._banner = tk.Frame(self, bg="#FFF3CD", pady=6)
        tk.Label(self._banner,
                 text="⚠  ยังไม่ได้ตั้งค่า LINE Credentials — ไปที่แท็บ Settings ก่อน",
                 font=("", 10, "bold"), bg="#FFF3CD", fg="#856404").pack(side="left", padx=14)
        tk.Button(self._banner, text="ไปที่ Settings →",
                  font=("", 10), bg="#856404", fg="white",
                  relief="flat", padx=10, pady=2, cursor="hand2",
                  command=lambda: self._app.show_tab(1)).pack(side="right", padx=10)
        if not is_configured():
            self._banner.pack(fill="x")

        # ── Status cards ──────────────────────────────────────────────────────
        card = tk.Frame(self, bg=C["CARD"], padx=16, pady=12,
                        relief="flat", bd=1,
                        highlightthickness=1, highlightbackground=C["BORDER"])
        card.pack(fill="x", padx=14, pady=(10, 4))

        self._st_server = self._stat_row(card, "Server")
        self._st_ollama = self._stat_row(card, "Ollama")
        self._st_rag    = self._stat_row(card, "RAG Index")
        self._st_ngrok  = self._stat_row(card, "ngrok")

        _ngrok_ok = bool(shutil.which("ngrok"))
        self._set_status(self._st_server, "offline", "ยังไม่ได้เริ่ม")
        self._set_status(self._st_ollama, "offline", "รอ...")
        self._set_status(self._st_rag,    "offline", "รอ...")
        self._set_status(self._st_ngrok,
                         "offline" if _ngrok_ok else "error",
                         "รอ..." if _ngrok_ok else "ไม่ได้ติดตั้ง ngrok")

        # ── Webhook URL bar ───────────────────────────────────────────────────
        url_card = tk.Frame(self, bg=C["CARD"], padx=16, pady=8,
                            highlightthickness=1, highlightbackground=C["BORDER"])
        url_card.pack(fill="x", padx=14, pady=(0, 4))

        tk.Label(url_card, text="Webhook URL", font=("", 9, "bold"),
                 bg=C["CARD"], fg=C["MUTED"]).pack(anchor="w")

        url_row = tk.Frame(url_card, bg=C["CARD"])
        url_row.pack(fill="x", pady=(2, 0))

        self._url_label = tk.Label(url_row, text="— รอ ngrok เริ่มทำงาน —",
                                   font=("Menlo" if sys.platform == "darwin" else "Consolas", 10),
                                   bg=C["CARD"], fg=C["MUTED"],
                                   anchor="w", cursor="hand2")
        self._url_label.pack(side="left", fill="x", expand=True)
        self._url_label.bind("<Button-1>", lambda e: self._open_webhook_url())

        self._btn_copy = tk.Button(url_row, text="📋 Copy",
                                   command=self._copy_url,
                                   font=("", 10), bg=C["PINK"], fg="white",
                                   relief="flat", padx=10, pady=3,
                                   cursor="hand2", state="disabled",
                                   activebackground=C["PINK2"],
                                   activeforeground="white")
        self._btn_copy.pack(side="right")

        self._btn_line_console = tk.Button(url_row, text="LINE Console ↗",
                                           command=lambda: webbrowser.open(
                                               "https://developers.line.biz/console/"),
                                           font=("", 10), bg=C["CARD"],
                                           fg=C["MUTED"], relief="flat",
                                           padx=8, pady=3, cursor="hand2")
        self._btn_line_console.pack(side="right", padx=(0, 4))

        # ── Action buttons ────────────────────────────────────────────────────
        btn_f = tk.Frame(self, bg=C["BG"])
        btn_f.pack(fill="x", padx=14, pady=4)

        self._btn_start = tk.Button(
            btn_f, text="▶  Start", command=self.start,
            font=("", 13, "bold"), bg=C["GREEN"], fg="white",
            relief="flat", padx=24, pady=10, cursor="hand2",
            activebackground="#009624", activeforeground="white")
        self._btn_start.pack(side="left", padx=(0, 6))

        self._btn_stop = tk.Button(
            btn_f, text="■  Stop", command=self.stop,
            font=("", 13, "bold"), bg=C["MUTED"], fg="white",
            relief="flat", padx=24, pady=10, cursor="hand2", state="disabled")
        self._btn_stop.pack(side="left", padx=(0, 6))

        self._btn_admin = tk.Button(
            btn_f, text="🌐  Admin Panel", command=self._open_admin,
            font=("", 12), bg=C["CYAN"], fg="white",
            relief="flat", padx=16, pady=10, cursor="hand2",
            activebackground="#0097A7", activeforeground="white")
        self._btn_admin.pack(side="left")

        # ── Log area ──────────────────────────────────────────────────────────
        log_header = tk.Frame(self, bg=C["BG"])
        log_header.pack(fill="x", padx=14, pady=(6, 2))
        tk.Label(log_header, text="Server Logs", font=("", 11, "bold"),
                 bg=C["BG"], fg=C["TEXT2"]).pack(side="left")

        tk.Button(log_header, text="Clear", font=("", 9),
                  command=self._clear_log,
                  bg=C["BG"], fg=C["MUTED"], relief="flat",
                  cursor="hand2").pack(side="right")
        tk.Button(log_header, text="↓ Bottom", font=("", 9),
                  command=lambda: self._log.see("end"),
                  bg=C["BG"], fg=C["MUTED"], relief="flat",
                  cursor="hand2").pack(side="right", padx=4)

        log_frame = tk.Frame(self, bg=C["LOG_BG"])
        log_frame.pack(fill="both", expand=True, padx=14, pady=(0, 0))

        sb = ttk.Scrollbar(log_frame)
        sb.pack(side="right", fill="y")

        self._log = tk.Text(
            log_frame, bg=C["LOG_BG"], fg=C["LOG_FG"],
            font=("Menlo" if sys.platform == "darwin" else "Consolas", 10),
            relief="flat", wrap="word", state="disabled",
            bd=0, padx=8, pady=6, yscrollcommand=sb.set,
            selectbackground=C["PINK2"], selectforeground="white",
        )
        self._log.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log.yview)

        self._log.tag_config("ERROR",   foreground="#FF6B6B", font=("Menlo" if sys.platform == "darwin" else "Consolas", 10, "bold"))
        self._log.tag_config("WARNING", foreground="#FFD700")
        self._log.tag_config("OK",      foreground="#69F0AE", font=("Menlo" if sys.platform == "darwin" else "Consolas", 10, "bold"))
        self._log.tag_config("INFO",    foreground="#90CAF9")
        self._log.tag_config("DIM",     foreground="#5555AA")
        self._log.tag_config("TS",      foreground="#4444AA")

        # ── Stats bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=C["BORDER"], height=1)
        bar.pack(fill="x", padx=0)

        stats = tk.Frame(self, bg=C["CARD"], pady=5)
        stats.pack(fill="x")

        self._lbl_uptime = tk.Label(stats, text="Uptime: —", font=("", 10),
                                     bg=C["CARD"], fg=C["MUTED"])
        self._lbl_uptime.pack(side="left", padx=12)

        self._lbl_msgs = tk.Label(stats, text="Messages: 0", font=("", 10),
                                   bg=C["CARD"], fg=C["MUTED"])
        self._lbl_msgs.pack(side="left", padx=4)

        tk.Label(stats, text=f"v{APP_VERSION}", font=("", 10),
                 bg=C["CARD"], fg=C["BORDER2"]).pack(side="right", padx=12)

        self.after(1000, self._tick_stats)

    # ── Status helpers ────────────────────────────────────────────────────────
    def _stat_row(self, parent: tk.Widget, label: str) -> tuple:
        f = tk.Frame(parent, bg=C["CARD"])
        f.pack(fill="x", pady=3)

        dot = PulseDot(f, size=12, bg=C["CARD"])
        dot.pack(side="left", padx=(0, 8))

        tk.Label(f, text=f"{label}:", font=("", 11), bg=C["CARD"],
                 fg=C["TEXT2"], width=11, anchor="w").pack(side="left")

        val = tk.Label(f, text="—", font=("", 11, "bold"),
                       bg=C["CARD"], fg=C["MUTED"], anchor="w")
        val.pack(side="left", fill="x", expand=True)

        return dot, val

    def _set_status(self, row: tuple, state: str, text: str) -> None:
        dot, lbl = row
        dot.set_state(state)
        color = {
            "online": C["GREEN"], "starting": C["ORANGE"],
            "offline": C["MUTED"], "error": C["RED"],
        }.get(state, C["MUTED"])
        lbl.config(text=text, fg=color)

    # ── Log helpers ───────────────────────────────────────────────────────────
    def _log_write(self, text: str, tag: str = "INFO") -> None:
        self._log.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self._log.insert("end", f"[{ts}] ", "TS")
        self._log.insert("end", text, tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _clear_log(self) -> None:
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _classify(self, line: str) -> str:
        ll = line.lower()
        if "error" in ll:         return "ERROR"
        if "warning" in ll:       return "WARNING"
        if any(w in ll for w in ("started", "ready", "ok ", " ok\n", "index built", "✓")):
            return "OK"
        return "DIM"

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        if not is_configured():
            messagebox.showwarning("ยังไม่ได้ตั้งค่า",
                                   "กรุณาใส่ LINE Credentials ในแท็บ Settings ก่อน",
                                   parent=self.winfo_toplevel())
            self._app.show_tab(1)
            return
        self._start_time = time.time()
        self._log_write("▶ Starting server...\n", "INFO")
        self._set_status(self._st_server, "starting", "กำลังเริ่ม...")
        self._btn_start.config(state="disabled", bg=C["MUTED"])
        self._btn_stop.config(state="normal", bg=C["RED"])
        self._opened_admin = False
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        self._proc = subprocess.Popen(
            [SERVER_PYTHON, "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", "8000"],
            cwd=str(PROJECT_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env, bufsize=1,
            start_new_session=(sys.platform != "win32"),
        )
        self._running = True
        threading.Thread(target=self._stream_logs, daemon=True).start()
        self.after(3000, self._poll_status)
        if shutil.which("ngrok"):
            threading.Thread(target=self._start_ngrok, daemon=True).start()

    def stop(self) -> None:
        _kill_proc(self._proc)
        _kill_proc(self._ngrok_proc)
        self._running = False
        self._proc = None
        self._ngrok_proc = None
        self._ngrok_url = ""
        self._opened_admin = False
        self._set_status(self._st_server, "offline", "หยุดแล้ว")
        self._set_status(self._st_ollama, "offline", "—")
        self._set_status(self._st_rag,    "offline", "—")
        self._set_status(self._st_ngrok,  "offline", "หยุดแล้ว")
        self._url_label.config(text="— รอ ngrok เริ่มทำงาน —", fg=C["MUTED"])
        self._btn_copy.config(state="disabled")
        self._btn_start.config(state="normal", bg=C["GREEN"])
        self._btn_stop.config(state="disabled", bg=C["MUTED"])
        self._log_write("■ Server stopped.\n", "WARNING")

    # ── Log streaming ─────────────────────────────────────────────────────────
    def _stream_logs(self) -> None:
        try:
            for line in self._proc.stdout:
                tag = self._classify(line)
                self.after(0, self._log_write, line, tag)
        except Exception:
            pass

    # ── Health polling ────────────────────────────────────────────────────────
    def _poll_status(self) -> None:
        if not self._running:
            return
        threading.Thread(target=self._fetch_health, daemon=True).start()
        self.after(6000, self._poll_status)

    def _fetch_health(self) -> None:
        try:
            import urllib.request as _ureq, json as _json
            with _ureq.urlopen(HEALTH_URL, timeout=3) as r:
                data = _json.loads(r.read())

            def _upd():
                self._set_status(self._st_server, "online", "Online ✓")
                if not self._opened_admin:
                    self._opened_admin = True
                    threading.Thread(target=lambda: webbrowser.open(ADMIN_URL),
                                     daemon=True).start()
                ollama = data.get("ollama", {})
                if ollama.get("healthy"):
                    model = ollama.get("model", "")
                    self._set_status(self._st_ollama, "online", f"Online · {model}")
                else:
                    self._set_status(self._st_ollama, "error", "Offline")
                rag = data.get("rag", {})
                if rag.get("ready"):
                    self._set_status(self._st_rag, "online",
                                     f"{rag.get('chunks', 0)} chunks")
                else:
                    self._set_status(self._st_rag, "starting", "Indexing...")

            self.after(0, _upd)
        except Exception:
            self.after(0, lambda: self._set_status(
                self._st_server, "starting", "กำลังเริ่ม..."))

    # ── ngrok ─────────────────────────────────────────────────────────────────
    def _start_ngrok(self) -> None:
        env = read_env()
        token = env.get("NGROK_AUTH_TOKEN", "").strip()
        if token:
            subprocess.run(["ngrok", "config", "add-authtoken", token],
                           capture_output=True)
        self.after(0, lambda: self._set_status(
            self._st_ngrok, "starting", "กำลังเชื่อมต่อ..."))
        try:
            self._ngrok_proc = subprocess.Popen(
                ["ngrok", "http", "8000"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
            self.after(0, self._poll_ngrok_url)
        except Exception as exc:
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "error", f"Error: {exc}"))

    def _poll_ngrok_url(self) -> None:
        if not self._running:
            return
        threading.Thread(target=self._fetch_ngrok_url, daemon=True).start()
        self.after(8000, self._poll_ngrok_url)

    def _fetch_ngrok_url(self) -> None:
        try:
            import urllib.request as _ureq, json as _json
            with _ureq.urlopen("http://localhost:4040/api/tunnels", timeout=3) as r:
                tunnels = _json.loads(r.read()).get("tunnels", [])
            for t in tunnels:
                if t.get("proto") == "https":
                    url = t["public_url"]
                    webhook = url + "/webhook"
                    if webhook != self._ngrok_url:
                        threading.Thread(
                            target=self._sync_line_webhook, args=(webhook,),
                            daemon=True,
                        ).start()

                    def _upd(u=url, w=webhook):
                        self._ngrok_url = w
                        short = u.replace("https://", "")
                        self._set_status(self._st_ngrok, "online", short)
                        self._url_label.config(text=w, fg=C["GREEN"])
                        self._btn_copy.config(state="normal")

                    self.after(0, _upd)
                    return
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "starting", "รอ tunnel..."))
        except Exception:
            self.after(0, lambda: self._set_status(
                self._st_ngrok, "starting", "กำลังเชื่อมต่อ..."))

    def _sync_line_webhook(self, webhook_url: str) -> None:
        import urllib.request as _ureq, urllib.error as _uerr, json as _json
        cfg = read_config()
        token = cfg.get("line_channel_access_token", "").strip()
        if not token:
            self.after(0, lambda: self._log_write(
                "⚠ ไม่มี LINE token — ข้าม webhook sync\n", "WARNING"))
            return
        self.after(0, lambda: self._log_write(
            f"→ Syncing webhook: {webhook_url}\n", "DIM"))
        try:
            body = _json.dumps({"webhookEndpointUrl": webhook_url}).encode("utf-8")
            req = _ureq.Request(
                "https://api.line.me/v2/bot/channel/webhook/endpoint",
                data=body,
                headers={"Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                method="PUT",
            )
            with _ureq.urlopen(req, timeout=10) as resp:
                status = resp.status
            if status == 200:
                self.after(0, lambda: self._log_write(
                    f"✓ LINE webhook อัปเดตแล้ว: {webhook_url}\n", "OK"))
            else:
                self.after(0, lambda: self._log_write(
                    f"⚠ Webhook sync failed: HTTP {status}\n", "WARNING"))
        except _uerr.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            self.after(0, lambda: self._log_write(
                f"⚠ Webhook sync HTTP {exc.code}: {err}\n", "WARNING"))
        except Exception as exc:
            self.after(0, lambda: self._log_write(
                f"⚠ Webhook sync error: {exc}\n", "WARNING"))

    # ── UI helpers ────────────────────────────────────────────────────────────
    def _copy_url(self) -> None:
        if not self._ngrok_url:
            return
        self.clipboard_clear()
        self.clipboard_append(self._ngrok_url)
        self._btn_copy.config(text="✓ Copied!")
        self.after(2000, lambda: self._btn_copy.config(text="📋 Copy"))

    def _open_webhook_url(self) -> None:
        if self._ngrok_url:
            webbrowser.open(self._ngrok_url.replace("/webhook", ""))

    def _open_admin(self) -> None:
        webbrowser.open(ADMIN_URL)

    def _tick_stats(self) -> None:
        if self._running and self._proc:
            elapsed = int(time.time() - self._start_time) if hasattr(self, "_start_time") else 0
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self._lbl_uptime.config(text=f"Uptime: {h:02d}:{m:02d}:{s:02d}")
        else:
            self._lbl_uptime.config(text="Uptime: —")
        self.after(1000, self._tick_stats)

    def on_close(self) -> None:
        _kill_proc(self._proc)
        _kill_proc(self._ngrok_proc)


# ═════════════════════════════════════════════════════════════════════════════
# SETTINGS TAB (replaces the popup wizard — fixes Mac Toplevel issues)
# ═════════════════════════════════════════════════════════════════════════════
class SettingsTab(tk.Frame):
    def __init__(self, master: tk.Widget, on_save: "Callable"):
        super().__init__(master, bg=C["BG"])
        self._on_save = on_save
        self._vars: dict[str, tk.StringVar] = {}
        self._build()
        self._load()

    def _section(self, title: str, icon: str = "") -> tk.Frame:
        outer = tk.Frame(self, bg=C["BG"])
        outer.pack(fill="x", padx=14, pady=(10, 0))
        hdr = tk.Frame(outer, bg=C["PINK_LIGHT"], pady=4, padx=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"{icon}  {title}" if icon else title,
                 font=("", 11, "bold"), bg=C["PINK_LIGHT"],
                 fg=C["PINK2"]).pack(anchor="w")
        body = tk.Frame(outer, bg=C["CARD"], padx=14, pady=10,
                        highlightthickness=1, highlightbackground=C["BORDER"])
        body.pack(fill="x")
        return body

    def _build(self) -> None:
        # Scrollable canvas
        canvas = tk.Canvas(self, bg=C["BG"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(canvas, bg=C["BG"])
        win = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        def _resize(e):
            canvas.itemconfig(win, width=e.width)
        canvas.bind("<Configure>", _resize)

        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)

        self._inner.bind("<Configure>",
                         lambda e: canvas.configure(
                             scrollregion=canvas.bbox("all")))

        self._build_sections()

    def _build_sections(self) -> None:
        p = self._inner

        # ── LINE Credentials ──────────────────────────────────────────────────
        sec = self._section_in(p, "🔑  LINE Credentials",
                               "หาได้ที่ developers.line.biz → เลือก Channel")
        self._vars["line_channel_access_token"] = tk.StringVar()
        self._vars["line_channel_secret"] = tk.StringVar()
        SecretEntry(sec, "Channel Access Token *",
                    self._vars["line_channel_access_token"], secret=False,
                    hint="ยาวมาก เริ่มต้นด้วย eyJ...")
        SecretEntry(sec, "Channel Secret *",
                    self._vars["line_channel_secret"], secret=True,
                    hint="32 ตัวอักษร — ดูใน Basic settings")

        link_f = tk.Frame(sec, bg=C["CARD"])
        link_f.pack(anchor="w", pady=(6, 0))
        tk.Button(link_f, text="🌐 เปิด LINE Developers Console",
                  font=("", 10), bg=C["CARD"], fg=C["PINK"],
                  relief="flat", cursor="hand2",
                  command=lambda: webbrowser.open(
                      "https://developers.line.biz/console/")).pack(side="left")

        # ── Bot Identity ──────────────────────────────────────────────────────
        sec2 = self._section_in(p, "🏫  Bot Identity",
                                "บอทจะแนะนำตัวเองด้วยข้อมูลนี้")
        self._vars["faculty_name"] = tk.StringVar()
        self._vars["university_name"] = tk.StringVar()
        self._plain_entry(sec2, "ชื่อคณะ / หน่วยงาน", "faculty_name",
                          hint="เช่น คณะวิทยาศาสตร์, งานทะเบียน")
        self._plain_entry(sec2, "ชื่อมหาวิทยาลัย / องค์กร", "university_name")

        # ── ngrok ─────────────────────────────────────────────────────────────
        sec3 = self._section_in(p, "🔗  ngrok Auth Token (ถ้ามี)",
                                "ใส่เพื่อไม่ให้ URL เปลี่ยนบ่อย")
        self._vars["NGROK_AUTH_TOKEN"] = tk.StringVar()
        SecretEntry(sec3, "Auth Token", self._vars["NGROK_AUTH_TOKEN"],
                    secret=True, hint="จาก dashboard.ngrok.com → Getting Started → Authtoken")
        tk.Button(sec3, text="🌐 เปิด ngrok Dashboard",
                  font=("", 10), bg=C["CARD"], fg=C["PINK"],
                  relief="flat", cursor="hand2",
                  command=lambda: webbrowser.open(
                      "https://dashboard.ngrok.com")).pack(anchor="w", pady=(4, 0))

        # ── Ollama ────────────────────────────────────────────────────────────
        sec4 = self._section_in(p, "🦙  Ollama Settings", "")
        self._vars["ollama_base_url"] = tk.StringVar()
        self._vars["ollama_chat_model"] = tk.StringVar()
        self._vars["ollama_embed_model"] = tk.StringVar()
        self._plain_entry(sec4, "Ollama URL", "ollama_base_url")
        self._plain_entry(sec4, "Chat Model", "ollama_chat_model",
                          hint="แนะนำ: llama3.2, typhoon2-8b-instruct")
        self._plain_entry(sec4, "Embed Model", "ollama_embed_model",
                          hint="แนะนำ: nomic-embed-text")

        status_f = tk.Frame(sec4, bg=C["CARD"])
        status_f.pack(fill="x", pady=(8, 0))
        self._ollama_status = tk.Label(status_f, text="", font=("", 10),
                                       bg=C["CARD"], fg=C["MUTED"])
        self._ollama_status.pack(side="left")
        tk.Button(status_f, text="ทดสอบ Ollama",
                  font=("", 10), bg=C["PINK"], fg="white",
                  relief="flat", padx=10, pady=3, cursor="hand2",
                  command=self._test_ollama).pack(side="right")

        # ── Save button ───────────────────────────────────────────────────────
        save_f = tk.Frame(p, bg=C["BG"], pady=14)
        save_f.pack(fill="x", padx=14)
        self._btn_save = tk.Button(
            save_f, text="💾  Save All Settings",
            command=self.save,
            font=("", 13, "bold"), bg=C["GREEN"], fg="white",
            relief="flat", padx=28, pady=10, cursor="hand2",
            activebackground="#009624", activeforeground="white",
        )
        self._btn_save.pack(side="left")

        self._save_label = tk.Label(save_f, text="", font=("", 10),
                                    bg=C["BG"], fg=C["GREEN"])
        self._save_label.pack(side="left", padx=12)

    def _section_in(self, parent: tk.Widget, title: str, hint: str = "") -> tk.Frame:
        outer = tk.Frame(parent, bg=C["BG"])
        outer.pack(fill="x", padx=14, pady=(10, 0))

        hdr = tk.Frame(outer, bg=C["PINK_LIGHT"], pady=6, padx=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text=title, font=("", 11, "bold"),
                 bg=C["PINK_LIGHT"], fg=C["PINK2"]).pack(side="left")
        if hint:
            tk.Label(hdr, text=hint, font=("", 9),
                     bg=C["PINK_LIGHT"], fg=C["MUTED"]).pack(side="left", padx=(8, 0))

        body = tk.Frame(outer, bg=C["CARD"], padx=14, pady=10,
                        highlightthickness=1, highlightbackground=C["BORDER"])
        body.pack(fill="x")
        return body

    def _plain_entry(self, parent: tk.Widget, label: str, key: str,
                     hint: str = "") -> None:
        tk.Label(parent, text=label, font=("", 11, "bold"),
                 bg=C["CARD"], fg=C["TEXT"]).pack(anchor="w", pady=(4, 0))
        e = tk.Entry(parent, textvariable=self._vars[key],
                     font=("", 11), relief="flat",
                     bg=C["CARD2"], fg=C["TEXT"],
                     insertbackground=C["PINK"],
                     highlightthickness=1,
                     highlightbackground=C["BORDER"],
                     highlightcolor=C["PINK"])
        e.pack(fill="x", ipady=5, pady=(2, 0))
        if hint:
            tk.Label(parent, text=hint, font=("", 9),
                     bg=C["CARD"], fg=C["MUTED"]).pack(anchor="w", pady=(2, 0))

    def _load(self) -> None:
        cfg = read_config()
        env = read_env()
        defaults = {
            "ollama_base_url": "http://localhost:11434",
            "ollama_chat_model": "llama3.2",
            "ollama_embed_model": "nomic-embed-text",
            "faculty_name": "",
            "university_name": "",
            "line_channel_access_token": "",
            "line_channel_secret": "",
        }
        for k, v in defaults.items():
            if k in self._vars:
                self._vars[k].set(cfg.get(k, v))
        ngrok = env.get("NGROK_AUTH_TOKEN", "")
        if "NGROK_AUTH_TOKEN" in self._vars:
            self._vars["NGROK_AUTH_TOKEN"].set(ngrok)

    def save(self) -> None:
        cfg_keys = [
            "line_channel_access_token", "line_channel_secret",
            "faculty_name", "university_name",
            "ollama_base_url", "ollama_chat_model", "ollama_embed_model",
        ]
        updates = {}
        for k in cfg_keys:
            if k in self._vars:
                v = self._vars[k].get().strip()
                if v:
                    updates[k] = v

        if not updates.get("line_channel_access_token") or \
           not updates.get("line_channel_secret"):
            messagebox.showerror("ขาดข้อมูล",
                                 "Channel Access Token และ Channel Secret ห้ามว่าง",
                                 parent=self.winfo_toplevel())
            return

        write_config(updates)

        ngrok_token = self._vars.get("NGROK_AUTH_TOKEN", tk.StringVar()).get().strip()
        if ngrok_token:
            write_env_key("NGROK_AUTH_TOKEN", ngrok_token)

        self._save_label.config(text="✓ บันทึกแล้ว!", fg=C["GREEN"])
        self.after(3000, lambda: self._save_label.config(text=""))

        self._on_save()

    def _test_ollama(self) -> None:
        self._ollama_status.config(text="⏳ กำลังตรวจสอบ...", fg=C["ORANGE"])
        url = self._vars.get("ollama_base_url", tk.StringVar()).get().strip()

        def _run():
            try:
                import urllib.request as _ureq, json as _json
                with _ureq.urlopen(f"{url}/api/tags", timeout=4) as r:
                    models = [m["name"] for m in _json.loads(r.read()).get("models", [])]
                msg = f"✓ เชื่อมต่อได้! พบ {len(models)} models"
                self.after(0, lambda: self._ollama_status.config(
                    text=msg, fg=C["GREEN"]))
            except Exception as exc:
                self.after(0, lambda: self._ollama_status.config(
                    text=f"✗ เชื่อมต่อไม่ได้: {exc}", fg=C["RED"]))

        threading.Thread(target=_run, daemon=True).start()


# ═════════════════════════════════════════════════════════════════════════════
# UPDATE DIALOG
# ═════════════════════════════════════════════════════════════════════════════
class UpdateDialog(tk.Toplevel):
    """Modal window that streams apply_update() output and offers restart."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.title("อัปเดต LINE Bot")
        self.resizable(True, True)
        self.minsize(480, 320)
        self.geometry("520x420")
        self.configure(bg=C["BG"])
        self.transient(parent)
        self.grab_set()
        self.after(10, self._center)
        self._build()
        self.after(200, lambda: threading.Thread(
            target=self._worker, daemon=True).start())

    def _center(self) -> None:
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 520, 420
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build(self) -> None:
        make_header(self, "อัปเดต LINE Bot", "กำลังดาวน์โหลดการอัปเดต...", height=60)

        log_frame = tk.Frame(self, bg=C["LOG_BG"])
        log_frame.pack(fill="both", expand=True, padx=14, pady=(10, 0))
        sb = ttk.Scrollbar(log_frame)
        sb.pack(side="right", fill="y")
        self._log_w = tk.Text(
            log_frame, bg=C["LOG_BG"], fg=C["LOG_FG"],
            font=("Menlo" if sys.platform == "darwin" else "Consolas", 10),
            relief="flat", state="disabled", bd=0,
            padx=8, pady=6, wrap="word", yscrollcommand=sb.set,
        )
        self._log_w.pack(side="left", fill="both", expand=True)
        sb.config(command=self._log_w.yview)

        btn_row = tk.Frame(self, bg=C["BG"])
        btn_row.pack(fill="x", padx=14, pady=10)
        self._btn_restart = tk.Button(
            btn_row, text="🔄  Restart Now",
            font=("", 12, "bold"), bg=C["GREEN"], fg="white",
            relief="flat", padx=20, pady=8, cursor="hand2",
            state="disabled",
            activebackground="#009624", activeforeground="white",
            command=self._restart,
        )
        self._btn_restart.pack(side="left")
        tk.Button(
            btn_row, text="✕  Close",
            font=("", 11), bg=C["MUTED"], fg="white",
            relief="flat", padx=16, pady=8, cursor="hand2",
            command=self.destroy,
        ).pack(side="right")

    def _append(self, text: str) -> None:
        def _u():
            self._log_w.config(state="normal")
            self._log_w.insert("end", text)
            self._log_w.see("end")
            self._log_w.config(state="disabled")
        self.after(0, _u)

    def _worker(self) -> None:
        try:
            from updater import apply_update
        except ImportError as exc:
            self._append(f"✗ Cannot import updater: {exc}\n")
            return
        try:
            for line in apply_update():
                self._append(line)
            self.after(0, lambda: self._btn_restart.config(state="normal"))
        except Exception as exc:
            self._append(f"\n✗ Error: {exc}\n")

    def _restart(self) -> None:
        launcher = str(PROJECT_DIR / "launcher" / "launcher.py")
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        try:
            subprocess.Popen([sys.executable, launcher],
                             cwd=str(PROJECT_DIR), env=env)
        except Exception as exc:
            self._append(f"\n✗ Restart failed: {exc}\n")
            return
        root = self.winfo_toplevel()
        try:
            root.destroy()
        except Exception:
            pass
        sys.exit(0)


# ═════════════════════════════════════════════════════════════════════════════
# SYSTEM TAB
# ═════════════════════════════════════════════════════════════════════════════
class SystemTab(tk.Frame):
    def __init__(self, master: tk.Widget):
        super().__init__(master, bg=C["BG"])
        self._build()
        self.after(500, self._refresh)
        self.after(2000, self._auto_check)

    def _build(self) -> None:
        import platform

        # Quick links
        link_card = tk.Frame(self, bg=C["CARD"], padx=16, pady=12,
                             highlightthickness=1, highlightbackground=C["BORDER"])
        link_card.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(link_card, text="Quick Links", font=("", 11, "bold"),
                 bg=C["CARD"], fg=C["TEXT"]).pack(anchor="w", pady=(0, 8))

        links = [
            ("🌐 Admin Panel",           ADMIN_URL),
            ("📊 LINE Developers Console", "https://developers.line.biz/console/"),
            ("🦙 Ollama Models",          "https://ollama.com/library"),
            ("🔗 ngrok Dashboard",        "https://dashboard.ngrok.com"),
            ("📖 LINE API Docs",          "https://developers.line.biz/en/docs/messaging-api/"),
        ]
        for label, url in links:
            f = tk.Frame(link_card, bg=C["CARD"])
            f.pack(fill="x", pady=2)
            btn = tk.Button(f, text=label, font=("", 11),
                            bg=C["PINK_LIGHT"], fg=C["PINK2"],
                            relief="flat", padx=10, pady=5,
                            cursor="hand2", anchor="w",
                            command=lambda u=url: webbrowser.open(u))
            btn.pack(side="left", fill="x", expand=True)

        # System info
        sys_card = tk.Frame(self, bg=C["CARD"], padx=16, pady=12,
                            highlightthickness=1, highlightbackground=C["BORDER"])
        sys_card.pack(fill="x", padx=14, pady=4)
        tk.Label(sys_card, text="System Info", font=("", 11, "bold"),
                 bg=C["CARD"], fg=C["TEXT"]).pack(anchor="w", pady=(0, 8))

        self._info_text = tk.Text(sys_card, height=6,
                                  font=("Menlo" if sys.platform == "darwin"
                                        else "Consolas", 10),
                                  bg=C["CARD2"], fg=C["TEXT2"],
                                  relief="flat", state="disabled",
                                  bd=0, padx=8, pady=6, wrap="none")
        self._info_text.pack(fill="x")

        # About
        about = tk.Frame(self, bg=C["CARD"], padx=16, pady=10,
                         highlightthickness=1, highlightbackground=C["BORDER"])
        about.pack(fill="x", padx=14, pady=4)
        tk.Label(about, text=f"LINE Bot Control Panel  v{APP_VERSION}",
                 font=("", 11, "bold"), bg=C["CARD"], fg=C["TEXT"]).pack(anchor="w")
        tk.Label(about, text="Powered by Ollama + FastAPI + LINE Messaging API",
                 font=("", 10), bg=C["CARD"], fg=C["MUTED"]).pack(anchor="w", pady=(2, 0))

        # ── Updates ───────────────────────────────────────────────────────────
        upd_card = tk.Frame(self, bg=C["CARD"], padx=16, pady=12,
                            highlightthickness=1, highlightbackground=C["BORDER"])
        upd_card.pack(fill="x", padx=14, pady=4)

        upd_hdr = tk.Frame(upd_card, bg=C["CARD"])
        upd_hdr.pack(fill="x")
        tk.Label(upd_hdr, text="🔄  Updates", font=("", 11, "bold"),
                 bg=C["CARD"], fg=C["TEXT"]).pack(side="left")
        tk.Label(upd_hdr, text=f"v{APP_VERSION}", font=("", 10),
                 bg=C["CARD"], fg=C["MUTED"]).pack(side="right")

        self._lbl_update_status = tk.Label(
            upd_card, text="กดปุ่มเพื่อตรวจสอบการอัปเดต",
            font=("", 10), bg=C["CARD"], fg=C["MUTED"], anchor="w")
        self._lbl_update_status.pack(fill="x", pady=(6, 6))

        upd_btns = tk.Frame(upd_card, bg=C["CARD"])
        upd_btns.pack(fill="x")

        self._btn_check = tk.Button(
            upd_btns, text="🔍  Check for Updates",
            font=("", 11), bg=C["CARD"], fg=C["TEXT2"],
            relief="flat", padx=12, pady=5, cursor="hand2",
            highlightthickness=1, highlightbackground=C["BORDER"],
            activebackground=C["PINK_LIGHT"],
            command=self._check_updates,
        )
        self._btn_check.pack(side="left")

        self._btn_update = tk.Button(
            upd_btns, text="⬇  Update Now",
            font=("", 11, "bold"), bg=C["GREEN"], fg="white",
            relief="flat", padx=12, pady=5, cursor="hand2",
            state="disabled",
            activebackground="#009624", activeforeground="white",
            command=self._do_update,
        )
        self._btn_update.pack(side="left", padx=(8, 0))

    def _check_updates(self) -> None:
        self._lbl_update_status.config(text="⏳ กำลังตรวจสอบ...", fg=C["ORANGE"])
        self._btn_check.config(state="disabled")
        self._btn_update.config(state="disabled")
        threading.Thread(target=self._check_updates_bg, daemon=True).start()

    def _check_updates_bg(self) -> None:
        try:
            from updater import check_for_updates
            info = check_for_updates()
        except ImportError as exc:
            _msg = f"✗ updater module not found: {exc}"
            def _err():
                self._lbl_update_status.config(text=_msg, fg=C["RED"])
                self._btn_check.config(state="normal")
            self.after(0, _err)
            return

        def _upd():
            self._btn_check.config(state="normal")
            if not info.get("git_available"):
                self._lbl_update_status.config(
                    text="✗ ไม่พบ git — กรุณาติดตั้ง git ก่อน", fg=C["RED"])
                return
            if info.get("error"):
                self._lbl_update_status.config(
                    text=f"✗ {info['error']}", fg=C["RED"])
                return
            if info.get("available"):
                n = info["commits_behind"]
                self._lbl_update_status.config(
                    text=f"✅ มีอัปเดต {n} commit{'s' if n != 1 else ''} — "
                         f"{info['local']} → {info['remote']}",
                    fg=C["GREEN"])
                self._btn_update.config(state="normal")
            else:
                self._lbl_update_status.config(
                    text=f"✓ เวอร์ชันล่าสุดแล้ว  ({info.get('local', '?')})",
                    fg=C["GREEN"])

        self.after(0, _upd)

    def _auto_check(self) -> None:
        threading.Thread(target=self._check_updates_bg, daemon=True).start()

    def _do_update(self) -> None:
        UpdateDialog(self.winfo_toplevel())

    def _refresh(self) -> None:
        import platform
        py_ver = sys.version.split()[0]
        plat = f"{platform.system()} {platform.release()}"
        cfg = read_config()
        token = cfg.get("line_channel_access_token", "")
        secret = cfg.get("line_channel_secret", "")
        model = cfg.get("ollama_chat_model", "llama3.2")

        lines = [
            f"Python:       {py_ver}",
            f"Platform:     {plat}",
            f"Project:      {PROJECT_DIR}",
            f"LINE Token:   {'✓ ตั้งค่าแล้ว' if token else '✗ ยังไม่ได้ตั้ง'}",
            f"LINE Secret:  {'✓ ตั้งค่าแล้ว' if secret else '✗ ยังไม่ได้ตั้ง'}",
            f"Chat Model:   {model}",
        ]
        self._info_text.config(state="normal")
        self._info_text.delete("1.0", "end")
        self._info_text.insert("end", "\n".join(lines))
        self._info_text.config(state="disabled")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN APP
# ═════════════════════════════════════════════════════════════════════════════
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LINE Bot — Control Panel")
        self.resizable(True, True)
        self.minsize(520, 560)
        self.geometry("560x680")
        self.configure(bg=C["BG"])
        self.after(10, self._center)

        # macOS dock/quit
        try:
            self.createcommand("tk::mac::Quit", self._on_quit)
            self.createcommand("tk::mac::ShowPreferences",
                               lambda: self.show_tab(1))
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self._on_quit)

        self._control_tab: ControlTab | None = None
        self._build()

        # First-run: show Settings if not configured
        if not is_configured():
            self.after(200, lambda: self.show_tab(1))

    def _center(self):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 560, 680
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    def _build(self):
        # Header
        make_header(self, "LINE Bot", "Control Panel", height=68)

        # Styled notebook
        style = ttk.Style()
        style.theme_use("default")
        style.configure("App.TNotebook",
                        background=C["BG"],
                        borderwidth=0,
                        tabmargins=[14, 6, 0, 0])
        style.configure("App.TNotebook.Tab",
                        background=C["BORDER"],
                        foreground=C["TEXT2"],
                        font=("", 11),
                        padding=[14, 6],
                        borderwidth=0)
        style.map("App.TNotebook.Tab",
                  background=[("selected", C["PINK"]),
                              ("active",   C["PINK_LIGHT"])],
                  foreground=[("selected", C["WHITE"]),
                              ("active",   C["PINK2"])])

        self._nb = ttk.Notebook(self, style="App.TNotebook")
        self._nb.pack(fill="both", expand=True)

        self._control_tab = ControlTab(self._nb, app=self)
        settings_tab = SettingsTab(self._nb, on_save=self._after_save)
        system_tab = SystemTab(self._nb)

        self._nb.add(self._control_tab, text="  ▶ Control  ")
        self._nb.add(settings_tab,      text="  ⚙ Settings  ")
        self._nb.add(system_tab,        text="  ℹ System  ")

    def show_tab(self, index: int) -> None:
        try:
            self._nb.select(index)
        except Exception:
            pass

    def _after_save(self) -> None:
        self.show_tab(0)
        # Hide banner if now configured
        if is_configured() and self._control_tab:
            try:
                self._control_tab._banner.pack_forget()
            except Exception:
                pass

    def _on_quit(self) -> None:
        if self._control_tab:
            self._control_tab.on_close()
        self.destroy()


if __name__ == "__main__":
    import traceback
    try:
        app = App()
        app.mainloop()
    except Exception:
        err = traceback.format_exc()
        try:
            _r = tk.Tk()
            _r.withdraw()
            messagebox.showerror("LINE Bot — Error", err, parent=_r)
        except Exception:
            print(err, file=sys.stderr)
