#!/usr/bin/env python3
"""
Ixel MAT — CLI entry point.

Usage:
  ixel                    Launch multi-agent terminal
  ixel setup              Interactive setup wizard
  ixel status             Show single-screen status dashboard
  ixel config             Show resolved config + validation
  ixel agents             List configured agents + status
  ixel help               Show all commands
  ixel version            Show version
  ixel doctor             Check dependencies + connectivity
"""
from __future__ import annotations

import asyncio
import datetime as dt
import os
import stat
import sys
import time
from pathlib import Path

# Ensure ixel-mat directory is in path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console


def classify_probe_status(ok: bool, message: str) -> tuple[str, str]:
    msg = (message or "").lower()
    if ok:
        return "ok", "✓ ok"
    if "429" in msg or "rate limit" in msg:
        return "rate_limited", "⚠ rate limited"
    if any(token in msg for token in ("401", "403", "invalid key", "invalid token", "auth failed", "forbidden")):
        return "auth_failed", "✗ auth failed"
    return "unreachable", "✗ unreachable"


def get_secret_file_status(path: Path) -> dict[str, str | bool]:
    if not path.exists():
        return {
            "exists": False,
            "permissions_octal": "—",
            "last_modified": "—",
        }

    st = path.stat()
    perms = stat.S_IMODE(st.st_mode)
    last_modified = dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "exists": True,
        "permissions_octal": f"{perms:o}",
        "last_modified": last_modified,
    }


def _status_color(status_key: str) -> str:
    return {
        "ok": C["green"],
        "rate_limited": C["gold"],
        "auth_failed": C["red"],
        "unreachable": C["red"],
    }.get(status_key, C["dim"])


def _probe_provider(provider: dict, key: str) -> tuple[str, str, int | None]:
    from config.setup import _probe_anthropic, _probe_google, _probe_openai_style, _probe_openclaw

    started = time.perf_counter()
    pid = provider.get("id", "")
    probe_type = provider.get("probe_type", "openai")

    try:
        if pid == "openclaw":
            ok, msg, _ = _probe_openclaw(key)
        elif probe_type == "anthropic":
            ok, msg = _probe_anthropic(key)
        elif probe_type == "google":
            ok, msg = _probe_google(key)
        else:
            ok, msg = _probe_openai_style(key, provider.get("probe_url", ""))
    except Exception as exc:
        ok, msg = False, f"connection error: {exc}"

    latency_ms = int((time.perf_counter() - started) * 1000)
    status_key, status_label = classify_probe_status(ok, msg)
    return status_key, status_label, latency_ms


async def _probe_agent_connection(cfg) -> tuple[str, str]:
    from agents import create_agent

    try:
        agent = create_agent(cfg)
    except Exception as exc:
        return "error", str(exc)

    try:
        await agent.connect()
        await agent.disconnect()
        return "ok", "connected"
    except Exception as exc:
        return "error", str(exc)

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
        ("ixel",             "Launch the multi-agent terminal"),
        ("ixel setup",       "Interactive setup — configure agents + API keys"),
        ("ixel configure",   "Alias for ixel setup"),
        ("ixel status",      "Single-screen health dashboard for providers, agents, and secrets"),
        ("ixel models",      "Show providers, models, and auth status"),
        ("ixel config",      "Show resolved config, tokens, validation status"),
        ("ixel agents",      "List agents + test connectivity"),
        ("ixel doctor",      "Check Python deps, config, gateway reachability"),
        ("ixel version",     "Show version"),
        ("ixel help",        "Show this help"),
    ]
    for cmd, desc in cmds:
        console.print(f"    [{C['blue']}]{cmd:<20}[/] [{C['dim']}]{desc}[/]")
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


def cmd_models():
    """Show all providers, their available models, auth status, and which model each agent uses."""
    from config.secrets import load_env
    load_env()
    from config.loader import load_config, build_agent_configs
    from config.setup import PROVIDERS, _mask_key

    config = load_config()
    agent_configs, _ = build_agent_configs(config)

    print_banner()
    console.print(f"  [{C['moon']}]Providers & Models[/]\n")

    from rich.table import Table
    from rich import box as rbox

    # ── Provider table ────────────────────────────────────────────────────
    ptable = Table(
        box=rbox.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    ptable.add_column("Provider",   style=C["blue"],  min_width=22)
    ptable.add_column("Auth",                         min_width=18)
    ptable.add_column("Key",        style=C["dim"],   min_width=14)
    ptable.add_column("Models",     style=C["dim"],   min_width=40)

    for p in PROVIDERS:
        env_name = p["env_name"]
        key      = os.getenv(env_name, "")
        if key:
            auth_str = f"[{C['green']}]✓ set[/]"
            key_str  = _mask_key(key)
        else:
            auth_str = f"[{C['red']}]✗ not set[/]"
            key_str  = "—"
        models_str = ", ".join(p.get("models", []))
        ptable.add_row(p["name"], auth_str, key_str, models_str)

    console.print(ptable)

    # ── Agent model usage table ───────────────────────────────────────────
    if agent_configs:
        console.print(f"  [{C['moon']}]Agent Model Usage[/]\n")

        atable = Table(
            box=rbox.SIMPLE,
            show_header=True,
            header_style=f"bold {C['moon']}",
            border_style=C["dim"],
            padding=(0, 1),
        )
        atable.add_column("Agent",   style=C["blue"],  min_width=14)
        atable.add_column("Label",   style=C["moon"],  min_width=24)
        atable.add_column("Type",    style=C["dim"],   min_width=10)
        atable.add_column("Model / Session", style=C["dim"], min_width=30)
        atable.add_column("Token",                     min_width=10)

        for name, cfg in agent_configs.items():
            extra      = cfg.model or cfg.session_key or "—"
            token_str  = f"[{C['green']}]✓[/]" if cfg.token else f"[{C['red']}]✗[/]"
            atable.add_row(name, cfg.label, cfg.type, extra, token_str)

        console.print(atable)
    else:
        console.print(f"  [{C['gold']}]⚠[/] [{C['dim']}]No agents configured — run: ixel setup[/]\n")


def cmd_status():
    """Single-screen status dashboard for providers, agents, secrets, and config."""
    from rich.table import Table
    from rich import box as rbox
    from config.secrets import load_env, get_env_file_path
    from config.loader import load_config, build_agent_configs, validate_config, find_config
    from config.setup import PROVIDERS, _mask_key

    load_env()
    config = load_config()
    configs, warnings = build_agent_configs(config)
    issues = validate_config(config)
    config_path = find_config() or config.get("_source", "defaults")
    secret_path = get_env_file_path()
    secret_status = get_secret_file_status(secret_path)

    print_banner()
    console.print(f"  [{C['gold']}]Status Dashboard[/]\n")
    console.print(f"  [{C['blue']}]Version[/] [{C['moon']}]v{VERSION}[/]  [{C['dim']}]Python {sys.version.split()[0]}[/]")
    console.print(f"  [{C['blue']}]Config source[/] [{C['dim']}]{config_path}[/]\n")

    ptable = Table(
        title=f"[{C['gold']}]Providers[/]",
        box=rbox.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    ptable.add_column("Provider", style=C["blue"], min_width=20)
    ptable.add_column("Auth", min_width=12)
    ptable.add_column("Probe", min_width=18)
    ptable.add_column("Latency", style=C["dim"], min_width=10)
    ptable.add_column("Key", style=C["dim"], min_width=14)

    for p in PROVIDERS:
        key = os.getenv(p["env_name"], "")
        auth_str = f"[{C['green']}]✓ set[/]" if key else f"[{C['red']}]✗ not set[/]"
        key_str = _mask_key(key) if key else "—"
        if key:
            status_key, status_label, latency_ms = _probe_provider(p, key)
            probe_str = f"[{_status_color(status_key)}]{status_label}[/]"
            latency_str = f"{latency_ms}ms"
        else:
            probe_str = f"[{C['dim']}]—[/]"
            latency_str = "—"
        ptable.add_row(p["name"], auth_str, probe_str, latency_str, key_str)

    console.print(ptable)
    console.print()

    atable = Table(
        title=f"[{C['gold']}]Agents[/]",
        box=rbox.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    atable.add_column("Agent", style=C["blue"], min_width=14)
    atable.add_column("Label", style=C["moon"], min_width=22)
    atable.add_column("Type", style=C["dim"], min_width=10)
    atable.add_column("Status", min_width=16)
    atable.add_column("Details", style=C["dim"], min_width=32)

    async def collect_agent_rows():
        rows = []
        for name, cfg in configs.items():
            status, detail = await _probe_agent_connection(cfg)
            status_str = f"[{C['green']}]✓ connected[/]" if status == "ok" else f"[{C['red']}]✗ failed[/]"
            rows.append((name, cfg.label, cfg.type, status_str, detail[:120]))
        return rows

    rows = asyncio.run(collect_agent_rows()) if configs else []
    for row in rows:
        atable.add_row(*row)
    if not rows:
        atable.add_row("—", "No agents configured", "—", f"[{C['gold']}]⚠[/]", "Run ixel setup")

    console.print(atable)
    console.print()

    stable = Table(
        title=f"[{C['gold']}]Secrets[/]",
        box=rbox.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    stable.add_column("Path", style=C["blue"], min_width=32)
    stable.add_column("Exists", min_width=10)
    stable.add_column("Perms", style=C["dim"], min_width=8)
    stable.add_column("Last Modified", style=C["dim"], min_width=20)
    stable.add_row(
        str(secret_path),
        f"[{C['green']}]✓[/]" if secret_status["exists"] else f"[{C['red']}]✗[/]",
        str(secret_status["permissions_octal"]),
        str(secret_status["last_modified"]),
    )
    console.print(stable)
    console.print()

    console.print(f"  [{C['gold']}]Warnings[/]")
    if warnings or issues:
        for item in [*warnings, *issues]:
            console.print(f"    [{C['gold']}]⚠[/] [{C['dim']}]{item}[/]")
    else:
        console.print(f"    [{C['green']}]✓[/] [{C['dim']}]No config warnings[/]")
    console.print()


def cmd_agents():
    """List agents and test connectivity."""
    from config.secrets import load_env
    load_env()
    from config.loader import load_config, build_agent_configs
    from agents import create_agent

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
                agent = create_agent(cfg)
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
    """Launch the Rich CLI multi-agent terminal (mat.py)."""
    from mat import main
    asyncio.run(main())



def main():
    args = sys.argv[1:]
    cmd = args[0] if args else ""

    commands = {
        "":           cmd_run,
        "setup":      cmd_setup,
        "configure":  cmd_setup,      # alias for setup
        "status":     cmd_status,
        "models":     cmd_models,
        "config":     cmd_config,
        "agents":     cmd_agents,
        "doctor":     cmd_doctor,
        "version":    cmd_version,
        "help":       cmd_help,
        "--help":     cmd_help,
        "-h":         cmd_help,
        "--version":  cmd_version,
        "-v":         cmd_version,
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
