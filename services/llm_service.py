"""
LLM Service — single place that creates ChatOpenAI instances.

Supports two modes:
  1. Admin DB mode (default): reads provider/model/temperature from admin.db
     per agent name.
  2. Env-fallback mode: uses .env variables when no admin config exists.

Every Agent and the Supervisor call create_llm() or create_supervisor_llm()
from here, so changing the provider is a one-line edit in .env or via the admin panel.
"""
from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI

from utils.config import Config
from utils.logger import setup_logger

logger = setup_logger(__name__)


def _admin_db_available() -> bool:
    """Check if admin_db module and its table exist."""
    try:
        from core.admin_db import get_agent_config_by_name, get_provider
        return True
    except Exception:
        return False


def create_llm(
    temperature: float | None = None,
    model: str | None = None,
    agent_name: str | None = None,
) -> ChatOpenAI:
    """
    Build a ChatOpenAI client.

    Resolution order:
      1. If agent_name is given, look up admin DB for per-agent provider/model/temp.
      2. Explicit temperature/model arguments override everything.
      3. Fall back to .env config (BYNARA_* vars).

    Args:
        temperature: Override the default agent temperature.
        model:       Override the default model from .env.
        agent_name:  Agent name to look up admin DB config (e.g. "writer", "planner").

    Returns:
        Configured ChatOpenAI instance (OpenAI-compatible, any provider).
    """
    base_url = Config.BYNARA_BASE_URL
    api_key = Config.BYNARA_API_KEY
    _model = model or Config.BYNARA_MODEL
    _temp = temperature if temperature is not None else Config.AGENT_TEMPERATURE

    # Try admin DB for per-agent configuration
    if agent_name and _admin_db_available():
        try:
            from core.admin_db import get_agent_config_by_name, get_provider
            ac = get_agent_config_by_name(agent_name)
            if ac and ac.get("is_active"):
                # Use admin-configured provider
                if ac.get("provider_id"):
                    prov = get_provider(ac["provider_id"])
                    if prov and prov.get("is_active"):
                        base_url = prov["base_url"]
                        if prov.get("api_key"):
                            api_key = prov["api_key"]
                        logger.debug(f"Admin DB provider: {prov['name']} → {base_url}")

                # Override model/temperature from admin config (unless explicitly passed)
                if not model and ac.get("model"):
                    _model = ac["model"]
                if temperature is None and ac.get("temperature") is not None:
                    _temp = ac["temperature"]
        except Exception as e:
            logger.warning(f"Failed to read admin DB config for '{agent_name}': {e}")

    logger.debug(f"LLM → model={_model}, temp={_temp}, base={base_url}")

    return ChatOpenAI(
        model=_model,
        api_key=api_key,
        base_url=base_url,
        temperature=_temp,
        timeout=Config.LLM_TIMEOUT,
        max_retries=2,
    )


def create_supervisor_llm() -> ChatOpenAI:
    """
    Build the LLM used by the Supervisor.
    Uses BYNARA_SUPERVISOR_MODEL and a lower temperature for
    more deterministic agent-selection decisions.
    """
    return create_llm(
        temperature=Config.SUPERVISOR_TEMPERATURE,
        model=Config.BYNARA_SUPERVISOR_MODEL,
        agent_name="supervisor",
    )


def create_llm_from_provider(
    provider_id: int,
    model: str,
    temperature: float = 0.7,
) -> Optional[ChatOpenAI]:
    """
    Create an LLM from an explicit admin provider ID.
    Used for the connection-test endpoint.
    Returns None if provider not found.
    """
    if not _admin_db_available():
        return None
    try:
        from core.admin_db import get_provider
        prov = get_provider(provider_id)
        if not prov:
            return None
        return ChatOpenAI(
            model=model,
            api_key=prov.get("api_key", "test"),
            base_url=prov["base_url"],
            temperature=temperature,
            timeout=Config.LLM_TIMEOUT,
            max_retries=1,
        )
    except Exception as e:
        logger.error(f"create_llm_from_provider error: {e}")
        return None