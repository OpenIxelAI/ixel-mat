#!/usr/bin/env python3
"""
Ixel MAT — CLI entry point.

Usage:
  ixel                    Launch multi-agent terminal
  ixel setup              Interactive setup wizard
  ixel config             Show resolved config + validation
  ixel agents             List configured agents + status
  ixel help               Show all commands
  ixel version            Show version
  ixel doctor             Check dependencies + connectivity
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure ixel-mat directory is in path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console

# IxelOS palette
C = {
    "bg":      "#070b14",
    "moon":    "#c8d8e8",
    "blue":    "#7eb8d4",
    "violet":  "#9b7fc7",
    "gold":    "#d4af37",
    "dim":     "#6b7d94",
    "green":   "#4ade80",
    "red":     "#e05252",
}

console = Console()
VERSION = "0.2.0"


def print_banner():
    console.print(f"\n  [{C['gold']}]Ixel MAT[/] [{C['dim']}]v{VERSION}[/]  [{C['dim']}]— Multi-Agent Terminal[/]")
    console.print(f"  [{C['dim']}]{'─' * 40}[/]\n")


def cmd_help():
    print_banner()
    cmds = [
        ("ixel",          "Launch the multi-agent terminal"),
        ("ixel setup",    "Interactive setup — configure agents + API keys"),
        ("ixel config",   "Show resolved config, tokens, validation status"),
        ("ixel agents",   "List agents + test connectivity"),
        ("ixel doctor",   "Check Python deps, config, gateway reachability"),
        ("ixel version",  "Show version"),
        ("ixel help",     "Show this help"),
    ]
    for cmd, desc in cmds:
        console.print(f"    [{C['blue']}]{cmd:<18}[/] [{C['dim']}]{desc}[/]")
    console.print()


def cmd_version():
    console.print(f"  [{C['gold']}]Ixel MAT[/] [{C['moon']}]v{VERSION}[/]")


def cmd_config():
    from config.secrets import load_env
    load_env()
    from config.loader import load_config, print_config_status
    config = load_config()
    print_banner()
    print_config_status(config)


def cmd_setup():
    from config.setup import run_setup
    run_setup()


def cmd_agents():
    """List agents and test connectivity."""
    from config.secrets import load_env
    load_env()
    from config.loader import load_config, build_agent_configs
    from agents.websocket import WebSocketAgent
    from agents.http import HttpAgent

    config = load_config()
    configs, warnings = build_agent_configs(config)

    print_banner()
    console.print(f"  [{C['moon']}]Agents ({len(configs)})[/]\n")

    for warn in warnings:
        console.print(f"  [{C['gold']}]⚠[/] [{C['dim']}]{warn}[/]")
    if warnings:
        console.print()

    async def test_agents():
        for name, cfg in configs.items():
            agent_type = cfg.type
            token_set = bool(cfg.token)
            url = cfg.url or "(none)"

            console.print(f"    [{C['blue']}]{name}[/] [{C['dim']}]— {cfg.label}[/]")
            console.print(f"      [{C['dim']}]type: {agent_type}  url: {url}  token: {'✓' if token_set else '✗'}[/]")

            if not token_set:
                console.print(f"      [{C['red']}]✗ no token — run ixel setup[/]")
                continue

            # Try connecting
            try:
                if agent_type == "http":
                    agent = HttpAgent(cfg)
                else:
                    agent = WebSocketAgent(cfg)

                await agent.connect()
                console.print(f"      [{C['green']}]✓ connected[/]")
                await agent.disconnect()
            except Exception as e:
                console.print(f"      [{C['red']}]✗ {e}[/]")

            console.print()

    asyncio.run(test_agents())


def cmd_doctor():
    """Check dependencies, config, and connectivity."""
    print_banner()
    console.print(f"  [{C['moon']}]Diagnostics[/]\n")

    # Python version
    py = sys.version.split()[0]
    ok = sys.version_info >= (3, 10)
    status = f"[{C['green']}]✓[/]" if ok else f"[{C['red']}]✗[/]"
    console.print(f"    {status} [{C['dim']}]Python {py} {'(3.10+ required)' if not ok else ''}[/]")

    # Dependencies
    deps = {
        "rich": "rich",
        "websockets": "websockets",
        "cryptography": "cryptography",
        "aiohttp": "aiohttp",
    }
    for name, module in deps.items():
        try:
            __import__(module)
            console.print(f"    [{C['green']}]✓[/] [{C['dim']}]{name}[/]")
        except ImportError:
            console.print(f"    [{C['red']}]✗[/] [{C['dim']}]{name} — pip install {name}[/]")

    # TOML parser
    try:
        import tomllib
        console.print(f"    [{C['green']}]✓[/] [{C['dim']}]tomllib (built-in)[/]")
    except ImportError:
        try:
            import tomli
            console.print(f"    [{C['green']}]✓[/] [{C['dim']}]tomli (fallback)[/]")
        except ImportError:
            console.print(f"    [{C['red']}]✗[/] [{C['dim']}]No TOML parser — pip install tomli[/]")

    console.print()

    # Config
    from config.secrets import load_env, secrets_exist, get_env_file_path
    load_env()
    from config.loader import load_config, validate_config, find_config

    config_path = find_config()
    if config_path:
        console.print(f"    [{C['green']}]✓[/] [{C['dim']}]Config: {config_path}[/]")
    else:
        console.print(f"    [{C['gold']}]⚠[/] [{C['dim']}]No config file — run: ixel setup[/]")

    if secrets_exist():
        console.print(f"    [{C['green']}]✓[/] [{C['dim']}]Secrets: {get_env_file_path()}[/]")
    else:
        console.print(f"    [{C['gold']}]⚠[/] [{C['dim']}]No secrets — run: ixel setup[/]")

    config = load_config()
    issues = validate_config(config)
    if issues:
        console.print()
        for issue in issues:
            console.print(f"    [{C['gold']}]⚠[/] [{C['dim']}]{issue}[/]")
    else:
        console.print(f"    [{C['green']}]✓[/] [{C['dim']}]Config valid[/]")

    console.print()


def cmd_run():
    """Launch the main MAT terminal."""
    from mat import main
    asyncio.run(main())


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""

    commands = {
        "":        cmd_run,
        "setup":   cmd_setup,
        "config":  cmd_config,
        "agents":  cmd_agents,
        "doctor":  cmd_doctor,
        "version": cmd_version,
        "help":    cmd_help,
        "--help":  cmd_help,
        "-h":      cmd_help,
        "--version": cmd_version,
        "-v":      cmd_version,
    }

    handler = commands.get(cmd)
    if handler:
        handler()
    else:
        console.print(f"  [{C['red']}]Unknown command: {cmd}[/]")
        console.print(f"  [{C['dim']}]Run 'ixel help' for available commands[/]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
