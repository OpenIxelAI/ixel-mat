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
import sys
import time
from pathlib import Path

from rich.console import Console
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
from schema.response import FULL_MODE_SUFFIX, parse_structured_response

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
        ("/consensus <prompt>", "All agents answer, then synthesize ONE best answer"),
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


def _print_answer(text: str):
    """Render an agent answer — uses Rich Markdown if it contains markdown syntax."""
    has_markdown = any(marker in text for marker in (
        "| ", "---|", "## ", "### ", "**", "```", "- [ ]", "1. ",
    ))
    if has_markdown:
        md = Markdown(text, code_theme="monokai")
        console.print()
        console.print(Panel(md, border_style=C["dim"], padding=(1, 2), width=min(console.width - 4, 100)))
        console.print()
    else:
        # Wrap plain text nicely
        for line in text.split("\n"):
            if line.strip():
                console.print(f"    [{C['moon']}]{line}[/]")


async def run_full(prompt: str, agents: dict[str, BaseAgent]):
    """Run /full via FullModeDispatcher — single orchestration path."""
    connected = [a for a in agents.values() if a.is_connected]
    if not connected:
        console.print(f"  [{C['red']}]No connected agents.[/]")
        return

    console.print(f"\n  [{C['gold']}]▸[/] [{C['moon']}]{prompt}[/]")
    console.print(f"  [{C['dim']}]dispatching to {len(connected)} agents...[/]\n")

    dispatcher = FullModeDispatcher(connected, timeout=60.0)

    async def on_start(name: str):
        console.print(f"  [{C['dim']}]→ {name} processing...[/]")

    async def on_done(resp):
        status = f"[{C['green']}]✓[/]" if not resp.degraded else f"[{C['gold']}]⚠ degraded[/]"
        console.print(f"  {status} [{C['blue']}]{resp.agent}[/]  [{C['dim']}]{resp.latency_ms}ms[/]")
        if resp.answer:
            _print_answer(resp.answer)
        if resp.confidence:
            console.print(f"    [{C['dim']}]Confidence:[/] [{C['blue']}]{resp.confidence.value}[/]")
        if resp.evidence:
            console.print(f"    [{C['dim']}]Evidence:[/] [{C['violet']}]{", ".join(resp.evidence[:5])}[/]")
        if resp.followup:
            console.print(f"    [{C['dim']}]Next:[/] {resp.followup}")
        console.print()

    result = await dispatcher.dispatch(prompt, on_agent_start=on_start, on_agent_done=on_done)

    # Summary
    valid = sum(1 for r in result.responses if not r.degraded)
    avg_ms = sum(r.latency_ms for r in result.responses) // len(result.responses) if result.responses else 0
    console.print(
        f"  [{C['dim']}]── /full ── {len(result.responses)} agents ── "
        f"{valid} valid ── avg {avg_ms}ms ──[/]\n"
    )


# ── Main loop ─────────────────────────────────────────────────────────────────

async def run_consensus_cmd(prompt: str, agents: dict[str, BaseAgent]):
    """Run /consensus — all agents answer, then synthesize ONE best answer."""
    connected = [a for a in agents.values() if a.is_connected]
    if not connected:
        console.print(f"  [{C['red']}]No connected agents.[/]")
        return

    console.print(f"\n  [{C['gold']}]▸[/] [{C['moon']}]{prompt}[/]")
    console.print(f"  [{C['dim']}]consensus mode — {len(connected)} agents[/]\n")

    async def on_phase(msg: str):
        console.print(f"  [{C['violet']}]⟐[/] [{C['dim']}]{msg}[/]")

    result = await run_consensus(
        prompt=prompt,
        agents=list(agents.values()),
        on_phase=on_phase,
        timeout=60.0,
    )

    if "error" in result:
        console.print(f"  [{C['red']}]{result['error']}[/]")
        return

    # Show Phase 1 results briefly
    console.print(f"\n  [{C['dim']}]── Individual Responses ──[/]")
    for name, reply, ms in result["phase1_responses"]:
        parsed = parse_structured_response(name, reply, ms)
        status = f"[{C['green']}]✓[/]" if not parsed.degraded else f"[{C['gold']}]⚠[/]"
        confidence = parsed.confidence.value if not parsed.degraded else "degraded"
        # Show just the first line of answer
        short = parsed.answer.split("\n")[0][:80] if parsed.answer else "(no answer)"
        console.print(f"    {status} [{C['blue']}]{name}[/]  [{C['dim']}]{ms}ms  {confidence}[/]")
        console.print(f"      [{C['dim']}]{short}[/]")  # summary line only, no markdown needed

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
        f"\n  [{C['dim']}]── /consensus ── {len(result['phase1_responses'])} agents ── "
        f"synthesized by {synth} ── {total}ms total ──[/]\n"
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
                user_input = Prompt.ask(f"  [{C['violet']}]⚕[/] [{C['dim']}]❯[/]")
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
                prompt = text[11:].strip()
                if prompt:
                    await run_consensus_cmd(prompt, agents)
                else:
                    console.print(f"  [{C['dim']}]Usage: /consensus <prompt>[/]")
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
