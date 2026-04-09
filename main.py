#!/usr/bin/env python3
"""Ixel MAT — Multi-Agent Terminal by IxelAI."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime
from contextlib import suppress

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog

from agents.base import AgentConfig
from agents.http import HttpAgent
from agents.oneshot import OneShotAgent
from agents.websocket import WebSocketAgent
from config.secrets import load_env
from config.loader import build_agent_configs, load_config
from modes.full import FullModeDispatcher
from session.manager import SessionManager

# Load secrets from ~/.config/ixel-mat/.env before config reads token_env
load_env()

# ── Config-driven agents ──────────────────────────────────────────────────────
# Loads from ~/.config/ixel-mat/config.toml (or defaults when absent).
_CONFIG = load_config()
AGENT_CONFIGS, _CONFIG_WARNINGS = build_agent_configs(_CONFIG)


# ── Theme ─────────────────────────────────────────────────────────────────────
# IxelOS palette by default. Override any color via env vars.
THEME = {
    "bg":        os.getenv("IXELMAT_THEME_BG",      "#070b14"),  # space black
    "bg2":       os.getenv("IXELMAT_THEME_BG2",     "#0d1b2a"),  # navy
    "fg":        os.getenv("IXELMAT_THEME_FG",      "#c8d8e8"),  # moonstone
    "accent":    os.getenv("IXELMAT_THEME_ACCENT",  "#7eb8d4"),  # lunar blue
    "accent2":   os.getenv("IXELMAT_THEME_ACCENT2", "#9b7fc7"),  # violet
    "gold":      os.getenv("IXELMAT_THEME_GOLD",    "#d4af37"),  # gold
    "dim":       os.getenv("IXELMAT_THEME_DIM",     "#6b7d94"),  # dim
    "error":     os.getenv("IXELMAT_THEME_ERROR",   "#e05252"),  # red
    "success":   os.getenv("IXELMAT_THEME_SUCCESS", "#4ade80"),  # green
}




class IxelMATApp(App):
    ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    OSC_RE = re.compile(r"\x1B\].*?(?:\x07|\x1B\\)")
    CONTROL_RE = re.compile(r"[\x00-\x08\x0B-\x1F\x7F]")

    @classmethod
    def _build_css(cls) -> str:
        t = THEME
        return f"""
        Screen {{ background: {t['bg']}; }}
        Header {{ background: {t['bg2']}; color: {t['accent']}; }}
        Footer {{ background: {t['bg2']}; color: {t['fg']}; }}
        RichLog {{
            background: {t['bg']};
            color: {t['fg']};
            border: solid {t['bg2']};
            height: 1fr;
            scrollbar-color: {t['accent']};
        }}
        Input {{
            background: {t['bg2']};
            color: {t['fg']};
            border: solid {t['accent']};
            height: 3;
        }}
        Input:focus {{ border: solid {t['accent2']}; }}
        """

    CSS = _build_css.__func__(None)

    TITLE = "Ixel MAT"
    SUB_TITLE = "Ixel MAT — Multi-Agent Terminal"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield RichLog(id="chat", wrap=True, markup=True, highlight=True)
            yield Input(
                placeholder="/agent <name> | /full <prompt> | /sessions | /help",
                id="input",
            )
        yield Footer()

    async def on_mount(self) -> None:
        self.session_manager = SessionManager()
        # Build agents from config-loader results; support websocket and http types
        self.agents: dict[str, WebSocketAgent | HttpAgent] = {}
        for name, cfg in AGENT_CONFIGS.items():
            if cfg.type == "http":
                self.agents[name] = HttpAgent(cfg)
            else:
                self.agents[name] = WebSocketAgent(cfg)
        self.listener_tasks: dict[str, asyncio.Task] = {}
        self.listener_errors: dict[str, str] = {}
        # Use first configured agent as default, fall back to "jose"
        self.active_agent = next(iter(self.agents), "jose")
        self.sub_title = f"Agent: {self.agents[self.active_agent].label}" if self.agents else "No agents configured"

        self._write_banner()
        chat = self.query_one("#chat", RichLog)
        # Surface config warnings (e.g. missing tokens)
        for warn in _CONFIG_WARNINGS:
            chat.write(f"[yellow]{warn}[/]")
        if not self.agents:
            chat.write("[red]No agents configured. Check ~/.config/ixel-mat/config.toml[/]")
        # Auto-connect ALL agents so /full works immediately
        for name in self.agents:
            await self._connect_agent(name)

    async def on_unmount(self) -> None:
        for task in self.listener_tasks.values():
            task.cancel()
        for task in self.listener_tasks.values():
            with suppress(asyncio.CancelledError):
                await task
            with suppress(Exception):
                _ = task.exception()
        for agent in self.agents.values():
            if agent.is_connected:
                await agent.disconnect()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        self.query_one("#input", Input).value = ""

        if text.startswith("/"):
            await self._handle_command(text)
            return

        await self._send_single(text)

    async def _handle_command(self, text: str) -> None:
        chat = self.query_one("#chat", RichLog)
        if text.startswith("/agent "):
            name = text.split(" ", 1)[1].strip()
            if name not in self.agents:
                chat.write(f"[red]Unknown agent:[/] {name}")
                return
            self.active_agent = name
            self.sub_title = f"Agent: {self.agents[name].label}"
            chat.write(f"[yellow]→ Switched to {self.agents[name].label}[/]")
            await self._connect_agent(name)
            return

        if text == "/agents":
            for name, agent in self.agents.items():
                active = "●" if name == self.active_agent else "○"
                connected = "connected" if agent.is_connected else "idle"
                extra = ""
                if name in self.listener_errors:
                    extra = f" [red](listener error: {self.listener_errors[name]})[/]"
                chat.write(f"{active} [cyan]{name}[/] — {agent.label} [{connected}]{extra}")
            return

        if text == "/new":
            self.session_manager.clear_active_session(self.active_agent)
            self.agents[self.active_agent].config.last_session_id = ""
            if self.agents[self.active_agent].is_connected:
                await self.agents[self.active_agent].disconnect()
            await self._connect_agent(self.active_agent)
            chat.write(f"[green]Started new session for {self.active_agent}[/]")
            return

        if text.startswith("/resume "):
            session_id = text.split(" ", 1)[1].strip()
            self.session_manager.set_active_session(self.active_agent, session_id)
            self.agents[self.active_agent].config.last_session_id = session_id
            if self.agents[self.active_agent].is_connected:
                await self.agents[self.active_agent].disconnect()
            await self._connect_agent(self.active_agent)
            chat.write(f"[green]Resumed session {session_id} on {self.active_agent}[/]")
            return

        if text == "/sessions":
            rows = self.session_manager.get_session_history(self.active_agent)
            if not rows:
                chat.write(f"[dim]No sessions recorded for {self.active_agent}[/]")
                return
            chat.write(f"[bold]{self.active_agent} sessions:[/]")
            for row in rows[:10]:
                chat.write(
                    f"  - {row.get('id')} | {row.get('messages', 0)} messages | {row.get('duration', '0m')}"
                )
            return

        if text.startswith("/full "):
            prompt = text.split(" ", 1)[1].strip()
            await self._run_full(prompt)
            return

        if text == "/help":
            chat.write(
                "[bold]Commands[/]\n"
                "  [cyan]/agent <name>[/]  switch active agent\n"
                "  [cyan]/agents[/]        list agent status\n"
                "  [cyan]/new[/]           force a new session for active agent\n"
                "  [cyan]/resume <id>[/]   resume a specific session id\n"
                "  [cyan]/sessions[/]      list recent sessions for active agent\n"
                "  [cyan]/full <prompt>[/] run prompt across connected agents\n"
                "  [cyan]/quit[/]          exit"
            )
            return

        if text in ("/quit", "/exit", "/q"):
            self.exit()
            return

        chat.write("[yellow]Unknown command. Try /help[/]")

    async def _run_full(self, prompt: str) -> None:
        chat = self.query_one("#chat", RichLog)
        connected = [agent for agent in self.agents.values() if agent.is_connected]
        if not connected:
            chat.write("[red]No connected agents. Use /agent <name> first.[/]")
            return

        dispatcher = FullModeDispatcher(connected, timeout=60.0)
        chat.write(f"[bold #d4af37]You[/] [dim]{self._now()}[/]")
        chat.write(f"[bold]/full[/] {prompt}\n")

        async def on_agent_start(name: str) -> None:
            chat.write(f"[dim]→ {name} processing...[/]")

        async def on_agent_done(response) -> None:
            status = "degraded" if response.degraded else "ok"
            chat.write(f"[dim]✓ {response.agent} done ({status}, {response.latency_ms}ms)[/]")

        result = await dispatcher.dispatch(
            prompt,
            on_agent_start=on_agent_start,
            on_agent_done=on_agent_done,
        )
        chat.write(result.format_summary())

    async def _send_single(self, text: str) -> None:
        chat = self.query_one("#chat", RichLog)
        agent = self.agents[self.active_agent]
        if not agent.is_connected:
            await self._connect_agent(self.active_agent)
        if not agent.is_connected:
            chat.write(f"[red]Not connected to {self.active_agent}[/]")
            return

        chat.write(f"[bold #d4af37]You[/] [dim]{self._now()}[/]")
        chat.write(f"{text}\n")

        try:
            await agent.send(text)
        except Exception as exc:
            chat.write(f"[red]Send failed for {self.active_agent}: {exc}[/]")
            if not agent.is_connected:
                chat.write(f"[dim]Agent disconnected. Try /agent {self.active_agent} to reconnect.[/]")
            return

        last_id = self.session_manager.get_last_session(self.active_agent)
        if last_id:
            self.session_manager.increment_message_count(self.active_agent, last_id)

    async def _connect_agent(self, name: str) -> None:
        chat = self.query_one("#chat", RichLog)
        agent = self.agents[name]
        if agent.is_connected:
            self._ensure_listener(name)
            return

        if agent.config.auto_resume:
            session_id = self.session_manager.get_last_session(name)
            if session_id:
                agent.config.last_session_id = session_id

        try:
            await agent.connect()
            self._ensure_listener(name)
            chat.write(f"[green]✓ Connected to {agent.label}[/]")
            session_id = agent.config.last_session_id
            if session_id:
                self.session_manager.record_session_metadata(name, session_id)
        except Exception as exc:
            chat.write(f"[red]✗ Failed to connect to {name}: {exc}[/]")
            if hasattr(agent, "binary_path") and getattr(agent, "binary_path", ""):
                chat.write(f"[dim]{name} binary: {getattr(agent, 'binary_path')}[/]")
            if hasattr(agent, "last_error") and getattr(agent, "last_error", ""):
                chat.write(f"[dim]{name} detail: {getattr(agent, 'last_error')}[/]")

    def _ensure_listener(self, name: str) -> None:
        if name in self.listener_tasks and not self.listener_tasks[name].done():
            return

        agent = self.agents[name]

        async def callback(chunk: str) -> None:
            if name != self.active_agent:
                return
            clean = self._clean_chunk(chunk)
            if not clean.strip():
                return
            chat = self.query_one("#chat", RichLog)
            chat.write(f"[bold cyan]{agent.label}[/] [dim]{self._now()}[/]")
            chat.write(clean)

        task = asyncio.create_task(agent.listen(callback))

        def _on_done(done_task: asyncio.Task) -> None:
            self.listener_tasks.pop(name, None)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc:
                self.listener_errors[name] = str(exc)

        task.add_done_callback(_on_done)
        self.listener_tasks[name] = task

    def _write_banner(self) -> None:
        chat = self.query_one("#chat", RichLog)
        chat.write(
            "[bold cyan]╔══════════════════════════════════════╗[/]\n"
            "[bold cyan]║  Ixel MAT  —  Multi-Agent Terminal ║[/]\n"
            "[bold cyan]╚══════════════════════════════════════╝[/]\n"
        )
        chat.write("[dim]Use /help for commands.[/]")

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M")

    def _clean_chunk(self, chunk: str) -> str:
        """
        Remove terminal control noise from subprocess output before writing to RichLog.
        Keeps normal newlines/tabs while dropping ANSI cursor/control sequences.
        """
        text = self.OSC_RE.sub("", chunk)
        text = self.ANSI_RE.sub("", text)
        text = self.CONTROL_RE.sub("", text)
        text = text.replace("\r", "")

        # Drop known noisy CPR warnings and control garbage lines.
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                lines.append("")
                continue
            if "cursor position requests (CPR)" in stripped:
                continue
            if re.fullmatch(r"[\[\]\?\d;hqlm]+", stripped):
                continue
            lines.append(line)
        return "\n".join(lines)


def main() -> None:
    IxelMATApp().run()


if __name__ == "__main__":
    main()
