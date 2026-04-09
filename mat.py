#!/usr/bin/env python3
"""
Ixel MAT — Multi-Agent Tool
IxelOS-branded CLI for parallel agent comparison.

Not a fullscreen TUI — just styled terminal output like OpenClaw/Hermes.
Your terminal stays your terminal.
"""
from __future__ import annotations

import asyncio
import os
import select
import shlex
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.table import Table
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich import box

from agents.base import AgentConfig, BaseAgent
from config.secrets import load_env, secrets_exist
from config.loader import load_config, build_agent_configs, validate_config, print_config_status

# Load secrets from ~/.config/ixel-mat/.env FIRST (before config reads token_env)
_loaded_secrets = load_env()
from agents import create_agent
from modes.full import FullModeDispatcher
from modes.consensus import run_consensus

# ── IxelOS Palette ────────────────────────────────────────────────────────────
C = {
    "bg":      "#070b14",
    "navy":    "#0d1b2a",
    "moon":    "#c8d8e8",
    "blue":    "#7eb8d4",
    "violet":  "#9b7fc7",
    "gold":    "#d4af37",
    "dim":     "#6b7d94",
    "red":     "#e05252",
    "green":   "#4ade80",
}

console = Console()

# ── Config-driven agents ──────────────────────────────────────────────────────
_CONFIG = load_config()
_AGENT_CONFIGS, _CONFIG_WARNINGS = build_agent_configs(_CONFIG)
_PASTE_STATE = {"count": 0}


# ── Splash ────────────────────────────────────────────────────────────────────

def print_splash():
    """Print the IxelOS moon logo + MAT branding."""
    logo_path = Path(__file__).parent / "assets" / "ixel-mat-logo.txt"
    if logo_path.exists():
        # Logo has raw ANSI escape codes — write directly to stdout, not through Rich
        logo = logo_path.read_text()
        sys.stdout.write("\n" + logo + "\n")
        sys.stdout.flush()
    else:
        console.print()
        console.print(f"  [{C['blue']}]·  [{C['violet']}]·  [{C['gold']}]·  [{C['violet']}]·  [{C['blue']}]·[/]")
        console.print(f"  [{C['moon']}]I  X  E  L  O  S[/]")
        console.print()

    console.print(
        f"  [{C['moon']}]M A T[/]  [{C['dim']}]Multi-Agent Tool[/]  "
        f"[{C['dim']}]v0.2.0[/]",
    )
    console.print(f"  [{C['dim']}]─────────────────────────────────────[/]")
    console.print()


# ── Agent management ──────────────────────────────────────────────────────────

async def connect_agents() -> dict[str, BaseAgent]:
    """Connect all configured agents. Returns dict of connected agents."""
    agents: dict[str, BaseAgent] = {}
    for name, config in _AGENT_CONFIGS.items():
        try:
            agent = create_agent(config)
        except ValueError as e:
            console.print(f"  [{C['red']}]✗[/] [{C['blue']}]{config.label}[/]  [{C['red']}]{e}[/]")
            continue
        try:
            await agent.connect()
            console.print(f"  [{C['green']}]✓[/] [{C['blue']}]{config.label}[/]  [{C['dim']}]connected[/]")
            agents[name] = agent
        except Exception as e:
            console.print(f"  [{C['red']}]✗[/] [{C['blue']}]{config.label}[/]  [{C['red']}]{e}[/]")
    console.print()
    return agents


async def disconnect_all(agents: dict[str, BaseAgent]):
    for agent in agents.values():
        try:
            await agent.disconnect()
        except Exception:
            pass


# ── Commands ──────────────────────────────────────────────────────────────────

def print_help():
    console.print(f"\n  [{C['gold']}]Ixel MAT[/] [{C['dim']}]— Commands[/]\n")
    cmds = [
        ("/full <prompt>",      "Send prompt to all agents — compare side by side"),
        ("/consensus [flags] <prompt>", "Stream responses, then synthesize once enough valid answers arrive"),
        ("/agents",             "Show connected agent status"),
        ("/config",             "Show resolved config + validation"),
        ("/help",               "Show this help"),
        ("/quit",               "Exit"),
    ]
    for cmd, desc in cmds:
        console.print(f"    [{C['blue']}]{cmd:<20}[/] [{C['dim']}]{desc}[/]")
    console.print()


def print_agents(agents: dict[str, BaseAgent]):
    console.print(f"\n  [{C['gold']}]Agents[/]\n")
    for name, agent in agents.items():
        if agent.is_connected:
            console.print(f"    [{C['green']}]●[/] [{C['blue']}]{name}[/]  [{C['dim']}]{agent.label}[/]  [{C['green']}]connected[/]")
        else:
            console.print(f"    [{C['dim']}]○[/] [{C['blue']}]{name}[/]  [{C['dim']}]{agent.label}[/]  [{C['red']}]disconnected[/]")
    console.print()


def _has_markdown(text: str) -> bool:
    return any(marker in text for marker in (
        "| ", "---|", "## ", "### ", "**", "```", "- [ ]", "1. ",
    ))


def _print_answer(text: str):
    """Render an agent answer — uses Rich Markdown if it contains markdown syntax."""
    if _has_markdown(text):
        md = Markdown(text, code_theme="monokai")
        console.print()
        console.print(Panel(md, border_style=C["dim"], padding=(1, 2), width=min(console.width - 4, 100)))
        console.print()
    else:
        # Wrap plain text nicely
        for line in text.split("\n"):
            if line.strip():
                console.print(f"    [{C['moon']}]{line}[/]")


def _response_attr(response, key: str, default=None):
    if response is None:
        return default
    if isinstance(response, dict):
        return response.get(key, default)
    return getattr(response, key, default)


def _format_elapsed(seconds: float) -> str:
    return f"{max(seconds, 0):.1f}s"


def format_prompt_preview(text: str, paste_state: dict[str, int] | None = None) -> str:
    stripped = text.strip()
    lines = stripped.splitlines()
    if len(lines) <= 1 and len(stripped) <= 240:
        return stripped
    state = paste_state if paste_state is not None else _PASTE_STATE
    state["count"] = state.get("count", 0) + 1
    extra_lines = max(len(lines) - 1, 0)
    if extra_lines > 0:
        return f"[paste #{state['count']} +{extra_lines} lines]"
    return f"[paste #{state['count']} +{max(len(stripped) - 1, 0)} chars]"


async def _prompt_async(label: str) -> str:
    return await asyncio.to_thread(Prompt.ask, label)


async def read_burst_submission(
    prompt_fn,
    main_prompt: str,
    continuation_prompt: str | None = None,
    burst_window: float = 0.05,
    stdin=None,
    select_fn=None,
) -> str:
    first = await prompt_fn(main_prompt)
    parts = [first]
    if "\n" in first:
        return first

    stream = stdin or sys.stdin
    selector = select_fn or select.select
    if not hasattr(stream, "readline"):
        return first

    while True:
        try:
            ready, _, _ = selector([stream], [], [], burst_window)
        except Exception:
            break
        if not ready:
            break
        nxt = stream.readline()
        if nxt == "":
            break
        parts.append(str(nxt).rstrip("\r\n"))
    return "\n".join(parts)


def build_full_status_lines(agent_states: dict[str, dict], now: float | None = None) -> list[str]:
    now = time.perf_counter() if now is None else now
    total = len(agent_states)
    responded = sum(1 for state in agent_states.values() if state.get("status") == "done")
    lines = [f"{responded}/{total} agents responded"]

    for name, state in agent_states.items():
        label = state.get("label", name)
        status = state.get("status", "pending")
        if status == "running":
            started_at = state.get("started_at", now)
            lines.append(f"{label} — processing... {_format_elapsed(now - started_at)}")
            continue
        response = state.get("response")
        if response is None:
            lines.append(f"{label} — waiting")
            continue
        answer = _response_attr(response, "answer", "") or "(no answer)"
        latency_ms = _response_attr(response, "latency_ms", 0)
        degraded = _response_attr(response, "degraded", False)
        marker = "degraded" if degraded else f"{latency_ms}ms"
        lines.append(f"{label} — {marker}")
        lines.append(answer.split("\n")[0][:120])
    return lines


def _build_full_renderable(prompt: str, agent_states: dict[str, dict]):
    now = time.perf_counter()
    total = len(agent_states)
    responded = sum(1 for state in agent_states.values() if state.get("status") == "done")
    progress = Text()
    progress.append(f"{responded}/{total}", style=C["green"])
    progress.append(" agents responded", style=C["dim"])

    panels = []
    for name, state in agent_states.items():
        label = state.get("label", name)
        status = state.get("status", "pending")
        if status == "running":
            started_at = state.get("started_at", now)
            body = Text()
            body.append("processing... ", style=C["dim"])
            body.append(_format_elapsed(now - started_at), style=C["gold"])
            border_style = C["violet"]
        elif status == "done":
            response = state.get("response")
            answer = _response_attr(response, "answer", "") or "(no answer)"
            degraded = _response_attr(response, "degraded", False)
            confidence = _response_attr(response, "confidence", None)
            evidence = _response_attr(response, "evidence", []) or []
            followup = _response_attr(response, "followup", "") or ""
            extra = []
            if confidence and hasattr(confidence, "value"):
                extra.append(Text.assemble(("Confidence: ", C["dim"]), (confidence.value, C["blue"])))
            if evidence:
                extra.append(Text.assemble(("Evidence: ", C["dim"]), (", ".join(evidence[:5]), C["violet"])))
            if followup:
                extra.append(Text.assemble(("Next: ", C["dim"]), (followup, C["moon"])))
            answer_renderable = Markdown(answer, code_theme="monokai") if _has_markdown(answer) else Text(answer, style=C["moon"])
            body = Group(answer_renderable, *extra) if extra else answer_renderable
            border_style = C["gold"] if degraded else C["green"]
        else:
            body = Text("queued...", style=C["dim"])
            border_style = C["dim"]

        panels.append(
            Panel(
                body,
                title=f"[{C['blue']}]{label}[/]",
                border_style=border_style,
                padding=(1, 2),
            )
        )

    header = Group(
        Text.assemble(("▸ ", C["gold"]), (prompt, C["moon"])),
        progress,
        Text("", style=C["dim"]),
    )
    return Group(header, Columns(panels, equal=True, expand=True))


@dataclass
class ConsensusOptions:
    prompt: str
    timeout: float = 30.0
    min_responses: int = 2


def parse_consensus_args(raw: str) -> ConsensusOptions:
    parts = shlex.split(raw)
    timeout = 30.0
    min_responses = 2
    prompt_parts: list[str] = []

    i = 0
    while i < len(parts):
        part = parts[i]
        if part == "--timeout":
            if i + 1 >= len(parts):
                raise ValueError("Missing value for --timeout")
            timeout = float(parts[i + 1])
            i += 2
            continue
        if part == "--min-responses":
            if i + 1 >= len(parts):
                raise ValueError("Missing value for --min-responses")
            min_responses = int(parts[i + 1])
            i += 2
            continue
        prompt_parts = parts[i:]
        break

    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        raise ValueError("Usage: /consensus [--timeout SECONDS] [--min-responses N] <prompt>")
    if timeout <= 0:
        raise ValueError("--timeout must be > 0")
    if min_responses < 1:
        raise ValueError("--min-responses must be >= 1")
    return ConsensusOptions(prompt=prompt, timeout=timeout, min_responses=min_responses)


async def run_full(prompt: str, agents: dict[str, BaseAgent]):
    """Run /full via FullModeDispatcher — single orchestration path."""
    connected = [a for a in agents.values() if a.is_connected]
    if not connected:
        console.print(f"  [{C['red']}]No connected agents.[/]")
        return

    dispatcher = FullModeDispatcher(connected, timeout=60.0)
    agent_states = {
        agent.name: {
            "label": agent.label,
            "status": "pending",
            "started_at": None,
            "response": None,
        }
        for agent in connected
    }

    async def on_start(name: str):
        state = agent_states[name]
        state["status"] = "running"
        state["started_at"] = time.perf_counter()

    async def on_done(resp):
        state = agent_states[resp.agent]
        state["status"] = "done"
        state["response"] = resp

    dispatch_task = asyncio.create_task(
        dispatcher.dispatch(prompt, on_agent_start=on_start, on_agent_done=on_done)
    )
    prompt_preview = format_prompt_preview(prompt)

    with Live(_build_full_renderable(prompt_preview, agent_states), console=console, refresh_per_second=10) as live:
        while not dispatch_task.done():
            live.update(_build_full_renderable(prompt_preview, agent_states))
            await asyncio.sleep(0.1)
        result = await dispatch_task
        live.update(_build_full_renderable(prompt_preview, agent_states))

    # Summary
    valid = sum(1 for r in result.responses if not r.degraded)
    avg_ms = sum(r.latency_ms for r in result.responses) // len(result.responses) if result.responses else 0
    console.print(
        f"  [{C['dim']}]── /full ── {len(result.responses)} agents ── "
        f"{valid} valid ── avg {avg_ms}ms ──[/]\n"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run_consensus_cmd(raw: str, agents: dict[str, BaseAgent]):
    """Run /consensus — all agents answer, then synthesize ONE best answer."""
    connected = [a for a in agents.values() if a.is_connected]
    if not connected:
        console.print(f"  [{C['red']}]No connected agents.[/]")
        return

    try:
        opts = parse_consensus_args(raw)
    except ValueError as e:
        console.print(f"  [{C['gold']}]⚠[/] [{C['dim']}]{e}[/]")
        return

    prompt = opts.prompt
    prompt_preview = format_prompt_preview(prompt)
    console.print(f"\n  [{C['gold']}]▸[/] [{C['moon']}]{prompt_preview}[/]")
    console.print(
        f"  [{C['dim']}]consensus mode — {len(connected)} agents — "
        f"timeout {int(opts.timeout)}s — min {opts.min_responses} valid[/]\n"
    )

    async def on_phase(msg: str):
        console.print(f"  [{C['violet']}]⟐[/] [{C['dim']}]{msg}[/]")

    async def on_agent_result(resp, included: bool):
        if resp.degraded:
            console.print(
                f"  [{C['gold']}]⚠[/] [{C['blue']}]{resp.agent}[/]  "
                f"[{C['dim']}]skipped — {resp.answer[:120]}[/]"
            )
            return

        status = f"[{C['green']}]✓[/]" if included else f"[{C['gold']}]◌[/]"
        console.print(
            f"  {status} [{C['blue']}]{resp.agent}[/]  "
            f"[{C['dim']}]{resp.latency_ms}ms  {resp.confidence.value}[/]"
        )
        short = resp.answer.split("\n")[0][:80] if resp.answer else "(no answer)"
        console.print(f"    [{C['dim']}]{short}[/]")

    async def on_late_response(resp):
        console.print(
            f"  [{C['gold']}]⚠[/] [{C['dim']}]Late response from {resp.agent} — not included in synthesis[/]"
        )

    result = await run_consensus(
        prompt=prompt,
        agents=list(agents.values()),
        on_phase=on_phase,
        on_agent_result=on_agent_result,
        on_late_response=on_late_response,
        timeout=opts.timeout,
        min_responses=opts.min_responses,
    )

    if "error" in result:
        console.print(f"  [{C['red']}]{result['error']}[/]")
        return

    # Show the consensus
    consensus = result["consensus"]
    synth = result["synthesizer_name"]
    total = result["total_ms"]

    console.print(f"\n  [{C['gold']}]══ CONSENSUS ══[/]  [{C['dim']}]synthesized by {synth}[/]\n")

    if consensus.answer:
        _print_answer(consensus.answer)
    if consensus.confidence:
        console.print(f"\n  [{C['dim']}]Confidence:[/] [{C['blue']}]{consensus.confidence.value}[/]")
    if consensus.evidence:
        console.print(f"  [{C['dim']}]Evidence:[/]")
        for e in consensus.evidence[:8]:
            console.print(f"    [{C['violet']}]• {e}[/]")
    if consensus.uncertainties:
        console.print(f"  [{C['dim']}]Uncertainties:[/]")
        for u in consensus.uncertainties[:5]:
            console.print(f"    [{C['gold']}]• {u}[/]")
    if consensus.followup:
        console.print(f"  [{C['dim']}]Next:[/] {consensus.followup}")

    console.print(
        f"\n  [{C['dim']}]── /consensus ── {len(result['included_phase1'])} included"
        f" / {len(result['phase1_responses'])} seen ── synthesized by {synth} ── {total}ms total ──[/]\n"
    )


async def main():
    issues = validate_config(_CONFIG)
    if any("token not set" in i for i in issues):
        for issue in issues:
            console.print(f"  [{C['red']}]⚠ {issue}[/]")
        console.print(f"  [{C['dim']}]Run: /config to see full status[/]\n")

    print_splash()

    # First-run: prompt setup if no secrets configured
    if not secrets_exist() and not _loaded_secrets:
        console.print(f"  [{C['gold']}]First time?[/] [{C['dim']}]Run setup to configure agents:[/]")
        console.print(f"    [{C['blue']}]python3 mat.py setup[/]\n")

    # Show config warnings
    for warn in _CONFIG_WARNINGS:
        console.print(f"  [{C['gold']}]⚠[/] [{C['dim']}]{warn}[/]")
    if _CONFIG_WARNINGS:
        console.print()

    agents = await connect_agents()

    if not agents:
        console.print(f"  [{C['red']}]No agents connected. Exiting.[/]")
        return

    console.print(f"  [{C['dim']}]Type /help for commands, or /full <prompt> to compare agents.[/]\n")

    try:
        while True:
            try:
                user_input = await read_burst_submission(
                    _prompt_async,
                    main_prompt=f"  [{C['violet']}]⚕[/] [{C['dim']}]❯[/]",
                    continuation_prompt=f"  [{C['violet']}]⚕[/] [{C['dim']}]…[/]",
                    burst_window=0.05,
                )
            except (EOFError, KeyboardInterrupt):
                break

            text = user_input.strip()
            if not text:
                continue

            if text in ("/quit", "/exit", "/q"):
                break
            elif text == "/help":
                print_help()
            elif text in ("/agents", "/status"):
                print_agents(agents)
            elif text.startswith("/full "):
                prompt = text[6:].strip()
                if prompt:
                    await run_full(prompt, agents)
                else:
                    console.print(f"  [{C['dim']}]Usage: /full <prompt>[/]")
            elif text == "/config":
                print_config_status(_CONFIG)
            elif text.startswith("/consensus "):
                await run_consensus_cmd(text[11:].strip(), agents)
            elif text.startswith("/"):
                console.print(f"  [{C['dim']}]Unknown command. Try /help[/]")
            else:
                # Default: send as /full
                await run_full(text, agents)

    except KeyboardInterrupt:
        pass

    console.print(f"\n  [{C['dim']}]Disconnecting...[/]")
    await disconnect_all(agents)
    console.print(f"  [{C['violet']}]✦[/] [{C['dim']}]Goodbye.[/]\n")


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "setup":
        from config.setup import run_setup
        run_setup()
    else:
        asyncio.run(main())
