"""
Admin Database — SQLite persistence for AI providers, bot tokens, and agent configurations.

Tables:
  - ai_providers:     AI service providers (OpenAI, Anthropic, Google, etc.)
  - bot_tokens:       Telegram bot tokens (one per bot)
  - agent_configs:    Per-agent configuration (model, temperature, prompt, etc.)

All data is stored in admin.db alongside the application.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from utils.logger import setup_logger

logger = setup_logger("admin_db")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "admin.db")


def _get_db_path() -> str:
    return os.path.abspath(DB_PATH)


@contextmanager
def get_conn():
    """Context manager that yields a connection with row_factory = Row."""
    conn = sqlite3.connect(_get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS ai_providers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                provider_type TEXT  NOT NULL DEFAULT 'openai_compatible',
                base_url    TEXT    NOT NULL,
                api_key     TEXT    NOT NULL DEFAULT '',
                description TEXT    DEFAULT '',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS bot_tokens (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                token       TEXT    NOT NULL,
                bot_username TEXT   DEFAULT '',
                description TEXT    DEFAULT '',
                is_active   INTEGER NOT NULL DEFAULT 1,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS agent_configs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name      TEXT    NOT NULL UNIQUE,
                display_name    TEXT    NOT NULL DEFAULT '',
                icon            TEXT    DEFAULT '🤖',
                description     TEXT    DEFAULT '',
                provider_id     INTEGER,
                model           TEXT    NOT NULL DEFAULT '',
                temperature     REAL    NOT NULL DEFAULT 0.7,
                system_prompt   TEXT    DEFAULT '',
                max_tokens      INTEGER DEFAULT 4096,
                is_active       INTEGER NOT NULL DEFAULT 1,
                extra_config    TEXT    DEFAULT '{}',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (provider_id) REFERENCES ai_providers(id) ON DELETE SET NULL
            );
        """)
    logger.info("Admin database initialized.")


# ── Helper ───────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


def _rows_to_list(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# AI PROVIDERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_providers() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_providers ORDER BY id"
        ).fetchall()
        return _rows_to_list(rows)


def get_active_providers() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ai_providers WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        return _rows_to_list(rows)


def get_provider(provider_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM ai_providers WHERE id = ?", (provider_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def add_provider(
    name: str,
    base_url: str,
    api_key: str = "",
    provider_type: str = "openai_compatible",
    description: str = "",
    is_active: bool = True,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO ai_providers (name, provider_type, base_url, api_key, description, is_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, provider_type, base_url, api_key, description, int(is_active)),
        )
        return cur.lastrowid


def update_provider(provider_id: int, **fields) -> bool:
    allowed = {"name", "provider_type", "base_url", "api_key", "description", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = datetime('now')"
    values = list(updates.values()) + [provider_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE ai_providers SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


def delete_provider(provider_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM ai_providers WHERE id = ?", (provider_id,)
        )
        return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════════════════════
# BOT TOKENS
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_tokens() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bot_tokens ORDER BY id"
        ).fetchall()
        return _rows_to_list(rows)


def get_active_tokens() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bot_tokens WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        return _rows_to_list(rows)


def get_token(token_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM bot_tokens WHERE id = ?", (token_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def add_token(
    name: str,
    token: str,
    bot_username: str = "",
    description: str = "",
    is_active: bool = True,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO bot_tokens (name, token, bot_username, description, is_active)
               VALUES (?, ?, ?, ?, ?)""",
            (name, token, bot_username, description, int(is_active)),
        )
        return cur.lastrowid


def update_token(token_id: int, **fields) -> bool:
    allowed = {"name", "token", "bot_username", "description", "is_active"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = datetime('now')"
    values = list(updates.values()) + [token_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE bot_tokens SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


def delete_token(token_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM bot_tokens WHERE id = ?", (token_id,)
        )
        return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CONFIGS
# ═══════════════════════════════════════════════════════════════════════════════

def get_all_agent_configs() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ac.*, ap.name AS provider_name, ap.base_url AS provider_url
               FROM agent_configs ac
               LEFT JOIN ai_providers ap ON ac.provider_id = ap.id
               ORDER BY ac.id"""
        ).fetchall()
        return _rows_to_list(rows)


def get_active_agent_configs() -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT ac.*, ap.name AS provider_name, ap.base_url AS provider_url
               FROM agent_configs ac
               LEFT JOIN ai_providers ap ON ac.provider_id = ap.id
               WHERE ac.is_active = 1
               ORDER BY ac.id"""
        ).fetchall()
        return _rows_to_list(rows)


def get_agent_config(agent_config_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT ac.*, ap.name AS provider_name, ap.base_url AS provider_url
               FROM agent_configs ac
               LEFT JOIN ai_providers ap ON ac.provider_id = ap.id
               WHERE ac.id = ?""",
            (agent_config_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def get_agent_config_by_name(agent_name: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT ac.*, ap.name AS provider_name, ap.base_url AS provider_url,
                      ap.api_key AS provider_api_key
               FROM agent_configs ac
               LEFT JOIN ai_providers ap ON ac.provider_id = ap.id
               WHERE ac.agent_name = ?""",
            (agent_name,),
        ).fetchone()
        return _row_to_dict(row) if row else None


def upsert_agent_config(
    agent_name: str,
    display_name: str = "",
    icon: str = "🤖",
    description: str = "",
    provider_id: Optional[int] = None,
    model: str = "",
    temperature: float = 0.7,
    system_prompt: str = "",
    max_tokens: int = 4096,
    is_active: bool = True,
    extra_config: str = "{}",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO agent_configs
                   (agent_name, display_name, icon, description, provider_id, model,
                    temperature, system_prompt, max_tokens, is_active, extra_config)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(agent_name) DO UPDATE SET
                   display_name  = excluded.display_name,
                   icon          = excluded.icon,
                   description   = excluded.description,
                   provider_id   = excluded.provider_id,
                   model         = excluded.model,
                   temperature   = excluded.temperature,
                   system_prompt = excluded.system_prompt,
                   max_tokens    = excluded.max_tokens,
                   is_active     = excluded.is_active,
                   extra_config  = excluded.extra_config,
                   updated_at    = datetime('now')""",
            (
                agent_name, display_name, icon, description, provider_id, model,
                temperature, system_prompt, max_tokens, int(is_active), extra_config,
            ),
        )
        return cur.lastrowid


def update_agent_config(config_id: int, **fields) -> bool:
    allowed = {
        "agent_name", "display_name", "icon", "description",
        "provider_id", "model", "temperature", "system_prompt",
        "max_tokens", "is_active", "extra_config",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
    if "temperature" in updates:
        updates["temperature"] = float(updates["temperature"])
    if "max_tokens" in updates:
        updates["max_tokens"] = int(updates["max_tokens"])
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    set_clause += ", updated_at = datetime('now')"
    values = list(updates.values()) + [config_id]
    with get_conn() as conn:
        cur = conn.execute(
            f"UPDATE agent_configs SET {set_clause} WHERE id = ?", values
        )
        return cur.rowcount > 0


def delete_agent_config(config_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM agent_configs WHERE id = ?", (config_id,)
        )
        return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT / IMPORT
# ═══════════════════════════════════════════════════════════════════════════════

def export_all() -> Dict[str, Any]:
    """Export all admin data as a JSON-serializable dict (for backup)."""
    return {
        "version": 1,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ai_providers": get_all_providers(),
        "bot_tokens": get_all_tokens(),
        "agent_configs": [
            {k: v for k, v in c.items() if k not in ("provider_name", "provider_url", "provider_api_key")}
            for c in get_all_agent_configs()
        ],
    }


def import_all(data: Dict[str, Any], overwrite: bool = False) -> Dict[str, int]:
    """Import admin data from a JSON dict."""
    counts = {"providers": 0, "tokens": 0, "agent_configs": 0}
    with get_conn() as conn:
        if overwrite:
            conn.execute("DELETE FROM agent_configs")
            conn.execute("DELETE FROM bot_tokens")
            conn.execute("DELETE FROM ai_providers")

        for p in data.get("ai_providers", []):
            conn.execute(
                """INSERT OR IGNORE INTO ai_providers
                   (name, provider_type, base_url, api_key, description, is_active)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (p["name"], p.get("provider_type", "openai_compatible"), p["base_url"],
                 p.get("api_key", ""), p.get("description", ""), p.get("is_active", 1)),
            )
            counts["providers"] += 1

        for t in data.get("bot_tokens", []):
            conn.execute(
                """INSERT OR IGNORE INTO bot_tokens
                   (name, token, bot_username, description, is_active)
                   VALUES (?, ?, ?, ?, ?)""",
                (t["name"], t["token"], t.get("bot_username", ""),
                 t.get("description", ""), t.get("is_active", 1)),
            )
            counts["tokens"] += 1

        for a in data.get("agent_configs", []):
            conn.execute(
                """INSERT OR IGNORE INTO agent_configs
                   (agent_name, display_name, icon, description, provider_id, model,
                    temperature, system_prompt, max_tokens, is_active, extra_config)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (a["agent_name"], a.get("display_name", ""), a.get("icon", "🤖"),
                 a.get("description", ""), a.get("provider_id"),
                 a.get("model", ""), a.get("temperature", 0.7),
                 a.get("system_prompt", ""), a.get("max_tokens", 4096),
                 a.get("is_active", 1), a.get("extra_config", "{}")),
            )
            counts["agent_configs"] += 1

    logger.info(f"Imported: {counts}")
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════════════

def get_admin_stats() -> Dict[str, int]:
    """Return quick counts for dashboard display."""
    with get_conn() as conn:
        providers_total = conn.execute("SELECT COUNT(*) FROM ai_providers").fetchone()[0]
        providers_active = conn.execute("SELECT COUNT(*) FROM ai_providers WHERE is_active=1").fetchone()[0]
        tokens_total = conn.execute("SELECT COUNT(*) FROM bot_tokens").fetchone()[0]
        tokens_active = conn.execute("SELECT COUNT(*) FROM bot_tokens WHERE is_active=1").fetchone()[0]
        agents_total = conn.execute("SELECT COUNT(*) FROM agent_configs").fetchone()[0]
        agents_active = conn.execute("SELECT COUNT(*) FROM agent_configs WHERE is_active=1").fetchone()[0]
    return {
        "providers_total": providers_total,
        "providers_active": providers_active,
        "tokens_total": tokens_total,
        "tokens_active": tokens_active,
        "agents_total": agents_total,
        "agents_active": agents_active,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DEFAULT PROVIDERS (run once)
# ═══════════════════════════════════════════════════════════════════════════════

def seed_defaults() -> None:
    """Insert default AI providers if the table is empty."""
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM ai_providers").fetchone()[0]
        if count > 0:
            return
        defaults = [
            ("Bynara Router", "openai_compatible", "https://router.bynara.id/v1", "", "Default Bynara router"),
            ("OpenAI", "openai_compatible", "https://api.openai.com/v1", "", "OpenAI GPT models"),
            ("Anthropic (Claude)", "openai_compatible", "https://api.anthropic.com/v1", "", "Anthropic Claude API"),
            ("Google Gemini", "openai_compatible", "https://generativelanguage.googleapis.com/v1beta", "", "Google Gemini API"),
            ("Groq", "openai_compatible", "https://api.groq.com/openai/v1", "", "Groq ultra-fast inference"),
            ("Together AI", "openai_compatible", "https://api.together.xyz/v1", "", "Together AI inference"),
            ("OpenRouter", "openai_compatible", "https://openrouter.ai/api/v1", "", "OpenRouter multi-provider"),
        ]
        conn.executemany(
            """INSERT INTO ai_providers (name, provider_type, base_url, api_key, description)
               VALUES (?, ?, ?, ?, ?)""",
            defaults,
        )
    logger.info("Default AI providers seeded.")