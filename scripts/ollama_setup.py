#!/usr/bin/env python3
"""
scripts/ollama_setup.py — Cross-platform Ollama manager.

Headless/CLI only. Never installs or launches the Ollama GUI app.
Uses only Python stdlib — safe to run before the venv is created.

Usage:
    python scripts/ollama_setup.py                    # detect + start + pull
    python scripts/ollama_setup.py --install          # install if missing
    python scripts/ollama_setup.py --start            # start service if stopped
    python scripts/ollama_setup.py --pull-models      # pull required models
    python scripts/ollama_setup.py --verify           # exit 1 if not ready
    python scripts/ollama_setup.py --status           # print JSON status

Exit codes:
    0 — Ollama ready (running + models available)
    1 — Not ready (see --verify)
    2 — Unrecoverable error
"""
from __future__ import annotations
import argparse, json, os, platform, shutil, subprocess, sys, time
import urllib.request, urllib.error
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE     = Path(__file__).resolve().parent          # scripts/
_ROOT     = _HERE.parent                             # project root
_CFG_JSON = _ROOT / "config.json"

# ── Platform helpers ──────────────────────────────────────────────────────────
def _macos()   -> bool: return sys.platform == "darwin"
def _windows() -> bool: return sys.platform == "win32"
def _linux()   -> bool: return sys.platform.startswith("linux")
def _arm()     -> bool: return platform.machine().lower() in ("arm64", "aarch64")

_NO_COLOR = _windows() or not sys.stdout.isatty()

def _c(code: str, s: str) -> str:
    return s if _NO_COLOR else f"\033[{code}m{s}\033[0m"

# ── Logging ───────────────────────────────────────────────────────────────────
_QUIET = False

def _log(msg: str, *, ok=False, warn=False, err=False) -> None:
    if _QUIET and not err:
        return
    if ok:   pfx = _c("32", "  ✓ ")
    elif warn: pfx = _c("33", "  ⚠ ")
    elif err:  pfx = _c("31", "  ✗ ")
    else:      pfx = _c("36", "  ▶ ")
    print(pfx + msg, flush=True)

# ── Configuration ─────────────────────────────────────────────────────────────
def _read_config() -> dict:
    if not _CFG_JSON.exists():
        return {}
    try:
        return json.loads(_CFG_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}

def get_base_url() -> str:
    env = os.environ.get("OLLAMA_BASE_URL", "").strip().rstrip("/")
    if env:
        return env
    cfg = _read_config()
    if url := cfg.get("ollama_base_url", "").strip().rstrip("/"):
        return url
    return "http://localhost:11434"

def get_required_models() -> list[str]:
    """Return model base names from config.json or defaults."""
    cfg = _read_config()
    models: set[str] = {"llama3.2", "nomic-embed-text"}
    for key in ("ollama_chat_model", "ollama_embed_model"):
        if val := cfg.get(key, "").strip():
            models.add(val.split(":")[0])
    return sorted(models)

# ── Binary discovery ──────────────────────────────────────────────────────────
_MAC_PATHS = [
    "/opt/homebrew/bin/ollama",   # Apple Silicon (Homebrew)
    "/usr/local/bin/ollama",      # Intel (Homebrew)
    "/usr/bin/ollama",            # Linux system install
]
_WIN_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
    r"C:\Program Files\Ollama\ollama.exe",
    r"C:\Program Files (x86)\Ollama\ollama.exe",
]

def find_ollama() -> Optional[str]:
    """Return absolute path to ollama binary, or None."""
    found = shutil.which("ollama")
    if found:
        return found
    paths = _WIN_PATHS if _windows() else _MAC_PATHS
    for p in paths:
        if os.path.isfile(p):
            return p
    return None

def ollama_version(cmd: str) -> str:
    """Return 'ollama x.y.z' or empty string."""
    try:
        r = subprocess.run(
            [cmd, "--version"], capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

# ── REST API helpers (stdlib urllib — no venv dependency) ─────────────────────
def _get(base: str, path: str, timeout: int = 5) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def _post(base: str, path: str, body: dict, timeout: int = 30) -> Optional[dict]:
    try:
        data = json.dumps(body).encode()
        req  = urllib.request.Request(
            f"{base}{path}", data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None

def is_running(base: str) -> bool:
    return _get(base, "/api/tags", timeout=3) is not None

def _wait_for_api(base: str, timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    tick = 0
    while time.time() < deadline:
        if is_running(base):
            return True
        time.sleep(1)
        tick += 1
        if tick % 5 == 0 and not _QUIET:
            _log(f"  Waiting for Ollama API... ({tick}s)")
    return False

# ── Model management ──────────────────────────────────────────────────────────
def list_models(base: str) -> list[str]:
    """All model name strings available in Ollama (full tag + base name)."""
    data = _get(base, "/api/tags")
    if not data:
        return []
    out: list[str] = []
    for m in data.get("models", []):
        name = m.get("name", "").strip()
        if name:
            out.append(name)
            if ":" in name:
                out.append(name.split(":")[0])
    return out

def model_available(base: str, model: str) -> bool:
    """True if `model` (or model:latest, or same base name) exists in Ollama."""
    available = list_models(base)
    base_name  = model.split(":")[0]
    return (
        model in available
        or f"{model}:latest" in available
        or base_name in available
        or any(m.split(":")[0] == base_name for m in available)
    )

def pull_model(base: str, model: str, cmd: Optional[str] = None) -> bool:
    """Pull model via CLI (preferred — shows progress) with API fallback."""
    _log(f"Pulling {model}  (first time — may take several minutes)")

    if cmd:
        try:
            env = os.environ.copy()
            host = base.removeprefix("http://").removeprefix("https://")
            env["OLLAMA_HOST"] = host
            r = subprocess.run(
                [cmd, "pull", model],
                text=True, encoding="utf-8", errors="replace",
                env=env,
            )
            if r.returncode == 0:
                _log(f"{model} ready", ok=True)
                return True
            _log(f"CLI pull exited {r.returncode} — retrying via API", warn=True)
        except Exception as e:
            _log(f"CLI pull error ({e}) — retrying via API", warn=True)

    # API fallback (non-streaming, 10-minute timeout for large models)
    _log(f"  Pulling {model} via API (this may take a while)...")
    try:
        data = json.dumps({"name": model, "stream": False}).encode()
        req  = urllib.request.Request(
            f"{base}/api/pull", data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=600) as r:
            r.read()
        _log(f"{model} ready", ok=True)
        return True
    except Exception as e:
        _log(f"API pull failed for {model}: {e}", err=True)
        return False

def verify_models(base: str, required: list[str]) -> dict[str, bool]:
    return {m: model_available(base, m) for m in required}

# ── Service management ────────────────────────────────────────────────────────
def _start_process(cmd: str, base: str) -> bool:
    """Launch `ollama serve` as a detached background process."""
    _log("Starting Ollama server (headless)...")
    env = os.environ.copy()
    # Tell Ollama which address to listen on (strip http://)
    host = base.removeprefix("http://").removeprefix("https://")
    env["OLLAMA_HOST"] = host

    try:
        if _windows():
            subprocess.Popen(
                [cmd, "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP
                               | subprocess.DETACHED_PROCESS),
                env=env,
            )
        else:
            subprocess.Popen(
                [cmd, "serve"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,   # survives parent shell exit
                env=env,
            )
        return True
    except Exception as e:
        _log(f"Failed to launch ollama serve: {e}", err=True)
        return False

def ensure_service(base: str, cmd: Optional[str] = None) -> bool:
    """Ensure Ollama is running; start headlessly if not. Returns True if API is up."""
    if is_running(base):
        return True

    if not cmd:
        _log("Ollama binary not found — cannot start service", err=True)
        return False

    # macOS: try brew services first (persists across reboots)
    if _macos():
        brew = shutil.which("brew") or "/opt/homebrew/bin/brew" or "/usr/local/bin/brew"
        if brew and os.path.isfile(brew):
            try:
                subprocess.run(
                    [brew, "services", "start", "ollama"],
                    capture_output=True, timeout=20,
                )
                if _wait_for_api(base, timeout_s=10):
                    return True
            except Exception:
                pass

    # Generic fallback: ollama serve detached
    if not _start_process(cmd, base):
        return False

    ready = _wait_for_api(base, timeout_s=30)
    if ready:
        _log("Ollama server is ready", ok=True)
    else:
        _log("Ollama did not respond within 30 s — check logs with: ollama serve", err=True)
    return ready

# ── Installation ──────────────────────────────────────────────────────────────
def install_ollama() -> bool:
    if _macos():   return _install_macos()
    if _windows(): return _install_windows()
    if _linux():   return _install_linux()
    _log(f"Auto-install not supported on {sys.platform}", err=True)
    _log("Download manually from: https://ollama.com")
    return False

def _find_brew() -> Optional[str]:
    for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if os.path.isfile(p):
            return p
    return shutil.which("brew")

def _install_macos() -> bool:
    brew = _find_brew()
    if brew:
        _log("Installing Ollama via Homebrew (headless CLI, no GUI app)...")
        r = subprocess.run([brew, "install", "ollama"], text=True)
        if r.returncode == 0:
            _log("Ollama installed via Homebrew", ok=True)
            return True
        _log("Homebrew install failed", warn=True)
    else:
        _log("Homebrew not found", warn=True)

    _log("Install Homebrew first: https://brew.sh", err=True)
    _log("Then run:  brew install ollama")
    return False

def _install_windows() -> bool:
    # winget (preferred — no GUI installer)
    winget = shutil.which("winget")
    if winget:
        _log("Installing Ollama via winget (silent)...")
        r = subprocess.run(
            [winget, "install", "--id", "Ollama.Ollama",
             "-e", "--accept-source-agreements", "--accept-package-agreements",
             "--silent"],
            text=True,
        )
        if r.returncode == 0:
            _log("Ollama installed", ok=True)
            # Refresh PATH so find_ollama() works immediately
            for p in _WIN_PATHS:
                d = os.path.dirname(p)
                if os.path.isdir(d):
                    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return True
        _log("winget failed — falling back to direct download", warn=True)

    # Direct download silent installer
    import tempfile
    url = "https://ollama.com/download/OllamaSetup.exe"
    tmp = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
    _log("Downloading Ollama installer...")
    try:
        def _hook(n, blk, total):
            if total > 0 and n % 50 == 0:
                pct = min(100, n * blk * 100 // total)
                print(f"\r  {pct}%", end="", flush=True)
        urllib.request.urlretrieve(url, str(tmp), reporthook=_hook)
        print()
        _log("Running installer (silent, no GUI)...")
        subprocess.run(
            [str(tmp), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
            timeout=120, check=True,
        )
        tmp.unlink(missing_ok=True)
        # Refresh PATH
        for p in _WIN_PATHS:
            d = os.path.dirname(p)
            if os.path.isdir(d):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
        _log("Ollama installed", ok=True)
        return True
    except Exception as e:
        _log(f"Download/install failed: {e}", err=True)
        tmp.unlink(missing_ok=True)
        return False

def _install_linux() -> bool:
    curl = shutil.which("curl")
    if not curl:
        _log("curl not found — install it and retry", err=True)
        return False
    _log("Downloading official Ollama install script...")
    r = subprocess.run([curl, "-fsSL", "https://ollama.com/install.sh"],
                       capture_output=True)
    if r.returncode != 0:
        _log("Failed to download install script", err=True)
        return False
    sh = shutil.which("sh") or "/bin/sh"
    r2 = subprocess.run([sh], input=r.stdout)
    if r2.returncode == 0:
        _log("Ollama installed", ok=True)
        return True
    _log("Install script failed", err=True)
    return False

# ── Main orchestration ────────────────────────────────────────────────────────
def run(
    *,
    base_url: str,
    required_models: list[str],
    auto_install: bool = False,
    auto_start:   bool = True,
    auto_pull:    bool = True,
    verify_only:  bool = False,
) -> dict:
    """
    Detect → (install) → start → (pull models) → verify.
    Returns a status dict. Never raises.
    """
    status: dict = {
        "ollama_found":     False,
        "ollama_version":   None,
        "service_running":  False,
        "models":           {},
        "all_models_ready": False,
        "error":            None,
    }

    # ── 1. Detect ─────────────────────────────────────────────────────────────
    cmd = find_ollama()
    status["ollama_found"] = cmd is not None

    if cmd:
        ver = ollama_version(cmd)
        status["ollama_version"] = ver
        _log(f"Ollama found: {cmd}" + (f"  ({ver})" if ver else ""), ok=True)
    else:
        if verify_only:
            status["error"] = "Ollama not installed"
            return status
        if not auto_install:
            _log("Ollama not found — pass --install to install automatically", err=True)
            status["error"] = "Ollama not installed"
            return status

        _log("Ollama not found — installing...")
        if not install_ollama():
            status["error"] = "Installation failed"
            return status

        cmd = find_ollama()
        if not cmd:
            status["error"] = "Ollama binary not found after installation"
            return status
        status["ollama_found"] = True
        status["ollama_version"] = ollama_version(cmd)

    # ── 2. Service ────────────────────────────────────────────────────────────
    running = is_running(base_url)
    if not running:
        if verify_only:
            status["error"] = "Ollama service not running"
            return status
        if auto_start:
            running = ensure_service(base_url, cmd)

    status["service_running"] = running
    if not running:
        status["error"] = "Ollama service not running"
        return status
    _log(f"Ollama API responding at {base_url}", ok=True)

    # ── 3. Models ─────────────────────────────────────────────────────────────
    model_status = verify_models(base_url, required_models)
    missing = [m for m, ok in model_status.items() if not ok]

    if missing:
        if verify_only:
            status["models"] = model_status
            status["error"]  = f"Missing models: {', '.join(missing)}"
            return status
        if auto_pull:
            for model in missing:
                ok = pull_model(base_url, model, cmd=cmd)
                model_status[model] = ok
        else:
            for m in missing:
                _log(f"Model '{m}' not found — run: ollama pull {m}", warn=True)
    else:
        _log(f"Required models OK: {', '.join(required_models)}", ok=True)

    status["models"]           = model_status
    status["all_models_ready"] = all(model_status.values())
    return status

# ── CLI ───────────────────────────────────────────────────────────────────────
def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ollama_setup.py",
        description="Cross-platform Ollama installer and model manager (headless, no GUI)",
    )
    p.add_argument("--install",      action="store_true",
                   help="Install Ollama if not found")
    p.add_argument("--start",        action="store_true",
                   help="Start Ollama service if not running")
    p.add_argument("--pull-models",  action="store_true",
                   help="Pull required models if missing")
    p.add_argument("--verify",       action="store_true",
                   help="Only verify status (exit 1 if not ready)")
    p.add_argument("--status",       action="store_true",
                   help="Print JSON status to stdout and exit")
    p.add_argument("--quiet",        action="store_true",
                   help="Suppress non-error output")
    p.add_argument("--base-url",     default=None,
                   help="Override Ollama URL (default: from config.json)")
    p.add_argument("--models",       nargs="*",
                   help="Override required model list")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    global _QUIET
    _QUIET = args.quiet

    base     = (args.base_url or get_base_url()).rstrip("/")
    required = args.models if args.models is not None else get_required_models()

    # --status: just print and exit
    if args.status:
        cmd = find_ollama()
        up  = is_running(base)
        info = {
            "platform":       f"{sys.platform}/{platform.machine()}",
            "ollama_path":    cmd,
            "ollama_version": ollama_version(cmd) if cmd else None,
            "base_url":       base,
            "service_running": up,
            "required_models": required,
            "models": verify_models(base, required) if up else {},
        }
        print(json.dumps(info, indent=2))
        return 0

    # --verify: check only, no mutations
    if args.verify:
        result = run(
            base_url=base, required_models=required,
            auto_install=False, auto_start=False, auto_pull=False,
            verify_only=True,
        )
        if result["error"]:
            _log(result["error"], err=True)
            return 1
        _log("Ollama is ready", ok=True)
        return 0

    # Normal run
    result = run(
        base_url=base, required_models=required,
        auto_install=args.install,
        auto_start=(args.install or args.start),
        auto_pull=args.pull_models,
    )

    if result.get("error") and not result["service_running"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
