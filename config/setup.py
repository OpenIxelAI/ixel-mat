"""
Interactive setup wizard for Ixel MAT.
Guided onboarding experience for configuring providers and agents.

Run with: ixel setup  (or ixel configure)
"""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from config.secrets import save_secret, get_env_file_path, load_env, normalize_secret_input

console = Console()

_CONFIG_DIR = Path.home() / ".config" / "ixel-mat"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"
VERSION = "0.2.0"

# IxelAI color palette
C = {
    "bg":      "#070b14",
    "navy":    "#0d1b2a",
    "moon":    "#c8d8e8",
    "blue":    "#7eb8d4",
    "violet":  "#9b7fc7",
    "gold":    "#d4af37",
    "dim":     "#6b7d94",
    "green":   "#4ade80",
    "red":     "#e05252",
}


# ── Provider definitions ───────────────────────────────────────────────────────

PROVIDERS = [
    {
        "id":            "openclaw",
        "name":          "OpenClaw Gateway",
        "env_name":      "IXELMAT_GATEWAY_TOKEN",
        "models":        ["all models via your OpenClaw gateway"],
        "type":          "websocket",
        "url":           "ws://127.0.0.1:18789",
        "probe_url":     "http://127.0.0.1:18789/api/sessions",
        "probe_type":    "openclaw",
    },
    {
        "id":            "openai",
        "name":          "OpenAI",
        "env_name":      "OPENAI_API_KEY",
        "models":        ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o3"],
        "type":          "http",
        "url":           "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o",
        "probe_url":     "https://api.openai.com/v1/models",
        "probe_type":    "openai",
    },
    {
        "id":            "anthropic",
        "name":          "Anthropic (Claude)",
        "env_name":      "ANTHROPIC_API_KEY",
        "models":        ["claude-opus-4", "claude-sonnet-4-5", "claude-haiku-3"],
        "type":          "http",
        "url":           "https://api.anthropic.com/v1/messages",
        "default_model": "claude-sonnet-4-5",
        "probe_url":     "https://api.anthropic.com/v1/models",
        "probe_type":    "anthropic",
    },
    {
        "id":            "xai",
        "name":          "xAI (Grok)",
        "env_name":      "XAI_API_KEY",
        "models":        ["grok-4", "grok-3", "grok-3-mini"],
        "type":          "http",
        "url":           "https://api.x.ai/v1/chat/completions",
        "default_model": "grok-4",
        "probe_url":     "https://api.x.ai/v1/models",
        "probe_type":    "openai",
    },
    {
        "id":            "gemini",
        "name":          "Google (Gemini)",
        "env_name":      "GOOGLE_API_KEY",
        "models":        ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
        "type":          "http",
        "url":           "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-2.5-pro",
        "probe_url":     "https://generativelanguage.googleapis.com/v1beta/models",
        "probe_type":    "google",
    },
]


# ── Validation probes ──────────────────────────────────────────────────────────

def _probe_openclaw(token: str, url: str = "http://127.0.0.1:18789/api/sessions") -> tuple[bool, str, list]:
    """Probe OpenClaw gateway. Returns (ok, message, sessions_list)."""
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            sessions = data if isinstance(data, list) else data.get("sessions", [])
            return True, f"connected ({len(sessions)} session(s))", sessions
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "invalid token (401 Unauthorized)", []
        return False, f"HTTP {e.code}", []
    except Exception as e:
        return False, f"could not connect — is OpenClaw running? ({e})", []


def _probe_openai_style(token: str, url: str) -> tuple[bool, str]:
    """Probe OpenAI-compatible API via the models endpoint."""
    try:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=8):
            return True, "key valid"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "invalid key (401 Unauthorized)"
        if e.code == 403:
            return False, "forbidden (403) — check key permissions"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"connection error: {e}"


def _probe_anthropic(token: str) -> tuple[bool, str]:
    """Probe Anthropic API."""
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": token, "anthropic-version": "2023-06-01"},
        )
        with urllib.request.urlopen(req, timeout=8):
            return True, "key valid"
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, "invalid key (401 Unauthorized)"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"connection error: {e}"


def _probe_google(token: str) -> tuple[bool, str]:
    """Probe Google Gemini API."""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={token}"
        with urllib.request.urlopen(url, timeout=8):
            return True, "key valid"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "invalid key (auth failed)"
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, f"connection error: {e}"


def _validate_key(provider: dict, key: str) -> tuple[bool, str]:
    """Validate a key for a given provider. Returns (ok, message)."""
    pid = provider["id"]
    probe_type = provider.get("probe_type", "openai")

    if pid == "openclaw":
        ok, msg, _ = _probe_openclaw(key)
        return ok, msg
    elif probe_type == "anthropic":
        return _probe_anthropic(key)
    elif probe_type == "google":
        return _probe_google(key)
    else:
        return _probe_openai_style(key, provider.get("probe_url", ""))


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return key[:4] + "..."
    return key[:8] + "..."


# ── Status detection ───────────────────────────────────────────────────────────

def _detect_status() -> dict[str, dict]:
    """Detect which providers are already configured (env or .env file)."""
    load_env()
    result = {}
    for p in PROVIDERS:
        env_name = p["env_name"]
        key = os.getenv(env_name, "")
        result[p["id"]] = {
            "configured": bool(key),
            "key": key,
            "masked": _mask_key(key) if key else "",
        }
    return result


# ── Welcome screen ─────────────────────────────────────────────────────────────

def _print_welcome(status: dict[str, dict]) -> None:
    """Print branded welcome screen with current provider status table."""
    console.print()

    # ASCII brand block
    console.print(
        f"[{C['gold']}]"
        "  ██╗██╗  ██╗███████╗██╗      \n"
        "  ██║╚██╗██╔╝██╔════╝██║      \n"
        "  ██║ ╚███╔╝ █████╗  ██║      \n"
        "  ██║ ██╔██╗ ██╔══╝  ██║      \n"
        "  ██║██╔╝ ██╗███████╗███████╗ \n"
        f"  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝[/] "
        f"[{C['moon']}]M A T[/]  [{C['dim']}]v{VERSION}[/]"
    )
    console.print()

    console.print(Panel(
        f"[{C['moon']}]Welcome to the Ixel MAT Setup Wizard[/]\n"
        f"[{C['dim']}]Configure your AI providers and agents for multi-agent comparison.[/]\n"
        f"[{C['dim']}]Secrets → [/][{C['blue']}]{get_env_file_path()}[/][{C['dim']}]  (permissions: 600)[/]",
        border_style=C["violet"],
        padding=(0, 2),
    ))
    console.print()

    # Status table
    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    table.add_column("Provider",    style=C["blue"],   min_width=22)
    table.add_column("Status",                         min_width=16)
    table.add_column("Models",      style=C["dim"],    min_width=34)
    table.add_column("Auth",        style=C["dim"],    min_width=14)

    for p in PROVIDERS:
        s = status[p["id"]]
        models_str = ", ".join(p.get("models", [])[:3])
        if s["configured"]:
            status_str = f"[{C['green']}]✓ configured[/]"
            auth_str   = s["masked"]
        else:
            status_str = f"[{C['dim']}]○ not set[/]"
            auth_str   = "—"
        table.add_row(p["name"], status_str, models_str, auth_str)

    console.print("  [bold]Current Status[/]")
    console.print(table)
    console.print()


# ── Provider setup ─────────────────────────────────────────────────────────────

def _setup_provider(provider: dict, existing_status: dict) -> Optional[str]:
    """
    Interactive setup for one provider.
    Returns the saved key/token string, or None if skipped.
    """
    pid      = provider["id"]
    name     = provider["name"]
    env_name = provider["env_name"]
    models   = provider.get("models", [])
    s        = existing_status[pid]

    # Section header
    console.print(f"  [{C['blue']}]━━ {name} ━━[/]")
    if models:
        console.print(f"  [{C['dim']}]Models: {', '.join(models)}[/]")
    console.print()

    if s["configured"]:
        console.print(f"  [{C['green']}]✓[/] [{C['dim']}]Key already set:[/] [{C['moon']}]{s['masked']}[/]")
        keep = Confirm.ask(f"  [{C['moon']}]Keep existing key?[/]", default=True)
        if keep:
            console.print(f"  [{C['dim']}]Keeping existing key.[/]\n")
            return s["key"]
        # Replace flow
        console.print(f"  [{C['dim']}]Enter replacement key (input is visible — paste carefully):[/]")
        new_key = Prompt.ask(f"  [{C['moon']}]{env_name}[/]")
        if not new_key.strip():
            console.print(f"  [{C['dim']}]No key entered — keeping existing.[/]\n")
            return s["key"]
        key = normalize_secret_input(new_key)
    else:
        if pid == "openclaw":
            console.print(
                f"  [{C['dim']}]Find your token at:[/] "
                f"[{C['blue']}]http://127.0.0.1:18789[/] "
                f"[{C['dim']}]→ Settings → Auth Token[/]"
            )
        want = Confirm.ask(f"  [{C['moon']}]Configure {name}?[/]", default=(pid == "openclaw"))
        if not want:
            console.print(f"  [{C['dim']}]Skipped.[/]\n")
            return None
        console.print(f"  [{C['dim']}]Enter key (input is visible — paste carefully):[/]")
        key = Prompt.ask(f"  [{C['moon']}]{env_name}[/]")
        if not key.strip():
            console.print(f"  [{C['dim']}]No key entered — skipped.[/]\n")
            return None
        key = normalize_secret_input(key)

    # Validate key live
    console.print(f"  [{C['dim']}]Validating...[/]", end="")
    ok, msg = _validate_key(provider, key)
    if ok:
        console.print(f"\r  [{C['green']}]✓[/] [{C['dim']}]{msg}[/]")
        save_secret(env_name, key)
        os.environ[env_name] = key
    else:
        console.print(f"\r  [{C['gold']}]⚠[/] [{C['dim']}]{msg}[/]")
        save_anyway = Confirm.ask(f"  [{C['dim']}]Save key anyway?[/]", default=False)
        if save_anyway:
            save_secret(env_name, key)
            os.environ[env_name] = key
        else:
            console.print(f"  [{C['dim']}]Key not saved.[/]\n")
            return None

    console.print()
    return key


# ── OpenClaw agent auto-detection ──────────────────────────────────────────────

def _detect_openclaw_sessions(token: str) -> list[str]:
    """Return list of session keys discovered on the gateway."""
    ok, _, sessions = _probe_openclaw(token)
    if not ok or not sessions:
        return []
    keys = []
    for s in sessions:
        if isinstance(s, dict):
            key = s.get("key") or s.get("session_key") or s.get("id", "")
        else:
            key = str(s)
        if key and key.startswith("agent:"):
            keys.append(key)
    return keys


# ── Agent configuration ────────────────────────────────────────────────────────

_HTTP_COLORS = {
    "openai":    "green",
    "anthropic": "blue",
    "xai":       "magenta",
    "gemini":    "red",
}


def _configure_agents(provider_keys: dict[str, Optional[str]]) -> list[dict]:
    """
    Walk through configured providers and build agent config entries.
    Returns list of dicts ready for TOML serialisation.
    """
    agents: list[dict] = []

    console.print(f"  [{C['blue']}]━━ Agent Configuration ━━[/]\n")
    console.print(
        f"  [{C['dim']}]We'll create one agent per configured provider.[/]\n"
        f"  [{C['dim']}]Press Enter to accept defaults.[/]\n"
    )

    # ── OpenClaw WebSocket agents ──────────────────────────────────────────
    gw_token = provider_keys.get("openclaw")
    if gw_token:
        console.print(f"  [{C['dim']}]Detecting active sessions on OpenClaw gateway...[/]")
        session_keys = _detect_openclaw_sessions(gw_token)

        if session_keys:
            console.print(
                f"  [{C['green']}]✓[/] [{C['dim']}]Found {len(session_keys)} session(s)[/]\n"
            )
            used_ids: set[str] = set()
            for sk in session_keys:
                parts   = sk.split(":")           # e.g. ["agent", "main", "main"]
                name_part = parts[1] if len(parts) > 1 else "agent"
                default_label = f"{name_part.title()} (OpenClaw)"
                agent_id = name_part.lower().replace("-", "_")
                # Deduplicate IDs
                if agent_id in used_ids:
                    agent_id = f"{agent_id}_{len(used_ids)}"
                used_ids.add(agent_id)

                console.print(f"  [{C['blue']}]Session:[/] [{C['moon']}]{sk}[/]")
                label = Prompt.ask(f"  [{C['moon']}]  Label[/]", default=default_label)
                agents.append({
                    "id":          agent_id,
                    "type":        "websocket",
                    "url":         "ws://127.0.0.1:18789",
                    "token_env":   "IXELMAT_GATEWAY_TOKEN",
                    "session_key": sk,
                    "label":       label.strip() or default_label,
                    "color":       "cyan",
                })
                console.print()
        else:
            console.print(
                f"  [{C['gold']}]⚠[/] [{C['dim']}]No active sessions found — configuring a default agent.[/]\n"
            )
            label = Prompt.ask(
                f"  [{C['moon']}]OpenClaw agent label[/]",
                default="OpenClaw Agent",
            )
            session_key = Prompt.ask(
                f"  [{C['moon']}]Session key[/]",
                default="agent:main:main",
            )
            agents.append({
                "id":          "openclaw",
                "type":        "websocket",
                "url":         "ws://127.0.0.1:18789",
                "token_env":   "IXELMAT_GATEWAY_TOKEN",
                "session_key": session_key,
                "label":       label.strip() or "OpenClaw Agent",
                "color":       "cyan",
            })
            console.print()

    # ── HTTP agents (one per API provider) ────────────────────────────────
    for p in PROVIDERS:
        if p["type"] != "http":
            continue
        key = provider_keys.get(p["id"])
        if not key:
            continue

        pid           = p["id"]
        default_label = p["name"]
        default_model = p.get("default_model", "")

        console.print(f"  [{C['blue']}]Provider:[/] [{C['moon']}]{p['name']}[/]")
        label = Prompt.ask(f"  [{C['moon']}]  Agent label[/]", default=default_label)
        model = Prompt.ask(f"  [{C['moon']}]  Model[/]",       default=default_model)
        agents.append({
            "id":        pid,
            "type":      "http",
            "url":       p["url"],
            "token_env": p["env_name"],
            "model":     model.strip() or default_model,
            "label":     label.strip() or default_label,
            "color":     _HTTP_COLORS.get(pid, "white"),
        })
        console.print()

    return agents


# ── TOML builder ───────────────────────────────────────────────────────────────

def _build_toml(agents: list[dict]) -> str:
    lines = [
        "# Ixel MAT — Agent Configuration",
        "# Generated by `ixel setup` wizard",
        "# Secrets are stored in .env — never in this file",
        "",
    ]
    for a in agents:
        lines.append(f"[agents.{a['id']}]")
        lines.append(f'type      = "{a["type"]}"')
        lines.append(f'url       = "{a["url"]}"')
        lines.append(f'token_env = "{a["token_env"]}"')
        if a.get("session_key"):
            lines.append(f'session_key = "{a["session_key"]}"')
        if a.get("model"):
            lines.append(f'model     = "{a["model"]}"')
        lines.append(f'label     = "{a["label"]}"')
        lines.append(f'color     = "{a["color"]}"')
        lines.append("")
    return "\n".join(lines)


# ── Summary + write ────────────────────────────────────────────────────────────

def _print_summary_and_write(agents: list[dict]) -> None:
    """Show final summary table, confirm, then write config.toml."""
    console.print(f"\n  [{C['blue']}]━━ Configuration Summary ━━[/]\n")

    if not agents:
        console.print(f"  [{C['gold']}]⚠[/] [{C['dim']}]No agents configured — nothing to write.[/]\n")
        return

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style=f"bold {C['moon']}",
        border_style=C["dim"],
        padding=(0, 1),
    )
    table.add_column("ID",              style=C["blue"],   min_width=14)
    table.add_column("Label",           style=C["moon"],   min_width=24)
    table.add_column("Type",            style=C["dim"],    min_width=10)
    table.add_column("Model / Session", style=C["dim"],    min_width=30)

    for a in agents:
        extra = a.get("model") or a.get("session_key") or "—"
        table.add_row(a["id"], a["label"], a["type"], extra)

    console.print(table)
    console.print(f"  [{C['dim']}]Config  →[/] [{C['blue']}]{_CONFIG_FILE}[/]")
    console.print(f"  [{C['dim']}]Secrets →[/] [{C['blue']}]{get_env_file_path()}[/]")
    console.print()

    do_write = Confirm.ask(f"  [{C['moon']}]Write configuration now?[/]", default=True)
    if not do_write:
        console.print(f"  [{C['dim']}]Aborted — no files written.[/]\n")
        return

    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if _CONFIG_FILE.exists():
        backup = _CONFIG_FILE.with_suffix(".toml.bak")
        shutil.copy2(_CONFIG_FILE, backup)
        console.print(f"  [{C['dim']}]Backed up → {backup}[/]")

    _CONFIG_FILE.write_text(_build_toml(agents))
    console.print(f"  [{C['green']}]✓[/] [{C['dim']}]Config written → {_CONFIG_FILE}[/]")
    console.print()


# ── Public entry point ─────────────────────────────────────────────────────────

def run_setup() -> None:
    """
    Interactive setup wizard for configuring providers and agents.

    Steps:
      1. Welcome screen with current status table
      2. Provider setup (key detection → validation → save)
      3. Agent configuration (auto-detect OpenClaw sessions, HTTP defaults)
      4. Summary table → write config.toml
    """
    # Load existing .env before anything else
    load_env()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Welcome ─────────────────────────────────────────────────────────
    status = _detect_status()
    _print_welcome(status)

    console.print(f"  [{C['dim']}]Walk through each provider — press Enter to keep defaults.[/]")
    console.print(f"  [{C['dim']}]You can skip any provider by answering 'n'.[/]\n")

    # ── 2. Providers ───────────────────────────────────────────────────────
    provider_keys: dict[str, Optional[str]] = {}
    for provider in PROVIDERS:
        provider_keys[provider["id"]] = _setup_provider(provider, status)

    configured_count = sum(1 for v in provider_keys.values() if v)
    if configured_count == 0:
        console.print(
            f"  [{C['gold']}]⚠[/] [{C['dim']}]No providers configured.[/]  "
            f"[{C['dim']}]Run '[/][{C['blue']}]ixel setup[/][{C['dim']}]' again when ready.[/]\n"
        )
        return

    # ── 3. Agent configuration ─────────────────────────────────────────────
    agents = _configure_agents(provider_keys)

    if not agents:
        console.print(
            f"  [{C['gold']}]⚠[/] [{C['dim']}]No agents configured.[/]  "
            f"[{C['dim']}]Run '[/][{C['blue']}]ixel setup[/][{C['dim']}]' again when ready.[/]\n"
        )
        return

    # ── 4. Summary + write ─────────────────────────────────────────────────
    _print_summary_and_write(agents)

    # ── Done ───────────────────────────────────────────────────────────────
    console.print(Panel(
        f"[{C['green']}]Setup complete![/]\n\n"
        f"[{C['dim']}]Start Ixel MAT:[/]    [{C['blue']}]ixel[/]\n"
        f"[{C['dim']}]From source:[/]       [{C['blue']}]python3 mat.py[/]\n"
        f"[{C['dim']}]Check agents:[/]      [{C['blue']}]ixel agents[/]\n\n"
        f"[{C['dim']}]No[/] [{C['moon']}]export[/] [{C['dim']}]commands needed — secrets load automatically.[/]",
        border_style=C["green"],
        padding=(0, 2),
    ))
    console.print()
