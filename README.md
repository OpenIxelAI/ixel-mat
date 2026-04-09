# Ixel MAT

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: Unlicensed](https://img.shields.io/badge/license-unlicensed-lightgrey)](https://github.com/OpenIxelAI/ixel-mat)
[![GitHub stars](https://img.shields.io/github/stars/OpenIxelAI/ixel-mat?style=social)](https://github.com/OpenIxelAI/ixel-mat/stargazers)

Multi-Agent Terminal by [IxelAI](https://github.com/OpenIxelAI).
Ask every AI at once. Compare, synthesize, decide.

## Why Ixel MAT?

- Fast multi-agent UX: `/full` streams responses as they land, `/consensus` starts synthesis early instead of waiting forever.
- Terminal-first control: local config, local secrets, health/status commands, no browser required.
- Mix providers freely: OpenClaw, OpenAI, Anthropic, xAI, and Gemini in one session.

## Demo

Real `/full` run excerpt:

```text
▸ Say hello in one sentence
4/5 agents responded

╭──────────────────────────── Main ────────────────────────────╮
│ Hey Angel! 👋 Good to see you tonight.                      │
│ Confidence: high                                            │
│ Next: Await Angel's request or question.                    │
╰─────────────────────────────────────────────────────────────╯
╭──────────────────────────── GPT ─────────────────────────────╮
│ Hello!                                                      │
│ Confidence: high                                            │
│ Next: None                                                  │
╰─────────────────────────────────────────────────────────────╯
╭───────────────────── Anthropic (Claude) ────────────────────╮
│ Hello!                                                      │
│ Confidence: high                                            │
╰─────────────────────────────────────────────────────────────╯
╭──────────────────────── xAI (Grok) ─────────────────────────╮
│ processing... 14.6s                                         │
╰─────────────────────────────────────────────────────────────╯
```

## Quick Start

Tested from a fresh clone:

```bash
git clone https://github.com/OpenIxelAI/ixel-mat.git
cd ixel-mat
python3 -m pip install -r requirements.txt
python3 cli.py help
python3 cli.py status
```

Then configure providers and launch:

```bash
python3 cli.py setup
python3 mat.py
```

Run tests:

```bash
pytest tests/
```

## Supported Providers

| Provider | Auth method | Models |
|---|---|---|
| OpenClaw Gateway | `IXELMAT_GATEWAY_TOKEN` | All models exposed by your gateway |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `o1`, `o3` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-opus-4`, `claude-sonnet-4-5`, `claude-haiku-3` |
| xAI | `XAI_API_KEY` | `grok-4`, `grok-3`, `grok-3-mini` |
| Google Gemini | `GOOGLE_API_KEY` | `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.0-flash` |

## Commands

| Command | What it does |
|---|---|
| `python3 mat.py` | Launch the interactive MAT terminal |
| `python3 cli.py setup` | Configure providers and agents |
| `python3 cli.py status` | One-screen health dashboard |
| `python3 cli.py agents` | Probe configured agents |
| `python3 cli.py models` | Show providers, models, auth status |
| `pytest tests/` | Run unit tests |

## Roadmap

- Token-level streaming from providers
- `/agent <name>` single-agent interactive mode
- Proper `pyproject.toml` + `pipx` install
- Local subprocess adapter improvements for CLI agents
- Compare/diff mode for agent disagreements

## Config + Secrets

- Config: `~/.config/ixel-mat/config.toml`
- Secrets: `~/.config/ixel-mat/.env` (`chmod 600`)
- Example config: `config.example.toml`

## Status

Use `python3 cli.py status` to see, in one screen:
- version + Python info
- config source
- provider probe status + latency
- agent connection status
- secrets file metadata
- config warnings
