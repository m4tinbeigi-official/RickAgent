"""
Web Panel — FastAPI server + پنل مدیریت فارسی با فونت وزیرمتن.

Endpoints
─────────
GET  /                    → HTML dashboard (RTL Persian, Vazirmatn font)
GET  /api/stats           → system metrics (JSON)
GET  /api/agents          → agent list with models & run counts (JSON)
GET  /api/conversations   → last 60 conversations (JSON)
GET  /api/config          → current .env config snapshot (JSON)
GET  /api/activity-stream → Server-Sent Events, real-time activity feed

Admin CRUD:
GET/POST/PUT/DELETE /api/admin/providers
GET/POST/PUT/DELETE /api/admin/tokens
GET/POST/PUT/DELETE /api/admin/agent-configs

Run alongside the Telegram bot via asyncio.gather() in main.py.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional

from utils.config import Config
from utils.logger import setup_logger
from utils.stats import stats

logger = setup_logger("panel")

# ── Session store ────────────────────────────────────────────────────────────
# {token: expires_at_unix}
_sessions: dict[str, float] = {}
SESSION_LIFETIME = 86400  # 24 h

_AUTH_SKIP = {"/login", "/api/auth/login"}


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_session(token: str | None) -> bool:
    if not token or token not in _sessions:
        return False
    if time.time() > _sessions[token]:
        del _sessions[token]
        return False
    return True


def _create_session() -> str:
    token = secrets.token_hex(32)
    _sessions[token] = time.time() + SESSION_LIFETIME
    return token


# ── Login HTML ───────────────────────────────────────────────────────────────
_LOGIN_HTML = """<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ورود به پنل مدیریت</title>
<link href="https://fonts.bunny.net/css?family=vazirmatn:400,600,700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Vazirmatn',sans-serif;background:#06090f;color:#e4ecf7;
  display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#0c1120;border:1px solid #233047;border-radius:16px;
  padding:40px 36px;width:100%;max-width:380px;text-align:center}
.logo{font-size:3rem;margin-bottom:12px}
h1{font-size:1.25rem;font-weight:700;margin-bottom:6px}
p{color:#4e6178;font-size:.85rem;margin-bottom:28px}
.field{text-align:right;margin-bottom:16px}
label{display:block;font-size:.8rem;color:#94aabf;margin-bottom:6px}
input{width:100%;background:#162133;border:1px solid #233047;color:#e4ecf7;
  border-radius:8px;padding:10px 14px;font-family:inherit;font-size:.9rem;outline:none;transition:.2s}
input:focus{border-color:#4895ef}
.btn{width:100%;background:linear-gradient(135deg,#4895ef,#2563eb);color:#fff;
  border:none;border-radius:10px;padding:12px;font-family:inherit;font-size:1rem;
  font-weight:700;cursor:pointer;margin-top:8px;transition:.2s}
.btn:hover{opacity:.9}
.err{color:#f2445a;font-size:.8rem;margin-top:12px;display:none}
</style>
</head>
<body>
<div class="card">
  <div class="logo">🤖</div>
  <h1>پنل مدیریت RickAgent</h1>
  <p>برای ورود نام کاربری و رمز عبور خود را وارد کنید</p>
  <div class="field"><label>نام کاربری</label>
    <input id="u" type="text" placeholder="admin" autocomplete="username"></div>
  <div class="field"><label>رمز عبور</label>
    <input id="p" type="password" placeholder="••••••••" autocomplete="current-password"></div>
  <button class="btn" onclick="login()">ورود به پنل</button>
  <div class="err" id="err">نام کاربری یا رمز عبور اشتباه است</div>
</div>
<script>
async function login() {
  const u = document.getElementById('u').value.trim();
  const p = document.getElementById('p').value;
  const r = await fetch('/api/auth/login', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({username:u, password:p}), credentials:'include'
  });
  if (r.ok) { window.location.href = '/'; }
  else { document.getElementById('err').style.display='block'; }
}
document.addEventListener('keydown', e => { if(e.key==='Enter') login(); });
</script>
</body>
</html>"""


# ── Auth middleware ──────────────────────────────────────────────────────────
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in _AUTH_SKIP:
            return await call_next(request)
        token = request.cookies.get("ra_session")
        if not _verify_session(token):
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
            return RedirectResponse("/login")
        return await call_next(request)


app = FastAPI(title="AI Agent Panel", docs_url=None, redoc_url=None)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models for request bodies ──────────────────────────────────────

class ProviderCreate(BaseModel):
    name: str
    base_url: str
    api_key: str = ""
    provider_type: str = "openai_compatible"
    description: str = ""
    is_active: bool = True

class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    provider_type: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class TokenCreate(BaseModel):
    name: str
    token: str
    bot_username: str = ""
    description: str = ""
    is_active: bool = True
    agent_config_id: Optional[int] = None

class TokenUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    bot_username: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    agent_config_id: Optional[int] = None

class SettingsUpdate(BaseModel):
    settings: dict

class AgentConfigCreate(BaseModel):
    agent_name: str
    display_name: str = ""
    icon: str = "🤖"
    description: str = ""
    provider_id: Optional[int] = None
    model: str = ""
    temperature: float = 0.7
    system_prompt: str = ""
    max_tokens: int = 4096
    is_active: bool = True
    extra_config: str = "{}"
    telegram_bot_token: Optional[str] = None

class AgentConfigUpdate(BaseModel):
    agent_name: Optional[str] = None
    display_name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    provider_id: Optional[int] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt: Optional[str] = None
    max_tokens: Optional[int] = None
    is_active: Optional[bool] = None
    extra_config: Optional[str] = None
    telegram_bot_token: Optional[str] = None

class GenerateAgentRequest(BaseModel):
    description: str

class TestConnectionRequest(BaseModel):
    provider_id: int
    model: str = "gpt-4o-mini"

class ImportRequest(BaseModel):
    data: dict
    overwrite: bool = False

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangeCredentialsRequest(BaseModel):
    current_password: str
    new_username: str
    new_password: str


# ── HTML dashboard ────────────────────────────────────────────────────────

_HTML = r"""<!DOCTYPE html>
<html dir="rtl" lang="fa">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>پنل مدیریت | AI Agent Team</title>

<!-- فونت وزیرمتن -->
<link rel="preconnect" href="https://fonts.bunny.net">
<link href="https://fonts.bunny.net/css?family=vazirmatn:300,400,500,600,700,800,900&display=swap" rel="stylesheet">

<style>
/* ═══════════════════════════════════ VARIABLES ═══════════════════════════ */
:root {
  --bg:      #06090f;
  --s1:      #0c1120;
  --s2:      #101827;
  --s3:      #162133;
  --s4:      #1c2a3f;
  --s5:      #223348;
  --bd:      #233047;
  --bd2:     #2e3f5c;

  --tx:      #e4ecf7;
  --tx2:     #94aabf;
  --dim:     #4e6178;

  --blue:    #4895ef;
  --blue-d:  #2563eb;
  --green:   #0fda7c;
  --red:     #f2445a;
  --yellow:  #f6b73c;
  --purple:  #a855f7;
  --cyan:    #22d3ee;
  --orange:  #fb923c;
  --pink:    #ec4899;

  --glow-b:  0 0 22px rgba(72,149,239,.25);
  --glow-g:  0 0 22px rgba(15,218,124,.25);
  --glow-p:  0 0 22px rgba(168,85,247,.25);

  --radius:  12px;
  --radius-sm: 8px;
}

/* ═══════════════════════════════════ RESET ════════════════════════════════ */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Vazirmatn', 'Tahoma', 'Arial', sans-serif;
  background: var(--bg);
  color: var(--tx);
  min-height: 100vh;
  font-size: 14px;
  line-height: 1.65;
  overflow-x: hidden;
}

::-webkit-scrollbar        { width: 5px; height: 5px; }
::-webkit-scrollbar-track  { background: transparent; }
::-webkit-scrollbar-thumb  { background: var(--bd2); border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: var(--dim); }

/* ═══════════════════════════════════ HEADER ══════════════════════════════ */
header {
  position: sticky; top: 0; z-index: 300;
  background: rgba(6,9,15,.9);
  backdrop-filter: blur(16px) saturate(1.4);
  -webkit-backdrop-filter: blur(16px) saturate(1.4);
  border-bottom: 1px solid var(--bd);
  height: 62px;
  padding: 0 28px;
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo {
  margin-left: auto;
  display: flex; align-items: center; gap: 10px;
  font-size: 16px; font-weight: 800;
  white-space: nowrap; color: var(--tx);
  text-decoration: none;
}
.logo-box {
  width: 36px; height: 36px;
  background: linear-gradient(135deg, var(--blue), var(--purple));
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 19px;
  box-shadow: var(--glow-b);
  flex-shrink: 0;
}
.logo em { color: var(--blue); font-style: normal; }

/* tabs */
.tabs { display: flex; gap: 4px; }
.tab {
  height: 36px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--dim);
  font-family: 'Vazirmatn', sans-serif;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: all .2s;
  white-space: nowrap;
}
.tab:hover  { background: var(--s3); color: var(--tx2); }
.tab.active { background: var(--s3); color: var(--tx); box-shadow: inset 0 0 0 1px var(--bd2); }
.tab .t-icon { font-size: 15px; }

/* pills */
.pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 13px;
  border-radius: 99px;
  font-size: 12px; font-weight: 600;
  border: 1px solid var(--bd);
  background: var(--s2);
  white-space: nowrap;
}
.pill.uptime { color: var(--tx2); }
.pill.status { }

.dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 8px var(--green);
  flex-shrink: 0;
  animation: blink 2s infinite;
}
.dot.off { background: var(--red); box-shadow: 0 0 8px var(--red); }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.35} }

/* ═══════════════════════════════════ PAGES ═══════════════════════════════ */
.page { display: none; padding: 26px 28px 40px; max-width: 1520px; margin: 0 auto; }
.page.active { display: block; }

/* ═══════════════════════════════════ STAT CARDS ══════════════════════════ */
.stats-bar {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 22px;
}
.sc {
  background: var(--s1);
  border: 1px solid var(--bd);
  border-radius: var(--radius);
  padding: 20px 22px;
  position: relative; overflow: hidden;
  transition: all .25s;
  cursor: default;
}
.sc:hover { transform: translateY(-3px); border-color: var(--bd2); }

.sc::before {
  content: '';
  position: absolute; top: -20px; right: -20px;
  width: 90px; height: 90px;
  border-radius: 50%;
  opacity: .08;
  transition: opacity .25s;
}
.sc:hover::before { opacity: .18; }
.sc.blue::before   { background: var(--blue);   }
.sc.green::before  { background: var(--green);  }
.sc.red::before    { background: var(--red);    }
.sc.purple::before { background: var(--purple); }
.sc.cyan::before   { background: var(--cyan);   }

.sc-icon  { font-size: 22px; margin-bottom: 10px; display: block; }
.sc-val   { font-size: 34px; font-weight: 900; line-height: 1; margin-bottom: 4px; font-variant-numeric: tabular-nums; }
.sc-lbl   { font-size: 11px; color: var(--dim); font-weight: 500; letter-spacing: .2px; }
.sc.blue  .sc-val { color: var(--blue); }
.sc.green .sc-val { color: var(--green); }
.sc.red   .sc-val { color: var(--red); }
.sc.purple .sc-val { color: var(--purple); }
.sc.cyan  .sc-val { color: var(--cyan); }

/* ═══════════════════════════════════ GRID ════════════════════════════════ */
.grid-2 { display: grid; grid-template-columns: 380px 1fr; gap: 16px; margin-bottom: 16px; }

/* ═══════════════════════════════════ PANEL ═══════════════════════════════ */
.panel {
  background: var(--s1);
  border: 1px solid var(--bd);
  border-radius: var(--radius);
  overflow: hidden;
}
.ph {
  display: flex; align-items: center; gap: 8px;
  padding: 13px 20px;
  border-bottom: 1px solid var(--bd);
  background: var(--s2);
  font-size: 13px; font-weight: 700;
}
.ph .badge {
  font-size: 10px; font-weight: 700;
  background: var(--s4); border-radius: 99px;
  padding: 2px 9px; color: var(--dim);
}
.ph .ph-right { margin-right: auto; font-size: 11px; color: var(--dim); font-weight: 400; }
.pb { padding: 14px 16px; }
.scroll { overflow-y: auto; max-height: 440px; }

/* ═══════════════════════════════════ AGENT CARD ══════════════════════════ */
.ac {
  background: var(--s2);
  border: 1px solid var(--bd);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  margin-bottom: 10px;
  transition: all .2s;
  position: relative;
  overflow: hidden;
}
.ac:last-child { margin-bottom: 0; }
.ac::before {
  content: '';
  position: absolute; top: 0; left: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(to bottom, var(--blue), var(--purple));
  transform: scaleY(0);
  transform-origin: top;
  transition: transform .25s;
  border-radius: 0 2px 2px 0;
}
.ac:hover { border-color: var(--bd2); background: var(--s3); }
.ac:hover::before { transform: scaleY(1); }

.ac-top {
  display: flex; align-items: center; gap: 12px;
  margin-bottom: 8px;
}
.ac-emoji {
  width: 44px; height: 44px;
  background: var(--s4);
  border: 1px solid var(--bd2);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 21px; flex-shrink: 0;
}
.ac-name  { font-size: 13px; font-weight: 700; }
.ac-sub   { font-size: 11px; color: var(--dim); }

.tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.tag {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; font-weight: 700;
  padding: 2px 8px; border-radius: 5px;
}
.tag.model  { background: rgba(34,211,238,.08);  color: var(--cyan);   border: 1px solid rgba(34,211,238,.2); }
.tag.runs   { background: rgba(15,218,124,.08);  color: var(--green);  border: 1px solid rgba(15,218,124,.2); }
.tag.temp   { background: rgba(246,183,60,.08);  color: var(--yellow); border: 1px solid rgba(246,183,60,.2); }

.bar-bg { background: var(--s5); border-radius: 4px; height: 4px; overflow: hidden; margin-top: 8px; }
.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--blue), var(--purple));
  border-radius: 4px;
  transition: width .7s cubic-bezier(.23,1,.32,1);
}
.ac-desc { font-size: 11px; color: var(--dim); margin-top: 7px; line-height: 1.55; }

/* ═══════════════════════════════════ CHART ═══════════════════════════════ */
.chart-row {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; border-bottom: 1px solid var(--bd);
}
.chart-row:last-child { border-bottom: none; }
.chart-lbl { font-size: 12px; color: var(--tx2); min-width: 80px; display: flex; align-items: center; gap: 6px; }
.chart-bg { flex: 1; background: var(--s3); border-radius: 5px; height: 7px; overflow: hidden; }
.chart-fill { height: 100%; background: linear-gradient(90deg, var(--blue), var(--purple)); border-radius: 5px; transition: width .8s ease; }
.chart-n { font-size: 11px; color: var(--dim); min-width: 26px; text-align: left; }

/* ═══════════════════════════════════ ACTIVITY FEED ══════════════════════ */
.feed-panel {
  background: var(--s1);
  border: 1px solid var(--bd);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 16px;
}
.feed-hdr {
  display: flex; align-items: center; gap: 10px;
  padding: 13px 20px;
  border-bottom: 1px solid var(--bd);
  background: var(--s2);
  font-size: 13px; font-weight: 700;
}
.live-pill {
  background: rgba(15,218,124,.08);
  border: 1px solid rgba(15,218,124,.25);
  color: var(--green);
  border-radius: 99px; padding: 2px 10px;
  font-size: 10px; font-weight: 700;
  display: flex; align-items: center; gap: 5px;
}
.live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--green);
  animation: blink 1.4s infinite;
}
.feed-scroll {
  height: 260px; overflow-y: auto;
  padding: 8px 14px;
  display: flex; flex-direction: column; gap: 1px;
  scroll-behavior: smooth;
}
.ev {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 5px 8px; border-radius: 6px;
  font-size: 12px; line-height: 1.45;
  transition: background .15s;
}
.ev:hover { background: var(--s2); }
.ev-t { font-size: 10px; color: var(--dim); min-width: 56px; padding-top: 2px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
.ev-m { color: var(--tx2); word-break: break-word; }
.ev.message     .ev-m { color: var(--blue); }
.ev.supervisor  .ev-m { color: var(--purple); }
.ev.agent_start .ev-m { color: var(--yellow); }
.ev.agent_done  .ev-m { color: var(--green); }
.ev.response    .ev-m { color: var(--cyan); }
.ev.error       .ev-m { color: var(--red); }

/* ═══════════════════════════════════ CONV ITEMS ═════════════════════════ */
.ci {
  padding: 12px 0;
  border-bottom: 1px solid var(--bd);
  cursor: pointer;
  transition: padding .15s;
}
.ci:last-child { border-bottom: none; }
.ci:hover { padding-right: 8px; }
.ci-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px; }
.ci-user { font-size: 12px; font-weight: 700; color: var(--blue); }
.ci-time { font-size: 10px; color: var(--dim); }
.ci-msg  { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 5px; }
.ci-foot { display: flex; align-items: center; gap: 8px; }
.ci-agents { font-size: 10px; color: var(--purple); font-weight: 600; }
.ci-dur    { font-size: 10px; color: var(--dim); }
.ci-arr    { margin-right: auto; font-size: 12px; color: var(--dim); transition: transform .2s; }
.ci-body {
  display: none; margin-top: 10px;
  padding: 12px 14px;
  background: var(--s3); border-radius: var(--radius-sm);
  border: 1px solid var(--bd);
  font-size: 12px; line-height: 1.7; color: var(--tx2);
}
.ci-body strong { color: var(--tx); display: block; margin-bottom: 4px; font-weight: 700; }

/* ═══════════════════════════════════ SEARCH ═════════════════════════════ */
.search-wrap { padding: 14px 16px 0; }
.search-box {
  width: 100%;
  background: var(--s2); border: 1px solid var(--bd);
  border-radius: var(--radius-sm); padding: 9px 16px;
  color: var(--tx); font-family: 'Vazirmatn', sans-serif;
  font-size: 13px; outline: none;
  transition: border-color .2s, box-shadow .2s;
}
.search-box::placeholder { color: var(--dim); }
.search-box:focus { border-color: var(--blue); box-shadow: 0 0 0 3px rgba(72,149,239,.12); }

/* ═══════════════════════════════════ TABLE ═══════════════════════════════ */
.tbl-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: right; padding: 11px 16px;
  font-size: 11px; color: var(--dim);
  font-family: 'Vazirmatn', sans-serif;
  font-weight: 700; letter-spacing: .3px;
  background: var(--s2);
  border-bottom: 1px solid var(--bd);
  white-space: nowrap;
}
td {
  padding: 11px 16px;
  border-bottom: 1px solid var(--bd);
  font-size: 12px; vertical-align: top;
  transition: background .12s;
}
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--s2); }
.clip { max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.clip-r { max-width: 300px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--dim); }

/* ═══════════════════════════════════ SETTINGS ═══════════════════════════ */
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.cfg-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 11px 20px; border-bottom: 1px solid var(--bd);
}
.cfg-row:last-child { border-bottom: none; }
.cfg-key { font-size: 12px; color: var(--tx2); font-weight: 500; }
.cfg-val {
  font-size: 11px; color: var(--cyan);
  font-family: 'Courier New', monospace;
  background: var(--s3); border: 1px solid var(--bd);
  padding: 3px 9px; border-radius: 5px;
  max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cfg-val.ok   { color: var(--green); border-color: rgba(15,218,124,.2); background: rgba(15,218,124,.05); }
.cfg-val.warn { color: var(--yellow); border-color: rgba(246,183,60,.2); background: rgba(246,183,60,.05); }
.cfg-val.bad  { color: var(--red);    border-color: rgba(242,68,90,.2);  background: rgba(242,68,90,.05); }

/* ═══════════════════════════════════ ADMIN PAGE STYLES ══════════════════ */
.admin-grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
.admin-card {
  background: var(--s1);
  border: 1px solid var(--bd);
  border-radius: var(--radius);
  overflow: hidden;
}
.admin-card-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: 13px 20px;
  border-bottom: 1px solid var(--bd);
  background: var(--s2);
}
.admin-card-hd h3 {
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; gap: 8px;
}
.admin-card-body { padding: 0; }

/* Sub-tabs for admin */
.sub-tabs {
  display: flex; gap: 2px;
  padding: 12px 20px 0;
  border-bottom: 1px solid var(--bd);
  background: var(--s1);
}
.sub-tab {
  padding: 8px 18px;
  border: none; border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--dim);
  font-family: 'Vazirmatn', sans-serif;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: all .2s;
  white-space: nowrap;
}
.sub-tab:hover { color: var(--tx2); }
.sub-tab.active { color: var(--blue); border-bottom-color: var(--blue); }

.sub-page { display: none; }
.sub-page.active { display: block; }

/* Form elements */
.form-group {
  margin-bottom: 14px;
}
.form-label {
  display: block;
  font-size: 12px; font-weight: 600;
  color: var(--tx2);
  margin-bottom: 5px;
}
.form-input, .form-select, .form-textarea {
  width: 100%;
  background: var(--s2);
  border: 1px solid var(--bd);
  border-radius: var(--radius-sm);
  padding: 9px 14px;
  color: var(--tx);
  font-family: 'Vazirmatn', sans-serif;
  font-size: 13px;
  outline: none;
  transition: border-color .2s, box-shadow .2s;
}
.form-input:focus, .form-select:focus, .form-textarea:focus {
  border-color: var(--blue);
  box-shadow: 0 0 0 3px rgba(72,149,239,.12);
}
.form-textarea {
  min-height: 80px;
  resize: vertical;
}
.form-select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%234e6178' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: 14px center;
  padding-left: 30px;
}
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.form-actions {
  display: flex; gap: 8px; justify-content: flex-start;
  margin-top: 16px; padding-top: 14px;
  border-top: 1px solid var(--bd);
}

/* Buttons */
.btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--bd);
  background: var(--s2);
  color: var(--tx2);
  font-family: 'Vazirmatn', sans-serif;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: all .15s;
}
.btn:hover { background: var(--s3); color: var(--tx); border-color: var(--bd2); }
.btn-primary {
  background: linear-gradient(135deg, var(--blue), var(--blue-d));
  color: #fff; border-color: transparent;
}
.btn-primary:hover { opacity: .88; }
.btn-success {
  background: rgba(15,218,124,.15);
  color: var(--green);
  border-color: rgba(15,218,124,.3);
}
.btn-success:hover { background: rgba(15,218,124,.25); }
.btn-danger {
  background: rgba(242,68,90,.1);
  color: var(--red);
  border-color: rgba(242,68,90,.3);
}
.btn-danger:hover { background: rgba(242,68,90,.2); }
.btn-sm { padding: 5px 12px; font-size: 11px; }
.btn-icon { padding: 5px 10px; }

/* Action bar */
.action-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--bd);
}
.action-bar-right { display: flex; gap: 8px; align-items: center; }

/* Status badges */
.status-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 10px; border-radius: 99px;
  font-size: 10px; font-weight: 700;
}
.status-badge.active {
  background: rgba(15,218,124,.1);
  color: var(--green);
  border: 1px solid rgba(15,218,124,.25);
}
.status-badge.inactive {
  background: rgba(242,68,90,.1);
  color: var(--red);
  border: 1px solid rgba(242,68,90,.25);
}

/* Modal */
.modal-overlay {
  display: none;
  position: fixed; inset: 0;
  background: rgba(0,0,0,.6);
  z-index: 500;
  align-items: center; justify-content: center;
}
.modal-overlay.show { display: flex; }
.modal {
  background: var(--s1);
  border: 1px solid var(--bd2);
  border-radius: var(--radius);
  width: 560px;
  max-width: 95vw;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0,0,0,.5);
}
.modal-hd {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 22px;
  border-bottom: 1px solid var(--bd);
  background: var(--s2);
}
.modal-hd h3 { font-size: 14px; font-weight: 700; }
.modal-close {
  background: none; border: none; color: var(--dim);
  font-size: 18px; cursor: pointer;
  padding: 4px 8px; border-radius: 6px;
  transition: all .15s;
}
.modal-close:hover { background: var(--s3); color: var(--tx); }
.modal-body { padding: 20px 22px; }

/* ═══════════════════════════════════ EMPTY ══════════════════════════════ */
.empty { text-align: center; padding: 36px 20px; color: var(--dim); }
.empty-icon { font-size: 30px; margin-bottom: 8px; }
.empty p { font-size: 13px; }

/* ═══════════════════════════════════ TOAST ══════════════════════════════ */
#toast {
  position: fixed; bottom: 24px; left: 50%;
  transform: translateX(-50%) translateY(90px);
  background: var(--s2); border: 1px solid var(--bd2);
  border-radius: var(--radius); padding: 11px 22px;
  font-size: 13px; font-weight: 500;
  box-shadow: 0 10px 40px rgba(0,0,0,.5);
  z-index: 9999; pointer-events: none;
  transition: transform .3s cubic-bezier(.23,1,.32,1);
  white-space: nowrap;
}
#toast.show { transform: translateX(-50%) translateY(0); }
#toast.error { border-color: rgba(242,68,90,.4); color: var(--red); }
#toast.success { border-color: rgba(15,218,124,.4); color: var(--green); }

/* ═══════════════════════════════════ DIVIDER ════════════════════════════ */
.mb { margin-bottom: 16px; }

/* ═══════════════════════════════════ RESPONSIVE ══════════════════════════ */
@media (max-width: 1100px) {
  .stats-bar { grid-template-columns: repeat(3,1fr); }
  .grid-2 { grid-template-columns: 1fr; }
  .settings-grid { grid-template-columns: 1fr; }
  .form-row { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .stats-bar { grid-template-columns: repeat(2,1fr); }
  header { padding: 0 14px; gap: 10px; }
  .page { padding: 14px 14px 32px; }
  .logo em { display: none; }
}

/* Template Wizard Cards */
.ac-tpl-card {
  transition: all 0.2s ease-in-out !important;
}
.ac-tpl-card:hover {
  border-color: var(--bd2) !important;
  background: var(--s3) !important;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}
</style>
</head>
<body>

<!-- ══════════════════════════════════════ HEADER ════════════════════════ -->
<header>
  <div class="tabs">
    <button class="tab active" onclick="goTab('dashboard',this)">
      <span class="t-icon">📊</span><span class="t-lbl">داشبورد</span>
    </button>
    <button class="tab" onclick="goTab('conversations',this)">
      <span class="t-icon">💬</span><span class="t-lbl">مکالمات</span>
    </button>
    <button class="tab" onclick="goTab('admin',this)">
      <span class="t-icon">🔧</span><span class="t-lbl">مدیریت AI</span>
    </button>
    <button class="tab" onclick="goTab('settings',this)">
      <span class="t-icon">⚙️</span><span class="t-lbl">تنظیمات</span>
    </button>
    <button class="tab" onclick="goTab('monitoring',this)">
      <span class="t-icon">🖥️</span><span class="t-lbl">مانیتورینگ زنده</span>
    </button>
    <button class="tab" onclick="goTab('about',this)">
      <span class="t-icon">👤</span><span class="t-lbl">درباره سازنده</span>
    </button>
  </div>

  <div class="pill uptime" id="uptime-pill">⏱ —</div>

  <div class="pill status">
    <span class="dot" id="conn-dot"></span>
    <span id="conn-txt">در حال اتصال...</span>
  </div>

  <div class="logo">
    <div class="logo-box">🤖</div>
    <span>AI Agent <em>Panel</em></span>
  </div>
</header>

<div id="toast"></div>

<!-- ════════════════════════════════ DASHBOARD ═══════════════════════════ -->
<div id="page-dashboard" class="page active">

  <!-- راهنمای راه‌اندازی سریع گروه تلگرام -->
  <div class="panel mb" style="background:linear-gradient(135deg, rgba(72,149,239,0.1) 0%, rgba(72,149,239,0.02) 100%);border:1px solid rgba(72,149,239,0.3)">
    <div class="ph" style="color:var(--blue);font-weight:700">🚀 راهنمای سریع راه‌اندازی ربات‌های گروهی تلگرام</div>
    <div class="pb" style="font-size:13px;line-height:1.7;color:var(--text)">
      <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px;padding:6px 0">
        <div>
          <strong>۱. ساخت ربات در تلگرام:</strong>
          <p style="color:var(--dim);margin:4px 0 0 0">وارد بات رسمی <a href="https://t.me/BotFather" target="_blank" style="color:var(--blue);text-decoration:underline;font-weight:bold">BotFather@</a> شوید. دستور <code>/newbot</code> را بزنید، توکن دریافتی را کپی کنید.</p>
        </div>
        <div>
          <strong>۲. غیرفعال‌سازی حریم خصوصی (بسیار مهم):</strong>
          <p style="color:var(--dim);margin:4px 0 0 0">در BotFather دستور <code>/setprivacy</code> را بزنید، ربات خود را انتخاب کرده و آن را روی <strong>Disable</strong> قرار دهید تا ربات بتواند بدون ریپلای مستقیم پیام‌های گروه را بخواند.</p>
        </div>
        <div>
          <strong>۳. ثبت ربات و ایجنت در پنل:</strong>
          <p style="color:var(--dim);margin:4px 0 0 0">در بخش <strong>مدیریت سیستم</strong> ابتدا ایجنت بسازید (با جادوی هوش مصنوعی گام‌به‌گام)، سپس توکن ربات تلگرام را ثبت و آن را به ایجنت متصل کنید.</p>
        </div>
        <div>
          <strong>۴. ساخت گروه و گفتگو:</strong>
          <p style="color:var(--dim);margin:4px 0 0 0">یک گروه بسازید، ربات‌ها را اد کنید. در تنظیمات پنل شناسه تلگرام خود را وارد کنید، همکاری گروهی را فعال کنید و پروژه را استارت بزنید!</p>
        </div>
      </div>
    </div>
  </div>

  <!-- آمار کلی -->
  <div class="stats-bar">
    <div class="sc blue">
      <span class="sc-icon">📨</span>
      <div class="sc-val" id="s-msgs">۰</div>
      <div class="sc-lbl">پیام پردازششده</div>
    </div>
    <div class="sc green">
      <span class="sc-icon">⚡</span>
      <div class="sc-val" id="s-rt">—</div>
      <div class="sc-lbl">میانگین پاسخ (ثانیه)</div>
    </div>
    <div class="sc red">
      <span class="sc-icon">⚠️</span>
      <div class="sc-val" id="s-err">۰</div>
      <div class="sc-lbl">خطاها</div>
    </div>
    <div class="sc purple">
      <span class="sc-icon">🤖</span>
      <div class="sc-val" id="s-agents">—</div>
      <div class="sc-lbl">Agentهای فعال</div>
    </div>
    <div class="sc cyan">
      <span class="sc-icon">💬</span>
      <div class="sc-val" id="s-convs">۰</div>
      <div class="sc-lbl">مکالمات ثبتشده</div>
    </div>
  </div>

  <!-- گرید اصلی -->
  <div class="grid-2">

    <div>
      <div class="panel mb">
        <div class="ph">🤖 اعضای تیم <span class="badge" id="agent-badge">۰</span></div>
        <div class="pb scroll" id="agents-list">
          <div class="empty"><div class="empty-icon">⏳</div><p>در حال بارگذاری...</p></div>
        </div>
      </div>

      <div class="panel">
        <div class="ph">📊 آمار اجرا</div>
        <div class="pb" id="chart-wrap">
          <div class="empty" style="padding:12px"><p>هنوز دادهای موجود نیست</p></div>
        </div>
      </div>
    </div>

    <div>
      <div class="feed-panel mb">
        <div class="feed-hdr">
          📡 فعالیت زنده
          <span class="live-pill"><span class="live-dot"></span> LIVE</span>
          <span class="ph-right" id="feed-count">۰ رویداد</span>
        </div>
        <div class="feed-scroll" id="activity-feed"></div>
      </div>

      <div class="panel">
        <div class="ph">💬 مکالمات اخیر <span class="badge" id="conv-badge">۰</span></div>
        <div class="pb scroll" id="conv-recent">
          <div class="empty"><div class="empty-icon">💬</div><p>هنوز مکالمهای ثبت نشده</p></div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ════════════════════════════════ CONVERSATIONS ══════════════════════ -->
<div id="page-conversations" class="page">
  <div class="panel">
    <div class="ph">💬 همه مکالمات <span class="badge" id="all-conv-badge">۰</span></div>
    <div class="search-wrap">
      <input class="search-box" id="search-inp" placeholder="🔍  جستجو در مکالمات..." oninput="filterTable(this.value)">
    </div>
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>کاربر</th><th>پیام کاربر</th><th>پاسخ سیستم</th><th>Agentها</th><th>ساعت</th><th>مدت</th>
          </tr>
        </thead>
        <tbody id="conv-tbody">
          <tr><td colspan="6" style="text-align:center;color:var(--dim);padding:36px">هنوز دادهای موجود نیست</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- ════════════════════════════════ ADMIN ══════════════════════════════ -->
<div id="page-admin" class="page">

  <!-- Admin Stats Counters -->
  <div class="stats-bar" style="grid-template-columns: repeat(6,1fr)">
    <div class="sc blue">
      <span class="sc-icon">🌐</span>
      <div class="sc-val" id="admin-prov-total">۰</div>
      <div class="sc-lbl">ارائهدهنده (کل / فعال)</div>
    </div>
    <div class="sc green">
      <span class="sc-icon">🔑</span>
      <div class="sc-val" id="admin-tok-total">۰</div>
      <div class="sc-lbl">توکن ربات (کل / فعال)</div>
    </div>
    <div class="sc purple">
      <span class="sc-icon">⚙️</span>
      <div class="sc-val" id="admin-ag-total">۰</div>
      <div class="sc-lbl">تنظیمات Agent (کل / فعال)</div>
    </div>
    <div class="sc cyan" style="cursor:pointer" onclick="doExport()">
      <span class="sc-icon">📤</span>
      <div class="sc-val" style="font-size:16px">خروجی بکاپ</div>
      <div class="sc-lbl">Export JSON</div>
    </div>
    <div class="sc cyan" style="cursor:pointer" onclick="doImport()">
      <span class="sc-icon">📥</span>
      <div class="sc-val" style="font-size:16px">بازیابی بکاپ</div>
      <div class="sc-lbl">Import JSON</div>
    </div>
  </div>

  <!-- Sub-tabs -->
  <div class="panel mb" style="overflow:visible">
    <div class="sub-tabs">
      <button class="sub-tab active" onclick="goAdminTab('providers',this)">🌐 ارائهدهندگان هوش مصنوعی</button>
      <button class="sub-tab" onclick="goAdminTab('agent-configs',this)">⚙️ مدیریت ایجنت‌ها و ربات‌ها</button>
    </div>
  </div>

  <!-- ── AI Providers ── -->
  <div id="admin-providers" class="sub-page active">
    <div class="admin-card">
      <div class="action-bar">
        <h3 style="font-size:14px;font-weight:700">🌐 ارائه‌دهندگان هوش مصنوعی</h3>
        <button class="btn btn-primary btn-sm" onclick="openProviderModal()">➕ افزودن ارائه‌دهنده</button>
      </div>
      <div class="admin-card-body tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>نام</th><th>نوع</th><th>آدرس API</th><th>کلید</th><th>وضعیت</th><th>عملیات</th>
            </tr>
          </thead>
          <tbody id="providers-tbody">
            <tr><td colspan="7" style="text-align:center;color:var(--dim);padding:36px">در حال بارگذاری...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ── Agent Configs ── -->
  <div id="admin-agent-configs" class="sub-page">
    <div class="admin-card">
      <div class="action-bar">
        <h3 style="font-size:14px;font-weight:700">⚙️ مدیریت ایجنت‌ها و ربات‌های تلگرام</h3>
        <button class="btn btn-primary btn-sm" onclick="openAgentConfigModal()">➕ ساخت ایجنت جدید</button>
      </div>
      <div class="admin-card-body tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>آیکون</th><th>نام انگلیسی</th><th>نام نمایشی</th><th>ارائه‌دهنده</th><th>مدل</th><th>دما</th><th>توکن ربات تلگرام</th><th>نام کاربری ربات</th><th>وضعیت ربات</th><th>عملیات</th>
            </tr>
          </thead>
          <tbody id="agent-configs-tbody">
            <tr><td colspan="11" style="text-align:center;color:var(--dim);padding:36px">در حال بارگذاری...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

</div>

<!-- ════════════════════════════════ SETTINGS ══════════════════════════ -->
<div id="page-settings" class="page">
  <div class="settings-grid">
    <div class="panel">
      <div class="ph">🔮 مدلهای هوش مصنوعی</div>
      <div id="cfg-api"></div>
    </div>
    <div class="panel">
      <div class="ph">🧩 مدل اختصاصی هر Agent</div>
      <div id="cfg-models"></div>
    </div>
    <div class="panel">
      <div class="ph">📱 تنظیمات تلگرام</div>
      <div id="cfg-telegram"></div>
    </div>
    <div class="panel">
      <div class="ph">🛠️ تنظیمات عمومی</div>
      <div id="cfg-other"></div>
    </div>
    <div class="panel" style="grid-column: span 2">
      <div class="ph">👥 تنظیمات گفتگوی گروهی و رئیس ایجنت‌ها</div>
      <div class="pb" style="padding: 20px">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">
              شناسه عددی رئیس ایجنت‌ها (Telegram User ID)
              <span style="font-size:11px;font-weight:normal;color:var(--dim)">
                (برای دریافت شناسه خود، به ربات <a href="https://t.me/userinfobot" target="_blank" style="color:var(--blue);text-decoration:underline">userinfobot@</a> پیام دهید)
              </span>
            </label>
            <input class="form-input" id="set-chief-id" placeholder="مثال: 123456789">
          </div>
          <div class="form-group" style="display:flex;align-items:flex-end;padding-bottom:14px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
              <input type="checkbox" id="set-group-collab" style="width:18px;height:18px;cursor:pointer">
              فعال‌سازی گفتگوی گروهی خودکار ایجنت‌ها (Cascading Replies)
            </label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">ترتیب و اولویت نوبت صحبت ایجنت‌ها در گروه (نام‌های انگلیسی ایجنت‌ها با کاما جدا شوند)</label>
          <input class="form-input" id="set-turn-order" placeholder="مثال: planner, writer, critic, supervisor">
        </div>
        
        <!-- LangSmith settings -->
        <div style="border-top: 1px solid var(--bd); margin-top: 20px; padding-top: 15px;">
          <h4 style="margin: 0 0 10px 0; font-size: 13px; color: var(--blue)">🛠️ تنظیمات ردیابی LangSmith</h4>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">کلید API ردیابی (LangSmith API Key)</label>
              <input class="form-input" id="set-ls-key" type="password" placeholder="lsv2_pt_...">
            </div>
            <div class="form-group">
              <label class="form-label">نام پروژه (LangSmith Project)</label>
              <input class="form-input" id="set-ls-project" placeholder="مثال: ai-telegram-agents">
            </div>
          </div>
          <div class="form-group" style="margin-top: 10px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
              <input type="checkbox" id="set-ls-tracing" style="width:18px;height:18px;cursor:pointer">
              فعال‌سازی ردیابی LangSmith (توصیه می‌شود)
            </label>
          </div>
        </div>

        <div style="text-align: left; margin-top: 15px;">
          <button class="btn btn-primary" onclick="saveSettingsDb()">💾 ذخیره تنظیمات عمومی و گروهی</button>
        </div>
      </div>
    </div>

    <!-- Domain & SSL Settings -->
    <div class="panel" style="grid-column: span 2; margin-top: 20px;">
      <div class="ph">🌐 تنظیمات دامنه و SSL</div>
      <div class="pb" style="padding:20px">
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">دامنه پنل (Domain)</label>
            <input class="form-input" id="set-domain" placeholder="مثال: panel.example.com">
          </div>
          <div class="form-group" style="display:flex;align-items:flex-end;padding-bottom:14px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
              <input type="checkbox" id="set-ssl-enabled" style="width:18px;height:18px;cursor:pointer" onchange="toggleSslFields()">
              فعال‌سازی SSL/HTTPS
            </label>
          </div>
        </div>
        <div id="ssl-fields" style="display:none">
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">مسیر فایل گواهی SSL (certfile)</label>
              <input class="form-input" id="set-ssl-cert" placeholder="مثال: /etc/ssl/certs/fullchain.pem">
            </div>
            <div class="form-group">
              <label class="form-label">مسیر فایل کلید SSL (keyfile)</label>
              <input class="form-input" id="set-ssl-key" placeholder="مثال: /etc/ssl/private/privkey.pem">
            </div>
          </div>
          <div style="background:rgba(246,183,60,0.1);border:1px solid rgba(246,183,60,0.3);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--yellow);margin-bottom:12px">
            ⚠️ پس از ذخیره تنظیمات SSL، باید اپلیکیشن را مجدداً راه‌اندازی کنید تا تغییرات اعمال شوند.
          </div>
        </div>
        <div style="text-align:left;margin-top:8px">
          <button class="btn btn-primary" onclick="saveDomainSettings()">💾 ذخیره تنظیمات دامنه</button>
        </div>
      </div>
    </div>

    <!-- Account & Security -->
    <div class="panel" style="grid-column: span 2; margin-top: 20px;">
      <div class="ph">🔐 امنیت پنل — تغییر نام کاربری و رمز عبور</div>
      <div class="pb" style="padding:20px">
        <div id="panel-current-user" style="font-size:12px;color:var(--dim);margin-bottom:14px">
          نام کاربری فعلی: در حال بارگذاری...
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">رمز عبور فعلی</label>
            <input class="form-input" id="sec-current-pw" type="password" placeholder="رمز عبور فعلی">
          </div>
          <div class="form-group">
            <label class="form-label">نام کاربری جدید</label>
            <input class="form-input" id="sec-new-user" type="text" placeholder="نام کاربری جدید">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">رمز عبور جدید</label>
            <input class="form-input" id="sec-new-pw" type="password" placeholder="رمز عبور جدید (حداقل ۴ کاراکتر)">
          </div>
          <div class="form-group">
            <label class="form-label">تکرار رمز عبور جدید</label>
            <input class="form-input" id="sec-new-pw2" type="password" placeholder="تکرار رمز عبور">
          </div>
        </div>
        <div style="text-align:left;margin-top:8px">
          <button class="btn btn-primary" onclick="changeCredentials()">🔒 تغییر اطلاعات ورود</button>
        </div>
      </div>
    </div>

    <!-- Agent Memories Manager Panel -->
    <div class="panel" style="margin-top: 20px;">
      <div class="ph">🧠 حافظه بلندمدت ایجنت‌ها (Memories)</div>
      <div class="pb" style="padding: 16px;">
        <p style="font-size: 13px; color: var(--dim); margin-top: 0; margin-bottom: 15px; direction: rtl; text-align: right;">
          لیست مطالبی که با پیام‌های <strong>«به خاطر بسپار»</strong> یا <strong>«یادت باشه»</strong> به ربات‌ها آموخته‌اید:
        </p>
        <div id="memories-container" style="display:flex; flex-direction:column; gap:12px;">
          <div class="empty"><p>در حال بارگذاری حافظه... ⏳</p></div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- ════════════════════════════════ MONITORING ══════════════════════════ -->
<div id="page-monitoring" class="page">
  <div class="grid-2">
    <!-- Health Check Status -->
    <div>
      <div class="panel mb">
        <div class="ph">🖥️ وضعیت سرور و اتصالات</div>
        <div class="pb" style="padding:16px">
          <!-- Server Status -->
          <div style="margin-bottom:16px">
            <h4 style="margin:0 0 8px 0;font-size:13px">📊 منابع سرور</h4>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
              <div style="background:var(--s2);padding:10px;border-radius:var(--radius-sm);border:1px solid var(--bd);text-align:center">
                <div style="font-size:11px;color:var(--dim)">بار پردازنده (CPU)</div>
                <div style="font-size:20px;font-weight:bold;color:var(--blue)" id="mon-cpu">۰%</div>
              </div>
              <div style="background:var(--s2);padding:10px;border-radius:var(--radius-sm);border:1px solid var(--bd);text-align:center">
                <div style="font-size:11px;color:var(--dim)">مصرف حافظه (RAM)</div>
                <div style="font-size:20px;font-weight:bold;color:var(--blue)" id="mon-ram">۰%</div>
              </div>
            </div>
            <div style="margin-top:10px;font-size:11px;color:var(--dim)">
              مدت زمان فعالیت سرور: <span id="mon-uptime">—</span> | پایگاه داده: <span id="mon-db" style="color:var(--green)">فعال</span>
            </div>
          </div>
          
          <!-- Telegram Bots -->
          <div style="margin-bottom:16px">
            <h4 style="margin:0 0 8px 0;font-size:13px">🤖 وضعیت اتصال ربات‌ها در تلگرام</h4>
            <div id="mon-bots-list" style="display:flex;flex-direction:column;gap:8px">
              <div style="color:var(--dim);font-size:12px">در حال بررسی...</div>
            </div>
          </div>
          
          <!-- AI Web Services -->
          <div>
            <h4 style="margin:0 0 8px 0;font-size:13px">🌐 وب‌سرویس‌های هوش مصنوعی (API)</h4>
            <div id="mon-providers-list" style="display:flex;flex-direction:column;gap:8px">
              <div style="color:var(--dim);font-size:12px">در حال بررسی...</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- System Logs Console -->
    <div>
      <div class="panel" style="height: 100%; display: flex; flex-direction: column;">
        <div class="ph" style="display:flex;justify-content:space-between;align-items:center">
          <span>📜 کنسول لاگ‌های سیستم (تک‌خطی)</span>
          <button class="btn btn-sm btn-icon" onclick="loadSystemLogs()" title="بروزرسانی لاگ‌ها">🔄</button>
        </div>
        <div class="pb" style="padding:12px;flex-grow:1;display:flex;flex-direction:column">
          <pre id="mon-console" style="background:#0b0f19;color:#a9b1d6;padding:12px;border-radius:var(--radius-sm);font-family:monospace;font-size:11px;line-height:1.5;overflow:auto;max-height:480px;height:480px;margin:0;white-space:pre-wrap;word-break:break-all;border:1px solid #1a233a"></pre>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ════════════════════════════════ ABOUT ═══════════════════════════════ -->
<div id="page-about" class="page">
  <div style="max-width:680px;margin:0 auto;padding:24px 0">

    <!-- Profile card -->
    <div class="panel mb" style="
      background: linear-gradient(135deg,rgba(108,92,231,0.12) 0%,rgba(10,10,15,0.0) 100%);
      border: 1px solid rgba(108,92,231,0.35);
      text-align:center;padding:40px 24px
    ">
      <div style="
        width:88px;height:88px;border-radius:50%;
        background:linear-gradient(135deg,#6c5ce7,#a29bfe);
        display:flex;align-items:center;justify-content:center;
        font-size:2.6rem;margin:0 auto 20px
      ">🤖</div>
      <h2 style="font-size:1.55rem;font-weight:800;margin:0 0 6px">Rick Sanchez</h2>
      <p style="color:var(--dim);font-size:0.9rem;margin:0 0 24px">
        توسعه‌دهنده | هوش مصنوعی | Open Source
      </p>

      <!-- Social links -->
      <div style="display:flex;justify-content:center;gap:12px;flex-wrap:wrap;margin-bottom:28px">

        <a href="https://instagram.com/m4tinbeigi" target="_blank" rel="noopener" style="
          display:flex;align-items:center;gap:8px;
          background:linear-gradient(135deg,#f09433,#e6683c,#dc2743,#cc2366,#bc1888);
          color:#fff;text-decoration:none;padding:10px 20px;
          border-radius:10px;font-weight:600;font-size:0.9rem;transition:opacity .2s
        " onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
            <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/>
          </svg>
          اینستاگرام
        </a>

        <a href="https://twitter.com/m4tinbeigi" target="_blank" rel="noopener" style="
          display:flex;align-items:center;gap:8px;
          background:#000;color:#fff;text-decoration:none;
          padding:10px 20px;border-radius:10px;font-weight:600;font-size:0.9rem;
          border:1px solid #333;transition:opacity .2s
        " onmouseover="this.style.opacity='.8'" onmouseout="this.style.opacity='1'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
            <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.259 5.631zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
          </svg>
          توییتر / X
        </a>

        <a href="https://t.me/m4tinbeigi" target="_blank" rel="noopener" style="
          display:flex;align-items:center;gap:8px;
          background:#0088cc;color:#fff;text-decoration:none;
          padding:10px 20px;border-radius:10px;font-weight:600;font-size:0.9rem;transition:opacity .2s
        " onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="white">
            <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
          </svg>
          تلگرام
        </a>
      </div>

      <!-- Support button -->
      <a href="https://reymit.ir/m4tinbeigi" target="_blank" rel="noopener" style="
        display:inline-flex;align-items:center;gap:10px;
        background:linear-gradient(135deg,#f7971e,#ffd200);
        color:#1a1a1a;text-decoration:none;
        padding:14px 32px;border-radius:12px;
        font-weight:800;font-size:1rem;
        box-shadow:0 4px 20px rgba(247,151,30,0.4);transition:all .2s
      " onmouseover="this.style.transform='translateY(-2px)';this.style.boxShadow='0 6px 28px rgba(247,151,30,0.55)'"
         onmouseout="this.style.transform='';this.style.boxShadow='0 4px 20px rgba(247,151,30,0.4)'">
        ☕ حمایت از سازنده
      </a>
      <p style="color:var(--dim);font-size:0.8rem;margin:12px 0 0">
        اگر این پروژه برات مفید بوده، یه قهوه مهمونم کن 🙏
      </p>
    </div>

    <!-- Project info -->
    <div class="panel mb">
      <div class="ph">🤖 درباره RickAgent</div>
      <div class="pb" style="padding:20px">
        <p style="color:var(--dim);line-height:1.8;margin:0 0 16px">
          RickAgent یک سیستم هوش مصنوعی چندعاملی متن‌باز برای تلگرام است که با LangGraph ساخته شده.
          طراحی شده برای راه‌اندازی سریع، بدون نیاز به ثبت‌نام ایجنت‌ها، با پشتیبانی از چندین ارائه‌دهنده AI.
        </p>
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          <a href="https://github.com/m4tinbeigi-official/RickAgent" target="_blank" rel="noopener"
             class="btn btn-sm" style="text-decoration:none">
            ⭐ GitHub
          </a>
          <a href="https://m4tinbeigi-official.github.io/RickAgent" target="_blank" rel="noopener"
             class="btn btn-sm" style="text-decoration:none">
            🌐 وب‌سایت
          </a>
          <a href="https://github.com/m4tinbeigi-official/RickAgent/issues" target="_blank" rel="noopener"
             class="btn btn-sm" style="text-decoration:none">
            🐛 گزارش باگ
          </a>
        </div>
      </div>
    </div>

    <!-- Version -->
    <div class="panel" style="text-align:center;padding:16px">
      <span style="color:var(--dim);font-size:0.85rem">
        RickAgent v2.0 &nbsp;·&nbsp; MIT License &nbsp;·&nbsp;
        ساخته شده با ❤️ توسط
        <a href="https://github.com/m4tinbeigi-official" target="_blank" style="color:var(--accent)">@m4tinbeigi</a>
      </span>
    </div>

  </div>
</div>

<!-- ════════════════════════════════ MODALS ══════════════════════════════ -->

<!-- Provider Modal -->
<div class="modal-overlay" id="modal-provider">
  <div class="modal">
    <div class="modal-hd">
      <h3 id="modal-provider-title">افزودن ارائه‌دهنده</h3>
      <button class="modal-close" onclick="closeModal('modal-provider')">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="prov-edit-id">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">نام ارائه‌دهنده *</label>
          <input class="form-input" id="prov-name" placeholder="مثال: OpenAI">
        </div>
        <div class="form-group">
          <label class="form-label">نوع</label>
          <select class="form-select" id="prov-type">
            <option value="openai_compatible">OpenAI Compatible</option>
            <option value="anthropic">Anthropic</option>
            <option value="google">Google</option>
            <option value="custom">سفارشی</option>
          </select>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">آدرس Base URL *</label>
        <input class="form-input" id="prov-url" placeholder="https://api.openai.com/v1">
      </div>
      <div class="form-group">
        <label class="form-label">API Key</label>
        <input class="form-input" id="prov-key" type="password" placeholder="sk-...">
      </div>
      <div class="form-group">
        <label class="form-label">توضیحات</label>
        <input class="form-input" id="prov-desc" placeholder="توضیحات اختیاری">
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" onclick="saveProvider()">💾 ذخیره</button>
        <button class="btn" onclick="closeModal('modal-provider')">انصراف</button>
      </div>
    </div>
  </div>
</div>

<!-- Agent Config Modal (Wizard) -->
<div class="modal-overlay" id="modal-agent-config">
  <div class="modal" style="width:640px">
    <div class="modal-hd">
      <h3 id="modal-ac-title">ساخت ایجنت جدید (مرحله به مرحله)</h3>
      <button class="modal-close" onclick="closeModal('modal-agent-config')">✕</button>
    </div>
    
    <!-- Progress Indicator -->
    <div style="padding: 16px 22px 0;">
      <div style="display:flex;justify-content:space-between;align-items:center;background:var(--s2);padding:10px 14px;border-radius:var(--radius-sm);border:1px solid var(--bd)">
        <div id="wz-step-1-indicator" style="font-weight:700;color:var(--blue);font-size:12px">۱. نقش و الگو</div>
        <div style="color:var(--dim)">←</div>
        <div id="wz-step-2-indicator" style="font-weight:500;color:var(--dim);font-size:12px">۲. مغز هوش مصنوعی</div>
        <div style="color:var(--dim)">←</div>
        <div id="wz-step-3-indicator" style="font-weight:500;color:var(--dim);font-size:12px">۳. تنظیمات نهایی</div>
      </div>
    </div>

    <div class="modal-body">
      <input type="hidden" id="ac-edit-id">
      
      <!-- STEP 1: Role Selection & Info -->
      <div id="wz-step-1">
        <div style="background:var(--s2);border:1px dashed var(--blue);border-radius:var(--radius-sm);padding:14px;margin-bottom:16px">
          <label class="form-label" style="color:var(--blue);font-weight:700">✨ ساخت خودکار با هوش مصنوعی (AI Magic)</label>
          <div style="display:flex;gap:8px">
            <input class="form-input" id="ac-ai-desc" placeholder="توضیح دهید چه ایجنتی می‌خواهید؟ (مثلا: یک مشاور مالی شخصی)">
            <button class="btn btn-primary" onclick="generateAgentWithAI()" id="ac-ai-btn">تولید 🪄</button>
          </div>
          <div style="font-size:11px;color:var(--dim);margin-top:6px">سیستم با تحلیل توصیف شما، نام، مشخصات و پرامپت حرفه‌ای برای ایجنت می‌سازد.</div>
        </div>
        
        <label class="form-label" style="margin-bottom:10px">یا یک الگو انتخاب کنید یا نقش سفارشی خود را بسازید:</label>
        <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:16px">
          <div class="ac-tpl-card" onclick="selectTemplateCard('writer')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">✍️</span> <strong>نویسنده (Writer)</strong>
            <div style="font-size:11px;color:var(--dim)">تولید محتوا، ایمیل، داستان و متون</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('critic')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">🔍</span> <strong>منتقد (Critic)</strong>
            <div style="font-size:11px;color:var(--dim)">بازبینی، ویراستاری و بهبود پیش‌نویس‌ها</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('analyst')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">📊</span> <strong>تحلیلگر (Analyst)</strong>
            <div style="font-size:11px;color:var(--dim)">مقایسه داده‌ها و تحلیل ساختاری</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('planner')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">📋</span> <strong>برنامه‌ریز (Planner)</strong>
            <div style="font-size:11px;color:var(--dim)">طراحی سناریو و نقشه راه کارها</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('researcher')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">🔬</span> <strong>محقق (Researcher)</strong>
            <div style="font-size:11px;color:var(--dim)">تحقیق علمی و جمع‌آوری اطلاعات</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('supervisor')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s">
            <span style="font-size:20px">🧠</span> <strong>ناظر (Supervisor)</strong>
            <div style="font-size:11px;color:var(--dim)">هماهنگ‌کننده کل تیم و نویسنده پاسخ</div>
          </div>
          <div class="ac-tpl-card" onclick="selectTemplateCard('custom')" style="background:var(--s2);border:1px solid var(--bd);border-radius:var(--radius-sm);padding:10px;cursor:pointer;transition:all 0.2s;grid-column:span 2;text-align:center">
            <span style="font-size:20px">⚙️</span> <strong>نقش جدید (سفارشی)</strong>
            <div style="font-size:11px;color:var(--dim)">تعریف مشخصات کامل ایجنت توسط خودتان</div>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">نام انگلیسی ایجنت (یکتا) *</label>
            <input class="form-input" id="ac-name" placeholder="مثال: writer">
          </div>
          <div class="form-group">
            <label class="form-label">نام نمایشی (فارسی)</label>
            <input class="form-input" id="ac-display" placeholder="مثال: نویسنده خلاق">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">آیکون / ایموجی</label>
            <input class="form-input" id="ac-icon" placeholder="🤖" style="text-align:center;font-size:24px">
          </div>
          <div class="form-group">
            <label class="form-label">توضیح کوتاه کارکرد</label>
            <input class="form-input" id="ac-desc" placeholder="ایجنت چه کاری انجام می‌دهد؟">
          </div>
        </div>
      </div>

      <!-- STEP 2: AI brain choice -->
      <div id="wz-step-2" style="display:none">
        <div class="form-group">
          <label class="form-label">ارائه‌دهنده هوش مصنوعی (AI Provider)</label>
          <select class="form-select" id="ac-provider" onchange="onProviderChange(this.value)">
            <option value="">— پیشفرض —</option>
          </select>
        </div>
        <div class="form-row">
          <div class="form-group" style="flex: 2">
            <label class="form-label">مدل هوش مصنوعی</label>
            <input class="form-input" id="ac-model" list="ac-model-list" placeholder="مدل را انتخاب یا تایپ کنید">
            <datalist id="ac-model-list"></datalist>
          </div>
          <div class="form-group" style="display:flex;align-items:flex-end;padding-bottom:14px">
            <button class="btn" style="height:38px;white-space:nowrap" onclick="testAgentModelConnection()" id="btn-test-model">🔌 تست اتصال مدل</button>
          </div>
          <div class="form-group">
            <label class="form-label">دما (خلاقیت - Temperature)</label>
            <input class="form-input" id="ac-temp" type="number" min="0" max="2" step="0.1" value="0.7">
          </div>
        </div>
      </div>

      <!-- STEP 3: Final Prompt & Settings -->
      <div id="wz-step-3" style="display:none">
        <div class="form-group">
          <label class="form-label">توکن ربات تلگرام اختصاصی (اختیاری)</label>
          <input class="form-input" id="ac-bot-token" placeholder="مثال: 123456789:ABCdefGhIJKlmNoPQRsT">
          <div style="font-size:11px;color:var(--dim);margin-top:4px">اگر می‌خواهید این ایجنت مستقیماً به یک ربات تلگرام اختصاصی متصل شود، توکن آن را اینجا وارد کنید.</div>
        </div>
        <div class="form-group">
          <label class="form-label">دستورات سیستمی (System Prompt)</label>
          <textarea class="form-textarea" id="ac-prompt" rows="6" placeholder="You are a helpful AI assistant..."></textarea>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">حداکثر توکن (Max Tokens)</label>
            <input class="form-input" id="ac-max-tokens" type="number" value="4096">
          </div>
          <div class="form-group" style="display:flex;align-items:flex-end;padding-bottom:14px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
              <input type="checkbox" id="ac-active" checked style="width:18px;height:18px;cursor:pointer">
              فعال باشد (آماده کار در سیستم)
            </label>
          </div>
        </div>
      </div>

      <!-- Wizard actions -->
      <div class="form-actions" style="display:flex;justify-content:space-between;align-items:center;margin-top:20px;padding-top:14px;border-top:1px solid var(--bd)">
        <button class="btn" id="wz-prev-btn" onclick="prevWizardStep()" style="display:none">⬅️ قبلی</button>
        <button class="btn btn-primary" id="wz-next-btn" onclick="nextWizardStep()">بعدی ➡️</button>
        <button class="btn btn-primary" id="wz-save-btn" onclick="saveAgentConfig()" style="display:none">💾 ذخیره ایجنت</button>
        <button class="btn" onclick="closeModal('modal-agent-config')">انصراف</button>
      </div>
    </div>
  </div>
</div>

<!-- ════════════════════════════════ SCRIPTS ══════════════════════════════ -->
<script>
'use strict';

/* ─── utils ─────────────────────────────────────────────────────────── */
const $ = id => document.getElementById(id);

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&').replace(/</g,'<')
    .replace(/>/g,'>').replace(/"/g,'"');
}

const FA_DIGITS = '۰۱۲۳۴۵۶۷۸۹';
function fa(n, fixed) {
  if (n == null || n === '—') return '—';
  const s = fixed != null ? Number(n).toFixed(fixed) : String(n);
  return s.replace(/\d/g, d => FA_DIGITS[d]);
}

let _toastTimer;
function toast(msg, ms = 3000, type = '') {
  const t = $('toast');
  t.textContent = msg;
  t.className = 'show' + (type ? ' ' + type : '');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.className = '', ms);
}

/* ─── tabs ───────────────────────────────────────────────────────────── */
function goTab(name, btn) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  $('page-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'conversations') loadConvTable();
  if (name === 'settings')     loadSettings();
  if (name === 'admin')        loadAdminData();
  if (name === 'monitoring') {
    loadMonitoringData();
    loadSystemLogs();
  }
}

/* ─── admin sub-tabs ─────────────────────────────────────────────────── */
function goAdminTab(name, btn) {
  document.querySelectorAll('.sub-page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
  $('admin-' + name).classList.add('active');
  btn.classList.add('active');
}

/* ─── modal helpers ──────────────────────────────────────────────────── */
function openModal(id) { $(id).classList.add('show'); }
function closeModal(id) { $(id).classList.remove('show'); }

// Close modal on overlay click
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('show');
  }
});

/* ─── online / offline ───────────────────────────────────────────────── */
function setOnline(ok) {
  $('conn-dot').className = 'dot' + (ok ? '' : ' off');
  $('conn-txt').textContent = ok ? 'متصل' : 'اتصال قطع شد';
}

/* ─── API helper ─────────────────────────────────────────────────────── */
async function api(url, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'خطای سرور');
  }
  return res.json();
}

/* ─── stats ──────────────────────────────────────────────────────────── */
async function fetchStats() {
  try {
    const d = await api('/api/stats');
    $('s-msgs').textContent = fa(d.total_messages);
    $('s-rt').textContent   = d.avg_response_time ? fa(d.avg_response_time, 1) : '—';
    $('s-err').textContent  = fa(d.total_errors);
    $('uptime-pill').textContent = '⏱ ' + (d.uptime_human || '—');
    setOnline(true);
  } catch { setOnline(false); }
}

/* ─── agents ─────────────────────────────────────────────────────────── */
let _agents = [];
async function fetchAgents() {
  try {
    _agents = await api('/api/agents');
    $('s-agents').textContent  = fa(_agents.length);
    $('agent-badge').textContent = fa(_agents.length);
    renderAgents(_agents);
    renderChart(_agents);
  } catch {}
}

function renderAgents(list) {
  const el = $('agents-list');
  if (!list.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">🤖</div><p>عضو فعالی در تیم وجود ندارد</p></div>';
    return;
  }
  const maxRuns = Math.max(...list.map(a => a.runs), 1);
  el.innerHTML = list.map(a => {
    let botBadge = '';
    if (a.telegram_bot_token) {
      botBadge = `<span class="tag runs" style="font-size:10px;background:rgba(46,204,113,0.1);color:#2ecc71;border:1px solid rgba(46,204,113,0.2)">🟢 ربات فعال ${a.bot_username ? `(${esc(a.bot_username)})` : ''}</span>`;
    } else {
      botBadge = `<span class="tag model" style="font-size:10px;background:rgba(231,76,60,0.1);color:#e74c3c;border:1px solid rgba(231,76,60,0.2)">🔴 بدون ربات</span>`;
    }
    
    return `
      <div class="ac" style="position:relative">
        <div class="ac-top">
          <div class="ac-emoji">${a.icon}</div>
          <div>
            <div class="ac-name" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">${esc(a.role)} ${botBadge}</div>
            <div class="ac-sub">${esc(a.name)}</div>
          </div>
        </div>
        <div class="tags">
          <span class="tag model">🔮 ${esc(a.model)}</span>
          <span class="tag runs">▶ ${fa(a.runs)} اجرا</span>
          <span class="tag temp">🌡 ${a.temperature}</span>
        </div>
        ${a.runs > 0 ? `<div class="bar-bg"><div class="bar-fill" style="width:${Math.round(a.runs/maxRuns*100)}%"></div></div>` : ''}
        <div class="ac-desc">${esc(a.description)}</div>
      </div>
    `;
  }).join('');
}

function renderChart(list) {
  const el = $('chart-wrap');
  const total = list.reduce((s, a) => s + a.runs, 0);
  if (!total) {
    el.innerHTML = '<div class="empty" style="padding:12px"><p>هنوز هیچ Agentی اجرا نشده</p></div>';
    return;
  }
  const maxRuns = Math.max(...list.map(a => a.runs), 1);
  el.innerHTML = list.map(a => `
    <div class="chart-row">
      <div class="chart-lbl">${a.icon} ${esc(a.role)}</div>
      <div class="chart-bg">
        <div class="chart-fill" style="width:${a.runs > 0 ? Math.round(a.runs/maxRuns*100) : 0}%"></div>
      </div>
      <div class="chart-n">${fa(a.runs)}</div>
    </div>
  `).join('');
}

/* ─── recent conversations ───────────────────────────────────────────── */
async function fetchConversations() {
  try {
    const convs = await api('/api/conversations');
    $('s-convs').textContent  = fa(convs.length);
    $('conv-badge').textContent = fa(convs.length);
    renderRecentConvs(convs.slice(0, 14));
  } catch {}
}

function renderRecentConvs(list) {
  const el = $('conv-recent');
  if (!list.length) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">💬</div><p>هنوز مکالمهای ثبت نشده</p></div>';
    return;
  }
  el.innerHTML = list.map((c, i) => `
    <div class="ci" onclick="toggleConv(this,${i})">
      <div class="ci-top">
        <span class="ci-user">${esc(c.username)}</span>
        <span class="ci-time">${esc(c.time)}</span>
      </div>
      <div class="ci-msg">${esc(c.message)}</div>
      <div class="ci-foot">
        <span class="ci-agents">${(c.agents||[]).join(' ← ')}</span>
        <span class="ci-dur">⏱ ${fa(c.duration)}ث</span>
        <span class="ci-arr">▾</span>
      </div>
      <div class="ci-body" id="cb-${i}">
        <strong>پاسخ سیستم:</strong>${esc(c.response)}
      </div>
    </div>
  `).join('');
}

function toggleConv(el, i) {
  const body = $('cb-' + i);
  const arr  = el.querySelector('.ci-arr');
  const open = body.style.display === 'block';
  body.style.display = open ? 'none' : 'block';
  if (arr) arr.textContent = open ? '▾' : '▴';
}

/* ─── full conversations table ───────────────────────────────────────── */
let _allConvs = [];
async function loadConvTable() {
  try {
    _allConvs = await api('/api/conversations');
    $('all-conv-badge').textContent = fa(_allConvs.length);
    renderConvTable(_allConvs);
  } catch {}
}

function renderConvTable(list) {
  const tbody = $('conv-tbody');
  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--dim);padding:36px">هنوز دادهای موجود نیست</td></tr>';
    return;
  }
  tbody.innerHTML = list.map(c => `
    <tr>
      <td style="color:var(--blue);font-weight:700">${esc(c.username)}</td>
      <td class="clip">${esc(c.message)}</td>
      <td class="clip-r">${esc(c.response)}</td>
      <td style="color:var(--purple);font-size:11px;white-space:nowrap">${(c.agents||[]).join(' ← ')}</td>
      <td style="color:var(--dim);white-space:nowrap">${esc(c.time)}</td>
      <td style="color:var(--green);white-space:nowrap">${fa(c.duration)}ث</td>
    </tr>
  `).join('');
}

function filterTable(q) {
  if (!q.trim()) { renderConvTable(_allConvs); return; }
  const lq = q.toLowerCase();
  renderConvTable(_allConvs.filter(c =>
    (c.message  || '').toLowerCase().includes(lq) ||
    (c.response || '').toLowerCase().includes(lq) ||
    (c.username || '').toLowerCase().includes(lq)
  ));
}

/* ─── settings ───────────────────────────────────────────────────────── */
async function loadSettings() {
  try {
    const cfg = await api('/api/config');
    const row = (k, v, cls = '') =>
      `<div class="cfg-row"><span class="cfg-key">${k}</span><span class="cfg-val ${cls}" title="${esc(v)}">${esc(v)}</span></div>`;

    $('cfg-api').innerHTML =
      row('مدل پیشفرض', cfg.bynara_model) +
      row('مدل ناظر',    cfg.bynara_supervisor_model) +
      row('آدرس API',    cfg.bynara_base_url);

    const modelEntries = Object.entries(cfg.agent_models || {});
    $('cfg-models').innerHTML = modelEntries.length
      ? modelEntries.map(([k, v]) => row(k, v)).join('')
      : row('همه Agentها', cfg.bynara_model + ' (پیشفرض)', 'warn');

    const boolRow = (k, v) => row(k,
      v === 'true' ? '✅ فعال' : '❌ غیرفعال',
      v === 'true' ? 'ok' : 'bad'
    );

    $('cfg-telegram').innerHTML =
      boolRow('پاسخ به همه پیامها', cfg.bot_respond_to_all) +
      row('تأخیر نرخگذاری (ث)', cfg.rate_limit_seconds) +
      row('حداکثر تاریخچه',      cfg.max_history);

    $('cfg-other').innerHTML =
      boolRow('ردیابی LangSmith', cfg.langsmith_tracing) +
      row('پروژه LangSmith', cfg.langsmith_project) +
      row('دمای Agent',       cfg.agent_temperature) +
      row('دمای ناظر',        cfg.supervisor_temperature) +
      row('سطح لاگ',          cfg.log_level);
      
    await loadSettingsDb();
  } catch {}
}

async function loadSettingsDb() {
  try {
    const s = await api('/api/admin/settings');
    $('set-chief-id').value = s.chief_user_id || '';
    $('set-group-collab').checked = s.group_collab_enabled === '1';
    $('set-turn-order').value = s.group_turn_order || '';
    $('set-ls-key').value = s.langsmith_api_key || '';
    $('set-ls-project').value = s.langsmith_project || 'ai-telegram-agents';
    $('set-ls-tracing').checked = s.langsmith_tracing === '1';
    await loadMemories();
  } catch (e) {
    console.error('loadSettingsDb error:', e);
  }
}

async function saveSettingsDb() {
  const body = {
    settings: {
      chief_user_id: $('set-chief-id').value.trim(),
      group_collab_enabled: $('set-group-collab').checked ? '1' : '0',
      group_turn_order: $('set-turn-order').value.trim(),
      langsmith_api_key: $('set-ls-key').value.trim(),
      langsmith_project: $('set-ls-project').value.trim(),
      langsmith_tracing: $('set-ls-tracing').checked ? '1' : '0'
    }
  };
  try {
    await api('/api/admin/settings', 'POST', body);
    toast('✅ تنظیمات عمومی و گروهی ذخیره شد', 3000, 'success');
    loadSettings();
  } catch (e) {
    toast('❌ خطا در ذخیره تنظیمات: ' + e.message, 4000, 'error');
  }
}

async function loadMemories() {
  try {
    const memories = await api('/api/admin/memories');
    const container = $('memories-container');
    if (!memories.length) {
      container.innerHTML = '<div class="empty" style="padding:10px"><p>هنوز چیزی به خاطر سپرده نشده است 💤</p></div>';
      return;
    }
    
    const grouped = {};
    memories.forEach(m => {
      const key = m.agent_name ? `مخصوص ایجنت: ${m.agent_name}` : 'عمومی (تمامی ایجنت‌ها)';
      if (!grouped[key]) grouped[key] = [];
      grouped[key].push(m);
    });
    
    let html = '';
    for (const [groupTitle, items] of Object.entries(grouped)) {
      const isGeneral = groupTitle.includes('عمومی');
      const badgeStyle = isGeneral 
        ? 'background:rgba(52,152,219,0.1);color:#3498db;border:1px solid rgba(52,152,219,0.2)' 
        : 'background:rgba(155,89,182,0.1);color:#9b59b6;border:1px solid rgba(155,89,182,0.2)';
        
      html += `
        <div style="border: 1px solid var(--bd); border-radius: var(--radius-sm); background: var(--s1); overflow: hidden; margin-bottom:10px">
          <div style="background: var(--s2); padding: 8px 12px; font-weight: bold; font-size: 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--bd);">
            <span>${esc(groupTitle)}</span>
            <span class="tag" style="margin:0; ${badgeStyle}">${items.length} یادآوری</span>
          </div>
          <div style="padding: 10px; display: flex; flex-direction: column; gap: 8px;">
      `;
      
      items.forEach(item => {
        html += `
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px; background: var(--bg); padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--bd);">
            <div style="font-size: 13px; color: var(--fg); flex: 1; text-align: right; direction: rtl;">
              📌 ${esc(item.content)}
            </div>
            <button class="btn btn-sm btn-danger" style="padding: 4px 8px; font-size: 11px; height: auto;" onclick="deleteMemory(${item.id})">🗑️ حذف</button>
          </div>
        `;
      });
      
      html += `
          </div>
        </div>
      `;
    }
    
    container.innerHTML = html;
  } catch (e) {
    console.error('loadMemories error:', e);
    $('memories-container').innerHTML = '<div class="empty"><p>❌ خطا در بارگذاری حافظه</p></div>';
  }
}

async function deleteMemory(id) {
  if (!confirm('آیا مطمئن هستید که می‌خواهید این مورد را از حافظه ایجنت پاک کنید؟')) return;
  try {
    await api(`/api/admin/memories/${id}`, 'DELETE');
    toast('✅ یادآوری از حافظه با موفقیت پاک شد', 3000, 'success');
    await loadMemories();
  } catch (e) {
    toast('❌ خطا در حذف یادآوری: ' + e.message, 4000, 'error');
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — AI PROVIDERS
   ═══════════════════════════════════════════════════════════════════════════ */

let _providers = [];

async function loadProviders() {
  try {
    _providers = await api('/api/admin/providers');
    renderProviders();
  } catch (e) { console.error('loadProviders:', e); }
}

function renderProviders() {
  const tbody = $('providers-tbody');
  if (!_providers.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--dim);padding:36px">ارائه‌دهنده‌ای ثبت نشده</td></tr>';
    return;
  }
  tbody.innerHTML = _providers.map(p => `
    <tr>
      <td style="color:var(--dim)">${p.id}</td>
      <td style="font-weight:700">${esc(p.name)}</td>
      <td><span class="tag model">${esc(p.provider_type)}</span></td>
      <td class="clip" style="font-family:monospace;font-size:11px;color:var(--cyan)">${esc(p.base_url)}</td>
      <td style="font-family:monospace;font-size:11px">${p.api_key ? '••••••••' : '<span style="color:var(--dim)">—</span>'}</td>
      <td>${p.is_active ? '<span class="status-badge active">● فعال</span>' : '<span class="status-badge inactive">● غیرفعال</span>'}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-success btn-icon" onclick="testProvider(${p.id},'${esc(p.name)}')" title="تست اتصال">🔌</button>
        <button class="btn btn-sm btn-icon" onclick="editProvider(${p.id})" title="ویرایش">✏️</button>
        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteProvider(${p.id},'${esc(p.name)}')" title="حذف">🗑️</button>
      </td>
    </tr>
  `).join('');
}

function openProviderModal(data) {
  $('modal-provider-title').textContent = data ? 'ویرایش ارائهدهنده' : 'افزودن ارائهدهنده';
  $('prov-edit-id').value = data ? data.id : '';
  $('prov-name').value = data ? data.name : '';
  $('prov-type').value = data ? data.provider_type : 'openai_compatible';
  $('prov-url').value = data ? data.base_url : '';
  $('prov-key').value = data ? data.api_key : '';
  $('prov-desc').value = data ? data.description : '';
  openModal('modal-provider');
}

async function editProvider(id) {
  const p = _providers.find(x => x.id === id);
  if (p) openProviderModal(p);
}

async function saveProvider() {
  const id   = $('prov-edit-id').value;
  const name = $('prov-name').value.trim();
  const url  = $('prov-url').value.trim();
  if (!name || !url) { toast('نام و آدرس الزامی است', 3000, 'error'); return; }
  const body = {
    name, base_url: url,
    api_key: $('prov-key').value,
    provider_type: $('prov-type').value,
    description: $('prov-desc').value,
  };
  try {
    if (id) {
      await api('/api/admin/providers/' + id, 'PUT', body);
      toast('✅ ارائهدهنده بروزرسانی شد', 3000, 'success');
    } else {
      await api('/api/admin/providers', 'POST', body);
      toast('✅ ارائهدهنده اضافه شد', 3000, 'success');
    }
    closeModal('modal-provider');
    loadProviders();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

async function deleteProvider(id, name) {
  if (!confirm('آیا از حذف «' + name + '» مطمئنید؟')) return;
  try {
    await api('/api/admin/providers/' + id, 'DELETE');
    toast('🗑️ ارائهدهنده حذف شد', 3000, 'success');
    loadProviders();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

let _tokens = [];

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — AGENT CONFIGS
   ═══════════════════════════════════════════════════════════════════════════ */

let _agentConfigs = [];

async function loadAgentConfigs() {
  try {
    _agentConfigs = await api('/api/admin/agent-configs');
    renderAgentConfigs();
  } catch (e) { console.error('loadAgentConfigs:', e); }
}

function renderAgentConfigs() {
  const tbody = $('agent-configs-tbody');
  if (!_agentConfigs.length) {
    tbody.innerHTML = '<tr><td colspan="11" style="text-align:center;color:var(--dim);padding:36px">ایجنت یا رباتی ثبت نشده است — از دکمه «ساخت ایجنت جدید» استفاده کنید</td></tr>';
    return;
  }
  tbody.innerHTML = _agentConfigs.map(c => `
    <tr>
      <td style="color:var(--dim)">${c.id}</td>
      <td style="font-size:22px;text-align:center">${c.icon}</td>
      <td style="font-family:monospace;font-size:12px;color:var(--cyan)">${esc(c.agent_name)}</td>
      <td style="font-weight:700">${esc(c.display_name || c.agent_name)}</td>
      <td style="font-size:11px;color:var(--purple)">${esc(c.provider_name || '—')}</td>
      <td style="font-family:monospace;font-size:11px">${esc(c.model || '—')}</td>
      <td style="color:var(--yellow)">${c.temperature}</td>
      <td class="clip" style="font-family:monospace;font-size:11px">${c.telegram_bot_token ? c.telegram_bot_token.substring(0,10) + '•••' : '<span style="color:var(--dim)">—</span>'}</td>
      <td style="color:var(--cyan);font-size:11px">${esc(c.bot_username || '—')}</td>
      <td>${(c.telegram_bot_token && c.is_active) ? '<span class="status-badge active">● فعال (آنلاین)</span>' : '<span class="status-badge inactive">● غیرفعال (آفلاین)</span>'}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-icon" onclick="editAgentConfig(${c.id})" title="ویرایش">✏️</button>
        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteAgentConfig(${c.id},'${esc(c.agent_name)}')" title="حذف">🗑️</button>
      </td>
    </tr>
  `).join('');
}

const AGENT_TEMPLATES = {
  writer: {
    name: 'writer',
    display: 'نویسنده خلاق (Writer)',
    icon: '✍️',
    desc: 'محتوا، ایمیل، داستان و متون متقاعدکننده',
    prompt: 'You are the Writer Agent. Your role is to generate high-quality content based on the plan provided by the Planner Agent and the original request. Write clearly and professionally.'
  },
  critic: {
    name: 'critic',
    display: 'منتقد (Critic)',
    icon: '🔍',
    desc: 'بازبینی، ویراستاری و بهبود کیفیت متن',
    prompt: 'You are the Critic Agent. Your role is to review the draft content generated by the Writer Agent. Critique it constructively. Look for errors, omissions, tone mismatch, or logic issues, and suggest improvements.'
  },
  analyst: {
    name: 'analyst',
    display: 'تحلیلگر (Analyst)',
    icon: '📊',
    desc: 'مقایسه داده‌ها، ارزیابی گزینه‌ها و تحلیل ساختاری',
    prompt: 'You are the Analyst Agent. Your role is to compare, evaluate, and analyze data or options to assist in decision making.'
  },
  planner: {
    name: 'planner',
    display: 'برنامه‌ریز (Planner)',
    icon: '📋',
    desc: 'طراحی سناریو، نقشه راه و مراحل کار پروژه',
    prompt: 'You are the Planner Agent. Your role is to analyze the user\'s request and construct a detailed plan for the Writer Agent. Outline what points should be covered, the structure of the response, and any specific details to include. Keep it concise. Do not write the final response yourself.'
  },
  researcher: {
    name: 'researcher',
    display: 'محقق (Researcher)',
    icon: '🔬',
    desc: 'تحقیق علمی، جمع‌آوری اطلاعات و وب‌گردی',
    prompt: 'You are the Researcher Agent. Your role is to search for information, synthesize facts, and gather details relevant to the user request.'
  },
  supervisor: {
    name: 'supervisor',
    display: 'ناظر (Supervisor)',
    icon: '🧠',
    desc: 'انتخاب تیم، هماهنگ‌کننده و ترکیب پاسخ نهایی',
    prompt: 'You are the Supervisor Agent. Your role is to oversee the entire system workflow, review the outputs from the Planner, Writer, and Critic, and synthesize the final response to the user. You are the ONLY agent authorized to send the final response directly to the user.'
  }
};

let currentStep = 1;

function showStep(stepNum) {
  currentStep = stepNum;
  $('wz-step-1').style.display = stepNum === 1 ? 'block' : 'none';
  $('wz-step-2').style.display = stepNum === 2 ? 'block' : 'none';
  $('wz-step-3').style.display = stepNum === 3 ? 'block' : 'none';
  
  $('wz-step-1-indicator').style.color = stepNum === 1 ? 'var(--blue)' : 'var(--dim)';
  $('wz-step-1-indicator').style.fontWeight = stepNum === 1 ? '700' : '500';
  
  $('wz-step-2-indicator').style.color = stepNum === 2 ? 'var(--blue)' : 'var(--dim)';
  $('wz-step-2-indicator').style.fontWeight = stepNum === 2 ? '700' : '500';
  
  $('wz-step-3-indicator').style.color = stepNum === 3 ? 'var(--blue)' : 'var(--dim)';
  $('wz-step-3-indicator').style.fontWeight = stepNum === 3 ? '700' : '500';
  
  $('wz-prev-btn').style.display = stepNum > 1 ? 'inline-flex' : 'none';
  $('wz-next-btn').style.display = stepNum < 3 ? 'inline-flex' : 'none';
  $('wz-save-btn').style.display = stepNum === 3 ? 'inline-flex' : 'none';
}

function nextWizardStep() {
  if (currentStep === 1) {
    if (!$('ac-name').value.trim()) {
      toast('نام انگلیسی ایجنت الزامی است', 3000, 'error');
      return;
    }
    showStep(2);
  } else if (currentStep === 2) {
    showStep(3);
  }
}

function prevWizardStep() {
  if (currentStep > 1) {
    showStep(currentStep - 1);
  }
}

function applyAgentTemplate(val) {
  if (!val || !AGENT_TEMPLATES[val]) return;
  const t = AGENT_TEMPLATES[val];
  $('ac-name').value = t.name;
  $('ac-display').value = t.display;
  $('ac-icon').value = t.icon;
  $('ac-desc').value = t.desc;
  $('ac-prompt').value = t.prompt;
}

function selectTemplateCard(tplName) {
  document.querySelectorAll('.ac-tpl-card').forEach(el => {
    el.style.borderColor = 'var(--bd)';
    el.style.boxShadow = 'none';
  });
  
  const clicked = event.currentTarget;
  clicked.style.borderColor = 'var(--blue)';
  clicked.style.boxShadow = '0 0 10px rgba(72,149,239,0.15)';
  
  if (tplName === 'custom') {
    $('ac-name').value = '';
    $('ac-display').value = '';
    $('ac-icon').value = '🤖';
    $('ac-desc').value = '';
    $('ac-prompt').value = '';
  } else {
    applyAgentTemplate(tplName);
  }
  
  setTimeout(() => {
    nextWizardStep();
  }, 350);
}

async function generateAgentWithAI() {
  const desc = $('ac-ai-desc').value.trim();
  if (!desc) {
    toast('لطفاً توصیف ایجنت را وارد کنید', 3000, 'error');
    return;
  }
  const btn = $('ac-ai-btn');
  btn.disabled = true;
  btn.textContent = 'در حال تولید... ⏳';
  try {
    const res = await api('/api/admin/generate-agent-prompt', 'POST', { description: desc });
    $('ac-name').value = res.agent_name || '';
    $('ac-display').value = res.display_name || '';
    $('ac-icon').value = res.icon || '🤖';
    $('ac-desc').value = res.description || '';
    $('ac-prompt').value = res.system_prompt || '';
    if (res.temperature != null) $('ac-temp').value = res.temperature;
    if (res.max_tokens != null) $('ac-max-tokens').value = res.max_tokens;
    
    toast('✨ مشخصات ایجنت با موفقیت تولید شد!', 3000, 'success');
    
    // Highlight custom card or clear other cards since it's custom
    document.querySelectorAll('.ac-tpl-card').forEach(el => {
      el.style.borderColor = 'var(--bd)';
      el.style.boxShadow = 'none';
    });
    
    // Auto advance to step 2 after success
    setTimeout(() => {
      showStep(2);
    }, 800);
  } catch (e) {
    toast('❌ خطا: ' + e.message, 4000, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'تولید 🪄';
  }
}

async function onProviderChange(providerId) {
  const dl = $('ac-model-list');
  dl.innerHTML = '';
  if (!providerId) return;
  try {
    const models = await api('/api/admin/models?provider_id=' + providerId);
    models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      dl.appendChild(opt);
    });
  } catch (e) {
    console.error('onProviderChange error:', e);
  }
}

async function testAgentModelConnection() {
  const providerId = $('ac-provider').value;
  const model = $('ac-model').value.trim();
  if (!providerId) { toast('لطفاً ابتدا ارائه‌دهنده را انتخاب کنید', 3000, 'error'); return; }
  if (!model) { toast('لطفاً نام مدل را وارد کنید', 3000, 'error'); return; }
  
  const btn = $('btn-test-model');
  btn.disabled = true;
  btn.textContent = 'در حال تست... ⏳';
  try {
    const res = await api('/api/admin/test-connection', 'POST', { provider_id: parseInt(providerId), model });
    toast('✅ اتصال موفق! پاسخ: ' + res.response_preview + ' (تأخیر: ' + res.latency + ' ثانیه)', 5000, 'success');
  } catch (e) {
    toast('❌ خطا: ' + e.message, 6000, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔌 تست اتصال مدل';
  }
}

function populateProviderSelect() {
  const sel = $('ac-provider');
  sel.innerHTML = '<option value="">— پیشفرض —</option>';
  _providers.filter(p => p.is_active).forEach(p => {
    sel.innerHTML += `<option value="${p.id}">${esc(p.name)}</option>`;
  });
}

function openAgentConfigModal(data) {
  populateProviderSelect();
  $('ac-ai-desc').value = '';
  
  document.querySelectorAll('.ac-tpl-card').forEach(el => {
    el.style.borderColor = 'var(--bd)';
    el.style.boxShadow = 'none';
  });
  
  $('modal-ac-title').textContent = data ? 'ویرایش تنظیمات Agent' : 'ساخت ایجنت جدید (مرحله به مرحله)';
  $('ac-edit-id').value = data ? data.id : '';
  $('ac-name').value = data ? data.agent_name : '';
  $('ac-display').value = data ? data.display_name : '';
  $('ac-icon').value = data ? data.icon : '🤖';
  $('ac-provider').value = data && data.provider_id ? data.provider_id : '';
  $('ac-model').value = data ? data.model : '';
  $('ac-temp').value = data ? data.temperature : '0.7';
  $('ac-desc').value = data ? data.description : '';
  $('ac-prompt').value = data ? data.system_prompt : '';
  $('ac-max-tokens').value = data ? data.max_tokens : 4096;
  $('ac-active').checked = data ? !!data.is_active : true;
  $('ac-bot-token').value = data && data.telegram_bot_token ? data.telegram_bot_token : '';
  
  if (data && data.provider_id) {
    onProviderChange(data.provider_id);
  } else {
    $('ac-model-list').innerHTML = '';
  }
  
  showStep(1);
  openModal('modal-agent-config');
}

async function editAgentConfig(id) {
  const c = _agentConfigs.find(x => x.id === id);
  if (c) openAgentConfigModal(c);
}

async function saveAgentConfig() {
  const id = $('ac-edit-id').value;
  const agentName = $('ac-name').value.trim();
  if (!agentName) { toast('نام Agent الزامی است', 3000, 'error'); return; }
  const body = {
    agent_name: agentName,
    display_name: $('ac-display').value.trim(),
    icon: $('ac-icon').value.trim() || '🤖',
    provider_id: $('ac-provider').value ? parseInt($('ac-provider').value) : null,
    model: $('ac-model').value.trim(),
    temperature: parseFloat($('ac-temp').value) || 0.7,
    description: $('ac-desc').value.trim(),
    system_prompt: $('ac-prompt').value,
    max_tokens: parseInt($('ac-max-tokens').value) || 4096,
    is_active: $('ac-active').checked,
    telegram_bot_token: $('ac-bot-token').value.trim() || null,
  };
  try {
    if (id) {
      await api('/api/admin/agent-configs/' + id, 'PUT', body);
      toast('✅ تنظیمات Agent بروزرسانی شد', 3000, 'success');
    } else {
      await api('/api/admin/agent-configs', 'POST', body);
      toast('✅ تنظیمات Agent اضافه شد', 3000, 'success');
    }
    closeModal('modal-agent-config');
    loadAgentConfigs();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

async function deleteAgentConfig(id, name) {
  if (!confirm('آیا از حذف تنظیمات «' + name + '» مطمئنید؟')) return;
  try {
    await api('/api/admin/agent-configs/' + id, 'DELETE');
    toast('🗑️ تنظیمات Agent حذف شد', 3000, 'success');
    loadAgentConfigs();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — TEST, STATS, EXPORT/IMPORT
   ═══════════════════════════════════════════════════════════════════════════ */

async function loadAdminStats() {
  try {
    const s = await api('/api/admin/stats');
    $('admin-prov-total').innerHTML = fa(s.providers_total) + ' <small style="font-size:14px;color:var(--green)">/ ' + fa(s.providers_active) + '</small>';
    $('admin-tok-total').innerHTML = fa(s.tokens_total) + ' <small style="font-size:14px;color:var(--green)">/ ' + fa(s.tokens_active) + '</small>';
    $('admin-ag-total').innerHTML = fa(s.agents_total) + ' <small style="font-size:14px;color:var(--green)">/ ' + fa(s.agents_active) + '</small>';
  } catch {}
}

async function testProvider(id, name) {
  toast('🔌 در حال تست اتصال «' + name + '»...', 8000);
  const model = prompt('مدل برای تست (مثال: gpt-4o-mini):', 'gpt-4o-mini');
  if (!model) return;
  try {
    const res = await api('/api/admin/test-connection', 'POST', { provider_id: id, model });
    toast('✅ اتصال موفق! تاخیر: ' + res.latency + ' ثانیه', 5000, 'success');
  } catch (e) {
    toast('❌ خطا در اتصال: ' + e.message, 6000, 'error');
  }
}

async function testToken(id, name) {
  toast('🔌 در حال تست توکن «' + name + '»...', 5000);
  try {
    const res = await api('/api/admin/test-token/' + id, 'POST');
    toast('✅ توکن مvalid — ربات: ' + res.bot_name + ' (' + res.bot_username + ')', 5000, 'success');
  } catch (e) {
    toast('❌ توکن نامvalid: ' + e.message, 6000, 'error');
  }
}

async function doExport() {
  try {
    const data = await api('/api/admin/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'admin-backup-' + new Date().toISOString().slice(0,10) + '.json';
    a.click(); URL.revokeObjectURL(url);
    toast('📤 فایل بکاپ دانلود شد', 3000, 'success');
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

function doImport() {
  const input = document.createElement('input');
  input.type = 'file'; input.accept = '.json';
  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const overwrite = confirm('آیا میخواهید دادههای موجود را بازنویسی کنید؟\n(بله = بازنویسی، خیر = ادغام)');
      const res = await api('/api/admin/import', 'POST', { data, overwrite });
      toast('📥 وارد شد: ' + fa(res.counts.providers) + ' ارائهدهنده، ' + fa(res.counts.tokens) + ' توکن، ' + fa(res.counts.agent_configs) + ' Agent', 5000, 'success');
      loadAdminData();
      loadAdminStats();
    } catch (err) { toast('❌ خطا: ' + err.message, 5000, 'error'); }
  };
  input.click();
}

/* ─── load all admin data ────────────────────────────────────────────── */
async function loadAdminData() {
  await loadProviders();
  await loadAgentConfigs();
  await loadAdminStats();
}

/* ─── SSE: activity stream ───────────────────────────────────────────── */
let _evCount = 0;
function startSSE() {
  const es = new EventSource('/api/activity-stream');
  const feed = $('activity-feed');
  es.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      const el = document.createElement('div');
      el.className = 'ev ' + (d.type || '');
      el.innerHTML =
        `<span class="ev-t">${esc(d.time || '')}</span>` +
        `<span class="ev-m">${esc(d.text || d.message || '')}</span>`;
      feed.appendChild(el);
      feed.scrollTop = feed.scrollHeight;
      _evCount++;
      $('feed-count').textContent = fa(_evCount) + ' رویداد';
    } catch {}
  };
  es.onerror = () => {
    setOnline(false);
    setTimeout(() => { es.close(); startSSE(); }, 5000);
  };
}

/* ─── BOOT ───────────────────────────────────────────────────────────── */
fetchStats();
fetchAgents();
fetchConversations();
startSSE();

async function loadMonitoringData() {
  try {
    const data = await api('/api/admin/health-check');
    $('mon-cpu').textContent = data.server.cpu_percent.toFixed(1) + '%';
    $('mon-ram').textContent = data.server.memory_percent.toFixed(1) + '%';
    
    let uptime = data.server.uptime_seconds;
    let h = Math.floor(uptime / 3600);
    let m = Math.floor((uptime % 3600) / 60);
    let s = uptime % 60;
    $('mon-uptime').textContent = `${h} ساعت و ${m} دقیقه و ${s} ثانیه`;
    
    const bList = $('mon-bots-list');
    if (!data.bots.length) {
      bList.innerHTML = '<div style="color:var(--dim);font-size:11px">رباتی در دیتابیس فعال نیست.</div>';
    } else {
      bList.innerHTML = data.bots.map(b => `
        <div style="display:flex;justify-content:space-between;align-items:center;background:var(--s2);padding:8px 12px;border-radius:var(--radius-sm);border:1px solid var(--bd)">
          <span>🤖 <strong>${esc(b.name)}</strong> <span style="font-size:11px;color:var(--dim)">(${esc(b.username)})</span></span>
          <span class="tag ${b.status === 'online' ? 'runs' : 'model'}" style="font-size:10px">${b.status === 'online' ? '🟢 متصل' : '🔴 غیرفعال'}</span>
        </div>
      `).join('');
    }
    
    const pList = $('mon-providers-list');
    if (!data.providers.length) {
      pList.innerHTML = '<div style="color:var(--dim);font-size:11px">ارائه‌دهنده‌ای ثبت نشده است.</div>';
    } else {
      pList.innerHTML = data.providers.map(p => `
        <div style="display:flex;justify-content:space-between;align-items:center;background:var(--s2);padding:8px 12px;border-radius:var(--radius-sm);border:1px solid var(--bd)">
          <span>🌐 <strong>${esc(p.name)}</strong></span>
          <div style="display:flex;align-items:center;gap:10px">
            ${p.latency_ms > 0 ? `<span style="font-size:11px;color:var(--dim)">تأخیر: ${p.latency_ms}ms</span>` : ''}
            <span class="tag ${p.status === 'online' ? 'runs' : (p.status === 'disabled' ? 'model' : 'model')}" style="font-size:10px">
              ${p.status === 'online' ? '🟢 آنلاین' : (p.status === 'disabled' ? '⚪️ غیرفعال' : '🔴 آفلاین')}
            </span>
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    console.error('loadMonitoringData:', e);
  }
}

async function loadSystemLogs() {
  try {
    const data = await api('/api/admin/system-logs');
    const con = $('mon-console');
    if (!con) return;
    if (!data.logs || !data.logs.length) {
      con.textContent = 'کنسول خالی است یا فایلی یافت نشد.';
      return;
    }
    con.textContent = data.logs.join('\n');
    con.scrollTop = con.scrollHeight;
  } catch (e) {
    console.error('loadSystemLogs:', e);
  }
}

setInterval(fetchStats, 10000);
setInterval(fetchAgents, 15000);
setInterval(fetchConversations, 20000);
setInterval(() => {
  if ($('page-monitoring') && $('page-monitoring').classList.contains('active')) {
    loadMonitoringData();
    loadSystemLogs();
  }
}, 5000);
</script>
</body>
</html>
"""


# ── Dashboard data: per-agent summary from live stats ──────────────────────

def _agent_rows():
    """Return one dict per loaded agent using dynamic instance attributes."""
    rows = []
    try:
        from utils.agent_loader import discover_agents
        agents = discover_agents()
        for name, ag in agents.items():
            if not getattr(ag, "is_active", True):
                continue
            
            token = None
            bot_user = None
            try:
                from core.admin_db import get_agent_config_by_name
                cfg = get_agent_config_by_name(name)
                if cfg:
                    token = cfg.get("telegram_bot_token")
                    bot_user = cfg.get("bot_username")
            except Exception:
                pass

            if not token:
                continue

            rows.append({
                "name":        name,
                "icon":        getattr(ag, "icon", None) or getattr(ag, "ICON", "🤖"),
                "role":        getattr(ag, "role", None) or getattr(ag, "ROLE", name),
                "model":       getattr(ag, "model", "?"),
                "temperature": getattr(ag, "temperature", None) or getattr(ag, "TEMPERATURE", 0.7),
                "description": getattr(ag, "description", None) or getattr(ag, "DESCRIPTION", ""),
                "system_prompt": getattr(ag, "system_prompt", ""),
                "max_tokens":  getattr(ag, "max_tokens", 4096),
                "is_active":   getattr(ag, "is_active", True),
                "runs":        stats.agent_runs.get(name, 0),
                "telegram_bot_token": token,
                "bot_username": bot_user,
            })
    except Exception:
        pass
    return rows


def _conversations():
    """Format recent conversations from live stats."""
    out = []
    for c in stats.conversations_list():
        out.append({
            "username":  c.get("username", "?"),
            "message":   c.get("message", ""),
            "response":  c.get("response", ""),
            "agents":    c.get("agents", []),
            "duration":  round(c.get("duration", 0), 1),
            "time":      c.get("time", ""),
        })
    return out


# ── FastAPI routes ──────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return _LOGIN_HTML


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, response: Response):
    from core.admin_db import get_setting
    stored_user = get_setting("panel_username", "admin")
    stored_hash = get_setting("panel_password_hash", _hash_pw("admin"))
    if body.username == stored_user and _hash_pw(body.password) == stored_hash:
        token = _create_session()
        response.set_cookie(
            "ra_session", token,
            max_age=SESSION_LIFETIME, httponly=True, samesite="lax", path="/"
        )
        return {"status": "ok"}
    return JSONResponse({"detail": "Invalid credentials"}, status_code=401)


@app.post("/api/auth/logout")
async def auth_logout(response: Response):
    response.delete_cookie("ra_session", path="/")
    return {"status": "ok"}


@app.post("/api/auth/change-credentials")
async def change_credentials(body: ChangeCredentialsRequest):
    from core.admin_db import get_setting, set_setting
    stored_hash = get_setting("panel_password_hash", _hash_pw("admin"))
    if _hash_pw(body.current_password) != stored_hash:
        return JSONResponse({"detail": "رمز عبور فعلی اشتباه است"}, status_code=400)
    if not body.new_username.strip():
        return JSONResponse({"detail": "نام کاربری نمی‌تواند خالی باشد"}, status_code=400)
    if len(body.new_password) < 4:
        return JSONResponse({"detail": "رمز عبور باید حداقل ۴ کاراکتر باشد"}, status_code=400)
    set_setting("panel_username", body.new_username.strip())
    set_setting("panel_password_hash", _hash_pw(body.new_password))
    # Invalidate all existing sessions
    _sessions.clear()
    return {"status": "ok"}


@app.get("/api/auth/me")
async def auth_me(request: Request):
    from core.admin_db import get_setting
    return {"username": get_setting("panel_username", "admin")}


@app.get("/", response_class=HTMLResponse)
async def index():
    return _HTML


@app.get("/health")
async def health():
    """Simple liveness probe — used by uptime monitors, Docker healthcheck, etc."""
    import time as _t
    uptime = int(_t.time() - stats.start_time)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "total_messages": stats.total_messages,
        "agents_loaded": len(_agent_rows()),
    }


@app.get("/api/stats")
async def api_stats():
    return stats.to_dict()


@app.get("/api/agents")
async def api_agents():
    return _agent_rows()


@app.get("/api/conversations")
async def api_conversations():
    return _conversations()


@app.get("/api/config")
async def api_config():
    models = {}
    for key in dir(Config):
        if key.startswith("MODEL_") and key != "MODEL_DEFAULT":
            models[key.replace("MODEL_", "")] = getattr(Config, key)
    return {
        "bynara_model":             Config.BYNARA_MODEL,
        "bynara_supervisor_model":  Config.BYNARA_SUPERVISOR_MODEL,
        "bynara_base_url":          Config.BYNARA_BASE_URL,
        "agent_models":             models,
        "agent_temperature":        str(getattr(Config, "AGENT_TEMPERATURE", 0.7)),
        "supervisor_temperature":   str(getattr(Config, "SUPERVISOR_TEMPERATURE", 0.4)),
        "max_history":              str(Config.MAX_HISTORY),
        "bot_respond_to_all":       str(getattr(Config, "BOT_RESPOND_TO_ALL", False)).lower(),
        "rate_limit_seconds":       str(getattr(Config, "RATE_LIMIT_SECONDS", 3)),
        "langsmith_tracing":        str(getattr(Config, "LANGSMITH_TRACING", False)).lower(),
        "langsmith_project":        getattr(Config, "LANGSMITH_PROJECT", ""),
        "log_level":                getattr(Config, "LOG_LEVEL", "INFO"),
    }


# ── SSE: live activity feed ────────────────────────────────────────────────

@app.get("/api/activity-stream")
async def activity_stream():
    async def gen():
        last_seq = 0
        while True:
            events = stats.activity_since(last_seq)
            for ev in events:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev["seq"] > last_seq:
                    last_seq = ev["seq"]
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN CRUD ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

from core.admin_db import (
    init_db, seed_defaults,
    get_all_providers, get_provider, add_provider, update_provider, delete_provider,
    get_all_tokens, get_token, add_token, update_token, delete_token,
    get_all_agent_configs, get_agent_config, update_agent_config, delete_agent_config,
    upsert_agent_config,
    get_admin_stats, export_all, import_all,
    get_all_settings, set_setting,
)


@app.on_event("startup")
async def _init_admin_db():
    init_db()
    seed_defaults()


# ── AI Providers ────────────────────────────────────────────────────────────

@app.get("/api/admin/providers")
async def list_providers():
    return get_all_providers()


@app.post("/api/admin/providers")
async def create_provider(body: ProviderCreate):
    try:
        pid = add_provider(
            name=body.name, base_url=body.base_url, api_key=body.api_key,
            provider_type=body.provider_type, description=body.description,
            is_active=body.is_active,
        )
        return {"id": pid, "status": "created"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/admin/providers/{pid}")
async def get_provider_detail(pid: int):
    p = get_provider(pid)
    if not p:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return p


@app.put("/api/admin/providers/{pid}")
async def update_provider_route(pid: int, body: ProviderUpdate):
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not fields:
        return JSONResponse(status_code=400, content={"detail": "فیلدی ارسال نشد"})
    ok = update_provider(pid, **fields)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "updated"}


@app.delete("/api/admin/providers/{pid}")
async def delete_provider_route(pid: int):
    ok = delete_provider(pid)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "deleted"}


# ── Bot Tokens ──────────────────────────────────────────────────────────────

@app.get("/api/admin/tokens")
async def list_tokens():
    return get_all_tokens()


@app.post("/api/admin/tokens")
async def create_token(body: TokenCreate):
    try:
        tid = add_token(
            name=body.name, token=body.token,
            bot_username=body.bot_username, description=body.description,
            is_active=body.is_active,
            agent_config_id=body.agent_config_id,
        )
        return {"id": tid, "status": "created"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/admin/tokens/{tid}")
async def get_token_detail(tid: int):
    t = get_token(tid)
    if not t:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return t


@app.put("/api/admin/tokens/{tid}")
async def update_token_route(tid: int, body: TokenUpdate):
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not fields:
        return JSONResponse(status_code=400, content={"detail": "فیلدی ارسال نشد"})
    ok = update_token(tid, **fields)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "updated"}


@app.delete("/api/admin/tokens/{tid}")
async def delete_token_route(tid: int):
    ok = delete_token(tid)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "deleted"}


# ── Agent Configs ───────────────────────────────────────────────────────────

@app.get("/api/admin/agent-configs")
async def list_agent_configs():
    return get_all_agent_configs()


@app.post("/api/admin/agent-configs")
async def create_agent_config(body: AgentConfigCreate):
    try:
        # Resolve bot username if token is provided
        bot_username = None
        token_str = body.telegram_bot_token.strip() if body.telegram_bot_token else ""
        if token_str:
            try:
                import urllib.request
                import json
                url = f"https://api.telegram.org/bot{token_str}/getMe"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    res_data = json.loads(resp.read())
                    if res_data.get("ok"):
                        bot_username = "@" + res_data["result"].get("username", "")
            except Exception as e:
                logger.warning(f"Failed to fetch bot username on create: {e}")

        cid = upsert_agent_config(
            agent_name=body.agent_name, display_name=body.display_name,
            icon=body.icon, description=body.description,
            provider_id=body.provider_id, model=body.model,
            temperature=body.temperature, system_prompt=body.system_prompt,
            max_tokens=body.max_tokens, is_active=body.is_active,
            extra_config=body.extra_config,
            telegram_bot_token=token_str or None,
            bot_username=bot_username,
        )
        return {"id": cid, "status": "created"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/admin/agent-configs/{cid}")
async def get_agent_config_detail(cid: int):
    c = get_agent_config(cid)
    if not c:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return c


@app.put("/api/admin/agent-configs/{cid}")
async def update_agent_config_route(cid: int, body: AgentConfigUpdate):
    try:
        # Resolve bot username if token is provided
        bot_username = None
        token_str = body.telegram_bot_token.strip() if body.telegram_bot_token is not None else None
        
        # If token is provided, verify it via Telegram API
        if token_str:
            try:
                import urllib.request
                import json
                url = f"https://api.telegram.org/bot{token_str}/getMe"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    res_data = json.loads(resp.read())
                    if res_data.get("ok"):
                        bot_username = "@" + res_data["result"].get("username", "")
            except Exception as e:
                logger.warning(f"Failed to fetch bot username on update: {e}")
        
        fields = {k: v for k, v in body.dict().items() if v is not None and k != "telegram_bot_token"}
        if token_str is not None:
            fields["telegram_bot_token"] = token_str or None
            fields["bot_username"] = bot_username
            
        if not fields:
            return JSONResponse(status_code=400, content={"detail": "فیلدی ارسال نشد"})
            
        ok = update_agent_config(cid, **fields)
        if not ok:
            return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
            
        return {"status": "updated"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.delete("/api/admin/agent-configs/{cid}")
async def delete_agent_config_route(cid: int):
    ok = delete_agent_config(cid)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "deleted"}


# ── Admin Stats ─────────────────────────────────────────────────────────────

@app.get("/api/admin/stats")
async def admin_stats():
    return get_admin_stats()


# ── Global Settings & Dynamic Models ───────────────────────────────────────

@app.get("/api/admin/settings")
async def list_settings():
    return get_all_settings()


@app.post("/api/admin/settings")
async def save_settings(body: SettingsUpdate):
    try:
        for k, v in body.settings.items():
            set_setting(k, str(v))
        
        # Re-apply LangSmith tracing parameters dynamically
        from utils.config import Config
        Config.setup_langsmith()
        
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/admin/memories")
async def get_memories():
    try:
        from core.admin_db import get_conn
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM memories ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.delete("/api/admin/memories/{id}")
async def delete_memory(id: int):
    try:
        from core.admin_db import get_conn
        with get_conn() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (id,))
        return {"status": "success"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.get("/api/admin/models")
async def list_provider_models(provider_id: Optional[int] = None):
    if not provider_id:
        return []
    import requests
    from core.admin_db import get_provider
    prov = get_provider(provider_id)
    if not prov:
        return []
    
    base_url = prov["base_url"].rstrip('/')
    api_key = prov.get("api_key", "")
    
    url = f"{base_url}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and "data" in data:
                models = [m["id"] for m in data["data"]]
                return sorted(models)
            elif isinstance(data, list):
                return sorted(data)
    except Exception as e:
        logger.warning(f"Failed to fetch models from {url}: {e}")
        
    if "localhost" in base_url or "127.0.0.1" in base_url:
        ollama_url = f"{base_url.rsplit('/', 1)[0]}/api/tags"
        try:
            res = requests.get(ollama_url, timeout=3)
            if res.status_code == 200:
                data = res.json()
                if "models" in data:
                    models = [m["name"] for m in data["models"]]
                    return sorted(models)
        except Exception:
            pass
            
    name_lower = prov["name"].lower()
    if "openai" in name_lower:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    elif "bynara" in name_lower:
        return ["mistralai/mistral-medium-3", "meta-llama/llama-3-70b-instruct", "openai/gpt-4o"]
    elif "gemini" in name_lower or "google" in name_lower:
        return ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.0-pro"]
    elif "anthropic" in name_lower or "claude" in name_lower:
        return ["claude-3-5-sonnet-20240620", "claude-3-opus-20240229", "claude-3-haiku-20240307"]
    elif "groq" in name_lower:
        return ["llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768", "gemma-7b-it"]
    
    return ["gpt-4o-mini"]


# ── Test Provider Connection ────────────────────────────────────────────────

@app.post("/api/admin/test-connection")
async def test_connection(body: TestConnectionRequest):
    """Test an AI provider connection by sending a minimal request."""
    import time as _time
    try:
        from services.llm_service import create_llm_from_provider
        llm = create_llm_from_provider(body.provider_id, body.model)
        if not llm:
            return JSONResponse(status_code=404, content={"detail": "ارائهدهنده یافت نشد"})
        
        t0 = _time.time()
        response = llm.invoke("Say 'ok' in one word.")
        latency = round(_time.time() - t0, 2)
        
        return {
            "status": "ok",
            "latency": latency,
            "model": body.model,
            "response_preview": str(response.content)[:100],
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={
            "status": "error",
            "detail": str(e)[:300],
        })


# ── Test Bot Token ──────────────────────────────────────────────────────────

@app.post("/api/admin/test-token/{tid}")
async def test_token(tid: int):
    """Validate a Telegram bot token by calling getMe API."""
    import urllib.request
    t = get_token(tid)
    if not t:
        return JSONResponse(status_code=404, content={"detail": "توکن یافت نشد"})
    try:
        url = f"https://api.telegram.org/bot{t['token']}/getMe"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                bot = data["result"]
                return {
                    "status": "ok",
                    "bot_name": bot.get("first_name", ""),
                    "bot_username": "@" + bot.get("username", ""),
                }
            return JSONResponse(status_code=400, content={"status": "error", "detail": "توکن نامعتبر است"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "error", "detail": str(e)[:200]})


# ── Reload agents (apply admin config changes without restart) ───────────────

@app.post("/api/admin/reload-agents")
async def reload_agents():
    """
    Clear the agent cache so the next request reloads agents with fresh DB config.
    Call this after editing agent configs, system prompts, or provider assignments
    in the admin panel — no bot restart needed.
    """
    try:
        from utils.agent_loader import reset_cache
        reset_cache()
        # Immediately warm the cache back up so /api/agents returns fresh data
        from utils.agent_loader import discover_agents
        agents = discover_agents()
        return {
            "status": "reloaded",
            "agents": list(agents.keys()),
            "message": f"✅ {len(agents)} Agent با تنظیمات جدید بارگذاری شد.",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


# ── Export / Import ─────────────────────────────────────────────────────────

@app.get("/api/admin/export")
async def export_config():
    """Export all admin configuration as JSON."""
    return export_all()


@app.post("/api/admin/import")
async def import_config(body: ImportRequest):
    """Import admin configuration from JSON."""
    try:
        counts = import_all(body.data, overwrite=body.overwrite)
        return {"status": "imported", "counts": counts}
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})


@app.post("/api/admin/generate-agent-prompt")
async def generate_agent_prompt(body: GenerateAgentRequest):
    if not body.description.strip():
        return JSONResponse(status_code=400, content={"detail": "توضیحات نمی‌تواند خالی باشد"})
    
    from services.llm_service import create_llm
    from langchain_core.messages import SystemMessage, HumanMessage
    import json
    
    prompt = f"""You are an AI Agent Config Generator. Based on the user's brief description, generate a complete profile configuration for a specialized AI agent.
    
    User Description: "{body.description}"
    
    You must output a valid JSON object ONLY. No markdown formatting, no backticks, no code fence, no text before or after.
    
    JSON Schema:
    {{
      "agent_name": "lowercase_snake_case_english_name",
      "display_name": "Friendly Persian display name",
      "icon": "One single emoji related to the role",
      "description": "Short Persian description of what this agent does",
      "system_prompt": "Highly detailed system prompt in English instructing the agent on its role, persona, and rules of engagement.",
      "temperature": 0.7,
      "max_tokens": 4096
    }}
    
    Ensure the system_prompt is comprehensive and professional.
    """
    
    try:
        llm = create_llm()
        response = llm.invoke([
            SystemMessage(content="You are a JSON generator. Respond only with valid JSON."),
            HumanMessage(content=prompt)
        ])
        
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        parsed = json.loads(content)
        return parsed
    except Exception as e:
        logger.error(f"Error generating agent prompt: {e}")
        return JSONResponse(status_code=500, content={"detail": f"خطا در تولید مشخصات ایجنت: {str(e)}"})


@app.get("/api/admin/system-logs")
async def get_system_logs(lines: int = 150):
    """Read the last N lines of logs/app.log."""
    import os
    log_file = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "logs", "app.log")
    )
    if not os.path.exists(log_file):
        log_file = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "logs", "app.log")
        )
        
    if not os.path.exists(log_file):
        return {"logs": ["Log file not found."]}
        
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            last_n = [l.strip() for l in all_lines[-lines:]]
            return {"logs": last_n}
    except Exception as e:
        return {"logs": [f"Error reading logs: {e}"]}


@app.get("/api/admin/health-check")
async def get_health_check():
    import time
    import requests
    from core.admin_db import get_active_tokens, get_all_providers
    
    cpu = 0.0
    mem_percent = 0.0
    try:
        import psutil
        cpu = psutil.cpu_percent()
        mem_percent = psutil.virtual_memory().percent
    except ImportError:
        pass
        
    uptime = int(time.time() - stats.start_time)
    
    server_status = {
        "status": "healthy",
        "cpu_percent": cpu,
        "memory_percent": mem_percent,
        "uptime_seconds": uptime,
        "db_connected": True,
    }
    
    providers_status = []
    providers = get_all_providers()
    for p in providers:
        if not p["is_active"]:
            providers_status.append({
                "name": p["name"],
                "status": "disabled",
                "latency_ms": 0,
            })
            continue
        
        status = "offline"
        latency = 9999
        t0 = time.time()
        try:
            url = p["base_url"]
            res = requests.get(url, timeout=3)
            status = "online"
            latency = int((time.time() - t0) * 1000)
        except Exception:
            status = "offline"
            
        providers_status.append({
            "name": p["name"],
            "status": status,
            "latency_ms": latency if status == "online" else 0,
        })
        
    bots_status = []
    tokens = get_active_tokens()
    for t in tokens:
        status = "offline"
        try:
            url = f"https://api.telegram.org/bot{t['token']}/getMe"
            res = requests.get(url, timeout=3)
            if res.status_code == 200:
                status = "online"
        except Exception:
            status = "offline"
            
        bots_status.append({
            "name": t["name"],
            "username": t.get("bot_username", "—"),
            "status": status,
        })
        
    from utils.agent_loader import discover_agents
    loaded_agents = []
    try:
        agents = discover_agents()
        for name, ag in agents.items():
            loaded_agents.append({
                "name": name,
                "display_name": getattr(ag, "display_name", name),
                "is_active": getattr(ag, "is_active", True),
            })
    except Exception:
        pass
        
    return {
        "server": server_status,
        "providers": providers_status,
        "bots": bots_status,
        "agents": loaded_agents,
    }


# ── start_panel helper (called from main.py) ────────────────────────────────

async def start_panel() -> None:
    """Start the uvicorn server in-process."""
    config = uvicorn.Config(
        app,
        host=Config.PANEL_HOST,
        port=Config.PANEL_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()
