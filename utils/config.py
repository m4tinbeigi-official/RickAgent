"""
Configuration management — all settings loaded from .env file.
No API keys are ever hardcoded here.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Central configuration class. Edit .env to change any setting."""

    # ── Bynara Router ─────────────────────────────────────────────────────────
    BYNARA_API_KEY: str = os.getenv("BYNARA_API_KEY", "")
    # Supports both BYNARA_BASE_URL and legacy BYNARA_API_BASE env vars
    BYNARA_BASE_URL: str = (
        os.getenv("BYNARA_BASE_URL")
        or os.getenv("BYNARA_API_BASE")
        or "https://router.bynara.id/v1"
    )
    BYNARA_MODEL: str = os.getenv("BYNARA_MODEL", "gpt-4o-mini")
    BYNARA_SUPERVISOR_MODEL: str = os.getenv(
        "BYNARA_SUPERVISOR_MODEL", os.getenv("BYNARA_MODEL", "gpt-4o-mini")
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = (
        os.getenv("TELEGRAM_BOT_TOKEN")
        or (os.getenv("TELEGRAM_BOT_TOKENS", "").split(",")[0].strip())
        or ""
    )
    BOT_RESPOND_TO_ALL: bool = os.getenv("BOT_RESPOND_TO_ALL", "false").lower() == "true"
    RATE_LIMIT_SECONDS: int = int(os.getenv("RATE_LIMIT_SECONDS", "3"))

    # ── LangSmith ─────────────────────────────────────────────────────────────
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "ai-telegram-agents")
    LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "true").lower() == "true"

    # ── Agent tuning ──────────────────────────────────────────────────────────
    AGENT_TEMPERATURE: float = float(os.getenv("AGENT_TEMPERATURE", "0.7"))
    SUPERVISOR_TEMPERATURE: float = float(os.getenv("SUPERVISOR_TEMPERATURE", "0.2"))
    # Hard timeout (seconds) for each LLM call — prevents the bot from hanging
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))

    # ── Conversation memory ───────────────────────────────────────────────────
    MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "6"))

    # ── Web Panel ─────────────────────────────────────────────────────────────
    PANEL_HOST: str = os.getenv("PANEL_HOST", "0.0.0.0")
    PANEL_PORT: int = int(os.getenv("PANEL_PORT", "8080"))
    # Optional password to protect the admin CRUD section (empty = no auth)
    PANEL_PASSWORD: str = os.getenv("PANEL_PASSWORD", "")

    # ── Misc ──────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    BOT_NAME: str = os.getenv("BOT_NAME", "AI Agent Team")

    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def validate(cls) -> None:
        """Raise ValueError if any required variable is missing."""
        missing: list[str] = []

        if not cls.BYNARA_API_KEY:
            missing.append("BYNARA_API_KEY")
        if not cls.TELEGRAM_BOT_TOKEN:
            missing.append("TELEGRAM_BOT_TOKEN  (یا TELEGRAM_BOT_TOKENS)")
        if cls.LANGSMITH_TRACING and not cls.LANGSMITH_API_KEY:
            missing.append("LANGSMITH_API_KEY  (یا LANGSMITH_TRACING=false قرار دهید)")

        if missing:
            hint = ""
            if "BYNARA_API_KEY" in missing:
                hint = (
                    "\n\n💡 کلید API رایگان (۷ میلیون توکن):"
                    "\n   https://router.bynara.id/register?ref=NMAP6F9D"
                )
            raise ValueError(
                "\n❌ متغیرهای محیطی زیر در فایل .env تنظیم نشده‌اند:\n"
                + "\n".join(f"   • {v}" for v in missing)
                + "\n\nفایل .env.example را کپی کرده و مقادیر را وارد کنید."
                + hint
            )

    @classmethod
    def setup_langsmith(cls) -> None:
        """Activate LangSmith tracing (must be called before LangChain is imported)."""
        if cls.LANGSMITH_TRACING and cls.LANGSMITH_API_KEY:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = cls.LANGSMITH_API_KEY
            os.environ["LANGCHAIN_PROJECT"] = cls.LANGSMITH_PROJECT
        else:
            os.environ["LANGCHAIN_TRACING_V2"] = "false"
