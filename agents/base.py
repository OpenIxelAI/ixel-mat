"""
BaseAgent — interface all agent transports implement.

Every agent (WebSocket, subprocess, ACP, API) must implement this.
This is the contract that /agent, /full, and future /max depend on.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Awaitable, Optional


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str               # internal id: "jose", "hermes"
    label: str              # display name e.g. "Claude", "Grok"
    type: str               # transport: "websocket", "subprocess", "acp", "api"
    color: str = "cyan"     # TUI color

    # WebSocket
    url: str = ""
    token: str = ""

    # Subprocess
    command: str = ""
    args: list[str] | None = None

    # Model (for HTTP adapters)
    model: str = ""          # model id e.g. gpt-4o, grok-4

    # Session
    session_key: str = ""    # full gateway session key e.g. agent:main:main
    auto_resume: bool = True
    last_session_id: str = ""


class BaseAgent(ABC):
    """Abstract base for all agent transports."""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.name = config.name
        self.label = config.label
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the agent."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean up connection."""
        ...

    @abstractmethod
    async def send(self, message: str) -> None:
        """Send a message to the agent (fire and forget)."""
        ...

    @abstractmethod
    async def send_and_receive(self, message: str, **kwargs) -> str:
        """Send a message and wait for the full response. Used by /full mode."""
        ...

    @abstractmethod
    async def listen(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """
        Listen for incoming messages and call callback for each.
        Used by /agent single mode for streaming responses.
        Should run until disconnect.
        """
        ...

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.disconnect()

    def __repr__(self) -> str:
        status = "●" if self.is_connected else "○"
        return f"{status} {self.label} ({self.config.type})"
