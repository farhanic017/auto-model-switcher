#!/usr/bin/env python3
#  Auto Model Switcher v2  ───  Always-On Smart Model Rotation
#  Copyright (c) 2026 Farhan Dhrubo  <farhaiee123@gmail.com>
#  License: GPL-3.0  —  https://github.com/farhanic017/auto-model-switcher
#
#  This program is free software. You may NOT remove this notice,
#  re-distribute as your own work, or sell without attribution.
# =============================================================================

"""
Auto Model Switcher v2 — Smart parallel model rotation across any CLI.

Auto-discovers models from CLI configs (opencode.jsonc, CLAUDE.md, etc.)
and environment variables. Checks ALL models in parallel (<2s). Scores them
by capability + health + cost. Picks the best working model instantly.

OpenRouter free-tier gate detection included ("buy N tokens" patterns).
When ALL models depleted, shows per-model recovery ETA.

Usage:
  python switcher.py status              # Show state + per-model ETAs
  python switcher.py switch [--task T]   # Pick best model for T (coding|chat|reasoning|general)
  python switcher.py watch               # Background daemon with auto-rotation
  python switcher.py discover            # Scan configs for models
"""

import json, os, sys, time, re, threading, subprocess, shutil
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

# ─── Paths ───────────────────────────────────────────────────────────────────

STATE_DIR = Path.home() / ".auto-model-switcher"
STATE_FILE = STATE_DIR / "state.json"
CONTEXT_FILE = STATE_DIR / "context.json"
LOG_FILE = STATE_DIR / "switcher.log"

CONFIG_PATHS = [
    Path.home() / ".config" / "opencode" / "opencode.jsonc",
    Path.home() / ".config" / "opencode" / "opencode.json",
    Path.cwd() / "opencode.jsonc",
    Path.cwd() / "opencode.json",
    Path.cwd() / "CLAUDE.md",
    Path.cwd() / ".cursorrules",
    Path.cwd() / ".cursor" / "mcp.json",
    Path.cwd() / ".cursor" / "settings.json",
    Path.cwd() / ".continue" / "config.json",
    Path.cwd() / ".continue" / "config.jsonc",
    Path.cwd() / ".vscode" / "settings.json",
    Path.cwd() / ".vscode" / "mcp.json",
    Path.cwd() / ".mcp.json",
    Path.cwd() / "mcp.json",
    Path.home() / ".claude" / "settings.json",
    Path.home() / ".claude" / "mcp.json",
    Path.home() / ".codex" / "config.toml",
    Path.home() / ".continue" / "config.json",
    Path.home() / ".continue" / "config.jsonc",
    Path.home() / ".cursor" / "mcp.json",
    Path.home() / ".cursor" / "settings.json",
    Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "settings.json",
    Path(os.environ.get("APPDATA", "")) / "Cursor" / "User" / "settings.json",
    Path(os.environ.get("APPDATA", "")) / "Windsurf" / "User" / "settings.json",
]

PROVIDER_DEFAULTS = {
    "openai": {
        "api_env": ["OPENAI_API_KEY"],
        "endpoint_env": ["OPENAI_BASE_URL", "OPENAI_API_BASE"],
        "model_env": ["OPENAI_MODEL", "OPENAI_MODELS"],
        "endpoint": "https://api.openai.com/v1",
        "models": ["gpt-4o"],
    },
    "anthropic": {
        "api_env": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "model_env": ["ANTHROPIC_MODEL", "CLAUDE_MODEL"],
        "models": ["claude-sonnet-4-20250514"],
    },
    "claude": {
        "api_env": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"],
        "model_env": ["ANTHROPIC_MODEL", "CLAUDE_MODEL"],
        "models": ["claude-sonnet-4-20250514"],
    },
    "google-ai": {
        "api_env": ["GEMINI_API_KEY", "GOOGLE_AI_API_KEY", "GOOGLE_API_KEY"],
        "model_env": ["GEMINI_MODEL", "GOOGLE_AI_MODEL", "GEMINI_MODELS"],
        "models": ["gemini/gemini-2.5-flash"],
        "is_free": True,
    },
    "openrouter": {
        "api_env": ["OPENROUTER_API_KEY"],
        "endpoint_env": ["OPENROUTER_BASE_URL"],
        "model_env": ["OPENROUTER_MODEL", "OPENROUTER_MODELS"],
        "endpoint": "https://openrouter.ai/api/v1",
        "models": ["openrouter/auto"],
    },
    "groq": {
        "api_env": ["GROQ_API_KEY"],
        "endpoint": "https://api.groq.com/openai/v1",
        "model_env": ["GROQ_MODEL", "GROQ_MODELS"],
        "models": ["llama-3.3-70b-versatile"],
    },
    "mistral": {
        "api_env": ["MISTRAL_API_KEY"],
        "endpoint": "https://api.mistral.ai/v1",
        "model_env": ["MISTRAL_MODEL", "MISTRAL_MODELS"],
        "models": ["mistral-large-latest"],
    },
    "together": {
        "api_env": ["TOGETHER_API_KEY"],
        "endpoint": "https://api.together.xyz/v1",
        "model_env": ["TOGETHER_MODEL", "TOGETHER_MODELS"],
        "models": [],
    },
    "fireworks": {
        "api_env": ["FIREWORKS_API_KEY"],
        "endpoint": "https://api.fireworks.ai/inference/v1",
        "model_env": ["FIREWORKS_MODEL", "FIREWORKS_MODELS"],
        "models": [],
    },
    "deepseek": {
        "api_env": ["DEEPSEEK_API_KEY"],
        "endpoint": "https://api.deepseek.com/v1",
        "model_env": ["DEEPSEEK_MODEL", "DEEPSEEK_MODELS"],
        "models": ["deepseek-chat"],
    },
    "xai": {
        "api_env": ["XAI_API_KEY", "GROK_API_KEY"],
        "endpoint": "https://api.x.ai/v1",
        "model_env": ["XAI_MODEL", "GROK_MODEL", "XAI_MODELS"],
        "models": [],
    },
    "perplexity": {
        "api_env": ["PERPLEXITY_API_KEY"],
        "endpoint": "https://api.perplexity.ai",
        "model_env": ["PERPLEXITY_MODEL", "PERPLEXITY_MODELS"],
        "models": [],
    },
    "cerebras": {
        "api_env": ["CEREBRAS_API_KEY"],
        "endpoint": "https://api.cerebras.ai/v1",
        "model_env": ["CEREBRAS_MODEL", "CEREBRAS_MODELS"],
        "models": [],
    },
    "sambanova": {
        "api_env": ["SAMBANOVA_API_KEY"],
        "endpoint": "https://api.sambanova.ai/v1",
        "model_env": ["SAMBANOVA_MODEL", "SAMBANOVA_MODELS"],
        "models": [],
    },
    "nvidia": {
        "api_env": ["NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"],
        "endpoint": "https://integrate.api.nvidia.com/v1",
        "model_env": ["NVIDIA_MODEL", "NVIDIA_MODELS"],
        "models": [],
    },
    "huggingface": {
        "api_env": ["HF_TOKEN", "HUGGINGFACE_API_KEY"],
        "endpoint": "https://router.huggingface.co/v1",
        "model_env": ["HF_MODEL", "HUGGINGFACE_MODEL", "HF_MODELS"],
        "models": [],
    },
}

OPENAI_COMPATIBLE_PROVIDERS = {
    "openai", "openrouter", "groq", "mistral", "together", "fireworks",
    "deepseek", "xai", "perplexity", "cerebras", "sambanova", "nvidia",
    "huggingface", "lm-studio", "lm_studio", "vllm", "localai", "jan",
    "llama-cpp", "text-generation-webui", "local-openai", "custom",
}

GENERIC_MODEL_KEYS = ("model", "modelId", "model_id", "modelName", "model_name",
                      "defaultModel", "default_model", "chatModel", "chat_model")
GENERIC_ENDPOINT_KEYS = ("endpoint", "baseURL", "baseUrl", "base_url", "apiBase",
                         "api_base", "apiUrl", "api_url", "serverUrl", "server_url")
GENERIC_API_KEY_KEYS = ("apiKey", "api_key", "key", "token", "authToken")

# OpenRouter free-tier gate patterns — models that say "buy X get Y free"
OPENROUTER_GATE_PATTERNS = [
    r"buy.*token.*free",
    r"purchase.*credit",
    r"insufficient.*credit",
    r"add.*funds",
    r"free.*tier.*limit",
]

USAGE_LIMIT_PATTERNS = [
    r"\b429\b",
    r"\b402\b",
    r"rate[-\s]?limit(?:ed)?",
    r"too many requests",
    r"quota (?:exceeded|reached)",
    r"exceeded.*quota",
    r"usage (?:limit|quota|cap)",
    r"token (?:limit|quota|budget) (?:exceeded|reached|exhausted)",
    r"out of (?:tokens|credits|quota)",
    r"(?:no|zero|0) credits? (?:remaining|left)",
    r"insufficient (?:credits?|funds|quota|balance)",
    r"payment required",
    r"billing hard limit",
    r"monthly spend limit",
    r"free[-\s]?tier.*(?:limit|exceeded|reached)",
    r"requests? per (?:minute|day|month)",
]

# Model capability tiers for scoring
CAPABILITY_TIER = {
    "reasoning": ["o4", "o3", "deepseek", "kimi", "ring", "trinity", "laguna-m", "qwen3-next"],
    "general": ["gpt-4", "gpt-5", "claude", "gemma", "nemotron", "llama", "cobuddy", "qwen3-coder", "grok", "glm", "hermes"],
    "fast": ["flash", "mini", "nano", "lite", "instruct"],
}

# Model specialties — maps model keyword to task + strength bonus
MODEL_SPECIALTIES = [
    # Reasoning (deep thinking, math, logic)
    ("o4", "reasoning", 50), ("o3", "reasoning", 50),
    ("deepseek", "reasoning", 40), ("kimi", "reasoning", 40),
    ("ring", "reasoning", 35), ("trinity", "reasoning", 30),
    ("laguna-m", "reasoning", 25), ("qwen3-next", "reasoning", 25),
    # Coding (code gen, debugging, refactoring)
    ("qwen3-coder", "coding", 55), ("gpt-4.1", "coding", 45),
    ("deepseek", "coding", 35), ("gpt-4o", "coding", 30),
    ("gpt-5.1", "coding", 30), ("cobuddy", "coding", 25),
    ("grok-4.1-fast-reasoning", "coding", 30), ("grok-4.3", "coding", 25),
    # Chat / creative (conversation, writing, brainstorming)
    ("gemma-4-26b", "chat", 40), ("gemma-4-31b", "chat", 40),
    ("nemotron-3-super", "chat", 35), ("nemotron-3-nano", "chat", 30),
    ("llama-3.3", "chat", 30), ("gpt-5.4", "chat", 35),
    ("gpt-5.4-mini", "chat", 30), ("glm", "chat", 25),
    ("hermes", "chat", 25), ("dolphin", "chat", 20),
    ("lyria", "chat", 30), ("liquid/lfm-2.5", "chat", 20),
    # Fast / quick responses
    ("flash", "fast", 45), ("mini", "fast", 35),
    ("nano", "fast", 30), ("lite", "fast", 25),
    ("instruct", "fast", 20), ("phi-4", "fast", 25),
]

# ─── Logging ─────────────────────────────────────────────────────────────────

def log(msg: str):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    clean = msg.encode("ascii", "replace").decode()
    print(f"[switcher] {clean}")

# ─── State ───────────────────────────────────────────────────────────────────

def _default_state() -> dict:
    return {
        "active": {},
        "depleted": {},
        "history": [],
        "last_switch": None,
        "knowledge": {"models": {}, "usage": {}, "cli_usage": {}},
    }


def _ensure_state_shape(state: dict) -> dict:
    state.setdefault("active", {})
    state.setdefault("depleted", {})
    state.setdefault("history", [])
    state.setdefault("last_switch", None)
    knowledge = state.setdefault("knowledge", {})
    knowledge.setdefault("models", {})
    knowledge.setdefault("usage", {})
    knowledge.setdefault("cli_usage", {})
    return state


def _read_json_with_backup(path: Path, default):
    candidates = [path, path.with_suffix(path.suffix + ".bak")]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
    return default


def _atomic_write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    if path.exists():
        try:
            path.with_suffix(path.suffix + ".bak").write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8"
            )
        except Exception:
            pass
    os.replace(tmp, path)


def _atomic_write_json(path: Path, data, **dump_kwargs):
    _atomic_write_text(path, json.dumps(data, **dump_kwargs))


def load_state() -> dict:
    data = _read_json_with_backup(STATE_FILE, _default_state())
    if not isinstance(data, dict):
        data = _default_state()
    return _ensure_state_shape(data)

def save_state(state: dict):
    _atomic_write_json(STATE_FILE, _ensure_state_shape(state), indent=2, default=str)

def get_active(cli: str = "opencode") -> Optional[str]:
    return load_state().get("active", {}).get(cli)

def set_active(cli: str, model_key: str):
    state = load_state()
    state["active"][cli] = model_key
    state["last_switch"] = datetime.now().isoformat()
    save_state(state)


def remember_discovered_models(providers: list[dict]):
    """Persist what models exist so future choices know the user's actual model pool."""
    if not providers:
        return
    state = load_state()
    models = state["knowledge"]["models"]
    now = datetime.now().isoformat()
    for p in providers:
        key = p.get("key")
        if not key:
            continue
        entry = models.setdefault(key, {
            "first_seen": now,
            "seen_count": 0,
        })
        entry.update({
            "provider": p.get("provider"),
            "model_id": p.get("model_id"),
            "deployment": p.get("deployment"),
            "endpoint": p.get("endpoint"),
            "source": p.get("source"),
            "is_free": p.get("is_free"),
            "last_seen": now,
        })
        entry["seen_count"] = int(entry.get("seen_count", 0)) + 1
    save_state(state)


def record_model_usage(model_key: Optional[str], cli: str = "opencode",
                       outcome: str = "run", exit_code: Optional[int] = None):
    """Record actual model use so ranking can learn the user's normal choices."""
    if not model_key:
        return
    state = load_state()
    now = datetime.now().isoformat()
    usage = state["knowledge"]["usage"].setdefault(model_key, {
        "runs": 0, "successes": 0, "failures": 0, "runtime_depletions": 0,
        "switches_to": 0, "last_used": None, "cli_counts": {},
    })
    if outcome == "success":
        usage["runs"] = int(usage.get("runs", 0)) + 1
        usage["successes"] = int(usage.get("successes", 0)) + 1
    elif outcome == "failure":
        usage["runs"] = int(usage.get("runs", 0)) + 1
        usage["failures"] = int(usage.get("failures", 0)) + 1
    elif outcome == "depleted":
        usage["runtime_depletions"] = int(usage.get("runtime_depletions", 0)) + 1
        usage["failures"] = int(usage.get("failures", 0)) + 1
    elif outcome == "selected":
        usage["switches_to"] = int(usage.get("switches_to", 0)) + 1
    else:
        usage["runs"] = int(usage.get("runs", 0)) + 1
    usage["last_used"] = now
    if exit_code is not None:
        usage["last_exit_code"] = exit_code
    cli_counts = usage.setdefault("cli_counts", {})
    cli_counts[cli] = int(cli_counts.get(cli, 0)) + 1
    state["knowledge"]["cli_usage"].setdefault(cli, {})
    state["knowledge"]["cli_usage"][cli][model_key] = int(
        state["knowledge"]["cli_usage"][cli].get(model_key, 0)
    ) + 1
    save_state(state)


def model_usage_bonus(model_key: str, cli: str = "opencode") -> int:
    """Small preference bonus for models the user commonly uses successfully."""
    usage = load_state().get("knowledge", {}).get("usage", {}).get(model_key, {})
    runs = int(usage.get("runs", 0))
    successes = int(usage.get("successes", 0))
    failures = int(usage.get("failures", 0))
    switches_to = int(usage.get("switches_to", 0))
    cli_runs = int(usage.get("cli_counts", {}).get(cli, 0))
    if runs <= 0 and switches_to <= 0:
        return 0
    success_rate = successes / max(1, runs)
    bonus = min(18, runs * 2 + cli_runs + switches_to)
    bonus += int(success_rate * 7)
    bonus -= min(12, failures * 3)
    return max(-10, min(25, bonus))


def most_used_models(limit: int = 5) -> list[tuple[str, dict]]:
    usage = load_state().get("knowledge", {}).get("usage", {})
    ranked = sorted(
        usage.items(),
        key=lambda item: (
            int(item[1].get("runs", 0)),
            int(item[1].get("successes", 0)),
            item[1].get("last_used") or "",
        ),
        reverse=True,
    )
    return ranked[:limit]

def mark_depleted(model_key: str, reason: str, cooldown_minutes: int = 30):
    state = load_state()
    now = datetime.now()

    # Extract retry-after seconds from reason string (e.g. "rate limited (429), retry in 120s")
    retry_secs = None
    m = re.search(r"retry in (\d+)s", reason)
    if m:
        retry_secs = int(m.group(1))
        cooldown_minutes = max(1, retry_secs // 60)

    state["depleted"][model_key] = {
        "reason": reason,
        "since": now.isoformat(),
        "cooldown_until": (now + timedelta(minutes=cooldown_minutes)).isoformat(),
        "retry_seconds": retry_secs,
    }
    state["history"].append({
        "model": model_key, "action": "depleted",
        "reason": reason, "time": now.isoformat(),
    })
    save_state(state)

def mark_recovered(model_key: str):
    state = load_state()
    state["depleted"].pop(model_key, None)
    state["history"].append({
        "model": model_key, "action": "recovered",
        "time": datetime.now().isoformat(),
    })
    save_state(state)

def is_depleted(model_key: str) -> bool:
    state = load_state()
    entry = state.get("depleted", {}).get(model_key)
    if not entry:
        return False
    cooldown = entry.get("cooldown_until")
    if cooldown and datetime.fromisoformat(cooldown) < datetime.now():
        state["depleted"].pop(model_key)
        save_state(state)
        return False
    return True

# ─── MCP State Preservation ──────────────────────────────────────────────────

MCP_STATE_FILE = STATE_DIR / "mcp_state.json"


def save_mcp_tool_call(name: str, params: dict, result_hash: str = ""):
    """Record a tool execution so the next model knows what already ran."""
    state = _load_mcp_state()
    state["tools_executed"].append({
        "name": name,
        "params_summary": str(list(params.keys())[:3]) if params else "",
        "result_hash": result_hash,
        "timestamp": datetime.now().isoformat(),
    })
    _write_mcp_state(state)


def save_mcp_file_write(path: str, action: str = "write", result_hash: str = ""):
    """Record a file write/change to avoid re-execution after swap."""
    state = _load_mcp_state()
    norm = Path(path).resolve().as_posix()
    if not any(e["path"] == norm for e in state["file_writes"]):
        state["file_writes"].append({
            "path": norm, "action": action, "result_hash": result_hash,
            "timestamp": datetime.now().isoformat(),
        })
    _write_mcp_state(state)


def save_mcp_terminal_cmd(command: str, cwd: str = ""):
    """Record a terminal command so the next model knows current state."""
    state = _load_mcp_state()
    state["terminal_cmds"].append({
        "command": command[:200], "cwd": cwd,
        "timestamp": datetime.now().isoformat(),
    })
    _write_mcp_state(state)


def _load_mcp_state() -> dict:
    default = {"tools_executed": [], "file_writes": [], "terminal_cmds": [],
               "conversation_summary": "", "last_model": None}
    data = _read_json_with_backup(MCP_STATE_FILE, default)
    return data if isinstance(data, dict) else default


def _write_mcp_state(state: dict):
    _atomic_write_json(MCP_STATE_FILE, state, indent=2)


def build_mcp_handoff(prev_model: str, new_model: str) -> dict:
    """Build a handoff context for the incoming model. Includes what tools
    already ran, which files were modified, and terminal state so the new
    model doesn't re-execute already-done work."""
    mcp = _load_mcp_state()
    handoff = {
        "previous_model": prev_model,
        "new_model": new_model,
        "switched_at": datetime.now().isoformat(),
        "already_executed_tools": [
            {"name": t["name"], "params": t["params_summary"]}
            for t in mcp.get("tools_executed", [])
        ],
        "files_modified": [
            {"path": f["path"], "action": f["action"]}
            for f in mcp.get("file_writes", [])
        ],
        "terminal_history": [
            {"command": c["command"][:100], "cwd": c["cwd"]}
            for c in mcp.get("terminal_cmds", [])[-5:]
        ],
        "conversation_summary": mcp.get("conversation_summary", ""),
    }
    return handoff


def clear_mcp_state(new_model: str = ""):
    """Reset MCP state for a fresh session after switch. Tracks the new model."""
    state = _load_mcp_state()
    state["tools_executed"] = []
    state["terminal_cmds"] = []
    state["file_writes"] = []
    state["conversation_summary"] = ""
    state["last_model"] = new_model or state.get("last_model") or "unknown"
    _write_mcp_state(state)


# ─── Context Passing ─────────────────────────────────────────────────────────

def save_context(prev_model: str, new_model: str, reason: str, summary: str = ""):
    mcp_handoff = build_mcp_handoff(prev_model, new_model)
    ctx = {
        "previous_model": prev_model,
        "new_model": new_model,
        "switch_reason": reason,
        "summary": summary,
        "switched_at": datetime.now().isoformat(),
        "mcp": mcp_handoff,
    }
    _atomic_write_json(CONTEXT_FILE, ctx, indent=2)
    # Clean MCP state after handoff built so fresh state for the new model
    clear_mcp_state(new_model)

def load_context() -> dict:
    data = _read_json_with_backup(CONTEXT_FILE, {})
    return data if isinstance(data, dict) else {}

def get_recovery_eta() -> dict:
    """Returns per-model recovery ETA and next-available info."""
    state = load_state()
    depleted = state.get("depleted", {})
    active_key = get_active("opencode")

    now = datetime.now()
    etas = {}
    fastest = None
    active_depleted = False

    for key, info in depleted.items():
        cooldown = datetime.fromisoformat(info["cooldown_until"])
        remaining = (cooldown - now).total_seconds()
        minutes_left = max(0, int(remaining // 60))
        seconds_left = max(0, int(remaining))
        etas[key] = {
            "recovery_at": cooldown.isoformat(),
            "minutes_remaining": minutes_left,
            "seconds_remaining": seconds_left,
            "reason": info.get("reason", "unknown"),
            "retry_seconds": info.get("retry_seconds"),
        }
        if key == active_key:
            active_depleted = True
        if fastest is None or remaining < fastest["seconds"]:
            fastest = {"key": key, "seconds": remaining, "minutes": minutes_left}

    return {
        "all_depleted": active_depleted,
        "models": etas,
        "fastest_recovery": fastest,
        "checked_at": now.isoformat(),
    }

# ─── Config Discovery ────────────────────────────────────────────────────────

def _slug(value: str) -> str:
    value = str(value or "").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-") or "custom"


def _first_env(names: list[str]) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _split_models(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,;\n]+", value)
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, (list, tuple, set)):
        models = []
        for item in value:
            if isinstance(item, str):
                models.extend(_split_models(item))
            elif isinstance(item, dict):
                model = _extract_first_string(item, GENERIC_MODEL_KEYS)
                if model:
                    models.append(model)
        return models
    if isinstance(value, dict):
        return [str(k) for k in value.keys()]
    return []


def _extract_first_string(data: dict, keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _infer_provider(provider: Optional[str] = None, endpoint: Optional[str] = None,
                    source: str = "") -> str:
    if provider:
        return _slug(provider)
    haystack = f"{endpoint or ''} {source}".lower()
    for name in PROVIDER_DEFAULTS:
        if name in haystack or name.replace("-", "") in haystack:
            return name
    if "generativelanguage.googleapis.com" in haystack:
        return "google-ai"
    if "api.anthropic.com" in haystack:
        return "anthropic"
    if "localhost" in haystack or "127.0.0.1" in haystack:
        return "local-openai"
    return "custom"


def _provider_default(provider: str, field: str, default=None):
    return PROVIDER_DEFAULTS.get(_slug(provider), {}).get(field, default)


def _is_free_model(provider: str, model_id: str, explicit=None) -> bool:
    if explicit is not None:
        return bool(explicit)
    provider = _slug(provider)
    model = str(model_id or "").lower()
    return (
        provider in ("google-ai", "ollama", "lm-studio", "lm_studio", "vllm",
                     "localai", "jan", "llama-cpp", "text-generation-webui",
                     "local-openai")
        or ":free" in model
        or model == "openrouter/free"
        or "/free" in model
    )


def _append_provider(providers: list, provider: str, model_id: str,
                     api_key: Optional[str] = None, endpoint: Optional[str] = None,
                     source: str = "", deployment: Optional[str] = None,
                     is_free=None, is_active: bool = False):
    if not model_id:
        return
    provider = _infer_provider(provider, endpoint, source)
    model_id = str(model_id).strip()
    deployment = deployment or model_id
    endpoint = endpoint or _provider_default(provider, "endpoint")
    key = f"{provider}:{model_id}"
    if any(p.get("key") == key for p in providers):
        return
    providers.append({
        "key": key,
        "provider": provider,
        "model_id": model_id,
        "deployment": deployment,
        "api_key": api_key,
        "endpoint": endpoint,
        "is_free": _is_free_model(provider, model_id, is_free),
        "source": source or "unknown",
        "is_active": is_active,
    })


def parse_opencode_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    stripped = []
    in_string = False
    string_char = None
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == string_char and (i == 0 or text[i-1] != "\\"):
                in_string = False
            stripped.append(ch)
            i += 1
        elif ch in ('"', "'"):
            in_string = True
            string_char = ch
            stripped.append(ch)
            i += 1
        elif ch == "/" and i + 1 < len(text):
            if text[i+1] == "/":
                while i < len(text) and text[i] != "\n":
                    i += 1
            elif text[i+1] == "*":
                i += 2
                while i < len(text) and not (text[i] == "*" and i+1 < len(text) and text[i+1] == "/"):
                    i += 1
                i += 2
            else:
                stripped.append(ch)
                i += 1
        else:
            stripped.append(ch)
            i += 1
    return json.loads("".join(stripped))


def parse_structured_config(path: Path):
    suffix = path.suffix.lower()
    if suffix in (".json", ".jsonc"):
        return parse_opencode_config(path)
    if suffix == ".toml":
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        return tomllib.loads(path.read_text(encoding="utf-8"))
    return None


def _discover_from_text(path: Path, providers: list):
    text = path.read_text(encoding="utf-8", errors="ignore")
    model_matches = re.findall(
        r"(?im)^\s*(?:model|model_id|modelId|defaultModel)\s*[:=]\s*['\"]?([^'\"\s#]+)",
        text,
    )
    if not model_matches:
        return
    provider_match = re.search(r"(?im)^\s*provider\s*[:=]\s*['\"]?([^'\"\s#]+)", text)
    endpoint_match = re.search(r"(?im)^\s*(?:baseURL|baseUrl|base_url|endpoint|apiBase)\s*[:=]\s*['\"]?([^'\"\s#]+)", text)
    api_key_match = re.search(r"(?im)^\s*(?:apiKey|api_key|token)\s*[:=]\s*['\"]?([^'\"\s#]+)", text)
    provider = provider_match.group(1) if provider_match else None
    endpoint = endpoint_match.group(1) if endpoint_match else None
    api_key = api_key_match.group(1) if api_key_match else None
    provider = _infer_provider(provider, endpoint, str(path))
    for model in model_matches:
        _append_provider(providers, provider, model, api_key=api_key,
                         endpoint=endpoint, source=str(path), is_active=True)


def _discover_from_env_dict(env: dict, providers: list, source: str,
                            context_provider: Optional[str] = None,
                            endpoint: Optional[str] = None):
    if not isinstance(env, dict):
        return
    upper_env = {str(k).upper(): str(v) for k, v in env.items() if v is not None}
    model_values = []
    for key, value in upper_env.items():
        if key.endswith("_MODEL") or key.endswith("_MODELS") or key in ("MODEL", "MODELS"):
            model_values.extend(_split_models(value))

    provider = context_provider
    api_key = None
    for key, value in upper_env.items():
        if key.endswith("_API_KEY") or key.endswith("_TOKEN") or key in ("API_KEY", "TOKEN"):
            api_key = value
            if not provider and key not in ("API_KEY", "TOKEN"):
                provider = key.rsplit("_", 2)[0].lower().replace("_", "-")
            elif key not in ("API_KEY", "TOKEN"):
                provider = key.rsplit("_", 2)[0].lower().replace("_", "-")
            break

    endpoint = endpoint or upper_env.get("BASE_URL") or upper_env.get("API_BASE") or upper_env.get("ENDPOINT")
    provider = _infer_provider(provider, endpoint, source)
    for model in model_values:
        _append_provider(providers, provider, model, api_key=api_key,
                         endpoint=endpoint, source=source)


def discover_from_generic_config(data, providers: list, source: str,
                                 context_provider: Optional[str] = None,
                                 context_endpoint: Optional[str] = None,
                                 context_key: Optional[str] = None):
    if isinstance(data, list):
        for item in data:
            discover_from_generic_config(item, providers, source,
                                         context_provider, context_endpoint,
                                         context_key)
        return
    if not isinstance(data, dict):
        return

    provider = (
        _extract_first_string(data, ("provider", "providerId", "provider_id", "name", "id"))
        or context_provider
    )
    endpoint = _extract_first_string(data, GENERIC_ENDPOINT_KEYS) or context_endpoint
    api_key = _extract_first_string(data, GENERIC_API_KEY_KEYS) or context_key

    if isinstance(data.get("env"), dict):
        _discover_from_env_dict(data["env"], providers, source, provider, endpoint)

    model_values = []
    for key in GENERIC_MODEL_KEYS:
        model_values.extend(_split_models(data.get(key)))

    models_node = data.get("models")
    if isinstance(models_node, dict):
        for model_id, model_cfg in models_node.items():
            deployment = model_id
            explicit_free = None
            if isinstance(model_cfg, dict):
                deployment = model_cfg.get("deployment", model_id)
                explicit_free = model_cfg.get("free") or model_cfg.get("isFree")
            _append_provider(providers, provider, model_id, api_key=api_key,
                             endpoint=endpoint, source=source, deployment=deployment,
                             is_free=explicit_free,
                             is_active=model_id in model_values or deployment in model_values)
    elif isinstance(models_node, list):
        for item in models_node:
            if isinstance(item, dict):
                discover_from_generic_config(item, providers, source, provider,
                                             endpoint, api_key)
            else:
                model_values.extend(_split_models(item))

    if model_values and (provider or endpoint or api_key):
        inferred = _infer_provider(provider, endpoint, source)
        for model in model_values:
            _append_provider(providers, inferred, model, api_key=api_key,
                             endpoint=endpoint, source=source, is_active=True)

    for key, value in data.items():
        if key in ("models", "env"):
            continue
        if key == "provider" and isinstance(value, dict):
            continue
        next_provider = provider
        if isinstance(value, dict) and key not in ("options", "settings", "config"):
            next_provider = provider or _slug(key)
        discover_from_generic_config(value, providers, source, next_provider,
                                     endpoint, api_key)


def discover_providers() -> list[dict]:
    providers = []
    for cfg_path in CONFIG_PATHS:
        if not cfg_path.exists():
            continue
        try:
            ext = cfg_path.suffix.lower()
            if ext == ".md":
                discover_from_claude(cfg_path, providers)
            elif ext in (".json", ".jsonc", ".toml"):
                cfg = parse_structured_config(cfg_path)
                if isinstance(cfg, dict):
                    discover_from_opencode_data(cfg_path, cfg, providers)
                    discover_from_generic_config(cfg, providers, str(cfg_path))
            else:
                _discover_from_text(cfg_path, providers)
        except Exception as e:
            log(f"  skip {cfg_path.name}: {e}")
    discover_from_env(providers)
    discover_local_models(providers)
    remember_discovered_models(providers)
    return providers

def discover_from_opencode(path: Path, providers: list):
    cfg = parse_opencode_config(path)
    discover_from_opencode_data(path, cfg, providers)


def discover_from_opencode_data(path: Path, cfg: dict, providers: list):
    model_override = cfg.get("model")

    for provider_name, provider_cfg in cfg.get("provider", {}).items():
        if not isinstance(provider_cfg, dict):
            continue
        opts = provider_cfg.get("options", {})
        api_key = opts.get("apiKey") or os.environ.get(f"{provider_name.upper().replace('-','_')}_API_KEY")

        for model_id, model_opts in provider_cfg.get("models", {}).items():
            if not isinstance(model_opts, dict):
                model_opts = {}
            is_free = (
                ":free" in model_id
                or provider_name in ("google-ai",)
                or model_id == "openrouter/free"
                or "free" in str(model_opts.get("tier", "")).lower()
            )
            deployment = model_opts.get("deployment", model_id)
            key = f"{provider_name}:{model_id}"
            is_active = model_id == model_override or deployment == model_override
            if model_override and not is_active:
                is_active = key.endswith(model_override) or model_id.endswith(model_override)

            _append_provider(providers, provider_name, model_id, api_key=api_key,
                             endpoint=opts.get("endpoint"), source=str(path),
                             deployment=deployment, is_free=is_free,
                             is_active=is_active)

def discover_from_claude(path: Path, providers: list):
    text = path.read_text(encoding="utf-8")
    m = re.search(r"model:\s*(\S+)", text)
    if m:
        _append_provider(providers, "claude", m.group(1),
                         api_key=os.environ.get("ANTHROPIC_API_KEY"),
                         source=str(path), is_free=False, is_active=True)

def discover_from_env(providers: list):
    for provider, defaults in PROVIDER_DEFAULTS.items():
        api_key = _first_env(defaults.get("api_env", []))
        endpoint = _first_env(defaults.get("endpoint_env", [])) or defaults.get("endpoint")
        model_override = _first_env(defaults.get("model_env", []))
        models = _split_models(model_override) or defaults.get("models", [])
        if not api_key and not os.environ.get(f"{provider.upper().replace('-', '_')}_BASE_URL"):
            continue
        for model in models:
            _append_provider(providers, provider, model, api_key=api_key,
                             endpoint=endpoint, source="env",
                             is_free=defaults.get("is_free"))

    # Fully generic provider support: FOO_API_KEY + FOO_MODEL(S) + optional FOO_BASE_URL.
    for env_name, api_key in os.environ.items():
        if not env_name.endswith("_API_KEY") or not api_key:
            continue
        prefix = env_name[:-8]
        provider = prefix.lower().replace("_", "-")
        if provider in PROVIDER_DEFAULTS:
            continue
        model_value = os.environ.get(f"{prefix}_MODEL") or os.environ.get(f"{prefix}_MODELS")
        endpoint = (
            os.environ.get(f"{prefix}_BASE_URL")
            or os.environ.get(f"{prefix}_API_BASE")
            or os.environ.get(f"{prefix}_ENDPOINT")
        )
        for model in _split_models(model_value):
            _append_provider(providers, provider, model, api_key=api_key,
                             endpoint=endpoint, source="env")

# ─── Task Detection ──────────────────────────────────────────────────────────

def detect_task() -> str:
    """Auto-detect the likely task type from project context."""
    # 1. CLI override via --task flag (highest priority)
    override = os.environ.get("AUTO_SWITCHER_TASK")
    if override in ("coding", "chat", "reasoning", "general"):
        return override

    # 2. Context from previous switch
    ctx = load_context()
    if ctx.get("task"):
        return ctx["task"]

    # 3. Project context auto-detection
    cwd = Path.cwd()
    code_markers = [
        "package.json", "requirements.txt", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle", "CMakeLists.txt",
        "composer.json", "Gemfile",
    ]
    for marker in code_markers:
        if (cwd / marker).exists():
            return "coding"

    code_extensions = ["*.py", "*.js", "*.ts", "*.jsx", "*.tsx",
                       "*.rs", "*.go", "*.java", "*.cpp", "*.c",
                       "*.cs", "*.rb", "*.php", "*.swift"]
    for ext in code_extensions:
        if list(cwd.glob(ext)):
            return "coding"

    return "general"


def get_model_specialty(model_id: str) -> tuple[str, int]:
    """Return (task, strength) for a model, or (\"general\", 0) if unknown."""
    mid = model_id.lower()
    best_task = "general"
    best_strength = 0
    for keyword, task, strength in MODEL_SPECIALTIES:
        if keyword.lower() in mid and strength > best_strength:
            best_task = task
            best_strength = strength
    return best_task, best_strength


# ─── Model Scoring ───────────────────────────────────────────────────────────

def score_model(provider: dict, health: tuple, task: str = "general") -> int:
    """Score 0-250. Higher = better fit for the given task."""
    healthy, msg = health
    if not healthy:
        return 0

    score = 100  # base for healthy

    if provider["is_free"]:
        score += 50
    else:
        score += 20

    # Task-specific specialty (biggest factor)
    model_id = provider["model_id"].lower()
    spec_task, spec_strength = get_model_specialty(model_id)

    if spec_task == task:
        score += spec_strength
    elif spec_task == "reasoning" and task in ("coding", "general", "chat"):
        score += spec_strength // 2
    elif spec_task in ("coding", "chat", "fast") and task == "general":
        score += spec_strength // 2

    # Fallback capability bonus for unknown models
    if spec_task == "general":
        if any(t in model_id for t in CAPABILITY_TIER["reasoning"]):
            score += 25
        elif any(t in model_id for t in CAPABILITY_TIER["general"]):
            score += 15

    # Provider reliability
    prov = provider["provider"].lower()
    if "azure" in prov:
        score += 15
    elif "openrouter" in prov and provider["is_free"]:
        score -= 5  # free openrouter can be slow but not worthless

    # Deduct for known OpenRouter "gate" patterns
    if detect_free_tier_gate(provider, msg):
        score -= 60

    return score

# ─── Health Checks (Parallel) ────────────────────────────────────────────────

def _parse_retry_after(r: requests.Response) -> Optional[int]:
    """Extract retry-after seconds from 429/503 responses. Returns None if absent."""
    # requests.Response.headers is CaseInsensitiveDict — single check for Retry-After
    h = r.headers.get("Retry-After")
    if h:
        try:
            return max(0, int(h))
        except ValueError:
            # Try parsing as HTTP-date: "Wed, 21 Oct 2015 07:28:00 GMT"
            # Strip timezone manually to avoid %Z platform dependence
            try:
                parts = h.rsplit(" ", 1)
                date_str = parts[0]
                if len(parts) > 1:
                    date_str = date_str.rstrip(",")
                retry_dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S")
                return max(0, int((retry_dt - datetime.now()).total_seconds()))
            except:
                pass
    # x-ratelimit-reset (common in OpenRouter/OpenAI) — Unix timestamp or ISO date
    h2 = r.headers.get("x-ratelimit-reset")
    if h2:
        try:
            reset_ts = float(h2)
            return max(0, int(reset_ts - time.time()))
        except ValueError:
            try:
                reset_dt = datetime.fromisoformat(h2.replace("Z", "+00:00"))
                return max(0, int((reset_dt - datetime.now()).total_seconds()))
            except:
                pass
    return None


def _build_rate_limit_msg(status: int, r: requests.Response) -> str:
    """Build a status message with retry-after info for 429/503."""
    retry = _parse_retry_after(r)
    retry_suffix = f", retry in {retry}s" if retry is not None else ""
    return f"rate limited ({status}){retry_suffix}"


def _response_error_summary(r: requests.Response, limit: int = 200) -> str:
    """Return a compact, user-facing response error message."""
    try:
        data = r.json()
        message = (
            data.get("error", {}).get("message")
            or data.get("message")
            or data.get("error")
        )
        if isinstance(message, dict):
            message = message.get("message") or str(message)
        if message:
            return str(message)[:limit]
    except Exception:
        pass
    return (r.text or "").strip()[:limit]


def _check_openrouter_model_completion(provider: dict, session: requests.Session) -> tuple[bool, str]:
    key = provider.get("api_key")
    model_id = provider.get("deployment") or provider.get("model_id")
    if not key:
        return False, "no API key"
    if not model_id:
        return False, "no model id"

    try:
        r = session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "ok"}],
                "max_tokens": 1,
                "temperature": 0,
            },
            timeout=8,
        )
        if r.status_code == 200:
            return True, f"model responding ({model_id})"
        if r.status_code in (429, 503):
            return False, _build_rate_limit_msg(r.status_code, r)
        if r.status_code in (402, 403):
            detail = _response_error_summary(r)
            suffix = f": {detail}" if detail else ""
            return False, f"usage unavailable ({r.status_code}){suffix}"
        detail = _response_error_summary(r)
        suffix = f": {detail}" if detail else ""
        return False, f"model check HTTP {r.status_code}{suffix}"
    except Exception as e:
        return False, str(e)


def _check_openai_compatible(provider: dict, session: requests.Session) -> tuple[bool, str]:
    endpoint = (provider.get("endpoint") or _provider_default(provider.get("provider", ""), "endpoint") or "").rstrip("/")
    model_id = provider.get("deployment") or provider.get("model_id")
    if not endpoint:
        return True, "no health check available"

    headers = {"Content-Type": "application/json"}
    api_key = provider.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if provider.get("_force_model_probe") and model_id:
            r = session.post(
                f"{endpoint}/chat/completions",
                headers=headers,
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "ok"}],
                    "max_tokens": 1,
                    "temperature": 0,
                    "stream": False,
                },
                timeout=8,
            )
            if r.status_code == 200:
                return True, f"model responding ({model_id})"
            if r.status_code in (429, 503):
                return False, _build_rate_limit_msg(r.status_code, r)
            detail = _response_error_summary(r)
            suffix = f": {detail}" if detail else ""
            return False, f"model check HTTP {r.status_code}{suffix}"

        r = session.get(f"{endpoint}/models", headers=headers, timeout=5)
        if r.status_code == 200:
            return True, "healthy"
        if r.status_code in (429, 503):
            return False, _build_rate_limit_msg(r.status_code, r)
        if r.status_code in (401, 403):
            return False, f"access denied ({r.status_code})"
        detail = _response_error_summary(r)
        suffix = f": {detail}" if detail else ""
        return False, f"HTTP {r.status_code}{suffix}"
    except requests.ConnectionError:
        return False, f"not running ({endpoint})"
    except Exception as e:
        return False, str(e)


def _check_openrouter(provider: dict, session: requests.Session) -> tuple[bool, str]:
    key = provider.get("api_key")
    if not key:
        return False, "no API key"
    try:
        r = session.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {key}"},
            timeout=4,
        )
        if r.status_code == 200:
            data = r.json().get("data", {})
            credits = data.get("credits", 0)
            limit = data.get("limit", 0)

            if credits is not None and credits <= 0:
                return False, "0 credits remaining"
            if provider.get("_force_model_probe"):
                return _check_openrouter_model_completion(provider, session)
            if limit and credits and credits / limit < 0.05:
                return True, f"low credits (${credits:.2f})"

            return True, f"healthy (${credits:.2f} credits)"
        elif r.status_code == 429:
            return False, _build_rate_limit_msg(429, r)
        elif r.status_code == 402:
            return False, "payment required (402)"
        elif r.status_code == 401:
            return False, "invalid API key (401)"
        else:
            body = r.text[:200]
            return False, f"HTTP {r.status_code}: {body}"
    except Exception as e:
        return False, str(e)

def _check_google_ai(provider: dict, session: requests.Session) -> tuple[bool, str]:
    key = provider.get("api_key")
    if not key:
        return False, "no API key"
    model_id = provider["deployment"].replace("gemini/", "")
    try:
        r = session.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": "ok"}]}]},
            timeout=4,
        )
        if r.status_code == 200:
            return True, "healthy"
        elif r.status_code == 429:
            return False, _build_rate_limit_msg(429, r)
        elif r.status_code == 404:
            return False, f"model not found (404): {model_id}"
        elif r.status_code == 403:
            return False, "quota exceeded (403)"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

def _check_azure(provider: dict, session: requests.Session) -> tuple[bool, str]:
    key = provider.get("api_key")
    endpoint = provider.get("endpoint")
    if not key or not endpoint:
        return False, "missing API key or endpoint"
    try:
        r = session.get(
            f"{endpoint.rstrip('/')}/openai/models?api-version=2024-10-01-preview",
            headers={"api-key": key},
            timeout=5,
        )
        if r.status_code == 200:
            return True, "healthy"
        elif r.status_code == 429:
            return False, _build_rate_limit_msg(429, r)
        elif r.status_code == 403:
            return False, "access denied (403)"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)

def _check_ollama(provider: dict, session: requests.Session) -> tuple[bool, str]:
    """Check Ollama local server. Distinguishes 'loading (cold start)' from dead."""
    try:
        r = session.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        try:
            models = r.json().get("models", [])
        except (json.JSONDecodeError, ValueError):
            return True, "server up, unexpected response"
        desired = provider.get("model_id", "").replace("ollama:", "")

        # Warm-up ping — try a tiny generation even if model not in loaded list
        # (Ollama auto-loads unlisted models on first request, takes 10-15s into VRAM)
        if desired:
            try:
                wr = session.post(
                    "http://localhost:11434/api/generate",
                    json={"model": desired, "prompt": "ok", "stream": False,
                           "options": {"num_predict": 1, "temperature": 0}},
                    timeout=2,
                )
                if wr.status_code == 200:
                    return True, f"loaded and ready ({len(models)} models)"
                return True, f"model responding but HTTP {wr.status_code}"
            except requests.Timeout:
                return True, "loading (cold start into VRAM)"
            except requests.ConnectionError:
                return True, "loading (model restarting)"

        return True, f"running ({len(models)} models loaded)"
    except requests.ConnectionError:
        return False, "Ollama not running (http://localhost:11434)"
    except Exception as e:
        return False, str(e)


def _check_lm_studio(provider: dict, session: requests.Session) -> tuple[bool, str]:
    """Check LM Studio local server. Does a quick completion check."""
    try:
        r = session.get("http://localhost:1234/v1/models", timeout=3)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        desired = provider.get("model_id", "local")
        try:
            wr = session.post(
                f"{provider.get('endpoint', 'http://localhost:1234')}/v1/chat/completions",
                json={"model": desired, "messages": [{"role": "user", "content": "ok"}],
                       "max_tokens": 1, "stream": False},
                timeout=3,
            )
            if wr.status_code == 200:
                return True, "loaded and ready"
            return True, f"running but completion HTTP {wr.status_code}"
        except requests.Timeout:
            return True, "loading (model cold-start into VRAM)"
        except requests.ConnectionError:
            return True, "loading (model restarting)"
        except (json.JSONDecodeError, ValueError):
            return True, "running (server up)"

    except requests.ConnectionError:
        return False, "LM Studio not running (http://localhost:1234)"
    except Exception as e:
        return False, str(e)


def _check_vllm(provider: dict, session: requests.Session) -> tuple[bool, str]:
    """Check vLLM/TGI server. Does a quick completion check."""
    endpoint = provider.get("endpoint", "http://localhost:8000").rstrip("/")
    try:
        r = session.get(f"{endpoint}/v1/models", timeout=3)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        desired = provider.get("model_id", "local")
        try:
            wr = session.post(
                f"{endpoint}/v1/chat/completions",
                json={"model": desired, "messages": [{"role": "user", "content": "ok"}],
                       "max_tokens": 1, "stream": False},
                timeout=3,
            )
            if wr.status_code == 200:
                return True, "loaded and ready"
            return True, f"running but completion HTTP {wr.status_code}"
        except requests.Timeout:
            return True, "loading (model cold-start into VRAM)"
        except requests.ConnectionError:
            return True, "loading (model restarting)"
        except (json.JSONDecodeError, ValueError):
            return True, "running (server up)"

    except requests.ConnectionError:
        return False, f"vLLM not running ({endpoint})"
    except Exception as e:
        return False, str(e)


def discover_local_models(providers: list):
    """Scan for local model servers in parallel. Quick timeout per endpoint."""
    endpoints = {
        "ollama": ("http://localhost:11434", "api/tags", True),
        "lm-studio": ("http://localhost:1234", "v1/models", False),
        "vllm": ("http://localhost:8000", "v1/models", False),
        "localai": ("http://localhost:8080", "v1/models", False),
        "jan": ("http://localhost:1337", "v1/models", False),
        "llama-cpp": ("http://localhost:8080", "v1/models", False),
        "text-generation-webui": ("http://localhost:5000", "v1/models", False),
    }
    session = _get_session()
    _local_lock = threading.Lock()

    def check_endpoint(name, base_url, check_path, is_ollama):
        key = f"{name}:local"
        if any(p["key"] == key for p in providers):
            return
        try:
            r = session.get(f"{base_url}/{check_path}", timeout=1.5)
            if r.status_code == 200:
                    if is_ollama:
                        model_list = r.json().get("models", [])
                        with _local_lock:
                            for m in model_list:
                                mname = m.get("name", "unknown")
                                providers.append({
                                    "key": f"ollama:{mname}", "provider": "ollama",
                                    "model_id": mname, "deployment": mname,
                                    "api_key": None, "endpoint": base_url,
                                    "is_free": True, "source": "local", "is_active": False,
                                })
                        if model_list:
                            log(f"Local: {len(model_list)} Ollama models found")
                    else:
                        found = []
                        try:
                            payload = r.json()
                            raw_models = payload.get("data") or payload.get("models") or []
                            for m in raw_models:
                                if isinstance(m, str):
                                    found.append(m)
                                elif isinstance(m, dict):
                                    found.append(m.get("id") or m.get("name"))
                        except Exception:
                            found = []
                        with _local_lock:
                            for model_id in [m for m in found if m] or ["local"]:
                                _append_provider(
                                    providers, name, model_id, api_key=None,
                                    endpoint=base_url, source="local",
                                    is_free=True, is_active=False,
                                )
                    log(f"Local: {name} running at {base_url}")
        except:
            pass

    with ThreadPoolExecutor(max_workers=3) as ex:
        for name, (base_url, check_path, is_ollama) in endpoints.items():
            ex.submit(check_endpoint, name, base_url, check_path, is_ollama)


def check_model(provider: dict) -> tuple[bool, str]:
    """Backward-compatible single-model check. Uses shared session."""
    s = _get_session()
    return _checked_model_with_session(provider, s)

# ─── Backward-compatible wrappers (used by tests) ─────────────────────────

def check_openrouter(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_openrouter(provider, s)

def check_google_ai(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_google_ai(provider, s)

def check_azure(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_azure(provider, s)

def check_ollama(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_ollama(provider, s)

def check_lm_studio(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_lm_studio(provider, s)

def check_vllm(provider: dict) -> tuple[bool, str]:
    s = _get_session()
    return _check_vllm(provider, s)


def detect_free_tier_gate(provider: dict, msg: str) -> bool:
    """Detect if a free model is behind a 'buy tokens' gate."""
    if not provider.get("is_free"):
        return False
    if not msg:
        return False
    return any(re.search(p, msg.lower()) for p in OPENROUTER_GATE_PATTERNS)

CACHE_FILE = STATE_DIR / "health_cache.json"
CACHE_TTL = 120  # seconds before re-checking healthy models


def _load_health_cache() -> dict:
    data = _read_json_with_backup(CACHE_FILE, {})
    if isinstance(data, dict):
        try:
            now = time.time()
            return {
                k: (v["healthy"], v["msg"])
                for k, v in data.items()
                if isinstance(v, dict) and now - v.get("time", 0) < CACHE_TTL
            }
        except Exception:
            pass
    return {}


def _save_health_cache(results: dict):
    now = time.time()
    data = {
        k: {"healthy": h, "msg": m, "time": now}
        for k, (h, m) in results.items() if h  # only cache healthy
    }
    _atomic_write_json(CACHE_FILE, data, indent=2)


_CHECK_SESSION = None

def _get_session() -> requests.Session:
    global _CHECK_SESSION
    if _CHECK_SESSION is None:
        s = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=20,
            max_retries=0
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _CHECK_SESSION = s
    return _CHECK_SESSION


def check_all_parallel(chain: list[dict], cached_health: dict = None,
                       force_check_keys: set[str] = None) -> dict:
    """Check ALL models in parallel. Uses cache for all healthy models, not just active.
    Deduplicates by API key — only one health check per provider+key combo."""
    results = {}
    cache = cached_health or {}
    force_keys = force_check_keys or set()

    unique_checks = {}
    for p in chain:
        key = p["key"]
        force_check = key in force_keys
        dedup_key = f"{p['provider']}:{str(p.get('api_key') or 'none')[:8]}"
        if force_check:
            dedup_key = f"{dedup_key}:{key}"
        if dedup_key not in unique_checks:
            unique_checks[dedup_key] = []

        if is_depleted(key):
            continue

        # Use cache for ANY healthy model, not just active
        cached = cache.get(key)
        if cached and cached[0] and not force_check:
            results[key] = cached
            continue

        if force_check:
            p = dict(p)
            p["_force_model_probe"] = True

        unique_checks[dedup_key].append(p)

    if not any(v for v in unique_checks.values()):
        return results

    session = _get_session()
    dedup_results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {}
        for dedup_key, providers in unique_checks.items():
            if providers:
                futures[ex.submit(_checked_model_with_session, providers[0], session)] = dedup_key

        for future in as_completed(futures):
            dedup_key = futures[future]
            try:
                dedup_results[dedup_key] = future.result()
            except Exception as e:
                dedup_results[dedup_key] = (False, str(e))

    for dedup_key, providers in unique_checks.items():
        health = dedup_results.get(dedup_key, (False, "no check"))
        for p in providers:
            results[p["key"]] = health

    return results


def _checked_model_with_session(provider: dict, session: requests.Session) -> tuple:
    """Wrapper that passes the shared session to check functions."""
    prov_name = provider["provider"].lower()
    if prov_name == "openrouter":
        return _check_openrouter(provider, session)
    elif "google" in prov_name:
        return _check_google_ai(provider, session)
    elif "azure" in prov_name:
        return _check_azure(provider, session)
    elif prov_name == "ollama":
        return _check_ollama(provider, session)
    elif prov_name in ("lm-studio", "lm_studio"):
        return _check_lm_studio(provider, session)
    elif prov_name == "vllm":
        return _check_vllm(provider, session)
    elif prov_name in OPENAI_COMPATIBLE_PROVIDERS or provider.get("endpoint"):
        return _check_openai_compatible(provider, session)
    else:
        return True, "no health check available"

# ─── Config Writers ──────────────────────────────────────────────────────────

def update_opencode_config(model_key: str) -> bool:
    for cfg_path in CONFIG_PATHS:
        if not cfg_path.exists() or cfg_path.suffix not in (".json", ".jsonc"):
            continue
        try:
            text = cfg_path.read_text(encoding="utf-8")
            provider, model_id = model_key.split(":", 1)
            text = re.sub(r'"model"\s*:\s*"[^"]*"', f'"model": "{model_id}"', text)
            cfg_path.write_text(text, encoding="utf-8")
            log(f"opencode config updated: model -> {model_id} (in {cfg_path.name})")
            return True
        except Exception as e:
            log(f"failed to update {cfg_path.name}: {e}")
    return False

def update_claude_config(model_key: str) -> bool:
    claude_path = Path.cwd() / "CLAUDE.md"
    if not claude_path.exists():
        return False
    try:
        text = claude_path.read_text(encoding="utf-8")
        model_id = model_key.split(":", 1)[1] if ":" in model_key else model_key
        if re.search(r"model:\s*\S+", text):
            text = re.sub(r"model:\s*\S+", f"model: {model_id}", text)
        else:
            text += f"\nmodel: {model_id}\n"
        claude_path.write_text(text, encoding="utf-8")
        log(f"Claude config updated: model -> {model_id}")
        return True
    except Exception as e:
        log(f"failed to update CLAUDE.md: {e}")
        return False

# ─── Core Logic ──────────────────────────────────────────────────────────────

def detect_usage_limit_error(text: str) -> Optional[str]:
    """Return a depletion reason when CLI output indicates quota/usage exhaustion."""
    if not text:
        return None
    lowered = text.lower()
    for pattern in USAGE_LIMIT_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            snippet_start = max(0, match.start() - 80)
            snippet_end = min(len(text), match.end() + 120)
            snippet = re.sub(r"\s+", " ", text[snippet_start:snippet_end]).strip()
            return snippet[:220] or match.group(0)
    return None


def _cli_state_name(command: str) -> str:
    name = Path(command).stem if command else "opencode"
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or "opencode"


def _is_metadata_command(command: list[str]) -> bool:
    if len(command) < 2:
        return False
    first_arg = str(command[1]).lower()
    return first_arg in ("--version", "version", "-v", "--help", "-h", "help")


def handle_runtime_failure(cli: str = "opencode", output: str = "",
                           exit_code: int = 1, silent: bool = False) -> bool:
    """Mark the active model depleted and switch if CLI output shows usage exhaustion."""
    reason = detect_usage_limit_error(output)
    if not reason:
        return False

    active_key = get_active(cli) or get_active("opencode")
    if active_key:
        mark_depleted(active_key, f"runtime usage limit: {reason}", cooldown_minutes=30)
        record_model_usage(active_key, cli=cli, outcome="depleted", exit_code=exit_code)
        log(f"Runtime depletion detected for {active_key}: {reason}")
    else:
        log(f"Runtime usage limit detected with no active model: {reason}")

    switched = switch(cli, silent=silent)
    if not switched and cli != "opencode":
        switched = switch("opencode", silent=silent)
    return switched


def run_wrapped_cli(command: list[str], cli: str = "", retry_once: bool = True) -> int:
    """Run a CLI, stream output, and retry once after usage-limit model switching."""
    if not command:
        print("Usage: python switcher.py run <cli> -- [args...]")
        return 2

    cli_name = cli or _cli_state_name(command[0])
    learn_usage = not _is_metadata_command(command)
    switch(cli_name, silent=True, record_selection=learn_usage)

    def run_once() -> tuple[int, str]:
        tail = []
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=None,
            text=True,
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            tail.append(line)
            if len(tail) > 400:
                tail.pop(0)
        return proc.wait(), "".join(tail)

    exit_code, output_tail = run_once()
    active_after_run = get_active(cli_name) or get_active("opencode")
    if exit_code == 0:
        if learn_usage:
            record_model_usage(active_after_run, cli=cli_name, outcome="success", exit_code=exit_code)
        return exit_code
    if not retry_once:
        if learn_usage:
            record_model_usage(active_after_run, cli=cli_name, outcome="failure", exit_code=exit_code)
        return exit_code

    if handle_runtime_failure(cli_name, output_tail, exit_code, silent=False):
        print("[switcher] Retrying once with the next best model...")
        retry_code, retry_tail = run_once()
        retry_active = get_active(cli_name) or get_active("opencode")
        if retry_code == 0:
            if learn_usage:
                record_model_usage(retry_active, cli=cli_name, outcome="success", exit_code=retry_code)
            return retry_code
        if retry_code != 0:
            if not handle_runtime_failure(cli_name, retry_tail, retry_code, silent=True):
                if learn_usage:
                    record_model_usage(retry_active, cli=cli_name, outcome="failure", exit_code=retry_code)
        return retry_code

    if learn_usage:
        record_model_usage(active_after_run, cli=cli_name, outcome="failure", exit_code=exit_code)
    return exit_code


def build_chain(providers: list[dict]) -> list[dict]:
    free_models = [p for p in providers if p["is_free"]]
    paid_models = [p for p in providers if not p["is_free"]]
    return free_models + paid_models

def discover():
    log("Discovering models...")
    providers = discover_providers()
    if not providers:
        discover_from_env(providers)
    if not providers:
        print("  No models discovered. Set up API keys in opencode.jsonc or env vars.")
        return []

    seen = {}
    unique = []
    for p in providers:
        if p["key"] not in seen:
            seen[p["key"]] = True
            unique.append(p)

    print(f"\n  Discovered {len(unique)} models across {len(set(p['provider'] for p in unique))} providers:\n")
    for p in unique:
        active = "*" if p.get("is_active") else " "
        free_tag = "[FREE]" if p["is_free"] else "[PAID]"
        spec, _ = get_model_specialty(p["model_id"])
        print(f"  {active} {free_tag:7s} {spec:10s} {p['key']:<45} from {p['source']}")
    print()
    return unique

def status():
    state = load_state()
    providers = discover_providers()
    chain = build_chain(providers)
    active_key = get_active("opencode")
    task = detect_task()

    print(f"\n  Auto Model Switcher v2 — Status\n")
    print(f"  State file: {STATE_FILE}")
    print(f"  Models discovered: {len(providers)}")
    print(f"  Depleted models: {len(state.get('depleted', {}))}")
    print(f"  Last switch: {state.get('last_switch', 'never')}")
    print(f"  Detected task: {task}\n")

    if active_key:
        spec, _ = get_model_specialty(active_key)
        print(f"  Active model: {active_key}  (specialty: {spec})")
    else:
        print(f"  Active model: (not set)")

    # Recovery ETA if all depleted
    eta = get_recovery_eta()
    if eta["all_depleted"] and state.get("depleted"):
        fastest = eta.get("fastest_recovery")
        if fastest:
            secs = fastest.get("seconds_remaining", fastest["minutes"] * 60)
            if secs < 120:
                print(f"\n  All models depleted. Next recovery: ~{secs}s ({fastest['key']})")
            else:
                print(f"\n  All models depleted. Next recovery: ~{fastest['minutes']} min ({fastest['key']})")
        print(f"\n  Per-model recovery ETAs:")
        for key, info in sorted(eta["models"].items(), key=lambda x: x[1]["minutes_remaining"]):
            reason_short = info["reason"][:40]
            secs = info.get("seconds_remaining", info["minutes_remaining"] * 60)
            if secs < 120:
                print(f"    {key:<50} {secs:3d}s  ({reason_short})")
            else:
                print(f"    {key:<50} {info['minutes_remaining']:3d} min  ({reason_short})")
        print()

    if state.get("depleted") and not eta["all_depleted"]:
        print(f"\n  Some models depleted:")
        for key, info in state["depleted"].items():
            until = info.get("cooldown_until", "?")
            print(f"    X {key:<50} cooldown until {until[:19]}")
        print()

    learned = most_used_models()
    if learned:
        print(f"  Learned usage preferences:")
        for key, info in learned:
            runs = int(info.get("runs", 0))
            successes = int(info.get("successes", 0))
            failures = int(info.get("failures", 0))
            print(f"    {key:<50} runs={runs} ok={successes} fail={failures}")
        print()

    print(f"  Model chain (free first, priority order):\n")
    for i, p in enumerate(chain, 1):
        key = p["key"]
        is_act = key == active_key
        is_dep = is_depleted(key)
        spec, _ = get_model_specialty(p["model_id"])
        status_icon = "*" if is_act else " "
        dep_icon = " [depleted]" if is_dep else ""
        free_tag = "F" if p["is_free"] else "P"
        match_tag = " <<< BEST FOR TASK" if is_act else ""
        print(f"  {i:2d}. {status_icon} [{free_tag}] {spec:10s} {key:<45}{dep_icon}{match_tag}")
    print()
    return chain


def _doctor_item(level: str, name: str, detail: str) -> dict:
    return {"level": level, "name": name, "detail": detail}


def _validate_state_for_doctor(state: dict) -> list[dict]:
    items = []
    for key, entry in state.get("depleted", {}).items():
        try:
            datetime.fromisoformat(entry.get("cooldown_until", ""))
        except Exception:
            items.append(_doctor_item("FAIL", "depleted-state",
                                      f"{key} has invalid cooldown_until"))
    for key, usage in state.get("knowledge", {}).get("usage", {}).items():
        for field in ("runs", "successes", "failures", "runtime_depletions"):
            try:
                int(usage.get(field, 0))
            except Exception:
                items.append(_doctor_item("FAIL", "usage-state",
                                          f"{key} has non-numeric {field}"))
    if not items:
        items.append(_doctor_item("OK", "state-shape", "state.json schema is readable"))
    return items


def doctor(run_health: bool = False) -> bool:
    """Local self-diagnostics for config, state, wrappers, CLIs, and optional health."""
    items = []

    state = load_state()
    items.extend(_validate_state_for_doctor(state))

    providers = discover_providers()
    if providers:
        items.append(_doctor_item("OK", "discovery",
                                  f"discovered {len(providers)} model entries"))
    else:
        items.append(_doctor_item("WARN", "discovery",
                                  "no models discovered from config or env"))

    key_counts = {}
    for p in providers:
        key_counts[p["key"]] = key_counts.get(p["key"], 0) + 1
    duplicate_keys = sorted(k for k, count in key_counts.items() if count > 1)
    if duplicate_keys:
        items.append(_doctor_item("FAIL", "discovery-duplicates",
                                  ", ".join(duplicate_keys[:5])))
    else:
        items.append(_doctor_item("OK", "discovery-duplicates", "no duplicate model keys"))

    active = state.get("active", {})
    for cli, model_key in active.items():
        if providers and model_key not in {p["key"] for p in providers}:
            items.append(_doctor_item("WARN", "active-model",
                                      f"{cli} active model {model_key} is not currently discovered"))

    for path in (STATE_FILE, CONTEXT_FILE, MCP_STATE_FILE, CACHE_FILE):
        if path.exists():
            try:
                json.loads(path.read_text(encoding="utf-8"))
                items.append(_doctor_item("OK", "json", f"{path.name} is valid JSON"))
            except Exception as e:
                backup = path.with_suffix(path.suffix + ".bak")
                if backup.exists():
                    items.append(_doctor_item("WARN", "json",
                                              f"{path.name} is corrupt but backup exists: {e}"))
                else:
                    items.append(_doctor_item("FAIL", "json",
                                              f"{path.name} is corrupt and no backup exists: {e}"))

    wrapper_files = [Path("auto-switch.bat"), Path("auto-switch.ps1"), Path("ams.ps1"),
                     Path("hooks") / "opencode_hook.ps1"]
    for wrapper in wrapper_files:
        if wrapper.exists():
            items.append(_doctor_item("OK", "wrapper", f"{wrapper} exists"))
        else:
            items.append(_doctor_item("WARN", "wrapper", f"{wrapper} missing"))

    cli_names = ["opencode", "claude", "codex", "gemini", "qwen", "cursor",
                 "code", "aider", "windsurf", "continue", "goose", "zed"]
    found = []
    for name in cli_names:
        if shutil.which(name):
            found.append(name)
    if found:
        items.append(_doctor_item("OK", "cli-path", "found: " + ", ".join(found)))
    else:
        items.append(_doctor_item("WARN", "cli-path", "no known agent CLIs found in PATH"))

    if run_health and providers:
        health = check_all_parallel(build_chain(providers), force_check_keys={get_active("opencode")} if get_active("opencode") else set())
        bad = [f"{k}: {v[1]}" for k, v in health.items() if not v[0]]
        if bad:
            items.append(_doctor_item("WARN", "health", "; ".join(bad[:5])))
        else:
            items.append(_doctor_item("OK", "health", "checked models are healthy or skipped"))

    print("\n  Auto Model Switcher v2 - Doctor\n")
    for item in items:
        icon = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(item["level"], "[INFO]")
        print(f"  {icon:6s} {item['name']:<22} {item['detail']}")
    print()
    return not any(item["level"] == "FAIL" for item in items)


def switch(cli: str = "opencode", silent: bool = False,
           record_selection: bool = True) -> bool:
    providers = discover_providers()
    chain = build_chain(providers)

    if not chain:
        log("No models available to switch to!")
        return False

    task = detect_task()
    active_key = get_active(cli)
    log(f"Active model: {active_key} | Task: {task}")

    # Phase 1: Check ALL models in parallel (<4s)
    log(f"Checking {len(chain)} models in parallel...")
    cached = _load_health_cache()
    force_check_keys = {p["key"] for p in chain if p.get("is_active")}
    if active_key:
        force_check_keys.add(active_key)
    health_results = check_all_parallel(
        chain, cached_health=cached, force_check_keys=force_check_keys
    )
    _save_health_cache(health_results)

    # Phase 2: Score and rank by task relevance
    scored = []
    for p in chain:
        key = p["key"]
        health = health_results.get(key, (False, "no check"))
        healthy, msg = health

        # Detect OpenRouter free-tier gate (e.g., "buy 10 tokens get 1000 free")
        if healthy and detect_free_tier_gate(p, msg):
            log(f"  {key}: free-tier gate detected ({msg})")
            mark_depleted(key, f"free-tier gate: {msg}", cooldown_minutes=60)
            healthy = False

        # Local model cold-start: loading into VRAM, don't deplete — schedule re-check
        is_cold_start = "cold start" in msg.lower()
        if is_cold_start and healthy:
            log(f"  {key}: cold start detected ({msg}), scheduling warm-up re-check")
            scored.append((score_model(p, health, task) - 30, p, msg))
            continue

        if not healthy:
            if not is_depleted(key):
                mark_depleted(key, msg, cooldown_minutes=30)
            continue

        if is_depleted(key):
            continue

        score = score_model(p, health, task) + model_usage_bonus(key, cli)
        if score > 0:
            scored.append((score, p, msg))

    scored.sort(key=lambda x: -x[0])

    if not scored:
        if not silent:
            eta = get_recovery_eta()
            print("\n  [FAIL] All models are depleted.")
            if eta.get("fastest_recovery"):
                f = eta["fastest_recovery"]
                secs = f.get("seconds_remaining", f["minutes"] * 60)
                if secs < 120:
                    print(f"  Next recovery: ~{secs}s ({f['key']})")
                else:
                    print(f"  Next recovery: ~{f['minutes']} min ({f['key']})")
            print(f"\n  Per-model recovery:")
            for key, info in sorted(eta["models"].items(), key=lambda x: x[1]["minutes_remaining"]):
                secs = info.get("seconds_remaining", info["minutes_remaining"] * 60)
                if secs < 120:
                    print(f"    {key:<50} {secs:3d}s  ({info['reason'][:50]})")
                else:
                    print(f"    {key:<50} {info['minutes_remaining']:3d} min  ({info['reason'][:50]})")
            print()
        log("All models depleted!")
        return False

    # Phase 3: Pick best model for the detected task
    best_score, best_provider, best_msg = scored[0]
    best_key = best_provider["key"]

    prev_key = active_key
    set_active(cli, best_key)
    if record_selection:
        record_model_usage(best_key, cli=cli, outcome="selected")

    if prev_key and prev_key != best_key:
        save_context(prev_key, best_key, f"auto-switch: {best_msg}",
                     f"Switched from {prev_key} to {best_key} ({best_msg})")
        log(f"Context saved: {prev_key} -> {best_key}")

    if cli == "opencode":
        update_opencode_config(best_key)
    elif cli == "claude":
        update_claude_config(best_key)

    spec, spec_str = get_model_specialty(best_provider["model_id"])
    free_tag = "FREE" if best_provider["is_free"] else "PAID"
    if not silent:
        print(f"\n  [OK] Switched to: {best_key}")
        print(f"       Tier: {free_tag} | Specialty: {spec} | Task: {task} | Score: {best_score}")
        print(f"       Health: {best_msg}")
        placed = next((i+1 for i, (s, p, m) in enumerate(scored) if p["key"] == best_key), None)
        print(f"       Matches: #{placed} of {len(scored)} working models")
        print(f"       Reason: best {spec} model for {task} task\n")

    log(f"Switched {cli} -> {best_key} (score={best_score}, spec={spec}, task={task}, {best_msg})")
    return True

def watch(interval: int = 120):
    log(f"Starting watch mode (check every {interval}s)...")
    print(f"  Watching model health every {interval}s. Ctrl+C to stop.\n")

    try:
        while True:
            providers = discover_providers()
            chain = build_chain(providers)
            active_key = get_active("opencode")

            if active_key:
                health_results = check_all_parallel(chain)
                active_health = health_results.get(active_key)

                if active_health and not active_health[0]:
                    log(f"Active model {active_key} failed: {active_health[1]}")
                    mark_depleted(active_key, active_health[1])
                    print(f"  [FAIL] {active_key}: {active_health[1]}")
                    print(f"  Switching...")
                    switch("opencode")
                else:
                    log(f"Active model {active_key}: {active_health[1] if active_health else 'ok'}")
            else:
                log("No active model, running initial switch...")
                switch("opencode")

            # Recover expired depleted models
            state = load_state()
            for key in list(state.get("depleted", {}).keys()):
                entry = state["depleted"][key]
                cooldown = entry.get("cooldown_until")
                if cooldown and datetime.fromisoformat(cooldown) < datetime.now():
                    provider = next((p for p in chain if p["key"] == key), None)
                    if provider:
                        healthy, msg = check_model(provider)
                        if healthy and not detect_free_tier_gate(provider, msg):
                            mark_recovered(key)
                            log(f"Model {key} recovered: {msg}")
                            print(f"  [OK] {key} recovered: {msg}")

            time.sleep(interval)
    except KeyboardInterrupt:
        log("Watch mode stopped by user")
        print("\n  Watch mode stopped.")

# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return

    cmd = args[0]
    task_override = None
    silent = "--silent" in args

    if "--task" in args:
        idx = args.index("--task")
        if idx + 1 < len(args):
            task_override = args[idx + 1]

    if task_override:
        os.environ["AUTO_SWITCHER_TASK"] = task_override

    # Strip known flags from args for positional parsing
    known_flags = {"--task", "--silent"}
    positional = [a for a in args if a not in known_flags and not any(
        args[i] == "--task" and i + 1 < len(args) and args[i + 1] == a
        for i in range(len(args))
    )]
    if not positional:
        positional = args[:1]  # keep cmd at least

    if cmd == "discover":
        discover()
    elif cmd == "status":
        status()
    elif cmd == "doctor":
        sys.exit(0 if doctor(run_health="--health" in args) else 1)
    elif cmd == "switch":
        cli = positional[1] if len(positional) > 1 else "opencode"
        switch(cli, silent=silent)
    elif cmd == "watch":
        interval = int(positional[1]) if len(positional) > 1 else 120
        watch(interval)
    elif cmd == "handle-failure":
        cli = positional[1] if len(positional) > 1 else "opencode"
        output = ""
        if "--file" in args:
            idx = args.index("--file")
            if idx + 1 < len(args):
                output = Path(args[idx + 1]).read_text(encoding="utf-8", errors="replace")
        else:
            output = sys.stdin.read()
        sys.exit(0 if handle_runtime_failure(cli, output, silent=silent) else 1)
    elif cmd == "run":
        cli = positional[1] if len(positional) > 1 else ""
        if "--" in args:
            sep = args.index("--")
            command = args[sep + 1:]
        else:
            command = positional[2:] if cli else positional[1:]
        if cli and not command:
            command = [cli]
        sys.exit(run_wrapped_cli(command, cli=cli))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)

if __name__ == "__main__":
    main()
