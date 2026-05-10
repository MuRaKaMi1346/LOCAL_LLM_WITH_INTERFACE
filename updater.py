"""
updater.py — Git-based auto-update for LINE Bot
Requires: git in PATH (macOS: Xcode CLT / Homebrew, Windows: Git for Windows)
"""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
from typing import Generator

PROJECT_DIR = Path(__file__).resolve().parent
_VENV_PIP_WIN = PROJECT_DIR / ".venv" / "Scripts" / "pip.exe"
_VENV_PIP_MAC = PROJECT_DIR / ".venv" / "bin" / "pip"
_W32 = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


# ── internal helpers ──────────────────────────────────────────────────────────

def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(PROJECT_DIR),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_W32,
    )


def _pip() -> str:
    for p in (_VENV_PIP_WIN, _VENV_PIP_MAC):
        if p.exists():
            return str(p)
    return "pip"


# ── public API ────────────────────────────────────────────────────────────────

def git_available() -> bool:
    return _git("--version").returncode == 0


def get_local_hash() -> str:
    r = _git("rev-parse", "--short", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def get_branch() -> str:
    r = _git("rev-parse", "--abbrev-ref", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else "main"


def check_for_updates() -> dict:
    """
    Fetch remote and compare.

    Returns dict:
        git_available  bool
        available      bool   — True if remote has newer commits
        commits_behind int
        local          str    — short hash
        remote         str    — short hash of origin/<branch>
        branch         str
        error          str | None
    """
    if not git_available():
        return {
            "git_available": False, "available": False,
            "commits_behind": 0, "local": "?", "remote": "?",
            "branch": "main", "error": "git not found",
        }

    branch = get_branch()

    fetch = _git("fetch", "--quiet", "origin")
    if fetch.returncode != 0:
        return {
            "git_available": True, "available": False,
            "commits_behind": 0, "local": get_local_hash(), "remote": "?",
            "branch": branch,
            "error": (fetch.stderr.strip() or "fetch failed")[:120],
        }

    r = _git("rev-list", f"HEAD..origin/{branch}", "--count")
    count = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0

    r2 = _git("rev-parse", "--short", f"origin/{branch}")
    remote_hash = r2.stdout.strip() if r2.returncode == 0 else "?"

    return {
        "git_available": True,
        "available": count > 0,
        "commits_behind": count,
        "local": get_local_hash(),
        "remote": remote_hash,
        "branch": branch,
        "error": None,
    }


def apply_update() -> Generator[str, None, None]:
    """
    Pull and reinstall deps if requirements.txt changed.
    Yields log lines (str).  Last line contains "✓" on success.
    """
    branch = get_branch()

    # ── fetch ────────────────────────────────────────────────────────────────
    yield f"▶ Fetching origin/{branch}...\n"
    fetch = _git("fetch", "origin")
    if fetch.returncode != 0:
        yield f"✗ Fetch failed:\n  {fetch.stderr.strip()}\n"
        return

    # ── check which files will change ────────────────────────────────────────
    diff = _git("diff", "--name-only", f"HEAD..origin/{branch}")
    changed = diff.stdout.strip().splitlines() if diff.returncode == 0 else []
    req_changed = "requirements.txt" in changed

    if not changed:
        yield "✓ Already up to date.\n"
        return

    yield f"▶ {len(changed)} file(s) will be updated\n"
    for f in changed[:10]:
        yield f"   • {f}\n"
    if len(changed) > 10:
        yield f"   … and {len(changed) - 10} more\n"

    # ── pull ─────────────────────────────────────────────────────────────────
    yield f"▶ Pulling changes...\n"
    pull = _git("pull", "--ff-only", "origin", branch)
    if pull.returncode != 0:
        yield "  (fast-forward failed — trying rebase)\n"
        pull = _git("pull", "--rebase", "origin", branch)
    if pull.returncode != 0:
        yield f"✗ Pull failed:\n  {pull.stderr.strip()}\n"
        yield f"  แก้ด้วย: cd '{PROJECT_DIR}' && git pull\n"
        return

    if pull.stdout.strip():
        for line in pull.stdout.strip().splitlines():
            yield f"  {line}\n"

    # ── pip install if requirements changed ──────────────────────────────────
    if req_changed:
        yield "▶ Installing updated packages...\n"
        pip_proc = subprocess.run(
            [_pip(), "install", "-r", str(PROJECT_DIR / "requirements.txt"),
             "-q", "--no-warn-script-location"],
            cwd=str(PROJECT_DIR),
            capture_output=True, text=True,
            creationflags=_W32,
        )
        if pip_proc.returncode == 0:
            yield "✓ Packages updated\n"
        else:
            yield f"⚠ pip warning:\n  {pip_proc.stderr.strip()[:200]}\n"

    yield "✓ Update complete — restart to apply changes\n"


def get_changelog(n: int = 8) -> list[str]:
    """Return last n commit messages from origin (after fetch)."""
    branch = get_branch()
    r = _git("log", f"origin/{branch}", f"-{n}",
             "--pretty=format:%h  %s  (%ar)")
    if r.returncode != 0:
        return []
    return r.stdout.strip().splitlines()
