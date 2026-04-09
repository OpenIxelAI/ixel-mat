import os
import stat
import tempfile
import time
import unittest
from pathlib import Path

from agents.base import AgentConfig
from cli import classify_probe_status, get_secret_file_status, remediation_hint, summarize_agent_probe


class CliStatusHelperTests(unittest.TestCase):
    def test_classify_probe_status_variants(self):
        self.assertEqual(classify_probe_status(True, "key valid")[0], "ok")
        self.assertEqual(classify_probe_status(False, "HTTP 429")[0], "rate_limited")
        self.assertEqual(classify_probe_status(False, "invalid key (401 Unauthorized)")[0], "auth_failed")
        self.assertEqual(classify_probe_status(False, "connection error: timeout")[0], "unreachable")

    def test_get_secret_file_status_reports_permissions_and_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("TOKEN=abc\n")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            info = get_secret_file_status(path)
            self.assertTrue(info["exists"])
            self.assertEqual(info["permissions_octal"], "600")
            self.assertIn("last_modified", info)
            self.assertTrue(info["last_modified"])

    def test_remediation_hint_for_auth_failure(self):
        hint = remediation_hint("auth_failed", "invalid key (401 Unauthorized)", "anthropic")
        self.assertIn("ixel setup", hint)
        self.assertIn("anthropic", hint)

    def test_summarize_agent_probe_marks_http_as_auth_probe(self):
        cfg = AgentConfig(
            name="openai",
            label="OpenAI",
            type="http",
            url="https://api.openai.com/v1/chat/completions",
            token="tok",
            model="gpt-4o",
        )
        status, detail = summarize_agent_probe(cfg, "ok", "auth ok", latency_ms=123)
        self.assertIn("auth ok", status)
        self.assertIn("123ms", detail)

    def test_summarize_agent_probe_marks_websocket_as_connected(self):
        cfg = AgentConfig(name="gw", label="Gateway", type="websocket", url="ws://127.0.0.1", token="tok")
        status, detail = summarize_agent_probe(cfg, "ok", "connected")
        self.assertIn("connected", status)
        self.assertEqual(detail, "transport ready")


if __name__ == "__main__":
    unittest.main()
