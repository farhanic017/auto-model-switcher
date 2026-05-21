# Auto Model Switcher

Auto-discovers models from your CLI configs and environment variables. Builds a
priority chain (free models first, paid fallbacks). When a model runs out of
credits or hits rate limits, rotates to the next working model automatically.

Works with: **OpenCode**, **Claude Code**, **Cursor**, and any CLI that
reads a model config.

## Instant Install

Give this repo URL to any AI agent:

```
https://github.com/farhanic017/auto-model-switcher
```

The AI will:
1. Clone the repo
2. Run `install.py` to scan your configs
3. Install hooks for automatic model switching
4. Set up the watch daemon

## Manual Install

```powershell
git clone https://github.com/farhanic017/auto-model-switcher.git
cd auto-model-switcher
python install.py
```

## Usage

```
python switcher.py status       # Show all models + their health
python switcher.py switch       # Rotate to next working model
python switcher.py watch        # Background daemon (auto-rotate)
python switcher.py discover     # List all discovered models
```

## How It Works

1. **Discovery**: Scans `opencode.jsonc`, `CLAUDE.md`, `.cursorrules`, and
   environment variables for all configured providers and models.

2. **Chain building**: Sorts models free-first. Google AI and OpenRouter
   `:free` models get priority. Paid models (Azure OpenAI, OpenRouter paid)
   are fallbacks.

3. **Health checks**: For each provider, makes a lightweight API call:
   - **OpenRouter**: `GET /api/v1/auth/key` to check credit balance
   - **Google AI**: Minimal content generation to check quota
   - **Azure OpenAI**: `GET /openai/models` to verify access

4. **Rotation**: When a model fails (429 rate limit, 0 credits, 402 payment
   required, 403 quota exceeded), it's marked as depleted with a 30-min
   cooldown. The switcher moves to the next model and updates the CLI config.

5. **Recovery**: After cooldown, depleted models are re-checked. If they
   recover (e.g., OpenRouter credits refresh), they re-enter the pool.

## Supported Providers

| Provider | Detection | Health Check |
|----------|-----------|-------------|
| OpenRouter (free) | `:free` suffix | Credit balance API |
| OpenRouter (paid) | no `:free` suffix | Credit balance API |
| Google AI | provider name | Content generation |
| Azure OpenAI | provider name | Models list API |
| OpenAI | env var `OPENAI_API_KEY` | (minimal check) |
| Anthropic | env var `ANTHROPIC_API_KEY` | (minimal check) |

## Watch Mode

Run in background for continuous monitoring:

```powershell
start /B python D:\open\ code\auto-model-switcher\switcher.py watch
```

Checks active model health every 2 minutes. Auto-switches on failure.
