# Ixel MAT — Roadmap

**Multi-Agent Terminal** by IxelAI
Last updated: 2026-04-08

---

## Consensus from All Reviewers (Codex, GPT-5.4, Cursor, Claude)

Four independent reviews all converged on the same priorities:

### 🔴 IMMEDIATE (today)
- [ ] **Rotate gateway token** — exposed in config.toml, treat as compromised
- [ ] **Remove secrets from tracked files** — ship `config.example.toml` only
- [ ] **Clean requirements.txt** — remove `textual`, add actual deps

### 🟡 v0.2 — Week 1 (session + config)
- [ ] **Per-request session isolation** — `agent:NAME:main:full:<uuid>` per /full call
- [ ] **RunId correlation** — tie `_chat_final` to specific runId, not global event
- [ ] **Config loader** — load agents from `~/.config/ixel-mat/config.toml`
- [ ] **Secret interpolation** — `token = "${IXELMAT_GATEWAY_TOKEN}"` in config
- [ ] **`mat config validate`** — show resolved config + missing env vars

### 🟡 v0.2 — Week 2 (UX + transport)
- [ ] **Incremental /full rendering** — show each agent as it finishes, not wait-for-all
- [ ] **JSON response schema** — ask agents for JSON first, markdown fallback
- [ ] **HTTP adapter** — direct OpenAI/Anthropic/xAI API (no gateway needed)
- [ ] **`pyproject.toml`** — proper packaging, `pipx install ixel-mat`

### 🟢 v0.3+ (scale)
- [ ] Subprocess adapter (local CLIs)
- [ ] Token-level streaming
- [ ] `/agent <name>` single-agent interactive mode
- [ ] `/compare` side-by-side diff view
- [ ] Agent hierarchy / delegation (user sets the chain of command)
- [ ] MCP adapter (tool ecosystems)
- [ ] `--wait-all` and `--json` flags for CI/automation

---

## Architecture Decisions (agreed by all)

| Decision | Choice | Why |
|---|---|---|
| Config format | **TOML** | Already started, `tomllib` built-in, clean scalar fit |
| Secrets | **Env vars only** | Never in config files |
| Transport layer | **Adapter pattern** | WS → HTTP → Subprocess → MCP (in order) |
| /full rendering | **Stream per-agent** | Show first result immediately, aggregate at end |
| Response schema | **JSON preferred** | Markdown regex as degraded fallback only |
| Packaging | **pyproject.toml + pipx** | Standard Python CLI distribution |
| Auth scopes | **Least privilege** | Reduce from admin to read+write only |
| Non-local transport | **wss:// enforced** | ws:// only for localhost dev mode |

---

## The Hierarchy Idea (IxelAI vision)

> "Wondering if a hierarchy approach can help — the hierarchy set by the user,
> or if Ixel MAT would be at the top of the hierarchy"

This is the v1.0 vision: **Ixel MAT as orchestrator.**

```
User
  └── Ixel MAT (orchestrator)
        ├── Agent A (lead / decision-maker)
        ├── Agent B (reviewer / second opinion)
        ├── Agent C (specialist / domain expert)
        └── Agent D (validator / fact-checker)
```

- User defines hierarchy in config: who leads, who reviews, who validates
- MAT routes prompts through the chain: lead answers → reviewer critiques → specialist adds depth
- Final output is the **synthesized consensus**, not just side-by-side
- User can override at any point: "I trust Agent A's answer, skip review"

This turns MAT from a comparison tool into a **multi-agent reasoning engine**.

Not for v0.2 — but the architecture decisions we make now (run model, transport adapters, session isolation) are the foundation for it.

---

## File Map (current → target)

```
ixel-mat/
├── mat.py              → cli.py (entry point)
├── agents/
│   ├── base.py         → add AgentRun model
│   ├── websocket.py    → fix session + runId correlation
│   ├── http.py         → NEW: direct API adapter
│   └── subprocess.py   → NEW: local CLI adapter
├── config/
│   ├── loader.py       → NEW: TOML loader + env interpolation
│   └── schema.py       → NEW: config validation
├── modes/
│   ├── full.py         → wire into mat.py properly
│   └── hierarchy.py    → FUTURE: chain-of-command mode
├── schema/
│   └── response.py     → add JSON schema, keep markdown fallback
├── assets/
│   └── ixel-mat-logo.txt
├── config.example.toml → NEW: template (no secrets)
├── pyproject.toml      → NEW: packaging
└── ROADMAP.md          → this file
```
