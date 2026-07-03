"""
Supervisor Agent — the orchestrator of the multi-agent pipeline.

Two phases
──────────
1. analyze()    → reads the user message + conversation history,
                  picks which agents to run and in what order.
                  Uses Pydantic structured output for reliable JSON parsing.

2. synthesize() → after all agents have run, merges their outputs into
                  one coherent, polished final response.

The Supervisor is NOT auto-discovered by agent_loader (it's in _SKIP).
It is instantiated directly by build_graph() in graphs/multi_agent_graph.py.
"""
from __future__ import annotations

from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from services.llm_service import create_supervisor_llm
from utils.logger import setup_logger
from utils.stats import stats

logger = setup_logger("agent.supervisor")


# ── Pydantic schema for structured agent-selection output ─────────────────

class _Decision(BaseModel):
    agents: List[str] = Field(
        description=(
            "Ordered list of agent names to invoke. "
            "Use ONLY names from the provided valid list."
        )
    )
    reasoning: str = Field(
        description="One or two sentences explaining the choice (in user's language)."
    )


# ── System prompts ────────────────────────────────────────────────────────

_ANALYZE_TMPL = """\
تو ناظر (Supervisor) یک تیم هوش مصنوعی چندعاملی هستی.
وظیفه‌ات تحلیل درخواست کاربر و انتخاب بهترین ترکیب از Agentها برای پاسخ‌گویی است.

{history_block}

عوامل موجود در تیم:
{agents_block}

قوانین انتخاب:
- سوال ساده یا چت کوتاه     → یک Agent کافی است (معمولاً writer یا analyst)
- محتوای خلاقانه             → writer (و اگر نیاز به بازبینی دارد: writer → critic)
- تحلیل پیچیده               → analyst (و اگر برنامه لازم است: analyst → planner)
- تحقیق و اطلاعات            → researcher (و اگر نیاز به نوشتار دارد: researcher → writer)
- پروژه جامع                 → ترکیبی از چند Agent
- ترتیب مهم است: ابتدا سازندگان، سپس بررسی‌کننده (critic آخر از همه)

فقط از نام‌های معتبر زیر استفاده کن:
{valid_names}
"""

_SYNTHESIZE_PROMPT = """\
تو ناظر یک تیم هوش مصنوعی هستی. خروجی تمام اعضای تیم آماده است.
وظیفه‌ات ادغام این خروجی‌ها در یک پاسخ نهایی، منسجم، روان و کامل است.

اصول ترکیب:
۱. بهترین و ارزشمندترین نکات هر عامل را استخراج کن.
۲. تناقض‌ها را برطرف کرده و بهترین رویکرد را انتخاب کن.
۳. پاسخ نهایی باید مستقیماً به نیاز کاربر پاسخ دهد.
۴. متن باید روان، منسجم و بدون تکرار باشد.
۵. از نوشتن «طبق عامل X…» یا «بر اساس نظر Y…» خودداری کن.
۶. فقط پاسخ نهایی را بنویس — بدون توضیح فرآیند کار.
۷. در همان زبانی که کاربر نوشته پاسخ بده (فارسی یا انگلیسی).
"""


# ── SupervisorAgent ───────────────────────────────────────────────────────

class SupervisorAgent:
    """
    Orchestrates the multi-agent pipeline.

    Args:
        available_agents: dict[name → BaseAgent instance] from agent_loader.
    """

    def __init__(self, available_agents: Dict) -> None:
        self._agents: Dict = available_agents
        self.llm = create_supervisor_llm()
        self.llm_structured = self.llm.with_structured_output(_Decision)
        self.logger = logger

    # ── Phase 1: analyze ─────────────────────────────────────────────────

    def analyze(self, state: Dict) -> Dict:
        """Select which agents to run and in what order."""
        self.logger.info("🎯 Supervisor: تحلیل درخواست …")

        # Build history block if available
        history: list[dict] = state.get("conversation_history", [])
        if history:
            lines = []
            for turn in history:
                role = "کاربر" if turn.get("role") == "user" else "دستیار"
                lines.append(f"{role}: {turn.get('content', '')[:300]}")
            history_block = "تاریخچه مکالمه اخیر:\n" + "\n".join(lines) + "\n"
        else:
            history_block = ""

        agents_block = "\n".join(
            f"  • {name} ({agent.icon}): {agent.description}"
            for name, agent in self._agents.items()
        )
        valid_names = ", ".join(self._agents.keys())

        system_prompt = _ANALYZE_TMPL.format(
            history_block=history_block,
            agents_block=agents_block,
            valid_names=valid_names,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"درخواست کاربر:\n{state.get('user_message', '')}"),
        ]

        try:
            decision: _Decision = self.llm_structured.invoke(messages)
            chosen = [a for a in decision.agents if a in self._agents]
            if not chosen:
                chosen = [next(iter(self._agents))]
            reasoning = decision.reasoning

        except Exception as exc:
            self.logger.warning(f"Structured output failed ({exc}) — falling back.")
            # Fallback: pick the first agent
            chosen = [next(iter(self._agents))]
            reasoning = "پیش‌فرض (خطا در تحلیل)"

        self.logger.info(f"  ✅ Agents انتخاب شدند: {chosen}")
        self.logger.info(f"  💭 دلیل: {reasoning}")
        stats.log_supervisor(chosen, reasoning)

        return {
            "agents_to_run": chosen,
            "supervisor_reasoning": reasoning,
            "agent_outputs": {},
            "messages": [],
        }

    # ── Phase 2: synthesize ───────────────────────────────────────────────

    def synthesize(self, state: Dict) -> Dict:
        """Combine all agent outputs into one final answer."""
        self.logger.info("🔄 Supervisor: ترکیب خروجی‌ها …")

        outputs: Dict[str, str] = state.get("agent_outputs", {})

        if not outputs:
            return {"final_response": "❌ هیچ خروجی‌ای از Agentها دریافت نشد."}

        # Single-agent: no synthesis needed, use output directly
        if len(outputs) == 1:
            final = next(iter(outputs.values()))
            self.logger.info("  ✅ تک Agent — خروجی مستقیم استفاده شد.")
            return {"final_response": final}

        # Multi-agent: build context and synthesize
        parts = [f"درخواست اصلی کاربر:\n{state.get('user_message', '')}"]
        parts.append("\n" + "═" * 50)
        parts.append("خروجی تیم:")
        for name, out in outputs.items():
            agent = self._agents.get(name)
            icon = agent.icon if agent else "🤖"
            role = agent.role if agent else name
            parts.append(f"\n{icon} {role} ({name}):\n{out}")

        context = "\n".join(parts)
        messages = [
            SystemMessage(content=_SYNTHESIZE_PROMPT),
            HumanMessage(content=context),
        ]

        try:
            response = self.llm.invoke(messages)
            final = response.content
            self.logger.info(f"  ✅ ترکیب موفق ({len(final)} کاراکتر).")
        except Exception as exc:
            self.logger.error(f"  ❌ خطا در ترکیب: {exc}")
            final = list(outputs.values())[-1]   # Graceful fallback

        return {"final_response": final}
