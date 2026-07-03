"""
Telegram Bot — wires together Application, commands, and the agent handler.
"""
from __future__ import annotations

import asyncio
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler as TGMessageHandler,
    ContextTypes,
    filters,
)

from graphs.multi_agent_graph import build_graph
from telegram_bot.handlers import AgentMessageHandler
from utils.agent_loader import discover_agents
from utils.config import Config
from utils.logger import setup_logger
from utils.memory import memory
from utils.stats import stats

logger = setup_logger(__name__)


# ── command handlers ──────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "کاربر"
    agents = discover_agents()
    agent_lines = "\n".join(
        f"• {a.icon} *{a.role}* — {a.description}"
        for a in agents.values()
    )
    await update.message.reply_text(
        f"👋 سلام {name}!\n\n"
        "🤖 *سیستم چندعاملی هوش مصنوعی*\n\n"
        "این سیستم از چند Agent متخصص تشکیل شده که با هم همکاری می‌کنند:\n\n"
        f"{agent_lines}\n\n"
        "🧠 Agent ناظر درخواست تو را تحلیل کرده و بهترین تیم را انتخاب می‌کند.\n\n"
        "💡 دستورات: /help\n"
        "🚀 فقط پیامت را بنویس!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 *راهنمای استفاده*\n\n"
        "*چت خصوصی:*\n"
        "هر پیامی بفرستید پردازش می‌شود.\n\n"
        "*گروه:*\n"
        "• بات را منشن کنید: `@نام_ربات سوال شما`\n"
        "• یا به پیام ربات ریپلای کنید.\n\n"
        "*دستورات:*\n"
        "/start — خوش‌آمدگویی\n"
        "/agents — لیست Agentهای فعال با مدل‌هایشان\n"
        "/stats — آمار کلی سیستم\n"
        "/panel — لینک پنل مدیریت\n"
        "/setprovider — انتخاب ارائه‌دهنده هوش مصنوعی\n"
        "/clear — پاک کردن تاریخچه مکالمه\n"
        "/status — وضعیت سیستم برای این چت\n"
        "/help — این راهنما\n\n"
        "*نمونه درخواست‌ها:*\n"
        "— «یک ایمیل حرفه‌ای برایم بنویس»\n"
        "— «این متن را نقد و بهبود بده»\n"
        "— «بازار رمزارز را تحلیل کن»\n"
        "— «برنامه یادگیری پایتون را بریز»\n"
        "— «درباره هوش مصنوعی تحقیق کن»\n",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_agents(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the list of currently loaded agents with their assigned models."""
    agents = discover_agents()

    lines = ["🤖 *Agentهای فعال:*\n"]
    for name, agent in agents.items():
        run_count = stats.agent_runs.get(name, 0)
        lines.append(
            f"{agent.icon} *{agent.role}* (`{name}`)\n"
            f"   🔮 مدل: `{agent.model}`\n"
            f"   ▶ اجراها: {run_count}\n"
            f"   _{agent.description}_\n"
        )
    lines.append(f"🧠 *ناظر:* `{Config.BYNARA_SUPERVISOR_MODEL}`")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show global system statistics."""
    s = stats.to_dict()
    agent_runs = s.get("agent_runs", {})

    top_agents = sorted(agent_runs.items(), key=lambda x: x[1], reverse=True)
    agent_lines = "\n".join(
        f"   {i+1}. `{name}` — {count} اجرا"
        for i, (name, count) in enumerate(top_agents[:5])
    ) or "   _هنوز هیچ Agentی اجرا نشده_"

    await update.message.reply_text(
        "📊 *آمار کلی سیستم*\n\n"
        f"📨 پیام‌های پردازش‌شده: `{s['total_messages']}`\n"
        f"⚡ میانگین زمان پاسخ: `{s['avg_response_time']}s`\n"
        f"⚠️ خطاها: `{s['total_errors']}`\n"
        f"⏱ آپتایم: `{s['uptime_human']}`\n"
        f"🗓 شروع از: `{s['start_time']}`\n\n"
        f"*🏆 پرکارترین Agentها:*\n{agent_lines}",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_setprovider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Let users browse and switch AI providers stored in admin DB."""
    try:
        from core.admin_db import get_active_providers
        providers = get_active_providers()
    except Exception:
        providers = []

    if not providers:
        await update.message.reply_text(
            "⚠️ هیچ ارائه‌دهنده‌ای در پایگاه داده ثبت نشده.\n"
            "از پنل ادمین (تب مدیریت AI) ارائه‌دهنده اضافه کنید.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Show provider list
    lines = ["🌐 *ارائه‌دهندگان هوش مصنوعی موجود:*\n"]
    for i, p in enumerate(providers, 1):
        current = "✅ " if p["base_url"] == Config.BYNARA_BASE_URL else "   "
        lines.append(f"{current}{i}. *{p['name']}*\n   `{p['base_url']}`\n")

    lines.append(
        "\n💡 برای انتخاب، عدد مربوطه را با دستور زیر بفرست:\n"
        "`/setprovider 2`  (مثال: انتخاب ارائه‌دهنده ۲)"
    )

    # If argument given, apply it
    if context.args:
        arg = context.args[0]
        if arg.isdigit() and 1 <= int(arg) <= len(providers):
            chosen = providers[int(arg) - 1]
            # Temporarily override in env (only affects this runtime session)
            os.environ["BYNARA_BASE_URL"]  = chosen["base_url"]
            if chosen.get("api_key"):
                os.environ["BYNARA_API_KEY"] = chosen["api_key"]
            # Reload config + agents
            import importlib, utils.config as _cfg
            importlib.reload(_cfg)
            from utils.agent_loader import reset_cache
            reset_cache()
            await update.message.reply_text(
                f"✅ *ارائه‌دهنده تغییر کرد!*\n\n"
                f"🌐 *{chosen['name']}*\n"
                f"`{chosen['base_url']}`\n\n"
                "⚠️ این تغییر تا ریستارت ربات فعال است.\n"
                "برای تغییر دائمی، `.env` یا پنل ادمین را ویرایش کنید.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the web panel link."""
    host = Config.PANEL_HOST
    # Replace 0.0.0.0 with localhost for display purposes
    display_host = "localhost" if host in ("0.0.0.0", "") else host
    port = Config.PANEL_PORT
    url = f"http://{display_host}:{port}"

    await update.message.reply_text(
        "🌐 *پنل مدیریت*\n\n"
        f"آدرس پنل:\n`{url}`\n\n"
        "در پنل می‌توانید:\n"
        "• 📊 آمار و فعالیت زنده ربات را ببینید\n"
        "• 💬 تاریخچه مکالمات را مرور کنید\n"
        "• ⚙️ تنظیمات سیستم را بررسی کنید\n"
        "• 🔧 پرووایدرها و Agentها را مدیریت کنید",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear conversation history for this chat."""
    chat_id = update.effective_chat.id
    existed = memory.clear(chat_id)
    if existed:
        await update.message.reply_text(
            "🗑️ تاریخچه مکالمه این چت پاک شد.\n"
            "می‌توانید یک مکالمه جدید شروع کنید."
        )
    else:
        await update.message.reply_text("ℹ️ تاریخچه‌ای برای پاک کردن وجود نداشت.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show system status and current configuration."""
    chat_id = update.effective_chat.id
    turn_count = memory.count(chat_id)

    await update.message.reply_text(
        "📊 *وضعیت سیستم*\n\n"
        f"✅ سیستم در حال اجرا\n"
        f"🔮 مدل Agent: `{Config.BYNARA_MODEL}`\n"
        f"🧠 مدل ناظر: `{Config.BYNARA_SUPERVISOR_MODEL}`\n"
        f"🌐 API: `{Config.BYNARA_BASE_URL}`\n"
        f"📝 LangSmith: {'✅ فعال' if Config.LANGSMITH_TRACING else '❌ غیرفعال'}\n"
        f"⏱ Timeout: `{Config.LLM_TIMEOUT}s`\n"
        f"💬 تاریخچه این چت: {turn_count} پیام\n"
        f"🔢 حداکثر تاریخچه: {Config.MAX_HISTORY} تبادل\n",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── TelegramBot class ─────────────────────────────────────────────────────

class TelegramBot:
    """Main bot class — discovers agents, builds graph, starts polling."""

    def __init__(self) -> None:
        self._agents = discover_agents()
        self._graph = build_graph(self._agents)
        self._msg_handler = AgentMessageHandler(self._graph)

    async def run(self) -> None:
        """Build the Application and start long-polling."""
        logger.info("🤖 راه‌اندازی Telegram Bot …")

        app = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Commands
        app.add_handler(CommandHandler("start",       cmd_start))
        app.add_handler(CommandHandler("help",        cmd_help))
        app.add_handler(CommandHandler("agents",      cmd_agents))
        app.add_handler(CommandHandler("stats",       cmd_stats))
        app.add_handler(CommandHandler("panel",       cmd_panel))
        app.add_handler(CommandHandler("clear",       cmd_clear))
        app.add_handler(CommandHandler("status",      cmd_status))
        app.add_handler(CommandHandler("setprovider", cmd_setprovider))

        # Text messages (non-commands)
        app.add_handler(
            TGMessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._msg_handler.handle,
            )
        )

        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        logger.info(
            f"🟢 ربات فعال است | {len(self._agents)} Agent بارگذاری شد. "
            "Ctrl+C برای توقف."
        )

        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            logger.info("🛑 درخواست توقف دریافت شد …")
        finally:
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
