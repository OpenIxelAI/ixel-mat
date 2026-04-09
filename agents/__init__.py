# agents package
from agents.base import AgentConfig, BaseAgent
from agents.websocket import WebSocketAgent
from agents.http import HttpAgent
from agents.subprocess import SubprocessAgent
from agents.oneshot import OneShotAgent


def create_agent(config: AgentConfig) -> BaseAgent:
    """Factory: create the right agent transport from config type."""
    match config.type:
        case "http":
            return HttpAgent(config)
        case "websocket":
            return WebSocketAgent(config)
        case "subprocess":
            return SubprocessAgent(config)
        case "oneshot":
            return OneShotAgent(config)
        case _:
            raise ValueError(
                f"Unknown agent type: {config.type!r} for agent {config.name!r}"
            )


__all__ = [
    "AgentConfig",
    "BaseAgent",
    "WebSocketAgent",
    "HttpAgent",
    "SubprocessAgent",
    "OneShotAgent",
    "create_agent",
]
