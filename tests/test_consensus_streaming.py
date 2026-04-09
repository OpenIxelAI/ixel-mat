import asyncio
import time
import unittest

from modes.consensus import run_consensus


VALID_HIGH = '{"answer":"ok","confidence":"high","evidence":["doc"],"uncertainties":[],"commands":[],"next_step":"ship it"}'
VALID_MED = '{"answer":"fine","confidence":"medium","evidence":[],"uncertainties":[],"commands":[],"next_step":"continue"}'
CONSENSUS_JSON = '{"answer":"consensus","confidence":"high","evidence":["merged"],"uncertainties":[],"commands":[],"next_step":"done"}'
DEGRADED_503 = 'Error: API 503: upstream unavailable'


class FakeAgent:
    def __init__(self, name, delays, replies):
        self.name = name
        self.label = name
        self.is_connected = True
        self._delays = list(delays)
        self._replies = list(replies)
        self.calls = []

    async def send_and_receive(self, message: str, **kwargs) -> str:
        self.calls.append({"message": message, "kwargs": kwargs, "at": time.perf_counter()})
        idx = len(self.calls) - 1
        await asyncio.sleep(self._delays[idx])
        return self._replies[idx]


class ConsensusStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_starts_synthesis_after_two_valid_responses_without_waiting_for_slowest(self):
        fast = FakeAgent("fast", [0.01, 0.08], [VALID_HIGH, CONSENSUS_JSON])
        medium = FakeAgent("medium", [0.02], [VALID_MED])
        slow = FakeAgent("slow", [0.04], [VALID_HIGH])

        seen = []
        phases = []
        late = []

        start = time.perf_counter()
        result = await run_consensus(
            prompt="what now",
            agents=[fast, medium, slow],
            timeout=1.0,
            min_responses=2,
            on_phase=lambda msg: _record(phases, msg),
            on_agent_result=lambda resp, included: _record(seen, (resp.agent, included, resp.degraded)),
            on_late_response=lambda resp: _record(late, resp.agent),
        )
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.20)
        self.assertEqual(result["synthesizer_name"], "fast")
        self.assertEqual(len(fast.calls), 2)
        self.assertEqual(len(medium.calls), 1)
        self.assertEqual(len(slow.calls), 1)
        self.assertIn(("fast", True, False), seen)
        self.assertIn(("medium", True, False), seen)
        self.assertIn("Phase 2: Synthesizing consensus...", phases)
        self.assertIn("slow", late)
        synthesis_prompt = fast.calls[1]["message"]
        self.assertIn("[fast]", synthesis_prompt)
        self.assertIn("[medium]", synthesis_prompt)
        self.assertNotIn("[slow]", synthesis_prompt)

    async def test_degraded_responses_do_not_count_toward_minimum_valid_responses(self):
        fast_degraded = FakeAgent("broken", [0.01], [DEGRADED_503])
        valid1 = FakeAgent("valid1", [0.02, 0.02], [VALID_HIGH, CONSENSUS_JSON])
        valid2 = FakeAgent("valid2", [0.08], [VALID_MED])

        seen = []
        result = await run_consensus(
            prompt="question",
            agents=[fast_degraded, valid1, valid2],
            timeout=1.0,
            min_responses=2,
            on_agent_result=lambda resp, included: _record(seen, (resp.agent, included, resp.degraded)),
        )

        self.assertEqual(result["synthesizer_name"], "valid1")
        self.assertIn(("broken", False, True), seen)
        self.assertIn(("valid1", True, False), seen)
        self.assertIn(("valid2", True, False), seen)
        synthesis_prompt = valid1.calls[1]["message"]
        self.assertNotIn("[broken]", synthesis_prompt)
        self.assertIn("[valid1]", synthesis_prompt)
        self.assertIn("[valid2]", synthesis_prompt)


async def _record(bucket, item):
    bucket.append(item)
