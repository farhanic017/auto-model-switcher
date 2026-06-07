# Auto Model Switcher - AI CLI Fallback for OpenCode, Claude Code, Aider, Cursor

**Never get blocked by "out of credits" again.** Auto Model Switcher is an
always-on AI model fallback engine for OpenCode, Claude Code, Aider, Cursor,
Windsurf, Qwen, Gemini CLI, OpenRouter, OpenAI-compatible APIs, and local LLMs.
It discovers your models, learns which ones you use, detects quota/token/usage
failures at runtime, switches to the next best healthy model, and retries the
original command once.

[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-blue)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-green)]()
[![License](https://img.shields.io/badge/license-GPLv3-purple)](LICENSE)
[![Author](https://img.shields.io/badge/author-Farhan%20Dhrubo-red)](https://github.com/farhanic017)

<video src="assets/auto-model-switcher-demo-14s-60fps.mp4" width="100%" autoplay muted loop playsinline preload="auto" controlslist="nodownload" disablepictureinpicture></video>

## Why Developers Star It

- **Fixes the most annoying AI CLI failure:** `429`, `402`, quota exceeded, no credits, token exhausted, free-tier limit.
- **Works across agents and IDEs:** OpenCode, Claude Code, Cursor, VS Code, Windsurf, Aider, Gemini CLI, Qwen CLI, Codex-style agents, and MCP configs.
- **Supports every configured provider:** OpenRouter, OpenAI, Anthropic, Google AI, Azure OpenAI, Groq, Mistral, DeepSeek, xAI, Perplexity, Together, Fireworks, Cerebras, SambaNova, NVIDIA, Hugging Face, local OpenAI-compatible servers, Ollama, LM Studio, vLLM, LocalAI, Jan, llama.cpp, text-generation-webui.
- **Learns your model habits:** healthy models you use successfully get a small preference boost.
- **No manual restart:** the wrapper marks the failed model depleted, switches, and retries the original command once.

**Search keywords:** AI model switcher, OpenRouter quota fallback, Claude Code fallback model, OpenCode model switcher, Aider model fallback, Cursor AI model router, local LLM fallback, MCP model discovery, OpenAI-compatible model router, auto switch AI models.

---

## Drop-in Install

Give this repo URL to **any AI agent** and say "install":

```
https://github.com/farhanic017/auto-model-switcher
```

The AI reads `SKILL.md`, clones, installs, and configures everything.
Zero manual steps.

### Manual Install

```bash
git clone https://github.com/farhanic017/auto-model-switcher.git
cd auto-model-switcher
python install.py
```

---

## The Problem

You're in the middle of work and suddenly get rate-limited or hit 0 credits.
Now you have to: stop, check which models have credits, dig into config files,
manually switch, and restart. **Every. Single. Time.**

## The Solution

```
python switcher.py watch
```

Scans your CLI configs (OpenCode, Claude Code, Cursor, Windsurf, Aider, etc.),
discovers every model you have access to, checks their health in parallel, and
when one fails - automatically rotates to the next working model.

**Free models get priority.** Paid models are fallbacks. Zero config needed.

---

## Supported Providers (all configured models auto-discovered)

| Provider | Models | Detection | Priority |
|----------|--------|-----------|----------|
| Google AI (free) | 4 Gemini models | Config + env | 1st - free |
| OpenRouter (free) | 30+ free models | `:free` suffix | 2nd - free |
| OpenRouter (paid) | 4+ paid models | No `:free` | 3rd - paid |
| Azure OpenAI | 10+ deployments | `azure-openai` provider | 4th - paid |
| OpenAI | Any GPT model | `OPENAI_API_KEY` env | Fallback |
| Anthropic | Claude models | `ANTHROPIC_API_KEY` env | Fallback |
| OpenAI-compatible APIs | Any configured model | `*_API_KEY` + `*_MODEL(S)` + optional `*_BASE_URL` | Fallback |
| Groq, Mistral, DeepSeek, xAI, Perplexity, Together, Fireworks, Cerebras, SambaNova, NVIDIA, Hugging Face | Any configured model | Provider env vars or agent/IDE configs | Fallback |

### Local Models (auto-detected)

| Runtime | Endpoint | Detection |
|---------|----------|-----------|
| **Ollama** | `http://localhost:11434` | Auto-scans, lists all models |
| **LM Studio** | `http://localhost:1234` | Auto-scans `/v1/models` |
| **vLLM** | `http://localhost:8000` | Auto-scans `/v1/models` |
| **LocalAI / Jan / llama.cpp / text-generation-webui** | Common local OpenAI-compatible ports | Auto-scans `/v1/models` |

---

## Commands

| Command | What it does |
|---------|-------------|
| `python switcher.py discover` | Scans all configs + env, lists every model found |
| `python switcher.py status` | Shows active model, health, depletion ETAs |
| `python switcher.py switch --task coding` | Picks best model for a task (coding/chat/reasoning/general) |
| `python switcher.py run opencode -- opencode ...` | Runs a CLI with failure detection, auto-switch, and one retry |
| `python switcher.py doctor` | Runs local diagnostics for state, configs, wrappers, and CLIs |
| `python switcher.py watch` | Background daemon - checks every 2min, auto-rotates |

### Or use the `ams` command after install:

```bash
ams status      # Same as above
ams switch      # Rotate to best model
ams watch       # Background daemon
ams discover    # List all models
```

---

## Task-Aware Model Selection

The switcher doesn't just pick a random model - it picks the **best model for
what you're doing**:

| Task | Models preferred | Example scores |
|------|-----------------|---------------|
| **coding** | qwen3-coder, gpt-4.1, deepseek-coder | 55 bonus |
| **reasoning** | o4, o3, deepseek-r1, kimi, qwen3-next | 50 bonus |
| **chat** | gemma-4, nemotron, gpt-5.4, llama-3.3 | 40 bonus |
| **general** | Falls back to capability tiers | 15-25 bonus |

Auto-detects task from project files (`package.json`, `*.py`, `requirements.txt`,
`Cargo.toml`, etc.) or use `--task` to override.

---

## How It Works

### 1. Auto-Discovery

Reads your existing CLI configs - no extra setup:

- **OpenCode**: `opencode.jsonc` - extracts all `provider` sections
- **Claude Code**: `CLAUDE.md` - extracts `model:` line
- **Cursor / VS Code / Windsurf**: workspace and user `settings.json`, `.cursor/mcp.json`, `.vscode/mcp.json`
- **Continue.dev / Aider / Codex / other agents**: JSON/JSONC/TOML configs with `model`, `models`, `provider`, `baseURL`, or `apiKey`
- **MCP local configs**: `mcp.json`, `.mcp.json`, `.claude/mcp.json`, `.cursor/mcp.json` and `mcpServers[*].env`
- **Environment**: known provider keys plus generic `FOO_API_KEY`, `FOO_MODEL(S)`, optional `FOO_BASE_URL`

### 2. Parallel Health Checking (<5s)

All discovered models checked simultaneously via connection-pooled session:

| Optimization | Impact |
|-------------|--------|
| Connection pooling (keep-alive) | Eliminates TCP handshake per check |
| Cache for ALL healthy models (120s TTL) | Subsequent calls near-instant |
| Reduced timeouts (4s-5s) | Worst case bound at 5s |
| Deduplication by API key | One check per provider, not per model |

Before optimization: **~19s**. After: **~5s first call, ~0.1s cached calls**.

### 3. Smart Scoring (0-250)

Each model scored on: health (base 100) + free tier bonus (+50) + specialty
strength (+up to 55) + reliability (+15 Azure, -5 free OpenRouter).

### 4. Rotation & Recovery

- Failed models marked **depleted** with cooldown (respects `Retry-After` header)
- CLI config updated automatically (`opencode.jsonc` `model` field)
- Runtime CLI failures are classified for quota/usage/rate-limit errors, then the active model is marked depleted, the next best model is selected, and the command is retried once
- The switcher learns which models the user has discovered and which ones they use successfully most often; those models get a small preference bonus when healthy
- After cooldown, model is re-checked and re-enters pool if healthy
- When ALL models depleted: shows **per-model recovery ETA** sorted fastest-first

---

## Context Passing (MCP Handoff)

When switching models mid-session, the switcher preserves:

- Which tools already executed (so new model doesn't repeat)
- Which files were modified
- Last 5 terminal commands
- Conversation summary

Saved to `~/.auto-model-switcher/context.json` for the next model to read.

---

## Always-On Integration

| Method | What it does |
|--------|-------------|
| **PowerShell Profile Hook** | Checks health on every shell start (<2s) |
| **PATH Wrappers** | `.bat` files intercept `opencode`/`claude`/`cursor`/`aider`/`windsurf` calls |
| **Watch Mode** | Background daemon checks every 2min, auto-rotates on failure |
| **Startup Task** | Windows Task Scheduler launches watch on boot |
| **WMI Watchdog** | Invisible background process, starts/stops with opencode.exe |
| **Desktop Shortcuts** | One-click status, switch, watch |

### Validated local CLI versions

Tested on June 7, 2026:

| Tool | Version |
|------|---------|
| OpenCode | 1.16.0 |
| Claude Code | 2.1.142 |
| Gemini CLI | 0.45.1 |
| Qwen CLI | 0.17.1 |
| Cursor | 3.5.33 |
| VS Code | 1.121.0 |
| Aider | 0.86.2 |
| Windsurf | 1.110.1 |
| FFmpeg | 8.1.1 |

### Adding a new CLI

The auto-switch wrapper system is **future-proof**. To add support for any new
CLI or agent:

1. Add its path to `install.py` -> `clis` dict (around line 119)
2. Re-run `python install.py`
3. Or manually create a `.bat` wrapper in `~/.auto-model-switcher/bin/`

The architecture is designed so **any future CLI, agent, or MCP server** can
be added by simply registering its path.

---

## For AI Agents (Drop-in Install)

Give this repo URL to **any AI assistant**:

```
https://github.com/farhanic017/auto-model-switcher
```

The AI reads `SKILL.md` and handles everything: cloning, installing, configuring.

---

## Project Structure

```
auto-model-switcher/
|-- switcher.py          # Core engine (2,076 lines)
|-- install.py           # Universal installer
|-- restore.ps1          # Windows restore script
|-- SKILL.md             # AI agent instructions
|-- README.md            # This file
|-- LICENSE              # GPL-3.0
|-- NOTICE               # Copyright and legal notices
|-- .gitignore
|-- data/                # Runtime state templates
|-- hooks/               # CLI integration hooks
`-- tests/
    |-- test_switcher.py # 39 test cases, all passing
    `-- debug_speed.py   # Performance profiler
```

---

## Copyright & License

**Copyright (c) 2026 Farhan Dhrubo** - All rights reserved.

This project is licensed under the **GNU General Public License v3.0**.
See [LICENSE](LICENSE) and [NOTICE](NOTICE) for full details.

**You may NOT:**
- Remove or alter any copyright notice in any file
- Re-distribute this software or any derivative as your own work
  without clear attribution to the original author
- Sell this software or any derivative without explicit permission

**Required attribution:** Any use, distribution, or derivative work MUST include:
"Originally created by Farhan Dhrubo (github.com/farhanic017)"

Every source file in this repository contains an embedded copyright notice
making the origin unambiguous. The GPL-3.0 license ensures all derivative
works remain open-source and properly attributed.

---

*Built with Python, caffeine, and the frustration of getting 402 errors
mid-session.*

