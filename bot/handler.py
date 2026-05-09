import logging
import re

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
    UnfollowEvent,
)

from bot.prompts import (
    build_system_prompt,
    get_quick_topics,
    get_welcome_message,
    RESET_KEYWORDS,
    HELP_KEYWORDS,
)
from bot.sessions import conversation_manager
from config import settings
from services.ollama import ollama
from services.rag import rag
from state import app_state

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text)            # __bold__
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)   # ## headers
    text = re.sub(r'^\s*[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)  # --- ***
    text = re.sub(r'\*{1,3}', '', text)                 # stray * left over
    text = re.sub(r'\n{3,}', '\n\n', text)              # collapse blank lines
    return text.strip()


def _line_api() -> MessagingApi:
    config = Configuration(access_token=settings.line_channel_access_token)
    return MessagingApi(ApiClient(config))


def _quick_reply_menu() -> QuickReply:
    items = [
        QuickReplyItem(action=MessageAction(label=label, text=text))
        for label, text in get_quick_topics()
    ]
    return QuickReply(items=items)


async def handle_text_message(event: MessageEvent) -> None:
    user_id: str = event.source.user_id
    reply_token: str = event.reply_token
    user_text: str = event.message.text.strip()

    if not reply_token:
        return

    if not app_state.bot_enabled:
        await _reply(reply_token, "🔧 ขณะนี้บอทปิดให้บริการชั่วคราว\nกรุณาลองใหม่อีกครั้งในภายหลังครับ")
        return

    app_state.record_message()

    if user_text.lower() in RESET_KEYWORDS:
        conversation_manager.clear(user_id)
        await _reply(reply_token, "ล้างประวัติการสนทนาแล้วครับ 🗑️ เริ่มใหม่ได้เลย!")
        return

    if user_text.lower() in HELP_KEYWORDS:
        await _reply(reply_token, get_welcome_message(), quick_reply=_quick_reply_menu())
        return

    # Show loading indicator
    try:
        _line_api().show_loading_animation(
            ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=60)
        )
    except Exception as exc:
        logger.warning("Loading indicator failed: %s", exc)

    # RAG context
    context = ""
    if rag.is_ready:
        try:
            context = await rag.retrieve_as_context(user_text)
        except Exception as exc:
            logger.warning("RAG retrieval failed: %s", exc)

    # Build and call
    session = conversation_manager.get_or_create(user_id)
    session.add_user(user_text)
    system_prompt = build_system_prompt(context or None)
    messages = session.get_messages()

    try:
        answer = await ollama.chat(messages=messages, system_prompt=system_prompt)
    except ConnectionError as exc:
        answer = str(exc) + "\n\nกรุณาลองใหม่อีกครั้งในภายหลังครับ 🙏"
    except Exception as exc:
        logger.error("Ollama error for user %s: %s", user_id, exc)
        answer = "ขออภัยครับ เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"

    answer = _strip_markdown(answer)
    session.add_assistant(answer)
    await _reply(reply_token, answer, quick_reply=_quick_reply_menu())


async def handle_follow(event: FollowEvent) -> None:
    if not event.reply_token:
        return
    await _reply(event.reply_token, get_welcome_message(), quick_reply=_quick_reply_menu())


async def handle_unfollow(event: UnfollowEvent) -> None:
    conversation_manager.clear(event.source.user_id)
    logger.info("User %s unfollowed — session cleared", event.source.user_id)


async def _reply(reply_token: str, text: str, quick_reply: QuickReply | None = None) -> None:
    msg = TextMessage(text=text, quick_reply=quick_reply)
    api = _line_api()
    try:
        api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[msg])
        )
    except Exception as exc:
        logger.error("LINE reply failed: %s", exc)
