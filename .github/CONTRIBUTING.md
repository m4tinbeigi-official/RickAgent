# Contributing to AgentRick

Thanks for wanting to contribute! Here are the most common ways:

---

## 🤖 Adding a New Agent (easiest contribution)

1. Fork the repo and create a branch: `git checkout -b feat/my-agent`
2. Create `agents/my_agent.py`:

```python
from agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    NAME        = "my_agent"          # unique snake_case identifier
    ROLE        = "My Role"           # shown in /agents command
    DESCRIPTION = "What I do"        # Supervisor reads this to decide routing
    ICON        = "🛠️"
    TEMPERATURE = 0.7                 # 0.0 = deterministic, 1.0 = creative
    SYSTEM_PROMPT = """
    You are a specialist in ...
    Always respond in the user's language.
    """
```

3. Test it: `source .venv/bin/activate && python3 main.py`
4. Open a PR — describe what your agent does and example prompts that trigger it.

**No other files need to change.** The agent is auto-discovered.

---

## 🐛 Bug Reports

Use the [bug report template](ISSUE_TEMPLATE/bug_report.md).

Include:
- Python version (`python3 --version`)
- Error message or traceback (from `logs/app.log`)
- Steps to reproduce

---

## 💡 Feature Requests

Use the [feature request template](ISSUE_TEMPLATE/feature_request.md).

---

## 🔧 Code Contributions

- Python 3.9+ compatible (use `from __future__ import annotations` for type hints)
- Follow the existing style — no external linter config yet
- All new features should work without changing existing agents

### Running locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python3 main.py
```

---

## 📋 PR Checklist

- [ ] New agent files only touch `agents/` (no graph changes needed)
- [ ] `from __future__ import annotations` at top of any file with type hints
- [ ] Tested locally with at least one real conversation
- [ ] `admin.db`, `.env`, `logs/` are NOT committed (check `.gitignore`)
