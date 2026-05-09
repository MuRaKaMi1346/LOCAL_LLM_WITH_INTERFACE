import json
import logging
import re
import sys
import platform
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)
from pydantic import BaseModel

from bot.prompts import _SYSTEM_TEMPLATE, _DEFAULT_WELCOME, _DEFAULT_QUICK_TOPICS
from bot.sessions import conversation_manager
from config import settings
from services.ollama import ollama
from services.rag import rag
from state import app_state
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_BASE = Path(__file__).parent.parent
ENV_FILE       = _BASE / ".env"
CONFIG_JSON    = _BASE / "config.json"
DATA_DIR       = _BASE / "data"
LOG_FILE       = _BASE / "logs" / "bot.log"
CUSTOM_PROMPT  = _BASE / "custom_prompt.txt"
CUSTOM_TOPICS  = _BASE / "custom_quick_topics.json"
CUSTOM_WELCOME = _BASE / "custom_welcome.txt"


# ── HTML ──────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def admin_page():
    return HTMLResponse((Path(__file__).parent / "index.html").read_text(encoding="utf-8"))


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/api/status")
async def api_status():
    ollama_ok = await ollama.is_healthy()
    models = await ollama.list_models() if ollama_ok else []
    chunk_count = rag.collection.count() if rag.collection else 0
    doc_count = 0
    if DATA_DIR.exists():
        doc_count = len(list(DATA_DIR.glob("**/*.md")) + list(DATA_DIR.glob("**/*.txt")))
    return {
        "ollama": {
            "healthy": ollama_ok,
            "chat_model": settings.ollama_chat_model,
            "embed_model": settings.ollama_embed_model,
            "available_models": models,
        },
        "rag": {"ready": rag.is_ready, "chunks": chunk_count, "documents": doc_count},
        "bot": {
            "enabled": app_state.bot_enabled,
            "faculty": settings.faculty_name,
            "university": settings.university_name,
        },
    }


@router.get("/api/sysinfo")
async def api_sysinfo():
    uptime = app_state.uptime_seconds
    h, m, s = int(uptime // 3600), int((uptime % 3600) // 60), int(uptime % 60)
    return {
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()}",
        "uptime": f"{h:02d}:{m:02d}:{s:02d}",
        "uptime_seconds": uptime,
        "messages_handled": app_state.message_count,
        "start_time": app_state.start_time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ── Bot On/Off ────────────────────────────────────────────────────────────────

@router.post("/api/bot/toggle")
async def toggle_bot(data: dict):
    enabled = bool(data.get("enabled", True))
    app_state.bot_enabled = enabled
    logger.info("Bot %s via admin panel", "ENABLED" if enabled else "DISABLED")
    return {"ok": True, "enabled": app_state.bot_enabled}


# ── Credentials ───────────────────────────────────────────────────────────────

_CRED_KEYS = ("LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET", "NGROK_AUTH_TOKEN")

def _mask(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "****"
    return val[:4] + "••••••••" + val[-4:]

def _read_env_raw() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


@router.get("/api/credentials")
async def get_credentials():
    raw = _read_env_raw()
    return {k: _mask(raw.get(k, "")) for k in _CRED_KEYS}


@router.post("/api/credentials")
async def save_credentials(data: dict):
    if not ENV_FILE.exists():
        raise HTTPException(404, ".env ไม่พบ")
    text = ENV_FILE.read_text(encoding="utf-8")
    changed = []
    for key in _CRED_KEYS:
        val = data.get(key, "").strip()
        if not val or "••••••••" in val:
            continue
        pattern = rf"^{key}=.*$"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, f"{key}={val}", text, flags=re.MULTILINE)
        else:
            text += f"\n{key}={val}"
        changed.append(key)
    ENV_FILE.write_text(text, encoding="utf-8")
    return {"ok": True, "changed": changed}


# ── Config ────────────────────────────────────────────────────────────────────

class ConfigPayload(BaseModel):
    faculty_name: str
    university_name: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embed_model: str
    rag_top_k: int
    chunk_size: int
    chunk_overlap: int
    max_history_turns: int


@router.get("/api/config")
async def get_config():
    return {
        "faculty_name": settings.faculty_name,
        "university_name": settings.university_name,
        "ollama_base_url": settings.ollama_base_url,
        "ollama_chat_model": settings.ollama_chat_model,
        "ollama_embed_model": settings.ollama_embed_model,
        "rag_top_k": settings.rag_top_k,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "max_history_turns": settings.max_history_turns,
    }


@router.get("/api/config/defaults")
async def get_config_defaults():
    from pydantic_core import PydanticUndefined
    result = {}
    skip = {"line_channel_access_token", "line_channel_secret"}
    for name, field in type(settings).model_fields.items():
        if name in skip:
            continue
        if field.default is not PydanticUndefined:
            result[name] = field.default
    return result


@router.post("/api/config")
async def update_config(data: ConfigPayload):
    payload = {
        "faculty_name":      data.faculty_name,
        "university_name":   data.university_name,
        "ollama_base_url":   data.ollama_base_url,
        "ollama_chat_model": data.ollama_chat_model,
        "ollama_embed_model":data.ollama_embed_model,
        "rag_top_k":         data.rag_top_k,
        "chunk_size":        data.chunk_size,
        "chunk_overlap":     data.chunk_overlap,
        "max_history_turns": data.max_history_turns,
    }
    CONFIG_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for key, val in payload.items():
        object.__setattr__(settings, key, val)
    ollama.base_url   = settings.ollama_base_url
    ollama.chat_model = settings.ollama_chat_model
    ollama.embed_model = settings.ollama_embed_model
    return {"ok": True}


@router.post("/api/reload")
async def hot_reload():
    """Apply latest secrets (.env) and runtime config (config.json) without restart."""
    changed = []

    # LINE secrets from .env only
    if ENV_FILE.exists():
        env_vals: dict[str, str] = {}
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env_vals[k.strip()] = v.strip()
        for env_key, (attr, typ) in {
            "LINE_CHANNEL_ACCESS_TOKEN": ("line_channel_access_token", str),
            "LINE_CHANNEL_SECRET":       ("line_channel_secret", str),
        }.items():
            if env_key in env_vals:
                try:
                    new_val = typ(env_vals[env_key])
                    if getattr(settings, attr) != new_val:
                        object.__setattr__(settings, attr, new_val)
                        changed.append(attr)
                except Exception:
                    pass

    # Runtime config from config.json
    if CONFIG_JSON.exists():
        try:
            data = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
            runtime_types = {
                "faculty_name": str, "university_name": str,
                "ollama_base_url": str, "ollama_chat_model": str, "ollama_embed_model": str,
                "rag_top_k": int, "chunk_size": int, "chunk_overlap": int,
                "max_history_turns": int,
            }
            for key, typ in runtime_types.items():
                if key in data:
                    try:
                        new_val = typ(data[key])
                        if getattr(settings, key) != new_val:
                            object.__setattr__(settings, key, new_val)
                            changed.append(key)
                    except Exception:
                        pass
        except Exception:
            pass

    # Sync Ollama client
    ollama.base_url    = settings.ollama_base_url
    ollama.chat_model  = settings.ollama_chat_model
    ollama.embed_model = settings.ollama_embed_model

    if "line_channel_secret" in changed:
        app_state.reload_parser(settings.line_channel_secret)

    logger.info("Hot reload: updated %s", changed)
    return {"ok": True, "changed": changed}


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.get("/api/sessions")
async def get_sessions():
    return {"sessions": conversation_manager.get_all_info(), "count": conversation_manager.active_sessions}


@router.delete("/api/sessions")
async def clear_sessions():
    conversation_manager.clear_all()
    return {"ok": True}


# ── Broadcast ─────────────────────────────────────────────────────────────────

@router.post("/api/broadcast")
async def broadcast(data: dict):
    user_id = data.get("user_id", "").strip()
    message = data.get("message", "").strip()
    if not user_id or not message:
        raise HTTPException(400, "user_id และ message ต้องไม่ว่าง")
    config = Configuration(access_token=settings.line_channel_access_token)
    line_api = MessagingApi(ApiClient(config))
    try:
        line_api.push_message(PushMessageRequest(to=user_id, messages=[TextMessage(text=message)]))
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Documents ─────────────────────────────────────────────────────────────────

@router.get("/api/documents")
async def list_documents():
    if not DATA_DIR.exists():
        return {"documents": []}
    files = sorted(list(DATA_DIR.glob("**/*.md")) + list(DATA_DIR.glob("**/*.txt")))
    return {
        "documents": [
            {"name": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime}
            for f in files
        ]
    }


@router.get("/api/documents/{filename}/content")
async def document_content(filename: str):
    if "/" in filename or ".." in filename:
        raise HTTPException(400, "ชื่อไฟล์ไม่ถูกต้อง")
    target = DATA_DIR / filename
    if not target.exists():
        raise HTTPException(404, "ไม่พบไฟล์")
    return {"content": target.read_text(encoding="utf-8"), "name": filename}


@router.post("/api/documents")
async def upload_document(file: UploadFile = File(...)):
    safe_name = Path(file.filename).name
    if not safe_name or "/" in safe_name or ".." in safe_name:
        raise HTTPException(400, "ชื่อไฟล์ไม่ถูกต้อง")
    if not (safe_name.endswith(".md") or safe_name.endswith(".txt")):
        raise HTTPException(400, "รองรับเฉพาะ .md และ .txt")
    DATA_DIR.mkdir(exist_ok=True)
    content = await file.read()
    (DATA_DIR / safe_name).write_bytes(content)
    return {"ok": True, "name": safe_name, "size": len(content)}


@router.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    if "/" in filename or ".." in filename:
        raise HTTPException(400, "ชื่อไฟล์ไม่ถูกต้อง")
    target = DATA_DIR / filename
    if not target.exists():
        raise HTTPException(404, "ไม่พบไฟล์")
    target.unlink()
    return {"ok": True}


@router.post("/api/rebuild-index")
async def rebuild_index():
    try:
        n = await rag.reset_and_rebuild()
        return {"ok": True, "chunks": n}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── RAG Search Test ───────────────────────────────────────────────────────────

@router.post("/api/rag-search")
async def rag_search(data: dict):
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(400, "query ไม่สามารถว่างได้")
    if not rag.is_ready:
        raise HTTPException(503, "RAG index ยังไม่พร้อม")
    results = await rag.retrieve_with_scores(query)
    return {"results": results, "query": query}


# ── System Prompt ─────────────────────────────────────────────────────────────

@router.get("/api/prompt")
async def get_prompt():
    if CUSTOM_PROMPT.exists():
        return {"prompt": CUSTOM_PROMPT.read_text(encoding="utf-8"), "custom": True}
    return {"prompt": _SYSTEM_TEMPLATE, "custom": False}


@router.post("/api/prompt")
async def save_prompt(data: dict):
    text = data.get("prompt", "").strip()
    if not text:
        raise HTTPException(400, "Prompt ไม่สามารถว่างได้")
    CUSTOM_PROMPT.write_text(text, encoding="utf-8")
    return {"ok": True}


@router.delete("/api/prompt")
async def reset_prompt():
    if CUSTOM_PROMPT.exists():
        CUSTOM_PROMPT.unlink()
    return {"ok": True}


# ── Welcome Message ───────────────────────────────────────────────────────────

@router.get("/api/welcome")
async def get_welcome():
    if CUSTOM_WELCOME.exists():
        return {"message": CUSTOM_WELCOME.read_text(encoding="utf-8"), "custom": True}
    return {"message": _DEFAULT_WELCOME, "custom": False}


@router.post("/api/welcome")
async def save_welcome(data: dict):
    text = data.get("message", "").strip()
    if not text:
        raise HTTPException(400, "Welcome message ไม่สามารถว่างได้")
    CUSTOM_WELCOME.write_text(text, encoding="utf-8")
    return {"ok": True}


@router.delete("/api/welcome")
async def reset_welcome():
    if CUSTOM_WELCOME.exists():
        CUSTOM_WELCOME.unlink()
    return {"ok": True}


# ── Quick Topics ──────────────────────────────────────────────────────────────

@router.get("/api/quick-topics")
async def get_quick_topics_api():
    if CUSTOM_TOPICS.exists():
        return {"topics": json.loads(CUSTOM_TOPICS.read_text(encoding="utf-8")), "custom": True}
    return {"topics": [{"label": l, "text": t} for l, t in _DEFAULT_QUICK_TOPICS], "custom": False}


@router.post("/api/quick-topics")
async def save_quick_topics(data: dict):
    CUSTOM_TOPICS.write_text(
        json.dumps(data.get("topics", []), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"ok": True}


# ── Ollama Model Management ───────────────────────────────────────────────────

@router.get("/api/ollama-models")
async def list_ollama_models():
    models = await ollama.list_models()
    return {"models": models}


async def _do_pull_model(model: str):
    try:
        logger.info("Starting model pull: %s", model)
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{settings.ollama_base_url}/api/pull",
                json={"name": model, "stream": False},
            )
            resp.raise_for_status()
        logger.info("Model pull completed: %s", model)
    except Exception as e:
        logger.error("Model pull failed for %s: %s", model, e)


@router.post("/api/ollama-pull")
async def pull_model(data: dict, background_tasks: BackgroundTasks):
    model = data.get("model", "").strip()
    if not model:
        raise HTTPException(400, "model ห้ามว่าง")
    background_tasks.add_task(_do_pull_model, model)
    return {"ok": True, "model": model, "message": f"เริ่ม pull {model} แล้ว ดูความคืบหน้าใน Logs"}


# ── Test Chat ─────────────────────────────────────────────────────────────────

class TestChatPayload(BaseModel):
    message: str
    use_rag: bool = True
    history: list[dict] = []


@router.post("/api/test-chat")
async def test_chat(req: TestChatPayload):
    context = ""
    if req.use_rag and rag.is_ready:
        try:
            context = await rag.retrieve_as_context(req.message)
        except Exception:
            pass
    from bot.prompts import build_system_prompt
    system_prompt = build_system_prompt(context or None)
    messages = req.history[-12:] + [{"role": "user", "content": req.message}]
    try:
        answer = await ollama.chat(messages=messages, system_prompt=system_prompt)
        return {"answer": answer, "context_used": bool(context)}
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Logs ──────────────────────────────────────────────────────────────────────

@router.get("/api/logs")
async def get_logs(lines: int = 120):
    if not LOG_FILE.exists():
        return {"logs": [], "message": "ยังไม่มี log file"}
    all_lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = all_lines[-lines:] if len(all_lines) > lines else all_lines
    parsed = []
    for line in tail:
        level = "INFO"
        if "[ERROR]" in line:
            level = "ERROR"
        elif "[WARNING]" in line or "[WARN]" in line:
            level = "WARNING"
        elif "[DEBUG]" in line:
            level = "DEBUG"
        parsed.append({"text": line, "level": level})
    return {"logs": parsed}
