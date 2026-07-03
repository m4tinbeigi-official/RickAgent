"""
Agent auto-discovery with instance caching.

Scans the agents/ directory and loads every class that:
  • inherits from BaseAgent
  • is NOT BaseAgent itself or SupervisorAgent

Adding a new agent = drop a .py file in agents/, no registration needed.

The singleton cache (_CACHE) means agents are instantiated once and reused
across all callers (Telegram handler, web panel API, etc.).
"""
import importlib
import inspect
import os
import threading
from typing import Dict, Optional

from utils.logger import setup_logger

logger = setup_logger(__name__)

# Files that live in agents/ but are NOT regular specialist agents
_SKIP = {"__init__.py", "base_agent.py", "supervisor.py"}

# Singleton cache: name → BaseAgent instance
_CACHE: Optional[Dict] = None
_CACHE_LOCK = threading.Lock()


def discover_agents(force_reload: bool = False) -> Dict[str, "BaseAgent"]:  # type: ignore[name-defined]
    """
    Auto-discover and instantiate all agent classes in the agents/ package.

    Results are cached in-process. Call with force_reload=True to rebuild
    the cache (e.g. if an agent file is hot-swapped at runtime).

    Returns:
        dict[agent_name -> agent_instance]
    """
    global _CACHE

    with _CACHE_LOCK:
        if _CACHE is not None and not force_reload:
            return _CACHE

        from agents.base_agent import BaseAgent  # local import avoids circulars

        found: Dict[str, BaseAgent] = {}

        agents_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "agents")
        )

        logger.info("🔍 اسکن پوشه agents …")

        for filename in sorted(os.listdir(agents_dir)):
            if not filename.endswith(".py") or filename in _SKIP:
                continue

            module_name = f"agents.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)

                for cls_name, cls in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(cls, BaseAgent)
                        and cls is not BaseAgent
                        and cls.__module__ == module_name
                    ):
                        instance: BaseAgent = cls()
                        found[instance.name] = instance
                        logger.info(
                            f"  ✅ Agent بارگذاری شد: {instance.ICON} {cls_name} → '{instance.name}'"
                        )

            except Exception as exc:
                logger.warning(f"  ⚠️  نتوانستم {filename} را بارگذاری کنم: {exc}")

        logger.info(f"📦 تعداد کل Agentها: {len(found)}")
        _CACHE = found
        return _CACHE


def reset_cache() -> None:
    """Invalidate the cached agent instances. Next call to discover_agents() will rebuild."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None
    logger.info("🔄 Agent cache invalidated.")
