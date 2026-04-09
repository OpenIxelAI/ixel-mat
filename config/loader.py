"""
Config loader for Ixel MAT.

Precedence: CLI flags > env vars > project-local > global > defaults
Secrets: never in config files — always env var references via token_env field.

Config location:
  1. --config /path/to/file.toml (explicit)
  2. ./.ixel-mat.toml (project-local)
  3. ~/.config/ixel-mat/config.toml (global)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from agents.base import AgentConfig

# Use tomllib (3.11+) or fallback to tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore


_GLOBAL_CONFIG = Path.home() / ".config" / "ixel-mat" / "config.toml"
_LOCAL_CONFIG  = Path(".ixel-mat.toml")

# Defaults if no config found
_DEFAULT_AGENTS = {
    "jose": {
        "type": "websocket",
        "url": "ws://127.0.0.1:18789",
        "token_env": "IXELMAT_GATEWAY_TOKEN",
        "session_key": "agent:main:main",
        "label": "Main Agent (OpenClaw)",
        "color": "cyan",
    },
    "hermes": {
        "type": "websocket",
        "url": "ws://127.0.0.1:18789",
        "token_env": "IXELMAT_GATEWAY_TOKEN",
        "session_key": "agent:hermes:main",
        "label": "Hermes (OpenClaw)",
        "color": "yellow",
    },
}


def find_config(explicit_path: str | None = None) -> Path | None:
    """Find the config file by precedence."""
    if explicit_path:
        p = Path(explicit_path)
        return p if p.exists() else None

    if _LOCAL_CONFIG.exists():
        return _LOCAL_CONFIG

    if _GLOBAL_CONFIG.exists():
        return _GLOBAL_CONFIG

    return None


def load_config(explicit_path: str | None = None) -> dict[str, Any]:
    """
    Load and return the full config dict.
    Returns defaults if no config file found.
    """
    path = find_config(explicit_path)

    if path is None:
        return {"agents": _DEFAULT_AGENTS, "_source": "defaults"}

    if tomllib is None:
        print(
            "Warning: no TOML parser available. "
            "Install tomli (pip install tomli) or use Python 3.11+.",
            file=sys.stderr,
        )
        return {"agents": _DEFAULT_AGENTS, "_source": "defaults (no toml parser)"}

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        data["_source"] = str(path)
        return data
    except Exception as e:
        print(f"Warning: failed to load {path}: {e}", file=sys.stderr)
        return {"agents": _DEFAULT_AGENTS, "_source": f"defaults (load error: {e})"}


def _resolve_token(agent_data: dict) -> str:
    """Resolve token from env var reference or direct value."""
    # Prefer token_env (env var name)
    env_name = agent_data.get("token_env", "")
    if env_name:
        val = os.getenv(env_name, "")
        if val:
            return val

    # Fallback: direct token (not recommended, will warn)
    direct = agent_data.get("token", "")
    if direct and not direct.startswith("${"):
        return direct

    # Handle ${ENV_VAR} interpolation
    if direct.startswith("${") and direct.endswith("}"):
        env_name = direct[2:-1]
        return os.getenv(env_name, "")

    return ""


def build_agent_configs(config: dict[str, Any]) -> dict[str, AgentConfig]:
    """
    Build AgentConfig objects from loaded config.
    Returns dict of name → AgentConfig.
    """
    agents_data = config.get("agents", {})
    configs: dict[str, AgentConfig] = {}
    warnings: list[str] = []

    for name, data in agents_data.items():
        if not isinstance(data, dict):
            continue

        token = _resolve_token(data)
        agent_type = data.get("type", "websocket")

        if agent_type == "websocket" and not token:
            env_name = data.get("token_env", "IXELMAT_GATEWAY_TOKEN")
            warnings.append(
                f"Agent '{name}': no token found. Set env var: export {env_name}=<your_token>"
            )

        configs[name] = AgentConfig(
            name=name,
            label=data.get("label", name),
            type=agent_type,
            url=data.get("url", ""),
            token=token,
            model=data.get("model", ""),
            session_key=data.get("session_key", f"agent:{name}:main"),
            color=data.get("color", "cyan"),
            command=data.get("command", ""),
            args=data.get("args"),
            auto_resume=data.get("auto_resume", True),
        )

    return configs, warnings


def validate_config(config: dict[str, Any]) -> list[str]:
    """
    Validate config and return list of issues.
    Empty list = valid.
    """
    issues: list[str] = []
    source = config.get("_source", "unknown")

    agents = config.get("agents", {})
    if not agents:
        issues.append("No agents configured")
        return issues

    for name, data in agents.items():
        if not isinstance(data, dict):
            issues.append(f"Agent '{name}': invalid config (not a dict)")
            continue

        agent_type = data.get("type", "")
        if agent_type not in ("websocket", "http", "subprocess"):
            issues.append(f"Agent '{name}': unknown type '{agent_type}'")

        if agent_type == "websocket":
            url = data.get("url", "")
            if not url:
                issues.append(f"Agent '{name}': missing url")
            elif not url.startswith(("ws://", "wss://")):
                issues.append(f"Agent '{name}': url must start with ws:// or wss://")

            token = _resolve_token(data)
            if not token:
                env_name = data.get("token_env", "IXELMAT_GATEWAY_TOKEN")
                issues.append(f"Agent '{name}': token not set (need: export {env_name}=...)")

        if not data.get("label"):
            issues.append(f"Agent '{name}': missing label")

    return issues


def print_config_status(config: dict[str, Any]):
    """Print resolved config status for mat config validate."""
    from rich.console import Console
    console = Console()

    source = config.get("_source", "unknown")
    console.print(f"\n  [bold]Config source:[/] {source}")

    agents = config.get("agents", {})
    console.print(f"  [bold]Agents:[/] {len(agents)}\n")

    for name, data in agents.items():
        if not isinstance(data, dict):
            continue
        agent_type = data.get("type", "?")
        label = data.get("label", name)
        url = data.get("url", "")
        token = _resolve_token(data)
        token_status = f"✓ set ({len(token)} chars)" if token else "✗ missing"
        env_name = data.get("token_env", "")

        console.print(f"    [cyan]{name}[/] — {label}")
        console.print(f"      type: {agent_type}")
        if url:
            console.print(f"      url: {url}")
        console.print(f"      token: {token_status}")
        if env_name:
            console.print(f"      token_env: {env_name}")
        console.print()

    issues = validate_config(config)
    if issues:
        console.print("  [yellow]Issues:[/]")
        for issue in issues:
            console.print(f"    [yellow]⚠[/] {issue}")
    else:
        console.print("  [green]✓ Config valid[/]")
    console.print()
