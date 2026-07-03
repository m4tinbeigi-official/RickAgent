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
import json

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from utils.config import Config
from utils.logger import setup_logger
from utils.stats import stats

logger = setup_logger("panel")

app = FastAPI(title="AI Agent Panel", docs_url=None, redoc_url=None)
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

class TokenUpdate(BaseModel):
    name: Optional[str] = None
    token: Optional[str] = None
    bot_username: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

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

class TestConnectionRequest(BaseModel):
    provider_id: int
    model: str = "gpt-4o-mini"

class ImportRequest(BaseModel):
    data: dict
    overwrite: bool = False


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
  .tab .t-lbl { display: none; }
  .logo em { display: none; }
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
      <button class="sub-tab" onclick="goAdminTab('tokens',this)">🔑 توکنهای ربات</button>
      <button class="sub-tab" onclick="goAdminTab('agent-configs',this)">⚙️ تنظیمات Agentها</button>
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

  <!-- ── Bot Tokens ── -->
  <div id="admin-tokens" class="sub-page">
    <div class="admin-card">
      <div class="action-bar">
        <h3 style="font-size:14px;font-weight:700">🔑 توکن‌های ربات تلگرام</h3>
        <button class="btn btn-primary btn-sm" onclick="openTokenModal()">➕ افزودن توکن</button>
      </div>
      <div class="admin-card-body tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>نام</th><th>نام کاربری</th><th>توکن</th><th>توضیحات</th><th>وضعیت</th><th>عملیات</th>
            </tr>
          </thead>
          <tbody id="tokens-tbody">
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
        <h3 style="font-size:14px;font-weight:700">⚙️ تنظیمات Agentها</h3>
        <button class="btn btn-primary btn-sm" onclick="openAgentConfigModal()">➕ افزودن تنظیمات</button>
      </div>
      <div class="admin-card-body tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th><th>آیکون</th><th>نام Agent</th><th>نام نمایشی</th><th>ارائه‌دهنده</th><th>مدل</th><th>دما</th><th>وضعیت</th><th>عملیات</th>
            </tr>
          </thead>
          <tbody id="agent-configs-tbody">
            <tr><td colspan="9" style="text-align:center;color:var(--dim);padding:36px">در حال بارگذاری...</td></tr>
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

<!-- Token Modal -->
<div class="modal-overlay" id="modal-token">
  <div class="modal">
    <div class="modal-hd">
      <h3 id="modal-token-title">افزودن توکن ربات</h3>
      <button class="modal-close" onclick="closeModal('modal-token')">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="tok-edit-id">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">نام ربات *</label>
          <input class="form-input" id="tok-name" placeholder="مثال: ربات پشتیبانی">
        </div>
        <div class="form-group">
          <label class="form-label">نام کاربری ربات</label>
          <input class="form-input" id="tok-username" placeholder="@mybot">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">توکن ربات تلگرام *</label>
        <input class="form-input" id="tok-token" placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11">
      </div>
      <div class="form-group">
        <label class="form-label">توضیحات</label>
        <input class="form-input" id="tok-desc" placeholder="توضیحات اختیاری">
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" onclick="saveToken()">💾 ذخیره</button>
        <button class="btn" onclick="closeModal('modal-token')">انصراف</button>
      </div>
    </div>
  </div>
</div>

<!-- Agent Config Modal -->
<div class="modal-overlay" id="modal-agent-config">
  <div class="modal" style="width:640px">
    <div class="modal-hd">
      <h3 id="modal-ac-title">افزودن تنظیمات Agent</h3>
      <button class="modal-close" onclick="closeModal('modal-agent-config')">✕</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="ac-edit-id">
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">نام Agent (یکتا) *</label>
          <input class="form-input" id="ac-name" placeholder="مثال: writer">
        </div>
        <div class="form-group">
          <label class="form-label">نام نمایشی</label>
          <input class="form-input" id="ac-display" placeholder="مثال: نویسنده خلاق">
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">آیکون</label>
          <input class="form-input" id="ac-icon" placeholder="✍️" style="text-align:center;font-size:24px">
        </div>
        <div class="form-group">
          <label class="form-label">ارائه‌دهنده</label>
          <select class="form-select" id="ac-provider">
            <option value="">— پیشفرض —</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">مدل</label>
          <input class="form-input" id="ac-model" placeholder="gpt-4o-mini">
        </div>
        <div class="form-group">
          <label class="form-label">دما (Temperature)</label>
          <input class="form-input" id="ac-temp" type="number" min="0" max="2" step="0.1" value="0.7">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">توضیحات</label>
        <input class="form-input" id="ac-desc" placeholder="توضیحات Agent">
      </div>
      <div class="form-group">
        <label class="form-label">System Prompt</label>
        <textarea class="form-textarea" id="ac-prompt" rows="4" placeholder="You are a helpful AI assistant..."></textarea>
      </div>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">حداکثر توکن</label>
          <input class="form-input" id="ac-max-tokens" type="number" value="4096">
        </div>
        <div class="form-group" style="display:flex;align-items:flex-end;padding-bottom:14px">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px">
            <input type="checkbox" id="ac-active" checked style="width:18px;height:18px;cursor:pointer">
            فعال
          </label>
        </div>
      </div>
      <div class="form-actions">
        <button class="btn btn-primary" onclick="saveAgentConfig()">💾 ذخیره</button>
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
    el.innerHTML = '<div class="empty"><div class="empty-icon">🤖</div><p>Agent یافت نشد</p></div>';
    return;
  }
  const maxRuns = Math.max(...list.map(a => a.runs), 1);
  el.innerHTML = list.map(a => `
    <div class="ac">
      <div class="ac-top">
        <div class="ac-emoji">${a.icon}</div>
        <div>
          <div class="ac-name">${esc(a.role)}</div>
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
  `).join('');
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
  } catch {}
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

/* ═══════════════════════════════════════════════════════════════════════════
   ADMIN — BOT TOKENS
   ═══════════════════════════════════════════════════════════════════════════ */

let _tokens = [];

async function loadTokens() {
  try {
    _tokens = await api('/api/admin/tokens');
    renderTokens();
  } catch (e) { console.error('loadTokens:', e); }
}

function renderTokens() {
  const tbody = $('tokens-tbody');
  if (!_tokens.length) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--dim);padding:36px">توکنی ثبت نشده</td></tr>';
    return;
  }
  tbody.innerHTML = _tokens.map(t => `
    <tr>
      <td style="color:var(--dim)">${t.id}</td>
      <td style="font-weight:700">${esc(t.name)}</td>
      <td style="color:var(--cyan)">${esc(t.bot_username || '—')}</td>
      <td class="clip" style="font-family:monospace;font-size:11px">${t.token.substring(0,12)}•••</td>
      <td style="color:var(--dim);font-size:11px">${esc(t.description || '—')}</td>
      <td>${t.is_active ? '<span class="status-badge active">● فعال</span>' : '<span class="status-badge inactive">● غیرفعال</span>'}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-success btn-icon" onclick="testToken(${t.id},'${esc(t.name)}')" title="تست توکن">🔌</button>
        <button class="btn btn-sm btn-icon" onclick="editToken(${t.id})" title="ویرایش">✏️</button>
        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteToken(${t.id},'${esc(t.name)}')" title="حذف">🗑️</button>
      </td>
    </tr>
  `).join('');
}

function openTokenModal(data) {
  $('modal-token-title').textContent = data ? 'ویرایش توکن ربات' : 'افزودن توکن ربات';
  $('tok-edit-id').value = data ? data.id : '';
  $('tok-name').value = data ? data.name : '';
  $('tok-username').value = data ? data.bot_username : '';
  $('tok-token').value = data ? data.token : '';
  $('tok-desc').value = data ? data.description : '';
  openModal('modal-token');
}

async function editToken(id) {
  const t = _tokens.find(x => x.id === id);
  if (t) openTokenModal(t);
}

async function saveToken() {
  const id  = $('tok-edit-id').value;
  const name = $('tok-name').value.trim();
  const tok  = $('tok-token').value.trim();
  if (!name || !tok) { toast('نام و توکن الزامی است', 3000, 'error'); return; }
  const body = {
    name, token: tok,
    bot_username: $('tok-username').value.trim(),
    description: $('tok-desc').value.trim(),
  };
  try {
    if (id) {
      await api('/api/admin/tokens/' + id, 'PUT', body);
      toast('✅ توکن بروزرسانی شد', 3000, 'success');
    } else {
      await api('/api/admin/tokens', 'POST', body);
      toast('✅ توکن اضافه شد', 3000, 'success');
    }
    closeModal('modal-token');
    loadTokens();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

async function deleteToken(id, name) {
  if (!confirm('آیا از حذف توکن «' + name + '» مطمئنید؟')) return;
  try {
    await api('/api/admin/tokens/' + id, 'DELETE');
    toast('🗑️ توکن حذف شد', 3000, 'success');
    loadTokens();
  } catch (e) { toast('❌ ' + e.message, 4000, 'error'); }
}

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
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--dim);padding:36px">تنظیماتی ثبت نشده — از دکمه «افزودن تنظیمات» استفاده کنید</td></tr>';
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
      <td>${c.is_active ? '<span class="status-badge active">● فعال</span>' : '<span class="status-badge inactive">● غیرفعال</span>'}</td>
      <td style="white-space:nowrap">
        <button class="btn btn-sm btn-icon" onclick="editAgentConfig(${c.id})" title="ویرایش">✏️</button>
        <button class="btn btn-sm btn-icon btn-danger" onclick="deleteAgentConfig(${c.id},'${esc(c.agent_name)}')" title="حذف">🗑️</button>
      </td>
    </tr>
  `).join('');
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
  $('modal-ac-title').textContent = data ? 'ویرایش تنظیمات Agent' : 'افزودن تنظیمات Agent';
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
  await loadTokens();
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

setInterval(fetchStats, 10000);
setInterval(fetchAgents, 15000);
setInterval(fetchConversations, 20000);
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
            # Use instance attrs (dynamic, DB-backed) with fallback to class attrs
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
    return {
        "total_messages":    stats.total_messages,
        "total_errors":      stats.total_errors,
        "avg_response_time": round(stats.avg_response_time, 2) if stats.avg_response_time else None,
        "uptime_human":      stats.uptime_human(),
    }


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
        cid = upsert_agent_config(
            agent_name=body.agent_name, display_name=body.display_name,
            icon=body.icon, description=body.description,
            provider_id=body.provider_id, model=body.model,
            temperature=body.temperature, system_prompt=body.system_prompt,
            max_tokens=body.max_tokens, is_active=body.is_active,
            extra_config=body.extra_config,
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
    fields = {k: v for k, v in body.dict().items() if v is not None}
    if not fields:
        return JSONResponse(status_code=400, content={"detail": "فیلدی ارسال نشد"})
    ok = update_agent_config(cid, **fields)
    if not ok:
        return JSONResponse(status_code=404, content={"detail": "یافت نشد"})
    return {"status": "updated"}


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
