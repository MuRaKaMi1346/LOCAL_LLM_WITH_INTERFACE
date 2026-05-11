import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Force UTF-8 on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# File logging
Path("logs").mkdir(exist_ok=True)
_file_handler = RotatingFileHandler(
    "logs/bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logging.getLogger().addHandler(_file_handler)
logger = logging.getLogger(__name__)

class _SuppressHealthCheck(logging.Filter):
    def filter(self, record):
        return "/health" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(_SuppressHealthCheck())
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, status
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent, UnfollowEvent

from admin.router import router as admin_router
from bot.handler import handle_follow, handle_text_message, handle_unfollow
from config import settings
from services.ollama import ollama
from services.rag import rag
from state import app_state

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s LINE Bot...", settings.faculty_name)

    healthy = await ollama.ensure_running()
    if not healthy:
        logger.warning(
            "Ollama not reachable at %s — chat will fail until Ollama starts",
            settings.ollama_base_url,
        )
    else:
        models = await ollama.list_models()
        for m in (settings.ollama_chat_model, settings.ollama_embed_model):
            if not await ollama.model_available(m):
                logger.warning("Model '%s' not in Ollama — run: ollama pull %s", m, m)
        logger.info(
            "Ollama OK | chat=%s | embed=%s | available=%s",
            settings.ollama_chat_model,
            settings.ollama_embed_model,
            models,
        )
        try:
            n = await rag.build_index()
            logger.info("RAG index ready — %d chunks", n)
        except Exception as exc:
            logger.error("RAG index build failed: %s", exc)

    yield

    await ollama.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title=f"{settings.faculty_name} LINE Bot",
    description="LINE Bot + Ollama + RAG",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(admin_router)


async def _dispatch(event) -> None:
    try:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            await handle_text_message(event)
        elif isinstance(event, FollowEvent):
            await handle_follow(event)
        elif isinstance(event, UnfollowEvent):
            await handle_unfollow(event)
    except Exception as exc:
        logger.error("Error handling %s: %s", type(event).__name__, exc)


@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(..., alias="X-Line-Signature"),
):
    body = (await request.body()).decode("utf-8")
    try:
        events = app_state.get_parser(settings.line_channel_secret).parse(body, x_line_signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    for event in events:
        background_tasks.add_task(_dispatch, event)
    return {"status": "ok"}


@app.get("/health")
async def health():
    ollama_ok = await ollama.is_healthy()
    chunk_count = rag.collection.count() if rag.collection else 0
    return {
        "status": "ok" if ollama_ok else "degraded",
        "bot_enabled": app_state.bot_enabled,
        "ollama": {"healthy": ollama_ok, "model": settings.ollama_chat_model},
        "rag": {"ready": rag.is_ready, "chunks": chunk_count},
    }


@app.get("/")
async def root():
    return {
        "service": f"{settings.faculty_name} LINE Bot",
        "version": "2.0.0",
        "admin": "http://localhost:8000/admin",
    }
