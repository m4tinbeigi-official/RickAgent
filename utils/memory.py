"""
Conversation Memory — per-chat message history.

Stores the last MAX_HISTORY exchanges (user + assistant turns) in memory.
No database required; data lives for the duration of the bot process.

Usage:
    from utils.memory import memory
    memory.add(chat_id, "user", "سلام!")
    memory.add(chat_id, "assistant", "سلام! چطور می‌تونم کمک کنم؟")
    history = memory.get_formatted(chat_id)
    memory.clear(chat_id)
"""
from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Tuple

from utils.config import Config


class ConversationMemory:
    """Thread-safe (GIL) in-memory store for multi-chat conversation history."""

    def __init__(self, max_turns: int) -> None:
        self._max = max_turns
        # chat_id → deque of (role, content)
        self._store: Dict[int, Deque[Tuple[str, str]]] = {}

    def add(self, chat_id: int, role: str, content: str) -> None:
        """
        Append a turn.

        Args:
            chat_id: Telegram chat/group ID.
            role:    "user" or "assistant".
            content: Message text (will be truncated to 2000 chars in storage).
        """
        if chat_id not in self._store:
            self._store[chat_id] = deque(maxlen=self._max * 2)  # 2 turns per exchange
        self._store[chat_id].append((role, content[:2000]))

    def get(self, chat_id: int) -> List[Tuple[str, str]]:
        """Return all stored turns as a list of (role, content) tuples."""
        return list(self._store.get(chat_id, []))

    def get_formatted(self, chat_id: int) -> str:
        """
        Return history as a formatted Persian string for injection into Agent context.
        Returns empty string if no history exists.
        """
        turns = self.get(chat_id)
        if not turns:
            return ""

        lines: list[str] = []
        for role, content in turns:
            label = "👤 کاربر" if role == "user" else "🤖 دستیار"
            lines.append(f"{label}: {content}")

        return "تاریخچه مکالمه:\n" + "\n".join(lines)

    def clear(self, chat_id: int) -> bool:
        """Delete history for a chat. Returns True if history existed."""
        existed = chat_id in self._store
        self._store.pop(chat_id, None)
        return existed

    def count(self, chat_id: int) -> int:
        """Number of stored turns for a chat."""
        return len(self._store.get(chat_id, []))

    def stats(self) -> Dict[str, int]:
        """Return a dict of chat_id → turn_count for all active chats."""
        return {cid: len(q) for cid, q in self._store.items()}


# Singleton — import this everywhere
memory = ConversationMemory(max_turns=Config.MAX_HISTORY)
