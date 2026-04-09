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

from ixel_commands import build_help_rows, resolve_command_name
from ixel_hyperlinks import hyperlink_text


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


def remediation_hint(status_key: str, message: str, provider_id: str | None = None) -> str:
    provider_label = provider_id or "provider"
    if status_key == "auth_failed":
        return f"Run ixel setup and replace the {provider_label} key."
    if status_key == "rate_limited":
        return f"{provider_label} is rate limited — retry shortly or switch models."
    return f"Check network reachability and verify {provider_label} endpoint/settings."


def summarize_agent_probe(cfg, status_key: str, detail: str, latency_ms: int | None = None) -> tuple[str, str]:
    if cfg.type == "http":
        if status_key == "ok":
            return f"[{C['green']}]✓ auth ok[/]", f"ready — {latency_ms}ms auth probe"
        if status_key == "rate_limited":
            return f"[{C['gold']}]⚠ rate limited[/]", detail
        if status_key == "auth_failed":
            return f"[{C['red']}]✗ auth failed[/]", detail
        return f"[{C['red']}]✗ unreachable[/]", detail
    if status_key == "ok":
        return f"[{C['green']}]✓ connected[/]", "transport ready"
    return f"[{C['red']}]✗ failed[/]", detail


def _provider_for_agent_cfg(cfg):
    from config.setup import PROVIDERS

    for provider in PROVIDERS:
        if cfg.url and provider.get("url") == cfg.url:
            return provider
    return None


async def _probe_agent_connection(cfg) -> tuple[str, str, int | None, str | None]:
    from agents import create_agent

    if cfg.type == "http":
        provider = _provider_for_agent_cfg(cfg)
        if provider is None:
            return "unreachable", "unknown provider configuration", None, None
        status_key, status_label, latency_ms = _probe_provider(provider, cfg.token)
        return status_key, status_label, latency_ms, provider.get("id")

    try:
        agent = create_agent(cfg)
    except Exception as exc:
        return "unreachable", str(exc), None, None

    try:
        await agent.connect()
        await agent.disconnect()
        return "ok", "connected", None, None
    except Exception as exc:
        return "unreachable", str(exc), None, None

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
    for cmd, desc in build_help_rows(mode='cli'):
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
    console.print(f"  [{C['blue']}]Config source[/]", end=" ")
    console.print(hyperlink_text(str(config_path)))
    console.print()

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
            status_key, detail, latency_ms, provider_id = await _probe_agent_connection(cfg)
            status_str, detail_str = summarize_agent_probe(cfg, status_key, detail, latency_ms)
            if status_key != 'ok':
                detail_str = f"{detail_str} — {remediation_hint(status_key, detail, provider_id)}"
            rows.append((name, cfg.label, cfg.type, status_str, detail_str[:120]))
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
        hyperlink_text(str(secret_path)),
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

            status_key, detail, latency_ms, provider_id = await _probe_agent_connection(cfg)
            status_str, detail_str = summarize_agent_probe(cfg, status_key, detail, latency_ms)
            console.print(f"      {status_str} [{C['dim']}]{detail_str}[/]")
            if status_key != 'ok':
                console.print(f"      [{C['gold']}]⚠[/] [{C['dim']}]{remediation_hint(status_key, detail, provider_id)}[/]")

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
    raw_cmd = args[0] if args else ''
    if raw_cmd in ('--help', '-h'):
        resolved = 'help'
    elif raw_cmd in ('--version', '-v'):
        resolved = 'version'
    else:
        resolved = resolve_command_name(raw_cmd, mode='cli')

    commands = {
        'run': cmd_run,
        'setup': cmd_setup,
        'status': cmd_status,
        'models': cmd_models,
        'config': cmd_config,
        'agents': cmd_agents,
        'doctor': cmd_doctor,
        'version': cmd_version,
        'help': cmd_help,
    }

    if isinstance(resolved, tuple) and resolved[0] == 'ambiguous':
        console.print(f"  [{C['red']}]Ambiguous command: {raw_cmd}[/]")
        console.print(f"  [{C['dim']}]Matches: {', '.join(resolved[1])}[/]\n")
        sys.exit(1)

    handler = commands.get(resolved)
    if handler:
        handler()
    else:
        console.print(f"  [{C['red']}]Unknown command: {raw_cmd}[/]")
        console.print(f"  [{C['dim']}]Run 'ixel help' for available commands[/]\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
