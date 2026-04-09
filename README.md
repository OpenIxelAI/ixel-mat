<p align="center">
  <img src="assets/ixel-logo.png" alt="Ixel" width="280">
</p>

# Ixel MAT

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: Unlicensed](https://img.shields.io/badge/license-unlicensed-lightgrey)](https://github.com/OpenIxelAI/ixel-mat)
[![GitHub stars](https://img.shields.io/github/stars/OpenIxelAI/ixel-mat?style=social)](https://github.com/OpenIxelAI/ixel-mat/stargazers)

Multi-Agent Terminal by [IxelAI](https://github.com/OpenIxelAI).
Run multiple AI providers side-by-side from the terminal, compare answers in real time, and synthesize a faster consensus when needed.

## Install

Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/OpenIxelAI/ixel-mat/main/install.sh | bash
```

Windows PowerShell

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/OpenIxelAI/ixel-mat/main/install.ps1 | iex"
```

After install:

```bash
ixel help
ixel status
ixel setup
ixel
```

## Why Ixel MAT?

- Real-time comparison: `/full` streams each model as soon as it responds.
- Faster synthesis: `/consensus` starts once enough strong answers arrive instead of waiting for every provider.
- Operator-first UX: local config, local secrets, health/status commands, and terminal-native workflows.

## Demo

```text
▸ Explain zero trust architecture
3/5 agents responded

╭──────────────────────────── OpenAI ────────────────────────────╮
│ Zero trust assumes no user, device, or network path should be │
│ trusted by default. Every request must be authenticated,       │
│ authorized, and continuously evaluated.                        │
╰────────────────────────────────────────────────────────────────╯
╭──────────────────────────── Claude ────────────────────────────╮
│ Zero trust replaces perimeter trust with identity, policy,    │
│ and verification at every step of access.                     │
╰────────────────────────────────────────────────────────────────╯
╭──────────────────────────── Gemini ────────────────────────────╮
│ processing... 6.4s                                             │
╰────────────────────────────────────────────────────────────────╯
```

## Supported Providers

| Provider | Auth method | Models |
|---|---|---|
| OpenClaw Gateway | `IXELMAT_GATEWAY_TOKEN` | Any model exposed by your OpenClaw gateway |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1`, `o3`, `gpt-5.4` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-opus-4`, `claude-sonnet-4-5`, `claude-haiku-3` |
| xAI | `XAI_API_KEY` | `grok-4`, `grok-3`, `grok-3-mini` |
| Google Gemini | `GOOGLE_API_KEY` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash` |

## Core Commands

| Command | What it does |
|---|---|
| `ixel` | Launch the interactive MAT terminal |
| `ixel status` | Show provider health, agent connectivity, secrets, and warnings |
| `ixel setup` | Configure providers and write config + `.env` |
| `ixel agents` | Probe configured agents |
| `ixel models` | Show providers, models, and auth state |
| `pytest tests/` | Run the automated test suite |

## How it works

- `mat.py` runs the interactive terminal UI
- `cli.py` handles setup, status, models, doctor, and config commands
- `agents/` provides HTTP, WebSocket, subprocess, and one-shot adapters
- `modes/full.py` and `modes/consensus.py` drive compare/synthesis workflows
- `config/` handles TOML loading, validation, setup, and secrets

## Quick Start from Source

```bash
git clone https://github.com/OpenIxelAI/ixel-mat.git
cd ixel-mat
python3 -m pip install -r requirements.txt
python3 cli.py help
python3 cli.py status
python3 cli.py setup
python3 mat.py
```

Run tests:

```bash
pytest tests/
```

## Config + Secrets

- Config: `~/.config/ixel-mat/config.toml`
- Secrets: `~/.config/ixel-mat/.env`
- Secrets file permissions are automatically set to `600`
- Starter config: `config.example.toml`

## Roadmap

- Token-level provider streaming
- Single-agent interactive mode (`/agent <name>`)
- `pyproject.toml` + `pipx` packaging
- Better local subprocess workflows for CLI-native agents
- Compare/diff mode for disagreements across models
