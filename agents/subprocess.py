"""Subprocess agent transport with PTY support for interactive CLIs."""

from __future__ import annotations

import asyncio
import logging
import os
import pty
import shutil
import signal
from contextlib import suppress
from typing import Awaitable, Callable

from agents.base import AgentConfig, BaseAgent

logger = logging.getLogger("ixel_mat.agents.subprocess")


class SubprocessAgent(BaseAgent):
    """
    Interactive subprocess transport.

    Uses a PTY by default so tools like Hermes behave as if attached to a terminal
    (colors, prompt behavior, interactive output).
    """

    def __init__(
        self,
        config: AgentConfig,
        *,
        use_pty: bool = True,
        response_idle_timeout: float = 1.2,
        startup_timeout: float = 10.0,
        shutdown_timeout: float = 4.0,
    ):
        super().__init__(config)
        self.use_pty = use_pty
        self.response_idle_timeout = response_idle_timeout
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout

        self.process: asyncio.subprocess.Process | None = None
        self.master_fd: int | None = None
        self.slave_fd: int | None = None
        self._read_task: asyncio.Task | None = None
        self._listen_callback: Callable[[str], Awaitable[None]] | None = None
        self._output_queue: asyncio.Queue[str] = asyncio.Queue()
        self._lock: asyncio.Lock = asyncio.Lock()
        self.binary_path: str = ""
        self.last_error: str = ""
        self.last_exit_code: int | None = None

    async def connect(self) -> None:
        if self._connected:
            return

        if not self.config.command:
            raise ValueError(f"Agent '{self.name}' missing command")

        binary = shutil.which(self.config.command)
        if not binary:
            raise FileNotFoundError(
                f"Command '{self.config.command}' not found in PATH for agent '{self.name}'"
            )
        self.binary_path = binary
        self.last_error = ""
        self.last_exit_code = None

        cmd = [binary] + list(self.config.args or [])
        if self.config.last_session_id and "--resume" not in cmd:
            cmd.extend(["--resume", self.config.last_session_id])
        logger.info("Starting subprocess agent '%s': %s", self.name, " ".join(cmd))

        try:
            if self.use_pty:
                self.master_fd, self.slave_fd = pty.openpty()
                self.process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=self.slave_fd,
                        stdout=self.slave_fd,
                        stderr=self.slave_fd,
                        preexec_fn=os.setsid,
                        close_fds=True,
                        env=self._build_env(),
                    ),
                    timeout=self.startup_timeout,
                )
                os.close(self.slave_fd)
                self.slave_fd = None
            else:
                self.process = await asyncio.wait_for(
                    asyncio.create_subprocess_exec(
                        *cmd,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        env=self._build_env(),
                    ),
                    timeout=self.startup_timeout,
                )

            self._read_task = asyncio.create_task(self._read_loop())
            # Give process a short moment to fail fast before marking connected.
            await asyncio.sleep(0.2)
            if self.process and self.process.returncode is not None:
                self.last_exit_code = self.process.returncode
                startup_output = await self._collect_startup_output()
                self.last_error = (
                    f"Process exited immediately with code {self.process.returncode}"
                )
                details = f"{self.last_error}. Output: {startup_output}" if startup_output else self.last_error
                await self.disconnect()
                raise RuntimeError(details)
            self._connected = True
        except Exception:
            await self._close_fds()
            raise

    async def disconnect(self) -> None:
        if self._read_task:
            self._read_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None

        if self.process:
            await self._terminate_process()
            self.process = None

        await self._close_fds()
        self._connected = False

    async def send(self, message: str) -> None:
        if not self.process or self.process.returncode is not None:
            raise RuntimeError(f"Agent '{self.name}' is not connected")

        payload = (message + "\n").encode("utf-8", errors="replace")
        if self.use_pty:
            if self.master_fd is None:
                raise RuntimeError("PTY master fd missing")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, os.write, self.master_fd, payload)
            return

        if not self.process.stdin:
            raise RuntimeError("Process stdin is unavailable")
        self.process.stdin.write(payload)
        await self.process.stdin.drain()

    async def send_and_receive(self, message: str, **kwargs) -> str:
        """
        Sends prompt then collects output until the stream goes idle.
        This keeps behavior transport-agnostic for /full without hard-coding prompts.
        kwargs accepted and ignored for transport-agnostic compatibility.
        """
        async with self._lock:
            self._drain_queue()
            await self.send(message)

            chunks: list[str] = []
            while True:
                try:
                    item = await asyncio.wait_for(
                        self._output_queue.get(), timeout=self.response_idle_timeout
                    )
                    chunks.append(item)
                except asyncio.TimeoutError:
                    break

            return "".join(chunks).strip()

    async def listen(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register a stream callback and block while connected."""
        self._listen_callback = callback
        while self._connected:
            await asyncio.sleep(0.1)

    async def cancel(self) -> None:
        """Interrupt current generation (SIGINT on process group when possible)."""
        if not self.process or self.process.returncode is not None:
            return
        if self.use_pty:
            with suppress(ProcessLookupError):
                os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
        else:
            self.process.send_signal(signal.SIGINT)

    async def _read_loop(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self.process and self.process.returncode is None:
                if self.use_pty:
                    if self.master_fd is None:
                        break
                    try:
                        data = await loop.run_in_executor(None, os.read, self.master_fd, 4096)
                    except OSError as exc:
                        # EIO is expected once PTY closes.
                        if exc.errno != 5:
                            logger.warning("PTY read error (%s): %s", self.name, exc)
                        break
                else:
                    if not self.process.stdout:
                        break
                    data = await self.process.stdout.read(4096)
                    if not data:
                        break

                if not data:
                    break

                text = data.decode("utf-8", errors="replace")
                await self._output_queue.put(text)
                if self._listen_callback:
                    await self._listen_callback(text)
        finally:
            self._connected = False
            if self.process and self.process.returncode is not None:
                self.last_exit_code = self.process.returncode

    async def _terminate_process(self) -> None:
        assert self.process is not None
        if self.process.returncode is not None:
            return

        try:
            if self.use_pty:
                with suppress(ProcessLookupError):
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            else:
                self.process.terminate()
            await asyncio.wait_for(self.process.wait(), timeout=self.shutdown_timeout)
        except Exception:
            if self.process.returncode is None:
                if self.use_pty:
                    with suppress(ProcessLookupError):
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                else:
                    self.process.kill()
                with suppress(Exception):
                    await asyncio.wait_for(self.process.wait(), timeout=1.5)

    async def _close_fds(self) -> None:
        if self.slave_fd is not None:
            with suppress(OSError):
                os.close(self.slave_fd)
            self.slave_fd = None
        if self.master_fd is not None:
            with suppress(OSError):
                os.close(self.master_fd)
            self.master_fd = None

    def _drain_queue(self) -> None:
        while True:
            try:
                self._output_queue.get_nowait()
            except asyncio.QueueEmpty:
                return

    async def _collect_startup_output(self) -> str:
        parts: list[str] = []
        while True:
            try:
                item = self._output_queue.get_nowait()
                parts.append(item)
            except asyncio.QueueEmpty:
                break
        return "".join(parts).strip()

    def _build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("TERM", "xterm-256color")
        return env
