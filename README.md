# ClawTTY TUI

Multi-agent terminal. One interface. Every AI agent.

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Commands

| Command | Description |
|---|---|
| `/agent jose` | Switch to OpenClaw (Claude) |
| `/agent hermes` | Switch to Hermes (coming soon) |
| `/agents` | List all agents |
| `/full <prompt>` | All agents, parallel answers (coming soon) |
| `/max <prompt>` | Multi-agent consensus mode (coming soon) |
| `/help` | Show help |
| `/quit` | Exit |

## Roadmap

- [x] WebSocket agent (OpenClaw)
- [ ] SSH agent (Hermes)
- [ ] ACP subprocess agent (Claude Code, Cursor)
- [ ] /full mode — split panes, parallel answers
- [ ] /max mode — consensus engine, fact-checking
- [ ] config.toml — agent profiles
