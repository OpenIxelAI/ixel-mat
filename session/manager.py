import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("clawtty.session.manager")

CONFIG_DIR = Path.home() / ".clawtty"
SESSION_FILE = CONFIG_DIR / "sessions.json"

class SessionManager:
    """Manages persistent session state across all ClawTTY agents."""
    
    def __init__(self):
        self.state: Dict[str, Any] = {}
        self._ensure_config_dir()
        self.load()

    def _ensure_config_dir(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def load(self):
        """Load session state from disk."""
        if SESSION_FILE.exists():
            try:
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except json.JSONDecodeError:
                logger.error("Corrupted sessions.json, starting fresh.")
                self.state = {}
            except OSError as e:
                logger.error("Failed to load sessions.json: %s", e)
                self.state = {}
        else:
            self.state = {}

    def save(self):
        """Save session state to disk."""
        try:
            with open(SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save sessions.json: {e}")

    def get_last_session(self, agent_name: str) -> Optional[str]:
        """Get the ID of the last active session for an agent."""
        agent_state = self.state.get(agent_name, {})
        return agent_state.get("last_session_id")

    def get_auto_resume(self, agent_name: str, default: bool = True) -> bool:
        agent_state = self.state.get(agent_name, {})
        return bool(agent_state.get("auto_resume", default))

    def set_auto_resume(self, agent_name: str, enabled: bool):
        if agent_name not in self.state:
            self.state[agent_name] = {"sessions": []}
        self.state[agent_name]["auto_resume"] = bool(enabled)
        self.save()

    def set_active_session(self, agent_name: str, session_id: Optional[str]):
        """Set the active session ID, making it the default for auto-resume."""
        if agent_name not in self.state:
            self.state[agent_name] = {"sessions": []}
            
        self.state[agent_name]["last_session_id"] = session_id
        
        # If it's a new non-null ID, make sure it's in the history list
        if session_id:
            self.record_session_metadata(agent_name, session_id)
            
        self.save()

    def record_session_metadata(self, agent_name: str, session_id: str, duration: str = "0m"):
        """Update or insert a session into the history list."""
        if not session_id:
             return
             
        if agent_name not in self.state:
            self.state[agent_name] = {"sessions": []}
            
        sessions = self.state[agent_name].setdefault("sessions", [])
        
        # Update existing or add new
        existing = next((s for s in sessions if s.get("id") == session_id), None)
        if existing:
            # We don't overwrite messages if we're just recording connection
            existing["duration"] = duration
        else:
            sessions.insert(0, {"id": session_id, "messages": 0, "duration": duration})
            
        self.save()

    def increment_message_count(self, agent_name: str, session_id: str):
        """Bump the message count for a specific session."""
        if not session_id or agent_name not in self.state:
            return
            
        sessions = self.state[agent_name].get("sessions", [])
        existing = next((s for s in sessions if s.get("id") == session_id), None)
        
        if existing:
            existing["messages"] = existing.get("messages", 0) + 1
            self.save()

    def get_session_history(self, agent_name: str) -> List[Dict]:
        """Return the list of recorded sessions for an agent."""
        return self.state.get(agent_name, {}).get("sessions", [])
        
    def clear_active_session(self, agent_name: str):
        """Clear the active session (forces /new behavior)."""
        self.set_active_session(agent_name, None)