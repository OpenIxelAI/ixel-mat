# Ixel MAT

**Multi-Agent Terminal** by [IxelAI](https://github.com/OpenIxelAI)

Ask every AI at once. Compare, synthesize, decide.

---

## What is it?

Ixel MAT is a terminal interface that lets you dispatch prompts to multiple AI agents simultaneously — Claude, GPT, Grok, Gemini, and more — and see their answers side-by-side or merged into a single consensus response.

Built for people who work with AI seriously and want full control from the terminal.

---

## Features

- **`/full <prompt>`** — Ask all configured agents in parallel, display responses side-by-side
- **`/consensus <prompt>`** — Aggregate all agent responses into one synthesized answer
- **Config-driven agents** — Define any agent in `~/.config/ixel-mat/config.toml`
- **HTTP + WebSocket adapters** — Connect directly to any OpenAI-compatible API or OpenClaw gateway
- **Secrets management** — API keys live in `~/.config/ixel-mat/.env`, never in config files
- **Rich terminal UI** — Markdown rendering, colored panels, clean layout
- **`ixel` CLI** — `ixel setup`, `ixel agents`, `ixel doctor`, `ixel config`

---

## Quick Start

```bash
# Clone
git clone https://github.com/OpenIxelAI/ixel-mat.git
cd ixel-mat

# Install dependencies
pip install -r requirements.txt

# Run setup wizard
python mat.py setup

# Launch
python mat.py
```

---

## Agent Configuration

Agents are defined in `~/.config/ixel-mat/config.toml`. Copy the example to get started:

```bash
cp config.example.toml ~/.config/ixel-mat/config.toml
```

Example config:

```toml
[agents.claude]
type = "http"
url = "https://api.anthropic.com/v1/messages"
token_env = "ANTHROPIC_API_KEY"
model = "claude-sonnet-4-5"
label = "Claude"
color = "blue"

[agents.gpt]
type = "http"
url = "https://api.openai.com/v1/chat/completions"
token_env = "OPENAI_API_KEY"
model = "gpt-4o"
label = "GPT-4o"
color = "green"

[agents.grok]
type = "http"
url = "https://api.x.ai/v1/chat/completions"
token_env = "XAI_API_KEY"
model = "grok-4"
label = "Grok"
color = "magenta"
```

Secrets go in `~/.config/ixel-mat/.env` (permissions set to 600 automatically):

```env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
XAI_API_KEY=xai-...
GOOGLE_API_KEY=AIza...
```

---

## Commands

| Command | Description |
|---|---|
| `/full <prompt>` | Ask all agents in parallel, display side-by-side |
| `/consensus <prompt>` | Ask all agents, synthesize one answer |
| `/agents` | List configured agents |
| `/help` | Show help |
| `/quit` | Exit |

---

## CLI

```bash
ixel            # Launch MAT
ixel setup      # Interactive setup wizard
ixel agents     # List configured agents
ixel config     # Show config file path
ixel doctor     # Health check
ixel help       # Help
ixel version    # Version
```

---

## Architecture

- `mat.py` — entry point + CLI routing
- `cli.py` — subcommand dispatcher
- `agents/` — HTTP and WebSocket agent adapters
- `modes/` — `/full` and `/consensus` logic
- `config/` — TOML loader, secrets, setup wizard
- `ui/` — Rich terminal rendering
- `session/` — session state management

---

## About

**IxelAI** — building tools for people who take AI seriously.

- GitHub: [github.com/OpenIxelAI](https://github.com/OpenIxelAI)
