"""
Stats & Activity Log — real-time telemetry for the web panel.

Thread-safe singleton. All agent nodes and the Telegram handler
call into this module to record what's happening.

Activity events are assigned a monotonically-increasing sequence number
so the SSE endpoint can reliably stream only NEW events to each client.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional


class StatsTracker:
    """
    Central metrics store.

    Fields (all thread-safe via a single lock):
        total_messages      Total Telegram messages processed.
        total_errors        Total errors encountered.
        agent_runs          name → total invocations.
        response_times      Last 500 end-to-end latencies (seconds).
        recent_conversations  Last 60 conversation records (deque).
        activity_deque      Last 600 activity events (deque, with seq).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq: int = 0                           # event sequence counter

        self.total_messages: int = 0
        self.total_errors: int = 0
        self.agent_runs: Dict[str, int] = {}
        self.response_times: List[float] = []        # trimmed at 500
        self.recent_conversations: deque = deque(maxlen=60)
        self.activity_deque: deque = deque(maxlen=600)
        self.start_time: float = time.time()

        # Token usage tracking
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0
        self.agent_tokens: Dict[str, Dict[str, int]] = {}   # name → {in, out}

        # Rate limit events (last 50)
        self.rate_limit_events: deque = deque(maxlen=50)

    # ── public log methods ────────────────────────────────────────────────

    def log_message(self, chat_id: int, username: Optional[str], text: str) -> None:
        with self._lock:
            self.total_messages += 1
        who = f"@{username}" if username else f"chat:{chat_id}"
        self._event("message", f"📩 پیام از {who}: {text[:60]}")

    def log_supervisor(self, agents_chosen: List[str], reasoning: str) -> None:
        flow = " → ".join(agents_chosen) if agents_chosen else "—"
        self._event("supervisor", f"🎯 ناظر انتخاب کرد: [{flow}]")

    def log_agent_start(self, agent_name: str, icon: str, model: str) -> None:
        with self._lock:
            self.agent_runs[agent_name] = self.agent_runs.get(agent_name, 0) + 1
        self._event("agent_start", f"{icon} {agent_name} شروع شد  ({model})")

    def log_agent_done(self, agent_name: str, icon: str, duration: float) -> None:
        self._event("agent_done", f"{icon} {agent_name} تمام شد  ({duration:.1f}s)")

    def log_response_sent(self, duration: float, agents: List[str]) -> None:
        with self._lock:
            self.response_times.append(duration)
            if len(self.response_times) > 500:
                self.response_times = self.response_times[-300:]
        names = ", ".join(agents) if agents else "—"
        self._event("response", f"✅ پاسخ ارسال شد  ({duration:.1f}s)  [{names}]")

    def log_conversation(
        self,
        chat_id: int,
        username: Optional[str],
        message: str,
        response: str,
        agents: List[str],
        duration: float,
    ) -> None:
        record = {
            "username": f"@{username}" if username else f"chat:{chat_id}",
            "chat_id": chat_id,
            "message": message[:200],
            "response": response[:600],
            "agents": agents,
            "duration": round(duration, 2),
            "time": _now_time(),
            "date": _now_date(),
        }
        with self._lock:
            self.recent_conversations.appendleft(record)

    def log_error(self, error: str) -> None:
        with self._lock:
            self.total_errors += 1
        self._event("error", f"❌ خطا: {str(error)[:120]}")

    def log_token_usage(
        self,
        agent_name: str,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        """Record token consumption for an agent invocation."""
        with self._lock:
            self.total_tokens_in  += tokens_in
            self.total_tokens_out += tokens_out
            rec = self.agent_tokens.setdefault(agent_name, {"in": 0, "out": 0})
            rec["in"]  += tokens_in
            rec["out"] += tokens_out

    def log_rate_limit(
        self,
        agent_name: str,
        provider: str,
        retry_after: int,
    ) -> None:
        """Record a rate-limit hit and emit an activity event."""
        event = {
            "agent": agent_name,
            "provider": provider,
            "retry_after": retry_after,
            "time": _now_time(),
        }
        with self._lock:
            self.total_errors += 1
            self.rate_limit_events.appendleft(event)
        self._event(
            "rate_limit",
            f"🚫 محدودیت سرویس | {provider} | retry after {retry_after}s",
        )

    # ── read methods ──────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            rt = self.response_times[-100:] if self.response_times else []
            avg_rt = sum(rt) / len(rt) if rt else 0.0
            uptime = int(time.time() - self.start_time)
            return {
                "total_messages":   self.total_messages,
                "total_errors":     self.total_errors,
                "agent_runs":       dict(self.agent_runs),
                "avg_response_time": round(avg_rt, 2),
                "uptime_seconds":   uptime,
                "uptime_human":     _fmt_uptime(uptime),
                "start_time":       datetime.fromtimestamp(self.start_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                # Token usage
                "total_tokens_in":  self.total_tokens_in,
                "total_tokens_out": self.total_tokens_out,
                "total_tokens":     self.total_tokens_in + self.total_tokens_out,
                "agent_tokens":     dict(self.agent_tokens),
                # Rate limits
                "rate_limit_hits":  len(self.rate_limit_events),
            }

    def conversations_list(self) -> List[Dict]:
        with self._lock:
            return list(self.recent_conversations)

    def activity_since(self, after_seq: int) -> List[Dict]:
        """Return all activity events with seq > after_seq."""
        with self._lock:
            return [e for e in self.activity_deque if e["seq"] > after_seq]

    # ── private ───────────────────────────────────────────────────────────

    def _event(self, event_type: str, message: str) -> None:
        with self._lock:
            self._seq += 1
            self.activity_deque.append(
                {
                    "seq": self._seq,
                    "type": event_type,
                    "message": message,
                    "time": _now_time(),
                }
            )


# ── helpers ───────────────────────────────────────────────────────────────

def _now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _fmt_uptime(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


# ── singleton ─────────────────────────────────────────────────────────────
stats = StatsTracker()
