"""
BaseAgent — abstract base class every agent must inherit.

To create a new agent
─────────────────────
1. Create  agents/my_agent.py
2. Define a class that inherits BaseAgent:

    class MyAgent(BaseAgent):
        NAME        = "my_agent"
        ROLE        = "نقش من"
        DESCRIPTION = "کارهایی که انجام می‌دهم"   ← shown to Supervisor
        ICON        = "🛠️"
        TEMPERATURE = 0.7
        SYSTEM_PROMPT = "You are …"

3. Done — agent_loader.py discovers it automatically, no registration needed.
"""
from __future__ import annotations

import os
import time
from abc import ABC
from typing import Dict

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from services.llm_service import create_llm
from utils.config import Config
from utils.logger import setup_logger
from utils.stats import stats


# ── Rate-limit detection helpers ──────────────────────────────────────────

def _is_rate_limit(exc: Exception) -> bool:
    """Return True for HTTP 429 / rate-limit errors from any provider."""
    name = type(exc).__name__
    msg  = str(exc).lower()
    return (
        name == "RateLimitError"
        or "429" in str(exc)
        or "rate limit" in msg
        or "ratelimit" in msg
        or "too many requests" in msg
        or "quota" in msg
    )


def _parse_retry_after(exc: Exception) -> int:
    """
    Extract how many seconds to wait from a rate-limit error.
    Falls back to 60 if not parseable.
    """
    # 1. Named attribute (openai SDK)
    retry = getattr(exc, "retry_after", None)
    if retry:
        return int(retry)

    # 2. Response headers
    resp = getattr(exc, "response", None)
    if resp:
        headers = getattr(resp, "headers", {}) or {}
        if headers.get("retry-after"):
            return int(headers["retry-after"])
        if headers.get("Retry-After"):
            return int(headers["Retry-After"])

    # 3. Parse error message text
    msg = str(exc)
    patterns = [
        r"retry.?after[:\s]+(\d+)",
        r"try again in[:\s]+(\d+)\s*s",
        r"available in[:\s]+(\d+)\s*s",
        r"wait[:\s]+(\d+)\s*s",
        r"reset in[:\s]+(\d+)\s*s",
        r"(\d+)\s*seconds?",
    ]
    for p in patterns:
        m = re.search(p, msg, re.IGNORECASE)
        if m:
            return int(m.group(1))

    return 60   # safe default


class BaseAgent(ABC):
    """Abstract base for all specialist agents."""

    # ── subclasses override these ──────────────────────────────────────────
    NAME: str = "base"
    ROLE: str = "Agent"
    DESCRIPTION: str = "یک Agent عمومی"
    ICON: str = "🤖"
    TEMPERATURE: float = 0.7
    SYSTEM_PROMPT: str = "You are a helpful AI assistant."
    # Optional: set MODEL = "gpt-4o" in a subclass to hard-pin a model.
    # Otherwise the env var AGENT_MODEL_<NAME> is checked, then BYNARA_MODEL.
    MODEL: str | None = None

    def __init__(self) -> None:
        self.name = self.__class__.NAME
        self.model = self._resolve_model()

        # ── Dynamic config: class defaults → overridden by admin_db ──────────
        db = self._load_db_config()

        # Each instance attribute is DB value if non-empty, else class default
        self.role        = db.get("display_name") or self.__class__.ROLE
        self.description = db.get("description")  or self.__class__.DESCRIPTION
        self.icon        = db.get("icon")          or self.__class__.ICON
        self.system_prompt = db.get("system_prompt") or self.__class__.SYSTEM_PROMPT
        self.temperature = (
            db["temperature"]
            if db.get("temperature") is not None
            else self.__class__.TEMPERATURE
        )
        self.max_tokens  = db.get("max_tokens") or 4096
        self.is_active   = bool(db.get("is_active", 1))

        # LLM — create_llm also checks DB for provider/model/temp overrides
        self.llm = create_llm(
            temperature=self.temperature,
            model=self.model,
            agent_name=self.name,
        )
        self.logger = setup_logger(f"agent.{self.name}")
        self.logger.debug(f"{self.icon} {self.role} → model: {self.model}")

    def _load_db_config(self) -> dict:
        """Load per-agent config from admin_db. Returns {} on any error."""
        try:
            from core.admin_db import get_agent_config_by_name
            return get_agent_config_by_name(self.name) or {}
        except Exception:
            return {}

    def _resolve_model(self) -> str:
        """
        Model priority (highest → lowest):
          1. CLASS-level MODEL attribute (hard-coded in subclass)
          2. Env var  AGENT_MODEL_<NAME>   (e.g. AGENT_MODEL_WRITER=gpt-4o)
          3. admin_db agent_configs.model
          4. Global   BYNARA_MODEL         (fallback default)
        """
        if self.__class__.MODEL:
            return self.__class__.MODEL
        env_key = f"AGENT_MODEL_{self.__class__.NAME.upper()}"
        env_val = os.getenv(env_key)
        if env_val:
            return env_val
        # Check DB (loaded separately in __init__ but needed here before __init__ finishes)
        try:
            from core.admin_db import get_agent_config_by_name
            cfg = get_agent_config_by_name(self.__class__.NAME)
            if cfg and cfg.get("model"):
                return cfg["model"]
        except Exception:
            pass
        return Config.BYNARA_MODEL

    # ── LangGraph node ────────────────────────────────────────────────────

    def run_node(self, state: Dict) -> Dict:
        """
        Called by LangGraph as a graph node.
        Returns a *partial* state update (only keys this agent changes).
        """
        self.logger.info(f"{self.icon} {self.role} در حال اجرا … (model: {self.model})")
        stats.log_agent_start(self.name, self.icon, self.model)
        t0 = time.time()

        try:
            context = self._build_context(state)
            messages = [
                SystemMessage(content=self.system_prompt),   # dynamic — from DB or class default
                HumanMessage(content=context),
            ]
            response = self.llm.invoke(messages)
            output: str = response.content
            duration = time.time() - t0

            # Track token usage if the response includes it
            usage = getattr(response, "usage_metadata", None) or {}
            if usage:
                stats.log_token_usage(
                    self.name,
                    usage.get("input_tokens", 0),
                    usage.get("output_tokens", 0),
                )

            self.logger.info(f"  ✅ {self.role} تمام شد ({len(output)} کاراکتر، {duration:.1f}s)")
            stats.log_agent_done(self.name, self.icon, duration)

        except Exception as exc:
            duration = time.time() - t0
            # Rate limit errors must propagate so the handler can send a specific message
            if _is_rate_limit(exc):
                retry = _parse_retry_after(exc)
                self.logger.warning(
                    f"  🚫 {self.role} محدودیت سرویس — retry after {retry}s"
                )
                stats.log_rate_limit(self.name, Config.BYNARA_BASE_URL, retry)
                # Attach retry info as an attribute for the handler to read
                exc.__retry_after__ = retry
                raise
            self.logger.error(f"  ❌ {self.role} خطا: {exc}")
            stats.log_agent_done(self.name, self.icon, duration)
            output = f"[خطا در {self.role}: {exc}]"

        return {
            "agent_outputs": {**state.get("agent_outputs", {}), self.name: output},
            "messages": [AIMessage(content=output, name=self.name)],
        }

    # ── helpers ───────────────────────────────────────────────────────────

    def _build_context(self, state: Dict) -> str:
        """
        Assemble the full context string for this agent:
          - Conversation history (last N turns)
          - User's current message
          - Outputs of agents that already ran
        """
        parts: list[str] = []

        # 1. Conversation history (so agents are aware of prior messages)
        history: list[dict] = state.get("conversation_history", [])
        if history:
            history_lines = []
            for turn in history:
                label = "👤 کاربر" if turn.get("role") == "user" else "🤖 دستیار"
                history_lines.append(f"{label}: {turn.get('content', '')}")
            parts.append("── تاریخچه مکالمه ──\n" + "\n".join(history_lines))
            parts.append("─" * 40)

        # 2. Current user message
        parts.append(f"درخواست فعلی کاربر:\n{state.get('user_message', '')}")

        # 3. Outputs of agents that already ran before this one
        prev = state.get("agent_outputs", {})
        if prev:
            parts.append("\n" + "─" * 40)
            parts.append("خروجی‌های سایر اعضای تیم (قبل از تو):")
            for agent_name, agent_output in prev.items():
                parts.append(f"\n📌 {agent_name}:\n{agent_output}")

        return "\n".join(parts)
