# Auto Model Switcher

Never get blocked by "out of credits" again. Auto-discovers all your AI
models across providers, monitors their health, and seamlessly rotates when
one runs out.

![Demo](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-GPLv3-purple)

---

## The Problem

You're in the middle of work and suddenly:

```
Error: 402 Payment Required — insufficient credits
```

Now you have to: stop, check which models have credits, dig into config files,
manually switch models, and restart. Every. Single. Time.

## The Solution

```
python switcher.py watch
```

Scans your CLI configs (OpenCode, Claude Code, Cursor), discovers every model
you have access to, checks their credit/rate-limit health, and when one fails,
automatically switches to the next working model.

**Free models get priority.** Paid models are fallbacks.

No config files to write. No model chains to define. Just API keys in your
existing CLI configs.

---

## Quick Start

```bash
# Clone
git clone https://github.com/farhanic017/auto-model-switcher.git
cd auto-model-switcher

# Install
python install.py

# See what's available
python switcher.py discover

# Switch to best available model
python switcher.py switch

# Or run in background (auto-rotate on failure)
start /B python switcher.py watch
```

### Commands

| Command | What it does |
|---------|-------------|
| `python switcher.py discover` | Scans configs, lists all models found |
| `python switcher.py status` | Shows active model + health of all models |
| `python switcher.py switch` | Rotates to next working model and updates config |
| `python switcher.py watch` | Background daemon — checks every 2min, auto-rotates |

---

## How It Works

### 1. Auto-Discovery

Reads your existing CLI configs — no extra setup:

- **OpenCode**: `opencode.jsonc` — extracts all `provider` sections
- **Claude Code**: `CLAUDE.md` — extracts `model:` line
- **Cursor**: `.cursorrules` / `settings.json`
- **Environment**: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`

### 2. Smart Chain Building

Models are automatically sorted:

```
Priority 1: Google AI free tier (genini/*)
Priority 2: OpenRouter free models (*:free)
Priority 3: OpenRouter paid models
Priority 4: Azure OpenAI models
Priority 5: Direct API models (OpenAI, Anthropic)
```

Within each tier, models are tried in order. If the first fails, it moves to
the next. When all free models are depleted, it rotates to paid.

### 3. Health Checking

| Provider | API Call Used |
|----------|-------------|
| OpenRouter | `GET /api/v1/auth/key` — checks credit balance |
| Google AI | `generateContent` — checks quota and availability |
| Azure OpenAI | `GET /openai/models` — checks key validity |
| OpenAI | Direct completion check |
| Anthropic | Direct completion check |

### 4. Rotation & Recovery

When a model fails (429 rate limit, 0 credits, 402/403 errors):

- Marked as **depleted** with a 30-minute cooldown
- Switcher moves to the next model in the chain
- CLI config is updated automatically (e.g., `opencode.jsonc` `model` field)
- After cooldown, the model is re-checked and re-enters the pool if healthy

---

## Supported CLIs

| CLI | Auto-Detection | Config Update |
|-----|---------------|---------------|
| **OpenCode** | Full (providers + models) | Updates `model` field in `opencode.jsonc` |
| **Claude Code** | Basic (model line in CLAUDE.md) | Updates `model:` in `CLAUDE.md` |
| **Cursor** | Basic (.cursorrules) | Coming soon |

---

## For AI Agents

Give this repo URL to any AI assistant:

```
https://github.com/farhanic017/auto-model-switcher
```

The AI will read `SKILL.md` and set everything up.

---

## Project Structure

```
auto-model-switcher/
├── switcher.py          # Core engine (discovery, health checks, rotation)
├── install.py           # Setup wizard
├── restore.ps1          # Windows restore script
├── SKILL.md             # AI agent instructions
├── README.md            # This file
├── LICENSE              # GPL-3.0
├── .gitignore
├── data/                # Runtime state (auto-created)
│   └── state.json       # Active model + depletion history
├── hooks/               # CLI integration hooks
└── tests/
```

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

Copyright (c) 2026 Farhan Dhrubo
