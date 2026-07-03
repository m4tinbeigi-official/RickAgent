#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════╗
║      AI Multi-Agent Telegram Bot  —  Smart Installer  v2.0      ║
║      اینستالر هوشمند سیستم چندعاملی هوش مصنوعی — تلگرام        ║
╚══════════════════════════════════════════════════════════════════╝

راه‌اندازی / Run:
    python3 install.py
"""
from __future__ import annotations

import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── ANSI colors ────────────────────────────────────────────────────────────────
IS_WIN   = platform.system() == "Windows"
NO_COLOR = IS_WIN or not sys.stdout.isatty()

def _c(code: str) -> str:
    return "" if NO_COLOR else f"\033[{code}m"

RST  = _c("0")
BOLD = _c("1")
DIM  = _c("2")
GRN  = _c("92")
RED  = _c("91")
YEL  = _c("93")
BLU  = _c("94")
CYN  = _c("96")
MAG  = _c("95")
WHT  = _c("97")

# ── Root of the project ───────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()

# ── Paths ─────────────────────────────────────────────────────────────────────
VENV       = ROOT / ".venv"
REQS       = ROOT / "requirements.txt"
ENV_FILE   = ROOT / ".env"
ENV_SAMPLE = ROOT / ".env.example"

if IS_WIN:
    VENV_PYTHON = VENV / "Scripts" / "python.exe"
    VENV_PIP    = VENV / "Scripts" / "pip.exe"
else:
    VENV_PYTHON = VENV / "bin" / "python"
    VENV_PIP    = VENV / "bin" / "pip"


# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clear():
    os.system("cls" if IS_WIN else "clear")


def banner():
    clear()
    w = 70
    lines = [
        ("╔" + "═" * (w - 2) + "╗"),
        ("║" + " AI Multi-Agent Telegram Bot — Smart Installer  v2.0 ".center(w - 2) + "║"),
        ("║" + " اینستالر هوشمند سیستم چندعاملی هوش مصنوعی تلگرام ".center(w - 2) + "║"),
        ("╠" + "═" * (w - 2) + "╣"),
        ("║" + " LangGraph  •  LangSmith  •  FastAPI  •  Telegram ".center(w - 2) + "║"),
        ("╚" + "═" * (w - 2) + "╝"),
    ]
    print(f"\n{BLU}{BOLD}", end="")
    for l in lines:
        print(l)
    print(RST + "\n")


def step(n: int, total: int, title_fa: str, title_en: str):
    bar = "─" * 60
    print(f"\n{CYN}{BOLD}{'─'*2} مرحله {n}/{total}: {title_fa}  ({title_en}){RST}")
    print(f"{DIM}{bar}{RST}")


def ok(msg_fa: str, msg_en: str = ""):
    extra = f"  {DIM}({msg_en}){RST}" if msg_en else ""
    print(f"  {GRN}✓  {msg_fa}{RST}{extra}")


def fail(msg_fa: str, msg_en: str = ""):
    extra = f"  {DIM}({msg_en}){RST}" if msg_en else ""
    print(f"  {RED}✗  {msg_fa}{RST}{extra}")


def warn(msg_fa: str, msg_en: str = ""):
    extra = f"  {DIM}({msg_en}){RST}" if msg_en else ""
    print(f"  {YEL}⚠  {msg_fa}{RST}{extra}")


def info(msg_fa: str, msg_en: str = ""):
    extra = f"  {DIM}({msg_en}){RST}" if msg_en else ""
    print(f"  {BLU}ℹ  {msg_fa}{RST}{extra}")


def ask(
    prompt_fa: str,
    prompt_en: str,
    default: str = "",
    secret: bool = False,
) -> str:
    """Interactive prompt — returns stripped input or default."""
    dflt_txt = f"  {DIM}[پیشفرض: {default}]{RST}" if default else ""
    full_prompt = f"\n  {WHT}{BOLD}{prompt_fa}  {DIM}({prompt_en}){RST}{dflt_txt}\n  {CYN}› {RST}"
    while True:
        if secret:
            value = getpass.getpass(prompt=full_prompt)
        else:
            value = input(full_prompt).strip()
        if value:
            return value
        if default:
            return default
        fail("این فیلد الزامی است.", "This field is required.")


def ask_yn(prompt_fa: str, prompt_en: str, default: bool = False) -> bool:
    hint = "بله/خیر" + ("  [پیشفرض: بله]" if default else "  [پیشفرض: خیر]")
    full_prompt = f"\n  {WHT}{BOLD}{prompt_fa}  {DIM}({prompt_en}){RST}  {DIM}{hint}{RST}\n  {CYN}› {RST}"
    ans = input(full_prompt).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes", "بله", "آره", "1", "true")


def separator():
    print(f"\n{DIM}{'─' * 60}{RST}\n")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Python version check
# ══════════════════════════════════════════════════════════════════════════════

def check_python():
    step(1, 7, "بررسی نسخه پایتون", "Check Python version")
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 10):
        fail(
            f"پایتون {ver_str} یافت شد — نیاز به ۳.۱۰ یا بالاتر",
            f"Python {ver_str} found — need 3.10+",
        )
        print(f"\n  {YEL}لطفاً از https://python.org نسخه جدید نصب کنید.{RST}\n")
        sys.exit(1)
    ok(f"پایتون {ver_str} ✓", f"Python {ver_str}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Virtual environment
# ══════════════════════════════════════════════════════════════════════════════

def create_venv():
    step(2, 7, "محیط مجازی پایتون", "Virtual environment")
    if VENV_PYTHON.exists():
        ok("محیط مجازی از قبل موجود است.", "venv already exists.")
        return
    info("در حال ساخت محیط مجازی...", "Creating virtual environment...")
    result = subprocess.run(
        [sys.executable, "-m", "venv", str(VENV)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        fail("ساخت محیط مجازی شکست خورد.", "venv creation failed.")
        print(f"  {RED}{result.stderr}{RST}")
        sys.exit(1)
    ok("محیط مجازی ساخته شد.", "Virtual environment created.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Install dependencies
# ══════════════════════════════════════════════════════════════════════════════

def install_deps():
    step(3, 7, "نصب وابستگی‌ها", "Install dependencies")
    if not REQS.exists():
        fail("فایل requirements.txt پیدا نشد.", "requirements.txt not found.")
        sys.exit(1)

    info("در حال ارتقاء pip...", "Upgrading pip...")
    subprocess.run(
        [str(VENV_PIP), "install", "--quiet", "--upgrade", "pip"],
        capture_output=True
    )

    info("در حال نصب پکیج‌ها... (ممکن است چند دقیقه طول بکشد)", "Installing packages...")
    result = subprocess.run(
        [str(VENV_PIP), "install", "--quiet", "-r", str(REQS)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        fail("نصب وابستگی‌ها با خطا مواجه شد.", "Dependency install failed.")
        print(f"  {RED}{result.stderr[:600]}{RST}")
        sys.exit(1)
    ok("تمام وابستگی‌ها نصب شدند.", "All dependencies installed.")


# ══════════════════════════════════════════════════════════════════════════════
# NETWORK TEST HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _http_post(url: str, payload: dict, headers: dict, timeout: int = 15):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="ignore")[:400]
        return False, body
    except Exception as e:
        return False, str(e)


def test_api_connection(base_url: str, api_key: str, model: str):
    """Test an OpenAI-compatible API without using langchain."""
    url = base_url.rstrip("/") + "/chat/completions"
    ok_resp, result = _http_post(
        url,
        {"model": model, "messages": [{"role": "user", "content": "Reply with: OK"}], "max_tokens": 5},
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    if ok_resp:
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "OK")
        return True, content.strip()[:80]
    return False, str(result)[:300]


def test_telegram_token(token: str):
    """Call Telegram getMe without python-telegram-bot."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                bot = data["result"]
                return True, f"@{bot.get('username')}  ({bot.get('first_name')})"
            return False, "توکن نامعتبر است."
    except Exception as e:
        return False, str(e)[:200]


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Config wizard
# ══════════════════════════════════════════════════════════════════════════════

# Known providers for quick selection
PROVIDERS = [
    ("Bynara Router (پیشفرض)", "https://router.bynara.id/v1"),
    ("OpenAI",                  "https://api.openai.com/v1"),
    ("Groq (سریع، رایگان)",    "https://api.groq.com/openai/v1"),
    ("Together AI",             "https://api.together.xyz/v1"),
    ("OpenRouter",              "https://openrouter.ai/api/v1"),
    ("Anthropic Claude",        "https://api.anthropic.com/v1"),
    ("Google Gemini",           "https://generativelanguage.googleapis.com/v1beta"),
    ("آدرس دلخواه / Custom",   "__custom__"),
]

MODELS_BY_PROVIDER = {
    "https://router.bynara.id/v1":                                ["gpt-4o-mini", "gpt-4o", "claude-3-5-sonnet-20241022"],
    "https://api.openai.com/v1":                                  ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
    "https://api.groq.com/openai/v1":                             ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    "https://api.together.xyz/v1":                                ["meta-llama/Llama-3-70b-chat-hf", "mistralai/Mixtral-8x7B-Instruct-v0.1"],
    "https://openrouter.ai/api/v1":                               ["openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet", "meta-llama/llama-3.1-70b-instruct"],
    "https://api.anthropic.com/v1":                               ["claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"],
    "https://generativelanguage.googleapis.com/v1beta":           ["gemini-1.5-flash", "gemini-1.5-pro"],
}


def pick_provider() -> tuple[str, str]:
    """Let user choose from list or enter custom URL."""
    print(f"\n  {WHT}{BOLD}لیست ارائه‌دهندگان / AI Providers:{RST}")
    for i, (name, _) in enumerate(PROVIDERS, 1):
        print(f"    {CYN}{i}{RST}.  {name}")

    while True:
        choice = input(f"\n  {CYN}شماره انتخاب کنید [1-{len(PROVIDERS)}] › {RST}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(PROVIDERS):
            name, url = PROVIDERS[int(choice) - 1]
            if url == "__custom__":
                url = ask("آدرس Base URL خود را وارد کنید:", "Enter your Base URL", "https://")
            return name, url
        fail("عدد معتبر وارد کنید.", "Enter a valid number.")


def pick_model(base_url: str) -> str:
    suggestions = MODELS_BY_PROVIDER.get(base_url, [])
    if suggestions:
        print(f"\n  {WHT}{BOLD}مدل‌های پیشنهادی / Suggested models:{RST}")
        for i, m in enumerate(suggestions, 1):
            print(f"    {CYN}{i}{RST}.  {m}")
        print(f"    {DIM}یا نام مدل دلخواه را مستقیم وارد کنید.{RST}")
        choice = input(f"\n  {CYN}شماره یا نام مدل › {RST}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(suggestions):
            return suggestions[int(choice) - 1]
        return choice or suggestions[0]
    return ask("نام مدل:", "Model name", "gpt-4o-mini")


def wizard() -> dict:
    step(4, 7, "تنظیمات اولیه", "Configuration wizard")

    print(f"\n  {YEL}این مرحله اطلاعات اولیه را می‌پرسد و `.env` را می‌سازد.{RST}")
    print(f"  {DIM}می‌توانید بعداً از پنل ادمین تنظیمات را تغییر دهید.{RST}\n")

    cfg: dict = {}

    # ── AI Provider ───────────────────────────────────────────────────────────
    separator()
    print(f"  {MAG}{BOLD}[۱/۵] ارائه‌دهنده هوش مصنوعی  /  AI Provider{RST}")

    prov_name, base_url = pick_provider()
    cfg["BYNARA_BASE_URL"] = base_url
    info(f"انتخاب شد: {prov_name}", f"Selected: {prov_name}")

    # ── API Key ───────────────────────────────────────────────────────────────
    separator()
    print(f"  {MAG}{BOLD}[۲/۵] کلید API  /  API Key{RST}")
    print(f"  {DIM}کلید مخفی API از ارائه‌دهنده انتخابی{RST}")

    # Show Bynara free signup hint if Bynara is selected
    if "bynara" in base_url.lower() or "router.bynara" in base_url.lower():
        print()
        print(f"  {GRN}{BOLD}🎁 ۷ میلیون توکن رایگان با Bynara!{RST}")
        print(f"  {CYN}اگر هنوز کلید ندارید، ثبت‌نام رایگان کنید:{RST}")
        print(f"  {BOLD}{WHT}  https://router.bynara.id/register?ref=NMAP6F9D{RST}")
        print(f"  {DIM}  → پس از ثبت‌نام، کلید API را از داشبورد کپی کنید{RST}")
        print()

    while True:
        api_key = ask("کلید API:", "API Key (hidden)", secret=True)
        model = pick_model(base_url)
        cfg["BYNARA_API_KEY"] = api_key
        cfg["BYNARA_MODEL"] = model
        cfg["BYNARA_SUPERVISOR_MODEL"] = model

        info("در حال تست اتصال به API...", "Testing API connection...")
        success, msg = test_api_connection(base_url, api_key, model)
        if success:
            ok(f"اتصال موفق! پاسخ: «{msg}»", "Connection OK!")
            break
        else:
            fail("اتصال شکست خورد.", "Connection failed.")
            print(f"  {RED}خطا: {msg}{RST}")
            if not ask_yn("دوباره تلاش کنید؟", "Retry?", default=True):
                warn("ادامه بدون تست — بعداً بررسی کنید.", "Skipping test — check later.")
                break

    # ── Telegram ──────────────────────────────────────────────────────────────
    separator()
    print(f"  {MAG}{BOLD}[۳/۵] توکن ربات تلگرام  /  Telegram Bot Token{RST}")
    print(f"  {DIM}توکن را از @BotFather بگیرید.{RST}")

    while True:
        token = ask("توکن ربات:", "Bot Token (hidden)", secret=True)
        info("در حال تست توکن...", "Testing Telegram token...")
        success, msg = test_telegram_token(token)
        if success:
            ok(f"ربات شناسایی شد: {msg}", "Bot recognized!")
            cfg["TELEGRAM_BOT_TOKEN"] = token
            break
        else:
            fail("توکن نامعتبر است.", "Invalid token.")
            print(f"  {RED}خطا: {msg}{RST}")
            if not ask_yn("دوباره وارد کنید؟", "Retry?", default=True):
                warn("توکن ذخیره نشد — بعداً در .env تنظیم کنید.", "Token not saved.")
                cfg["TELEGRAM_BOT_TOKEN"] = ""
                break

    # ── LangSmith ─────────────────────────────────────────────────────────────
    separator()
    print(f"  {MAG}{BOLD}[۴/۵] LangSmith (اختیاری / Optional){RST}")
    print(f"  {DIM}برای مانیتورینگ pipeline روی smith.langchain.com{RST}")

    want_ls = ask_yn("آیا LangSmith را فعال کنید؟", "Enable LangSmith?", default=False)
    if want_ls:
        ls_key = ask("کلید LangSmith API:", "LangSmith API key", secret=True)
        ls_proj = ask("نام پروژه LangSmith:", "LangSmith project name", "ai-telegram-agents")
        cfg["LANGSMITH_API_KEY"] = ls_key
        cfg["LANGSMITH_PROJECT"] = ls_proj
        cfg["LANGSMITH_TRACING"] = "true"
        ok("LangSmith فعال شد.", "LangSmith enabled.")
    else:
        cfg["LANGSMITH_API_KEY"] = ""
        cfg["LANGSMITH_PROJECT"] = "ai-telegram-agents"
        cfg["LANGSMITH_TRACING"] = "false"
        info("LangSmith غیرفعال.", "LangSmith disabled.")

    # ── Panel port ────────────────────────────────────────────────────────────
    separator()
    print(f"  {MAG}{BOLD}[۵/۵] تنظیمات پنل مدیریت  /  Admin Panel{RST}")

    port = ask("پورت پنل مدیریت:", "Admin panel port", "8080")
    cfg["PANEL_PORT"] = port
    cfg["PANEL_HOST"] = "0.0.0.0"

    # ── Fixed defaults ────────────────────────────────────────────────────────
    cfg.setdefault("BOT_RESPOND_TO_ALL", "false")
    cfg.setdefault("RATE_LIMIT_SECONDS", "3")
    cfg.setdefault("AGENT_TEMPERATURE", "0.7")
    cfg.setdefault("SUPERVISOR_TEMPERATURE", "0.2")
    cfg.setdefault("MAX_HISTORY", "6")
    cfg.setdefault("LLM_TIMEOUT", "60")
    cfg.setdefault("LOG_LEVEL", "INFO")
    cfg.setdefault("BOT_NAME", "AI Agent Team")

    return cfg


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Write .env
# ══════════════════════════════════════════════════════════════════════════════

def write_env(cfg: dict):
    step(5, 7, "ذخیره تنظیمات", "Save configuration")

    if ENV_FILE.exists():
        if not ask_yn(
            ".env قبلاً وجود دارد. بازنویسی شود؟",
            ".env already exists. Overwrite?",
            default=False,
        ):
            warn(".env دست‌نخورده ماند.", ".env unchanged.")
            return

    lines = [
        "# ════════════════════════════════════════════════════════════════",
        "#  AI Multi-Agent Telegram Bot — Auto-generated by install.py",
        "#  تنظیمات خودکار — برای ویرایش این فایل یا پنل ادمین استفاده کنید",
        "# ════════════════════════════════════════════════════════════════",
        "",
        "# ── AI Provider ──────────────────────────────────────────────────",
        f"BYNARA_BASE_URL={cfg['BYNARA_BASE_URL']}",
        f"BYNARA_API_KEY={cfg['BYNARA_API_KEY']}",
        f"BYNARA_MODEL={cfg['BYNARA_MODEL']}",
        f"BYNARA_SUPERVISOR_MODEL={cfg['BYNARA_SUPERVISOR_MODEL']}",
        "",
        "# ── Telegram ──────────────────────────────────────────────────────",
        f"TELEGRAM_BOT_TOKEN={cfg['TELEGRAM_BOT_TOKEN']}",
        f"BOT_RESPOND_TO_ALL={cfg['BOT_RESPOND_TO_ALL']}",
        f"RATE_LIMIT_SECONDS={cfg['RATE_LIMIT_SECONDS']}",
        "",
        "# ── LangSmith ─────────────────────────────────────────────────────",
        f"LANGSMITH_API_KEY={cfg['LANGSMITH_API_KEY']}",
        f"LANGSMITH_PROJECT={cfg['LANGSMITH_PROJECT']}",
        f"LANGSMITH_TRACING={cfg['LANGSMITH_TRACING']}",
        "",
        "# ── Agent tuning ──────────────────────────────────────────────────",
        f"AGENT_TEMPERATURE={cfg['AGENT_TEMPERATURE']}",
        f"SUPERVISOR_TEMPERATURE={cfg['SUPERVISOR_TEMPERATURE']}",
        f"LLM_TIMEOUT={cfg['LLM_TIMEOUT']}",
        f"MAX_HISTORY={cfg['MAX_HISTORY']}",
        "",
        "# ── Web Panel ─────────────────────────────────────────────────────",
        f"PANEL_HOST={cfg['PANEL_HOST']}",
        f"PANEL_PORT={cfg['PANEL_PORT']}",
        "",
        "# ── Misc ──────────────────────────────────────────────────────────",
        f"LOG_LEVEL={cfg['LOG_LEVEL']}",
        f"BOT_NAME={cfg['BOT_NAME']}",
    ]

    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok("فایل .env ذخیره شد.", ".env saved.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — Initialize admin database
# ══════════════════════════════════════════════════════════════════════════════

def init_database():
    step(6, 7, "راه‌اندازی پایگاه داده", "Initialize database")
    # Run init_db + seed_defaults using the installed venv python
    script = (
        "import sys; sys.path.insert(0, '.');"
        "from dotenv import load_dotenv; load_dotenv();"
        "from core.admin_db import init_db, seed_defaults;"
        "init_db(); seed_defaults();"
        "print('DB_OK')"
    )
    result = subprocess.run(
        [str(VENV_PYTHON), "-c", script],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if "DB_OK" in result.stdout:
        ok("پایگاه داده admin.db ساخته شد.", "admin.db created with default providers.")
    else:
        warn(
            "پایگاه داده بعد از اولین اجرا ساخته می‌شود.",
            "DB will be created on first run.",
        )
        if result.stderr:
            print(f"  {DIM}{result.stderr[:200]}{RST}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — Success summary
# ══════════════════════════════════════════════════════════════════════════════

def print_success(cfg: dict):
    step(7, 7, "نصب کامل شد!", "Installation complete!")

    port = cfg.get("PANEL_PORT", "8080")

    print(f"""
{GRN}{BOLD}  ╔══════════════════════════════════════════════════════════╗
  ║           🎉  نصب با موفقیت انجام شد!  /  Done!         ║
  ╚══════════════════════════════════════════════════════════╝{RST}

  {WHT}اجرای ربات / Run the bot:{RST}
  {CYN}    source .venv/bin/activate       # Linux/Mac{RST}
  {CYN}    .venv\\Scripts\\activate          # Windows{RST}
  {CYN}    python3 main.py{RST}

  {WHT}پنل مدیریت / Admin Panel:{RST}
  {CYN}    http://localhost:{port}{RST}

  {WHT}دستورات ربات / Bot commands:{RST}
  {DIM}    /start   /help   /agents   /stats   /panel   /clear{RST}
  {DIM}    /setprovider  — تغییر ارائه‌دهنده هوش مصنوعی{RST}

  {WHT}تغییر تنظیمات / Change settings:{RST}
  {DIM}    • ویرایش .env{RST}
  {DIM}    • پنل ادمین در مرورگر (تب «مدیریت AI»){RST}
  {DIM}    • دستور /setprovider در تلگرام{RST}

{YEL}  ─────────────────────────────────────────────────────────{RST}
{DIM}  برای افزودن Agent جدید فقط یک فایل .py در پوشه agents/ بسازید.{RST}
{DIM}  To add a new agent, just drop a .py file in the agents/ folder.{RST}
""")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    banner()

    print(f"  {DIM}این اسکریپت پروژه را نصب و تنظیم می‌کند.{RST}")
    print(f"  {DIM}This script installs and configures the project.{RST}\n")
    print(f"  {YEL}پوشه پروژه:{RST} {ROOT}")
    print(f"  {YEL}Project root:{RST} {ROOT}\n")

    if not ask_yn("شروع کنیم؟", "Ready to begin?", default=True):
        print(f"\n  {YEL}انصراف داده شد.  Cancelled.{RST}\n")
        sys.exit(0)

    check_python()
    create_venv()
    install_deps()
    cfg = wizard()
    write_env(cfg)
    init_database()
    print_success(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {YEL}لغو شد توسط کاربر.  Cancelled by user.{RST}\n")
        sys.exit(0)
