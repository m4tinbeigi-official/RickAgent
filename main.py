"""
AI Multi-Agent Telegram Bot  v2.0
════════════════════════════════════
سیستم چندعاملی هوش مصنوعی روی تلگرام + پنل مدیریت وب

نصب و راهاندازی:
  1. pip install -r requirements.txt
  2. cp .env.example .env  و مقادیر را پر کنید
  3. python3 main.py

پنل مدیریت:
  http://localhost:8080   (یا هر پورتی که در PANEL_PORT تنظیم کردهاید)
"""
import asyncio
import sys

# ── 1. بارگذاری متغیرهای محیطی قبل از هر import دیگری ────────────────────
from dotenv import load_dotenv
load_dotenv()

from utils.config import Config
from utils.logger import setup_logger
import logging

# ── 2. تنظیم سطح لاگ ──────────────────────────────────────────────────────
logging.getLogger().setLevel(getattr(logging, Config.LOG_LEVEL, logging.INFO))
logger = setup_logger("main")


def _print_banner() -> None:
    print(
        "\n"
        "╔══════════════════════════════════════════════════════╗\n"
        "║     AI Multi-Agent Telegram Bot  v2.0               ║\n"
        "║     سیستم چندعاملی هوش مصنوعی — تلگرام             ║\n"
        "╠══════════════════════════════════════════════════════╣\n"
        "║  LangGraph  •  LangSmith  •  Admin Panel             ║\n"
        "║  Web Panel  •  Real-time Stats  •  Activity Feed     ║\n"
        "╚══════════════════════════════════════════════════════╝\n"
    )


async def main() -> None:
    _print_banner()

    # ── اعتبارسنجی تنظیمات ────────────────────────────────────────────────
    logger.info("🔧 بررسی تنظیمات ...")
    try:
        Config.validate()
        logger.info("✅ تنظیمات معتبر است.")
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    # ── مقداردهی اولیه پایگاه داده ادمین ─────────────────────────────────
    logger.info("🗄️  راه‌اندازی پایگاه داده ادمین …")
    from core.admin_db import init_db, seed_defaults
    init_db()
    seed_defaults()   # inserts default AI providers if the table is empty
    logger.info("✅ پایگاه داده ادمین آماده است.")

    # ── فعالسازی LangSmith (باید قبل از import langchain باشد) ───────────
    Config.setup_langsmith()
    if Config.LANGSMITH_TRACING:
        logger.info(
            f"📊 LangSmith فعال — پروژه: {Config.LANGSMITH_PROJECT}"
        )

    # ── import بعد از تنظیم LangSmith ────────────────────────────────────
    from telegram_bot.bot import TelegramBot
    from web_panel.server import start_panel

    logger.info(
        f"🌐 پنل مدیریت روی http://{Config.PANEL_HOST}:{Config.PANEL_PORT} راهاندازی میشود ..."
    )

    try:
        bot = TelegramBot()
        await asyncio.gather(
            bot.run(),
            start_panel(),
        )
    except KeyboardInterrupt:
        logger.info("👋 خداحافظ!")
    except Exception as exc:
        logger.exception(f"❌ خطای بحرانی: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())