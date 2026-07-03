"""
Shared state for the LangGraph multi-agent pipeline.

Every node reads from and returns *partial* updates to this TypedDict.
The `messages` field uses operator.add so lists are appended, not replaced.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import BaseMessage


class AgentState(dict):
    """
    Pipeline-wide state shared between all nodes.

    Fields
    ------
    user_message          Original text from the Telegram user.
    conversation_history  Recent chat turns [{role, content}] for context.
    messages              LangChain message objects (auto-appended via operator.add).
    agents_to_run         Ordered agent names chosen by Supervisor.
    agent_outputs         name → output text for each completed agent.
    supervisor_reasoning  Why those agents were chosen.
    final_response        The final answer to send back to Telegram.
    error                 Non-fatal error string.
    metadata              Chat/user context (chat_id, username, …).
    """

    user_message: str
    conversation_history: List[Dict[str, str]]
    messages: Annotated[List[BaseMessage], operator.add]
    agents_to_run: List[str]
    agent_outputs: Dict[str, str]
    supervisor_reasoning: Optional[str]
    final_response: Optional[str]
    error: Optional[str]
    metadata: Dict[str, Any]


def initial_state(
    user_message: str,
    conversation_history: List[Dict[str, str]] | None = None,
    metadata: Dict | None = None,
) -> AgentState:
    """Convenience constructor — returns a fully initialised state dict."""
    return AgentState(
        user_message=user_message,
        conversation_history=conversation_history or [],
        messages=[],
        agents_to_run=[],
        agent_outputs={},
        supervisor_reasoning=None,
        final_response=None,
        error=None,
        metadata=metadata or {},
    )
