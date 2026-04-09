# ClawTTY TUI — Multi-Agent Terminal Architecture

**Version:** 0.2 — Post-Consensus (Jose + Hermes + Cursor + GPT 5.4)  
**Date:** 2026-04-08  

**Pitch:** A unified terminal workspace for AI agents, with consistent commands and better session control.

---

## How This Architecture Was Made

Four AI agents (Claude Opus, Gemini 3.1 Pro, Cursor/Claude, GPT 5.4) independently reviewed the concept and iterated on each other's feedback. The result is stronger than any single agent produced alone. This document IS the proof of concept.

---

## MVP Scope (All 4 Agents Agree)

### Build First
- `/agent` — single agent mode
- `/full` — parallel answers from all agents

### Build Later (after dogfooding)
- `/max` — consensus mode (requires evidence schema first)

### Do NOT Build Yet
- Discord/Telegram integration
- ACP transports (verify with spikes first)
- Custom themes/skins

---

## Modes

### Single Agent Mode — `/agent <name>`
```
/agent jose       → OpenClaw (Claude) — persistent session
/agent hermes     → Hermes (Gemini) — subprocess, fresh or resumed
```
One agent, full terminal pane, normal back-and-forth.

### Full Mode — `/full <prompt>`
All configured agents receive the same prompt simultaneously.
Each responds in their own pane (split view or sequential).

**Critical (from GPT 5.4):** /full must normalize outputs into structured format:
```
┌─ Jose (Claude) ──────────────────────────────────┐
│ Answer: OSPF selects routes by lowest cost       │
│ Confidence: High                                 │
│ Evidence: RFC 2328 §16.1                         │
│ Uncertainties: Vendor-specific tiebreakers vary   │
└──────────────────────────────────────────────────┘
```

This structured output is what makes future /max possible.
Without it, /full is just "walls of text side by side."

### Max Mode — `/max <prompt>` (FUTURE — not in MVP)
Requires evidence schema from /full to be working first.

When built, /max will NOT be "majority wins." It will:
1. Extract claims from each agent
2. Require support/evidence for factual claims
3. Mark unsupported claims explicitly
4. Detect conflicts between agents
5. Produce synthesis with explicit unresolved points

**Risk (from Cursor):** Three agents can agree on the same wrong thing 
("confident group hallucinations"). Evidence/citation requirements are 
the defense against this.

---

## Transport Layer — MVP (2 transports only)

| Agent | Protocol | How |
|---|---|---|
| OpenClaw/Jose | WebSocket | ws://127.0.0.1:18789 + token |
| Hermes | Local subprocess | hermes --resume <session_id> |

### Future Transports (verify with spikes before committing)
| Agent | Protocol | Status |
|---|---|---|
| Claude Code | ACP subprocess | Unverified — needs spike |
| Cursor | ACP subprocess | Unverified — needs spike |
| Direct API | REST /v1/chat/completions | Straightforward but low priority |

**Rule (from GPT 5.4):** Do NOT architect around unproven connectors.
Each new transport gets a tiny spike first.

---

## Session Management — THE Star Feature

This is what separates ClawTTY from just opening two terminals.
OpenClaw has persistent sessions. Hermes starts fresh. This mismatch 
is the pain. ClawTTY smooths it.

### Per-Agent Session Config
```toml
[agents.jose]
type = "websocket"
url = "ws://127.0.0.1:18789"
token = "..."
auto_resume = true          # always reconnects to same session

[agents.hermes]  
type = "subprocess"
command = "hermes"
auto_resume = true           # passes --resume <last_session_id>
last_session_id = "20260408_020000_abc123"
```

### Session Commands
```
/new              → force new session with current agent
/resume <id>      → resume specific session
/sessions         → list recent sessions for current agent
/session          → show current session info (id, duration, messages)
```

### Session State File
```
~/.clawtty/sessions.json
{
  "jose": {
    "last_session_id": null,       # WS sessions are always persistent
    "last_connected": "2026-04-08T02:30:00Z"
  },
  "hermes": {
    "last_session_id": "20260408_020000_abc123",
    "last_connected": "2026-04-08T02:25:00Z",
    "sessions": [
      {"id": "20260408_020000_abc123", "messages": 12, "duration": "4m"},
      {"id": "20260407_135336_e9552c", "messages": 5, "duration": "4m"}
    ]
  }
}
```

### Visible Session State in UI
```
┌─────────────────────────────────────────────────────┐
│  CLAWTTY  │ [1:Jose ●] [2:Hermes ○]                 │
│           │ Session: persistent │ 47 messages │ 2h    │
├─────────────────────────────────────────────────────┤
```

---

## /full Response Schema

Every agent response in /full mode MUST be parsed into:

```python
@dataclass
class AgentResponse:
    agent: str              # "jose", "hermes"
    answer: str             # the actual answer
    confidence: str         # "high", "medium", "low", "uncertain"
    evidence: list[str]     # citations, RFC numbers, docs, commands
    uncertainties: list[str] # what the agent isn't sure about
    commands: list[str]     # any commands suggested
    followup: str           # recommended next step
    raw: str                # original unstructured response
    latency_ms: int         # how long the agent took
```

This schema is what makes /max buildable later.
For MVP, display both raw AND structured side by side.

---

## TUI Layout (Textual)

### Single Agent View
```
┌─────────────────────────────────────────────────────┐
│  CLAWTTY  │ [1:Jose ●] [2:Hermes ○]                 │
│           │ Session: persistent │ Connected           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  You 02:30                                          │
│  explain OSPF route selection                       │
│                                                     │
│  Jose 02:31                                         │
│  OSPF selects routes based on lowest cost...        │
│                                                     │
├─────────────────────────────────────────────────────┤
│  > your message here                                │
└─────────────────────────────────────────────────────┘
```

### /full Split View
```
┌──────────────────────┬──────────────────────────────┐
│  CLAWTTY  │ /full    │ 2 agents │ 1.2s / 2.8s       │
├──────────────────────┼──────────────────────────────┤
│  Jose (Claude)       │  Hermes (Gemini)              │
│  ─────────────────── │  ──────────────────────────── │
│  Answer:             │  Answer:                      │
│  Cost = 10^8/bw ...  │  Lowest cost path wins...     │
│                      │                               │
│  Confidence: High    │  Confidence: High             │
│  Evidence: RFC 2328  │  Evidence: Cisco docs         │
│  Uncertainties:      │  Uncertainties:               │
│  - vendor tiebreaker │  - ECMP behavior varies       │
├──────────────────────┴──────────────────────────────┤
│  > your message here                                │
└─────────────────────────────────────────────────────┘
```

---

## Stack

- **Language:** Python 3.10+
- **TUI Framework:** Textual (async, rich widgets, mouse support)
- **Transport:** asyncio websockets + asyncio subprocess
- **Config:** ~/.clawtty/config.toml
- **Session state:** ~/.clawtty/sessions.json

---

## File Structure

```
clawtty-tui/
├── main.py              # Entry point
├── app.py               # Textual App class
├── config.py            # Load ~/.clawtty/config.toml
├── agents/
│   ├── base.py          # BaseAgent interface (connect, send, receive, session)
│   ├── websocket.py     # OpenClaw WS agent
│   └── subprocess.py    # Local subprocess agent (Hermes)
├── session/
│   ├── manager.py       # Session tracking, auto-resume, /new, /resume
│   └── state.py         # Read/write ~/.clawtty/sessions.json
├── modes/
│   ├── single.py        # /agent mode handler
│   └── full.py          # /full mode — parallel dispatch + structured output
├── schema/
│   └── response.py      # AgentResponse dataclass + parser
└── ui/
    ├── chat_pane.py     # Single agent chat widget
    ├── split_view.py    # /full multi-pane layout
    └── status_bar.py    # Agent tabs + session info
```

---

## Dogfooding Plan (7 days)

Use ClawTTY for real work every day. Track:

| Metric | What It Tells You |
|---|---|
| How often /full changed your final answer | Is multi-agent actually useful? |
| Whether switching agents was faster | Is the hub model saving time? |
| Whether session handling reduced friction | Is the star feature working? |
| Which commands you used repeatedly | What's core vs what's bloat? |
| When the second agent added value vs noise | Is /full worth the extra tokens? |

**Success criteria (from GPT 5.4):**
> If testers say "I'd miss this if removed," you have product signal.
> If not, you still built a powerful internal tool and learned fast.

Track in: `~/.clawtty/dogfood.md` (daily notes)

---

## Build Order (Final — All 4 Agents Agree)

1. [x] Architecture doc (this file)
2. [x] Prototype: Textual app + WS to OpenClaw (main.py exists)
3. [ ] Add subprocess agent (Hermes)
4. [ ] Session manager (auto_resume, /new, /resume, /sessions)
5. [ ] /full mode — parallel dispatch, split pane
6. [ ] /full structured output (AgentResponse schema)
7. [ ] Config file (~/.clawtty/config.toml)
8. [ ] 7-day dogfood
9. [ ] Evidence schema refinement based on dogfood data
10. [ ] /max mode (consensus with evidence scoring)
11. [ ] Ship

---

## What This Proves

This architecture was created by manually running `/max` mode:
- 4 agents reviewed the same concept
- Each caught things others missed
- The final plan is better than any single agent produced
- Jose missed session UX and scoping risks
- Hermes was too optimistic on adoption
- Cursor caught group hallucination risk
- GPT 5.4 gave the tightest scope and best pitch

**The product proved itself before it was built.**

---

## The Pitch

> A unified terminal workspace for AI agents, with consistent commands 
> and better session control.

If that works → /full becomes a real differentiator.  
If that works consistently → /max becomes worth attempting.
