<div align="center">

# 🤖 AgentRick — AI Multi-Agent Telegram Bot

**A production-ready multi-agent AI system for Telegram, built with LangGraph.**  
Drop a Python file into `agents/` — it's live. No registration, no restart, no config changes.

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.6%2B-orange)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Telegram](https://img.shields.io/badge/python--telegram--bot-22%2B-blue?logo=telegram)](https://python-telegram-bot.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[فارسی 🇮🇷](#-راهنمای-فارسی) · [Quick Start](#-quick-start) · [Architecture](#-architecture) · [Adding Agents](#-adding-a-new-agent-30-seconds)

</div>

---

## ✨ What makes this different

| Feature | Details |
|---------|---------|
| **Zero-registration agents** | Drop a `.py` file into `agents/` — auto-discovered on next run |
| **LangGraph orchestration** | Supervisor picks the right team of agents per request |
| **Any OpenAI-compatible API** | Bynara, OpenAI, Groq, Together, Anthropic, custom endpoints |
| **Runtime provider switch** | `/setprovider` in Telegram — no restart needed |
| **Persian web panel** | RTL dashboard (Vazirmatn font) with live SSE activity feed |
| **Rate limit handling** | Detects 429s, tells users exactly when limits reset |
| **Token usage tracking** | Per-agent input/output token counts in stats |
| **Python 3.9+** | No bleeding-edge syntax, works on almost any server |

---

## 🚀 Quick Start

**Option A — Smart installer (recommended)**
```bash
git clone https://github.com/YOUR_USERNAME/AgentRick.git
cd AgentRick
python3 install.py
```
The installer picks your AI provider, tests your API key live, configures Telegram, and writes `.env` automatically.

> **Free API key:** Sign up at [router.bynara.id/register?ref=NMAP6F9D](https://router.bynara.id/register?ref=NMAP6F9D) for **7 million free tokens**.

**Option B — Manual**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in BYNARA_API_KEY and TELEGRAM_BOT_TOKEN
python3 main.py
```

Both the Telegram bot and web panel start together:
- **Bot** — ready for messages
- **Panel** → http://localhost:8080

---

## 🏗 Architecture

```
User message
    │
    ▼
Supervisor (LangGraph) ──analyzes──► picks agent team
    │
    ├──► Writer ✍️
    ├──► Analyst 📊
    ├──► Researcher 🔬
    ├──► Planner 📋
    └──► Critic 🔍
    │
    ▼
Supervisor synthesizes all outputs ──► Final response to Telegram
```

```
AgentRick/
├── agents/          # Drop new agents here — auto-discovered
│   ├── base_agent.py
│   ├── supervisor.py
│   ├── writer.py
│   ├── analyst.py
│   └── ...
├── graphs/          # LangGraph StateGraph wiring
├── telegram_bot/    # Bot handlers, commands, rate limiting
├── web_panel/       # FastAPI + SSE + Persian RTL dashboard
├── core/admin_db.py # SQLite CRUD for providers/tokens/configs
├── services/        # LLM factory (any OpenAI-compatible endpoint)
├── utils/           # Config, logging, stats, memory, agent loader
├── install.py       # Smart interactive installer
└── main.py          # Entry point — runs bot + panel concurrently
```

---

## ⚡ Adding a New Agent (30 seconds)

Create one file. That's it.

```python
# agents/translator.py
from agents.base_agent import BaseAgent

class TranslatorAgent(BaseAgent):
    NAME        = "translator"
    ROLE        = "Translator"
    DESCRIPTION = "Translates text between languages"   # Supervisor reads this
    ICON        = "🌐"
    TEMPERATURE = 0.3
    SYSTEM_PROMPT = "You are an expert translator. Preserve tone and nuance."
```

The agent is auto-discovered on the next run. The Supervisor learns about it from `DESCRIPTION` and includes it in routing decisions.

You can also override `SYSTEM_PROMPT`, `TEMPERATURE`, and model from the admin panel — no code change needed.

---

## 🤖 Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + team introduction |
| `/agents` | List active agents with models and run counts |
| `/stats` | System stats — uptime, token usage, top agents |
| `/panel` | Web panel link |
| `/setprovider` | Browse and switch AI providers at runtime |
| `/setprovider 2` | Switch to provider #2 directly |
| `/clear` | Clear conversation history for this chat |
| `/status` | Current system configuration |

---

## 🌐 Web Panel API

```
GET  /api/stats                   System metrics + token usage
GET  /api/agents                  Active agents with dynamic config
GET  /api/conversations           Last 60 conversations
GET  /api/activity-stream         SSE live activity feed

POST /api/admin/reload-agents     Apply config changes without restart

GET|POST|PUT|DELETE /api/admin/providers
GET|POST|PUT|DELETE /api/admin/tokens
GET|POST|PUT|DELETE /api/admin/agent-configs
```

---

## 🔌 Supported AI Providers

Any OpenAI-compatible endpoint works. Pre-configured in the installer:

| Provider | Notes |
|----------|-------|
| [Bynara Router](https://router.bynara.id/register?ref=NMAP6F9D) | **7M free tokens** · multi-model router |
| OpenAI | GPT-4o, GPT-4o-mini, o1 |
| Groq | Ultra-fast · free tier |
| Together AI | Open-source models |
| OpenRouter | 200+ models |
| Anthropic | Claude family |
| Google Gemini | Gemini family |
| Custom | Any OpenAI-compatible URL |

Switch providers at runtime with `/setprovider` — no restart needed.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BYNARA_API_KEY` | — | **Required.** API key |
| `BYNARA_BASE_URL` | `https://router.bynara.id/v1` | Provider base URL |
| `BYNARA_MODEL` | `gpt-4o-mini` | Default model |
| `TELEGRAM_BOT_TOKEN` | — | **Required.** From @BotFather |
| `LANGSMITH_API_KEY` | — | Optional tracing |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith |
| `PANEL_PORT` | `8080` | Web panel port |
| `RATE_LIMIT_SECONDS` | `3` | Per-chat cooldown |
| `MAX_HISTORY` | `6` | Conversation turns to remember |
| `LLM_TIMEOUT` | `60` | Per-call timeout (seconds) |

---

## 🤝 Contributing

Contributions are welcome. The easiest way to contribute is to **add a new agent** — see [CONTRIBUTING.md](.github/CONTRIBUTING.md).

---

---

# 🇮🇷 راهنمای فارسی

یک سیستم چندعاملی (Multi-Agent) پیشرفته روی تلگرام با پنل مدیریت فارسی.

## درباره پروژه

هر پیام کاربر توسط یک Agent ناظر تحلیل می‌شود و بهترین ترکیب از Agentهای متخصص انتخاب می‌شود:

```
کاربر → ناظر (Supervisor) → [Writer, Analyst, Researcher, Planner, Critic] → پاسخ نهایی
```

## ویژگی‌های کلیدی

- **تیم چندعاملی** — ۵ Agent متخصص + Supervisor با LangGraph
- **کشف خودکار Agent** — هر فایل Python در `agents/` بدون نیاز به رجیستری بارگذاری می‌شود
- **پنل مدیریت فارسی** — داشبورد زنده با فونت وزیرمتن و SSE real-time
- **پشتیبانی از همه Provider ها** — Bynara، OpenAI، Groq، Together، Anthropic و ...
- **تغییر Provider در لحظه** — `/setprovider` بدون نیاز به ریستارت
- **مدیریت محدودیت** — شناسایی خطای ۴۲۹، اعلام زمان دقیق بازگشایی
- **پیکربندی کاملاً داینامیک** — System Prompt، دما، مدل همه از پنل ادمین قابل تغییر

## نصب سریع

```bash
git clone https://github.com/YOUR_USERNAME/AgentRick.git
cd AgentRick
python3 install.py
```

> **کلید API رایگان (۷ میلیون توکن):**  
> [router.bynara.id/register?ref=NMAP6F9D](https://router.bynara.id/register?ref=NMAP6F9D)

## افزودن Agent جدید (۳۰ ثانیه)

```python
# agents/my_agent.py
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    NAME        = "my_agent"
    ROLE        = "نقش من"
    DESCRIPTION = "توضیح کوتاه برای Supervisor"
    ICON        = "🛠️"
    TEMPERATURE = 0.7
    SYSTEM_PROMPT = "You are a specialist in ..."
```

Agent بعد از اجرای بعدی به صورت خودکار کشف و بارگذاری می‌شود.

## Agentها

| Agent | نقش | مناسب برای |
|-------|-----|-----------|
| ✍️ Writer | نویسنده خلاق | محتوا، ایمیل، داستان |
| 🔍 Critic | منتقد | بازبینی و بهبود متن |
| 📊 Analyst | تحلیلگر | مقایسه، ارزیابی، داده |
| 📋 Planner | برنامه‌ریز | roadmap، مراحل کار |
| 🔬 Researcher | محقق | تحقیق، اطلاعات |
| 🧠 Supervisor | ناظر | انتخاب تیم + ترکیب پاسخ |

## مشکلات رایج

**ربات پاسخ نمی‌دهد در گروه** → `BOT_RESPOND_TO_ALL=true` یا ربات را منشن کنید

**خطای BYNARA_API_KEY** → فایل `.env` را بررسی کنید یا `python3 install.py` اجرا کنید

**LangSmith خطا می‌دهد** → `LANGSMITH_TRACING=false` قرار دهید

**پنل باز نمی‌شود** → پورت ۸۰۸۰ آزاد باشد
