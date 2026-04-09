import time
import unittest

from mat import build_full_status_lines


class BuildFullStatusLinesTests(unittest.TestCase):
    def test_shows_live_progress_and_timer_for_processing_agents(self):
        now = 100.0
        agent_states = {
            "fast": {
                "label": "Fast",
                "status": "done",
                "response": {"answer": "Done answer", "latency_ms": 1200, "degraded": False},
                "started_at": 98.0,
            },
            "slow": {
                "label": "Slow",
                "status": "running",
                "started_at": 95.4,
                "response": None,
            },
        }

        lines = build_full_status_lines(agent_states, now=now)
        joined = "\n".join(lines)
        self.assertIn("1/2 agents responded", joined)
        self.assertIn("slow", joined.lower())
        self.assertIn("4.6s", joined)
        self.assertIn("Done answer", joined)


if __name__ == "__main__":
    unittest.main()
