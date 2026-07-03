"""
Telegram message handlers.

Key features
────────────
• Persistent typing indicator (refreshed every 4 s via background task)
• Per-chat conversation memory (last N turns)
• Per-chat rate limiting (min N seconds between requests)
• Graceful Markdown → plain-text fallback for Telegram send
• Runs the synchronous LangGraph graph in a thread-pool executor
"""
from __future__ import annotations

import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Dict

from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from graphs.state import initial_state
from utils.config import Config
from utils.logger import setup_logger
from utils.memory import memory
from utils.stats import stats

logger = setup_logger(__name__)

# One thread-pool for all synchronous graph invocations
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent-worker")

# Telegram message length limit
_MAX_LEN = 4096

# Per-chat rate-limit tracker  { chat_id: last_processed_timestamp }
_last_processed: Dict[int, float] = {}


# ── background typing indicator ──────────────────────────────────────────

async def _keep_typing(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    stop: asyncio.Event,
) -> None:
    """Send 'typing…' action every 4 seconds until `stop` is set."""
    while not stop.is_set():
        try:
            await context.bot.send_chat_action(
                chat_id=chat_id, action=ChatAction.TYPING
            )
        except Exception:
            pass
        try:
            await asyncio.wait_for(stop.wait(), timeout=4.0)
        except asyncio.TimeoutError:
            pass


# ── main handler class ────────────────────────────────────────────────────

class AgentMessageHandler:
    """Wraps the compiled graph and exposes a Telegram-compatible handler."""

    def __init__(self, graph) -> None:
        self._graph = graph

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Process an incoming Telegram text message end-to-end."""
        if not update.message or not update.message.text:
            return

        msg: Message = update.message
        chat_id: int = msg.chat_id
        chat_type: str = msg.chat.type
        raw_text: str = msg.text.strip()

        bot_info = await context.bot.get_me()
        bot_username: str = bot_info.username or ""

        # ── gate checks ───────────────────────────────────────────────────

        if not _should_respond(msg, chat_type, bot_username):
            return

        if _is_rate_limited(chat_id):
            await msg.reply_text(
                "⏳ لطفاً چند ثانیه صبر کنید و دوباره امتحان کنید."
            )
            return

        # ── clean input ───────────────────────────────────────────────────

        clean_text = _strip_mention(raw_text, bot_username)
        if not clean_text:
            await msg.reply_text("👋 سلام! پیام یا سوالت را بنویس.")
            return

        logger.info(
            f"📩 [{chat_type}] از {msg.from_user.username or msg.from_user.id}: "
            f"{clean_text[:80]}…"
        )
        stats.log_message(chat_id, msg.from_user.username, clean_text)

        # ── persistent typing + processing message ────────────────────────

        t_start = time.time()
        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(
            _keep_typing(context, chat_id, stop_typing)
        )

        processing_msg = await msg.reply_text(
            "⏳ *تیم هوش مصنوعی در حال بررسی درخواست شما …*",
            parse_mode=ParseMode.MARKDOWN,
        )

        try:
            # ── build state ───────────────────────────────────────────────

            history_turns = memory.get(chat_id)
            conversation_history = [
                {"role": role, "content": content}
                for role, content in history_turns
            ]

            state = initial_state(
                user_message=clean_text,
                conversation_history=conversation_history,
                metadata={
                    "user_id": msg.from_user.id,
                    "username": msg.from_user.username,
                    "first_name": msg.from_user.first_name,
                    "chat_id": chat_id,
                    "chat_type": chat_type,
                },
            )

            # ── run graph (blocking → thread pool) ───────────────────────

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _executor,
                lambda: self._graph.invoke(state),
            )

            final: str = result.get("final_response") or ""
            agents_used: list[str] = result.get("agents_to_run", [])
            reasoning: str = result.get("supervisor_reasoning", "")

            if not final:
                final = "❌ نتوانستم پاسخی تولید کنم. لطفاً دوباره تلاش کنید."

            # ── update conversation memory ────────────────────────────────

            memory.add(chat_id, "user", clean_text)
            memory.add(chat_id, "assistant", final[:1500])  # trim for storage

            # ── format and send ───────────────────────────────────────────

            response_text = final + _build_footer(agents_used)

            await processing_msg.delete()
            await _send_chunked(msg, response_text)

            elapsed = time.time() - t_start
            stats.log_response_sent(elapsed, agents_used)
            stats.log_conversation(
                chat_id,
                msg.from_user.username,
                clean_text,
                final,
                agents_used,
                elapsed,
            )

            logger.info(f"✅ پاسخ ارسال شد | Agents: {agents_used} | دلیل: {reasoning}")

        except Exception as exc:
            logger.error(f"❌ خطای پردازش: {exc}", exc_info=True)
            stats.log_error(str(exc))

            # ── Rate limit: send a specific, user-friendly message ─────────
            retry_after = getattr(exc, "__retry_after__", None)
            if retry_after is None:
                # Also check common indicators directly in the exception
                exc_str = str(exc).lower()
                if (
                    "429" in str(exc)
                    or "rate limit" in exc_str
                    or "too many requests" in exc_str
                    or "quota" in exc_str
                ):
                    retry_after = 60

            if retry_after is not None:
                reset_time = (datetime.now() + timedelta(seconds=int(retry_after))).strftime("%H:%M:%S")
                err = (
                    "🚫 *محدودیت سرویس هوش مصنوعی*\n\n"
                    f"ارائه‌دهنده فعلی به حداکثر درخواست مجاز رسیده است.\n\n"
                    f"⏱ *بازگشایی تقریبی:* `{reset_time}`\n"
                    f"⏳ *زمان انتظار:* `{retry_after}` ثانیه\n\n"
                    "💡 *راهکارها:*\n"
                    "• چند دقیقه صبر کنید و دوباره امتحان کنید\n"
                    "• با `/setprovider` ارائه‌دهنده دیگری انتخاب کنید\n"
                    "• از [Bynara](https://router.bynara.id/register?ref=NMAP6F9D) "
                    "کلید رایگان با ۷ میلیون توکن بگیرید"
                )
            else:
                err = (
                    f"❌ خطایی رخ داد:\n`{str(exc)[:300]}`\n\n"
                    "لطفاً دوباره تلاش کنید."
                )
            try:
                await processing_msg.edit_text(err, parse_mode=ParseMode.MARKDOWN)
            except Exception:
                await processing_msg.edit_text(
                    re.sub(r"[_*`\[\]()]", "", err)
                )

        finally:
            stop_typing.set()
            typing_task.cancel()
            _last_processed[chat_id] = time.time()


# ── helper functions ─────────────────────────────────────────────────────

def _should_respond(msg: Message, chat_type: str, bot_username: str) -> bool:
    """Return True if the bot should process this message."""
    if chat_type == "private":
        return True
    if Config.BOT_RESPOND_TO_ALL:
        return True
    if bot_username and f"@{bot_username}" in (msg.text or ""):
        return True
    if (
        msg.reply_to_message
        and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.username == bot_username
    ):
        return True
    return False


def _is_rate_limited(chat_id: int) -> bool:
    """Return True if this chat sent a message too recently."""
    last = _last_processed.get(chat_id, 0.0)
    return (time.time() - last) < Config.RATE_LIMIT_SECONDS


def _strip_mention(text: str, bot_username: str) -> str:
    """Remove @botname from message text."""
    if bot_username:
        text = re.sub(
            rf"@{re.escape(bot_username)}\s*", "", text, flags=re.IGNORECASE
        ).strip()
    return text


def _build_footer(agents_used: list[str]) -> str:
    """Small italicised footer listing which agents ran."""
    if not agents_used:
        return ""
    icons = {
        "writer": "✍️", "critic": "🔍",
        "analyst": "📊", "planner": "📋",
        "researcher": "🔬",
    }
    icon_str = " ".join(icons.get(a, "🤖") for a in agents_used)
    names = ", ".join(agents_used)
    return f"\n\n─────────────\n_{icon_str} {names}_"


async def _send_chunked(reply_to: Message, text: str) -> None:
    """Send text, splitting into ≤4096-char chunks when needed."""
    if len(text) <= _MAX_LEN:
        await _safe_reply(reply_to, text)
        return

    chunks: list[str] = []
    while text:
        if len(text) <= _MAX_LEN:
            chunks.append(text)
            break
        # Find the best split point
        split = _MAX_LEN
        for sep in ["\n\n", "\n", ". ", " "]:
            pos = text.rfind(sep, 0, _MAX_LEN)
            if pos != -1:
                split = pos + len(sep)
                break
        chunks.append(text[:split])
        text = text[split:].strip()

    for i, chunk in enumerate(chunks):
        await _safe_reply(reply_to, chunk)
        if i < len(chunks) - 1:
            await asyncio.sleep(0.3)


async def _safe_reply(msg: Message, text: str) -> None:
    """Reply with Markdown; silently fall back to plain text if parsing fails."""
    try:
        await msg.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        # Strip common Markdown symbols and send plain
        plain = re.sub(r"[_*`\[\]]", "", text)
        try:
            await msg.reply_text(plain)
        except Exception as exc:
            logger.error(f"Failed to send message: {exc}")
