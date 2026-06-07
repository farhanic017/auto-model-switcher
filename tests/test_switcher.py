#  Auto Model Switcher  ───  Test Suite (26 tests)
#  Copyright (c) 2026 Farhan Dhrubo  <farhaiee123@gmail.com>
#  License: GPL-3.0  —  https://github.com/farhanic017/auto-model-switcher
#
#  This program is free software. You may NOT remove this notice,
#  re-distribute as your own work, or sell without attribution.
# =============================================================================

"""Auto Model Switcher v2 — Tests"""

import json, sys, os, tempfile, types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

SAMPLE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "model": "opencode/big-pickle",
    "provider": {
        "google-ai": {
            "options": {"apiKey": "test-google-key"},
            "models": {"gemini/gemini-2.0-flash-001": {}},
        },
        "openrouter": {
            "options": {"apiKey": "sk-or-test-key"},
            "models": {
                "deepseek/deepseek-v4-flash:free": {},
                "qwen/qwen3-coder:free": {},
            },
        },
        "azure-openai": {
            "options": {"apiKey": "test-azure-key", "endpoint": "https://test.openai.azure.com"},
            "models": {"gpt-4o": {}, "o4-mini": {}},
        },
    },
}

# ─── Config Parsing ──────────────────────────────────────────────────────────

def test_parse_opencode_config():
    from switcher import parse_opencode_config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
        f.write(json.dumps(SAMPLE_CONFIG, indent=2))
        tmp = f.name
    try:
        cfg = parse_opencode_config(Path(tmp))
        assert cfg["model"] == "opencode/big-pickle"
        assert "google-ai" in cfg["provider"]
    finally:
        os.unlink(tmp)


def test_parse_with_comments():
    from switcher import parse_opencode_config
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
        f.write("""{
  // comment
  "model": "m1",
  "provider": {
    "p": {
      "options": {"apiKey": "k"},
      "models": {"m1": {}}
    }
  }
}""")
        tmp = f.name
    try:
        cfg = parse_opencode_config(Path(tmp))
        assert cfg["model"] == "m1"
    finally:
        os.unlink(tmp)


def test_parse_jsonc_preserves_comment_markers_inside_strings():
    from switcher import parse_opencode_config
    cases = [
        '{"model":"https://example.com/model","provider":{"p":{"models":{"m1":{}}}}}',
        '{"model":"m/*not-comment*/1","provider":{"p":{"models":{"m1":{}}}}}',
        '{"model":"m//not-comment","provider":{"p":{"models":{"m1":{}}}}}',
        """{
          "model": "m1",
          /* block comment */
          "provider": {"p": {"models": {"m1": {}}}}
        }""",
    ]
    for text in cases:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonc", delete=False) as f:
            f.write(text)
            tmp = f.name
        try:
            cfg = parse_opencode_config(Path(tmp))
            assert "model" in cfg
            assert "provider" in cfg
        finally:
            os.unlink(tmp)

# ─── State ───────────────────────────────────────────────────────────────────

def test_state_lifecycle():
    from switcher import (is_depleted, mark_depleted, mark_recovered,
                          load_state, save_state, get_active, set_active)
    state = load_state()
    key = "test:depleted-model"
    assert not is_depleted(key)
    mark_depleted(key, "test reason", cooldown_minutes=1)
    assert is_depleted(key)
    mark_recovered(key)
    assert not is_depleted(key)
    set_active("opencode", "test:active")
    assert get_active("opencode") == "test:active"
    state = load_state()
    state["depleted"].pop(key, None)
    save_state(state)


def test_context():
    from switcher import save_context, load_context
    save_context("model:a", "model:b", "test switch", "summary text")
    ctx = load_context()
    assert ctx["previous_model"] == "model:a"
    assert ctx["new_model"] == "model:b"
    assert ctx["switch_reason"] == "test switch"
    os.remove(Path.home() / ".auto-model-switcher" / "context.json")


def test_recovery_eta():
    from switcher import get_recovery_eta, mark_depleted, load_state, save_state
    eta = get_recovery_eta()
    assert not eta["all_depleted"]
    mark_depleted("test:model1", "out of credits", cooldown_minutes=60)
    eta = get_recovery_eta()
    assert eta["all_depleted"] is False  # active model isn't in depleted
    state = load_state()
    state["active"]["opencode"] = "test:model1"
    save_state(state)
    eta = get_recovery_eta()
    assert eta["all_depleted"] is True
    state = load_state()
    state["depleted"].pop("test:model1", None)
    save_state(state)

# ─── Model Scoring ───────────────────────────────────────────────────────────

def test_load_state_recovers_from_backup_when_primary_corrupt():
    from switcher import STATE_FILE, save_state, load_state
    original = load_state()
    marker = "test:backup-recovery"
    try:
        state = load_state()
        state["active"]["opencode"] = marker
        save_state(state)
        STATE_FILE.with_suffix(STATE_FILE.suffix + ".bak").write_text(
            json.dumps(state), encoding="utf-8"
        )
        STATE_FILE.write_text("{not json", encoding="utf-8")
        recovered = load_state()
        assert recovered["active"]["opencode"] == marker
    finally:
        save_state(original)


def test_health_cache_ignores_corrupt_primary_and_uses_backup():
    from switcher import CACHE_FILE, _load_health_cache, _save_health_cache
    CACHE_FILE.unlink(missing_ok=True)
    CACHE_FILE.with_suffix(CACHE_FILE.suffix + ".bak").unlink(missing_ok=True)
    try:
        _save_health_cache({"test:m": (True, "ok")})
        CACHE_FILE.with_suffix(CACHE_FILE.suffix + ".bak").write_text(
            CACHE_FILE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        CACHE_FILE.write_text("{bad", encoding="utf-8")
        assert _load_health_cache()["test:m"] == (True, "ok")
    finally:
        CACHE_FILE.unlink(missing_ok=True)
        CACHE_FILE.with_suffix(CACHE_FILE.suffix + ".bak").unlink(missing_ok=True)


def test_model_knowledge_remembers_discovery_and_usage():
    from switcher import (remember_discovered_models, record_model_usage,
                          load_state, save_state)
    key = "test:knowledge-model"
    state = load_state()
    state["knowledge"]["models"].pop(key, None)
    state["knowledge"]["usage"].pop(key, None)
    state["knowledge"]["cli_usage"].pop("opencode", None)
    save_state(state)

    remember_discovered_models([{
        "key": key, "provider": "test", "model_id": "knowledge-model",
        "deployment": "knowledge-model", "endpoint": None,
        "source": "test", "is_free": True,
    }])
    record_model_usage(key, cli="opencode", outcome="success", exit_code=0)

    state = load_state()
    assert key in state["knowledge"]["models"]
    assert state["knowledge"]["usage"][key]["runs"] == 1
    assert state["knowledge"]["usage"][key]["successes"] == 1
    assert state["knowledge"]["cli_usage"]["opencode"][key] == 1

    state["knowledge"]["models"].pop(key, None)
    state["knowledge"]["usage"].pop(key, None)
    state["knowledge"]["cli_usage"].pop("opencode", None)
    save_state(state)


def test_model_usage_bonus_prefers_successful_user_models():
    from switcher import record_model_usage, model_usage_bonus, load_state, save_state
    key = "test:preferred-model"
    state = load_state()
    state["knowledge"]["usage"].pop(key, None)
    state["knowledge"]["cli_usage"].pop("opencode", None)
    save_state(state)

    record_model_usage(key, cli="opencode", outcome="success", exit_code=0)
    record_model_usage(key, cli="opencode", outcome="success", exit_code=0)

    assert model_usage_bonus(key, cli="opencode") > 0

    state = load_state()
    state["knowledge"]["usage"].pop(key, None)
    state["knowledge"]["cli_usage"].pop("opencode", None)
    save_state(state)


def test_score_free_beat_paid():
    from switcher import score_model
    free_healthy = (True, "healthy")
    paid_healthy = (True, "healthy")
    free_score = score_model({"key": "f", "model_id": "m", "is_free": True, "provider": "test"}, free_healthy)
    paid_score = score_model({"key": "p", "model_id": "m", "is_free": False, "provider": "test"}, paid_healthy)
    assert free_score > paid_score, f"Free {free_score} should beat paid {paid_score}"


def test_score_zero_on_unhealthy():
    from switcher import score_model
    assert score_model({"key": "x", "model_id": "m", "is_free": False, "provider": "t"}, (False, "fail")) == 0


def test_score_reasoning_boost():
    from switcher import score_model
    h = (True, "healthy")
    base = score_model({"key": "x", "model_id": "gpt-4o", "is_free": False, "provider": "t"}, h)
    reasoning = score_model({"key": "x", "model_id": "o4-mini", "is_free": False, "provider": "t"}, h)
    assert reasoning > base

# ─── Health Checks ───────────────────────────────────────────────────────────

def test_check_openrouter_healthy():
    from unittest.mock import patch, MagicMock
    from switcher import check_openrouter, _get_session
    with patch("switcher._get_session") as mock_sess:
        mock_sess.return_value = MagicMock()
        mock_sess.return_value.get.return_value.status_code = 200
        mock_sess.return_value.get.return_value.json.return_value = {"data": {"credits": 50.0, "limit": 200.0}}
        h, m = check_openrouter({"api_key": "k"})
        assert h


def test_check_openrouter_zero_credits():
    from unittest.mock import patch, MagicMock
    from switcher import check_openrouter
    with patch("switcher._get_session") as mock_sess:
        mock_sess.return_value = MagicMock()
        mock_sess.return_value.get.return_value.status_code = 200
        mock_sess.return_value.get.return_value.json.return_value = {"data": {"credits": 0.0, "limit": 200.0}}
        h, m = check_openrouter({"api_key": "k"})
        assert not h
        assert "0 credits" in m


def test_check_openrouter_402():
    from unittest.mock import patch, MagicMock
    from switcher import check_openrouter
    with patch("switcher._get_session") as mock_sess:
        mock_sess.return_value = MagicMock()
        mock_sess.return_value.get.return_value.status_code = 402
        h, m = check_openrouter({"api_key": "k"})
        assert not h
        assert "0 credits" in m


def test_check_openrouter_402():
    from unittest.mock import patch, MagicMock
    from switcher import check_openrouter
    mock_session = MagicMock()
    mock_session.get.return_value.status_code = 402
    with patch("switcher._get_session", return_value=mock_session):
        h, m = check_openrouter({"api_key": "k"})
        assert not h

# ─── Free-Tier Gate Detection ────────────────────────────────────────────────

def test_check_openrouter_forced_model_probe_detects_usage_limit():
    from unittest.mock import MagicMock
    from switcher import _check_openrouter

    mock_session = MagicMock()
    auth = MagicMock()
    auth.status_code = 200
    auth.json.return_value = {"data": {"credits": 1.0, "limit": 100.0}}
    completion = MagicMock()
    completion.status_code = 429
    completion.headers = {"Retry-After": "120"}
    mock_session.get.return_value = auth
    mock_session.post.return_value = completion

    h, m = _check_openrouter({
        "api_key": "k",
        "model_id": "m1",
        "deployment": "m1",
        "_force_model_probe": True,
    }, mock_session)

    assert not h
    assert "rate limited (429)" in m
    mock_session.post.assert_called_once()


def test_check_openai_compatible_forced_model_probe():
    from unittest.mock import MagicMock
    from switcher import _check_openai_compatible

    mock_session = MagicMock()
    mock_session.post.return_value.status_code = 200
    h, m = _check_openai_compatible({
        "provider": "acme",
        "model_id": "acme-model",
        "deployment": "acme-model",
        "endpoint": "http://localhost:9999/v1",
        "api_key": "k",
        "_force_model_probe": True,
    }, mock_session)

    assert h is True
    assert "model responding" in m
    mock_session.post.assert_called_once()


def test_detect_free_tier_gate():
    from switcher import detect_free_tier_gate
    provider = {"is_free": True}
    assert detect_free_tier_gate(provider, "buy 10 tokens get 1000 free")
    assert detect_free_tier_gate(provider, "insufficient credits, add funds")
    assert detect_free_tier_gate(provider, "purchase credits to continue using free tier")
    assert not detect_free_tier_gate(provider, "healthy, 100 credits remaining")


def test_detect_gate_only_for_free():
    from switcher import detect_free_tier_gate
    assert not detect_free_tier_gate({"is_free": False}, "buy tokens free")

# ─── Parallel Checking ───────────────────────────────────────────────────────

def test_detect_usage_limit_error():
    from switcher import detect_usage_limit_error

    assert detect_usage_limit_error("Error 429: rate limit exceeded")
    assert detect_usage_limit_error("You have no credits remaining")
    assert detect_usage_limit_error("monthly spend limit reached")
    assert detect_usage_limit_error("quota exceeded for this model")
    assert detect_usage_limit_error("normal syntax error") is None


def test_detect_usage_limit_error_provider_message_matrix():
    from switcher import detect_usage_limit_error

    positive = [
        "OpenAI: You exceeded your current quota, please check your plan.",
        "Anthropic API error: rate_limit_error requests per minute exceeded.",
        "OpenRouter returned 402 payment required.",
        "Gemini quota exceeded for quota metric GenerateContent request.",
        "insufficient credits, add funds to continue.",
        "free tier limit reached for this model.",
        "monthly spend limit has been reached.",
    ]
    negative = [
        "SyntaxError: invalid syntax",
        "Cannot find module './missing'",
        "ECONNREFUSED localhost:3000",
        "Authentication failed: invalid API key",
    ]
    for msg in positive:
        assert detect_usage_limit_error(msg), msg
    for msg in negative:
        assert detect_usage_limit_error(msg) is None, msg


def test_metadata_commands_do_not_count_as_model_usage():
    from switcher import _is_metadata_command

    assert _is_metadata_command(["opencode", "--version"])
    assert _is_metadata_command(["aider", "--help"])
    assert _is_metadata_command(["claude", "version"])
    assert not _is_metadata_command(["opencode", "write some code"])


def test_handle_runtime_failure_marks_active_and_switches():
    from unittest.mock import patch
    from switcher import handle_runtime_failure

    with patch("switcher.get_active", return_value="openrouter:m1"), \
         patch("switcher.mark_depleted") as depleted, \
         patch("switcher.switch", return_value=True) as switched:
        ok = handle_runtime_failure(
            "opencode",
            "provider returned 429 rate limit exceeded",
            exit_code=1,
            silent=True,
        )

    assert ok is True
    depleted.assert_called_once()
    assert "runtime usage limit" in depleted.call_args.args[1]
    switched.assert_called_once_with("opencode", silent=True)


def test_handle_runtime_failure_ignores_non_usage_errors():
    from unittest.mock import patch
    from switcher import handle_runtime_failure

    with patch("switcher.mark_depleted") as depleted, \
         patch("switcher.switch") as switched:
        ok = handle_runtime_failure("opencode", "file not found", exit_code=1)

    assert ok is False
    depleted.assert_not_called()
    switched.assert_not_called()


def test_validate_state_for_doctor_catches_bad_cooldown():
    from switcher import _validate_state_for_doctor

    state = {
        "active": {},
        "depleted": {"test:m": {"cooldown_until": "not-a-date"}},
        "history": [],
        "last_switch": None,
        "knowledge": {"models": {}, "usage": {}, "cli_usage": {}},
    }
    items = _validate_state_for_doctor(state)
    assert any(i["level"] == "FAIL" and i["name"] == "depleted-state" for i in items)


def test_doctor_clean_config_passes(tmp_path, monkeypatch):
    from switcher import doctor, STATE_FILE, CACHE_FILE, CONTEXT_FILE, MCP_STATE_FILE

    monkeypatch.chdir(tmp_path)
    (tmp_path / "opencode.jsonc").write_text(json.dumps({
        "model": "m1",
        "provider": {"test": {"models": {"m1": {}, "m2": {}}}},
    }), encoding="utf-8")
    for path in (STATE_FILE, CACHE_FILE, CONTEXT_FILE, MCP_STATE_FILE):
        path.unlink(missing_ok=True)
        path.with_suffix(path.suffix + ".bak").unlink(missing_ok=True)

    assert doctor(run_health=False) is True


def test_check_all_parallel():
    from unittest.mock import patch
    from switcher import check_all_parallel
    chain = [{"key": "a:m1", "provider": "test", "model_id": "m1", "is_free": True}]
    with patch("switcher._checked_model_with_session") as mock:
        mock.return_value = (True, "mock ok")
        results = check_all_parallel(chain)
        assert "a:m1" in results
        assert results["a:m1"][0] is True


def test_check_all_parallel_forced_active_does_not_poison_same_key_models():
    from unittest.mock import patch
    from switcher import check_all_parallel

    chain = [
        {"key": "openrouter:m1", "provider": "openrouter", "model_id": "m1",
         "deployment": "m1", "api_key": "sk-test", "is_free": True},
        {"key": "openrouter:m2", "provider": "openrouter", "model_id": "m2",
         "deployment": "m2", "api_key": "sk-test", "is_free": True},
    ]

    def fake_check(provider, session):
        if provider.get("_force_model_probe"):
            return False, "rate limited (429)"
        return True, "healthy account"

    with patch("switcher._checked_model_with_session", side_effect=fake_check):
        results = check_all_parallel(chain, force_check_keys={"openrouter:m1"})

    assert results["openrouter:m1"] == (False, "rate limited (429)")
    assert results["openrouter:m2"] == (True, "healthy account")


def test_build_chain():
    from switcher import build_chain
    c = build_chain([
        {"key": "p", "is_free": False},
        {"key": "f", "is_free": True},
    ])
    assert c[0]["key"] == "f"
    assert c[1]["key"] == "p"


def test_discover_from_env():
    from switcher import discover_from_env
    os.environ["OPENAI_API_KEY"] = "test-key"
    providers = []
    discover_from_env(providers)
    assert any(p["provider"] == "openai" for p in providers)
    del os.environ["OPENAI_API_KEY"]

# ─── MCP State Preservation ───────────────────────────────────────────────────

def test_discover_from_env_catalog_and_custom_provider():
    from switcher import discover_from_env

    env_updates = {
        "GROQ_API_KEY": "test-groq",
        "GROQ_MODELS": "llama-a,llama-b",
        "ACME_API_KEY": "test-acme",
        "ACME_MODELS": "acme-model",
        "ACME_BASE_URL": "http://localhost:9999/v1",
    }
    old = {k: os.environ.get(k) for k in env_updates}
    try:
        os.environ.update(env_updates)
        providers = []
        discover_from_env(providers)
        keys = {p["key"] for p in providers}
        assert "groq:llama-a" in keys
        assert "groq:llama-b" in keys
        assert "acme:acme-model" in keys
        acme = next(p for p in providers if p["key"] == "acme:acme-model")
        assert acme["endpoint"] == "http://localhost:9999/v1"
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_discover_from_generic_mcp_env_config():
    from switcher import discover_from_generic_config

    providers = []
    cfg = {
        "mcpServers": {
            "agent": {
                "command": "agent",
                "env": {
                    "OPENROUTER_API_KEY": "sk-test",
                    "OPENROUTER_MODELS": "openrouter/auto,deepseek/deepseek-chat",
                },
            }
        }
    }
    discover_from_generic_config(cfg, providers, "mcp.json")
    keys = {p["key"] for p in providers}
    assert "openrouter:openrouter/auto" in keys
    assert "openrouter:deepseek/deepseek-chat" in keys


def test_discover_from_generic_agent_config():
    from switcher import discover_from_generic_config

    providers = []
    cfg = {
        "models": [
            {
                "provider": "groq",
                "model": "llama-agent",
                "apiKey": "test",
                "baseURL": "https://api.groq.com/openai/v1",
            }
        ]
    }
    discover_from_generic_config(cfg, providers, "continue.json")
    assert any(p["key"] == "groq:llama-agent" for p in providers)


def test_generic_config_does_not_duplicate_opencode_provider_map():
    from switcher import discover_from_opencode_data, discover_from_generic_config

    cfg = {
        "model": "m1",
        "provider": {
            "test": {
                "models": {"m1": {}, "m2": {}}
            }
        }
    }
    providers = []
    discover_from_opencode_data(Path("opencode.jsonc"), cfg, providers)
    discover_from_generic_config(cfg, providers, "opencode.jsonc")
    keys = {p["key"] for p in providers}
    assert keys == {"test:m1", "test:m2"}
    assert not any(k.startswith("provider:") for k in keys)


def test_mcp_tool_call_record():
    from switcher import save_mcp_tool_call, _load_mcp_state, clear_mcp_state
    clear_mcp_state()
    save_mcp_tool_call("read_file", {"path": "/foo/bar.py"}, "hash123")
    state = _load_mcp_state()
    assert len(state["tools_executed"]) == 1
    assert state["tools_executed"][0]["name"] == "read_file"
    clear_mcp_state()


def test_mcp_file_write_record():
    from switcher import save_mcp_file_write, _load_mcp_state, clear_mcp_state
    clear_mcp_state()
    save_mcp_file_write("/foo/bar.py", "write")
    state = _load_mcp_state()
    assert len(state["file_writes"]) == 1
    assert state["file_writes"][0]["action"] == "write"
    clear_mcp_state()


def test_mcp_handoff_has_executed_tools():
    from switcher import (save_mcp_tool_call, build_mcp_handoff, clear_mcp_state)
    clear_mcp_state()
    save_mcp_tool_call("bash", {"command": "npm test"}, "abc")
    handoff = build_mcp_handoff("model:a", "model:b")
    assert handoff["previous_model"] == "model:a"
    assert handoff["new_model"] == "model:b"
    assert len(handoff["already_executed_tools"]) == 1
    assert handoff["already_executed_tools"][0]["name"] == "bash"
    clear_mcp_state()


def test_mcp_handoff_clears_after_save_context():
    from switcher import (save_mcp_tool_call, save_context, load_context,
                          _load_mcp_state, clear_mcp_state)
    from pathlib import Path
    clear_mcp_state()
    save_mcp_tool_call("read_file", {"path": "/x.py"}, "h1")
    save_context("model:a", "model:b", "test", "summary")
    ctx = load_context()
    assert "mcp" in ctx
    assert len(ctx["mcp"]["already_executed_tools"]) == 1
    # MCP state should be cleared after building handoff
    mcp = _load_mcp_state()
    assert len(mcp["tools_executed"]) == 0
    # Clean up
    Path.home().joinpath(".auto-model-switcher", "context.json").unlink(missing_ok=True)
    Path.home().joinpath(".auto-model-switcher", "mcp_state.json").unlink(missing_ok=True)


# ─── Local Model Cold Starts ─────────────────────────────────────────────────

def test_check_ollama_cold_start_detected():
    from unittest.mock import patch, MagicMock
    from switcher import check_ollama
    provider = {"model_id": "llama3", "provider": "ollama"}
    with patch("switcher._get_session") as mock_sess:
        mock_sess.return_value = MagicMock()
        mock_sess.return_value.get.return_value.status_code = 200
        mock_sess.return_value.get.return_value.json.return_value = {"models": [{"name": "llama2"}]}
        mock_sess.return_value.post.side_effect = __import__("requests").Timeout("model loading")
        h, m = check_ollama(provider)
        assert h is True
        assert "cold start" in m.lower() or "loading" in m.lower()


def test_check_ollama_ready():
    from unittest.mock import patch, MagicMock
    from switcher import check_ollama
    provider = {"model_id": "llama3", "provider": "ollama"}
    with patch("switcher._get_session") as mock_sess:
        mock_sess.return_value = MagicMock()
        mock_sess.return_value.get.return_value.status_code = 200
        mock_sess.return_value.get.return_value.json.return_value = {"models": [{"name": "llama3"}]}
        mock_sess.return_value.post.return_value.status_code = 200
        mock_sess.return_value.post.return_value.json.return_value = {"response": "ok"}
        h, m = check_ollama(provider)
        assert h is True
        assert "ready" in m.lower()


# ─── Rate Limit Header Parsing ────────────────────────────────────────────────

def test_parse_retry_after_header():
    from unittest.mock import MagicMock
    from switcher import _parse_retry_after, _build_rate_limit_msg
    r = MagicMock()
    r.headers = {"Retry-After": "120"}
    assert _parse_retry_after(r) == 120


def test_parse_ratelimit_reset_header():
    from unittest.mock import MagicMock
    from switcher import _parse_retry_after
    import time
    r = MagicMock()
    reset_ts = int(time.time()) + 300
    r.headers = {"x-ratelimit-reset": str(reset_ts)}
    retry = _parse_retry_after(r)
    assert retry is not None
    assert 295 <= retry <= 305


def test_build_rate_limit_msg():
    from unittest.mock import MagicMock
    from switcher import _build_rate_limit_msg
    r = MagicMock()
    r.headers = {"Retry-After": "45"}
    msg = _build_rate_limit_msg(429, r)
    assert "rate limited (429)" in msg
    assert "retry in 45s" in msg


def test_mark_depleted_uses_retry_seconds():
    from switcher import mark_depleted, load_state, save_state
    # Mark depleted with a retry-after style reason
    mark_depleted("test:rate-limited-model", "rate limited (429), retry in 120s")
    state = load_state()
    entry = state["depleted"].get("test:rate-limited-model")
    assert entry is not None
    assert entry.get("retry_seconds") == 120
    assert "cooldown_until" in entry
    state["depleted"].pop("test:rate-limited-model", None)
    save_state(state)


# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [obj for name, obj in globals().items()
             if name.startswith("test_") and isinstance(obj, types.FunctionType)]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  [OK] {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            failed += 1
    print(f"\n  {passed}/{passed + failed} passed")
    sys.exit(1 if failed else 0)
