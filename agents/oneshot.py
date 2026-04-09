"""One-shot subprocess agent — runs a fresh command per message."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

from agents.base import AgentConfig, BaseAgent

logger = logging.getLogger("ixel_mat.agents.oneshot")

# Strip ANSI escape sequences
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[^\[\]][^a-zA-Z]*[a-zA-Z]?')
SESSION_ID_RE = re.compile(r"(?:session_id|session)\s*[:=]\s*([A-Za-z0-9_\-]+)", re.IGNORECASE)


class OneShotAgent(BaseAgent):
    """
    Runs a fresh subprocess per message (e.g. hermes chat -q "prompt").
    
    No persistent process, no PTY, no TUI rendering issues.
    Each send() spawns a new process, captures stdout, returns the result.
    """

    def __init__(self, config: AgentConfig, *, timeout: float = 120.0):
        super().__init__(config)
        self.timeout = timeout
        self._listen_callback: Callable[[str], Awaitable[None]] | None = None

    async def connect(self) -> None:
        """One-shot doesn't maintain a connection — just mark as ready."""
        if not self.config.command:
            raise ValueError(f"Agent '{self.name}' missing command")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def send(self, message: str) -> None:
        """Send a message and stream the response via listener callback."""
        response = await self._run_command(message)
        if self._listen_callback and response:
            await self._listen_callback(response)

    async def send_and_receive(self, message: str) -> str:
        """Send and return full response. Used by /full mode."""
        return await self._run_command(message)

    async def listen(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register callback and block while 'connected'."""
        self._listen_callback = callback
        while self._connected:
            await asyncio.sleep(0.2)

    async def _run_command(self, message: str) -> str:
        """Spawn hermes chat -q "message" and capture output."""
        cmd = [self.config.command] + list(self.config.args or [])
        
        # Add the query
        cmd.extend(["-q", message])
        
        # Add resume if we have a session
        if self.config.last_session_id:
            cmd.extend(["--resume", self.config.last_session_id])

        logger.info("Running one-shot: %s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=None,  # inherit parent env
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )

            output = stdout.decode("utf-8", errors="replace")
            
            # Strip ANSI codes
            output = ANSI_RE.sub("", output)
            
            # Strip common Hermes noise lines
            lines = output.split("\n")
            clean_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip empty lines, spinner chars, pure numbers (progress), session info
                if not stripped:
                    continue
                if stripped.isdigit():
                    continue
                if stripped.endswith("s") and stripped[:-1].isdigit():
                    continue
                session_match = SESSION_ID_RE.search(stripped)
                if session_match:
                    self.config.last_session_id = session_match.group(1)
                    continue
                if stripped.startswith("Duration:") or stripped.startswith("Messages:"):
                    continue
                clean_lines.append(line)
            
            result = "\n".join(clean_lines).strip()
            
            if proc.returncode != 0 and not result:
                err = stderr.decode("utf-8", errors="replace").strip()
                return f"Error (exit {proc.returncode}): {err or 'unknown error'}"
            
            return result

        except asyncio.TimeoutError:
            return f"Timed out after {self.timeout}s"
        except FileNotFoundError:
            return f"Command not found: {self.config.command}"
        except Exception as e:
            return f"Error: {e}"
