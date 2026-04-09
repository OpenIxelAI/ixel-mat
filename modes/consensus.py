"""
/consensus mode — Multi-agent convergence to a single best answer.

Streaming flow:
  1. Send prompt to all agents in parallel
  2. Emit each Phase 1 response as soon as it arrives
  3. Start Phase 2 synthesis as soon as N valid responses are available
  4. Continue accepting late arrivals while synthesis is running and mark them
     as not included in the synthesis
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from schema.response import (
    FULL_MODE_SUFFIX,
    AgentResponse,
    Confidence,
    parse_structured_response,
)

CONSENSUS_PROMPT = """You are the consensus synthesizer. Multiple AI agents were asked the same question.
Their responses are below. Your job:

1. Read ALL responses carefully
2. Identify the strongest answer, best evidence, and most accurate claims
3. Resolve any disagreements by picking the most well-supported position
4. Produce ONE final answer that represents the best of all inputs
5. Credit which agent(s) contributed key insights

ORIGINAL QUESTION:
{question}

AGENT RESPONSES:
{responses}

Now synthesize the single best answer.

IMPORTANT: Structure your response in this exact format:

**Answer:** [the consensus answer — comprehensive but concise]

**Confidence:** [high/medium/low/uncertain]

**Evidence:** [combined evidence from all agents — one per line, or "none"]

**Uncertainties:** [any disagreements or gaps — one per line, or "none"]

**Commands:** [any commands if relevant — one per line, or "none"]

**Next Step:** [what the user should do next]
"""


async def _maybe_call(callback, *args) -> None:
    if callback:
        await callback(*args)


def _score_response(parsed: AgentResponse) -> int:
    return {
        Confidence.HIGH: 3,
        Confidence.MEDIUM: 2,
        Confidence.LOW: 1,
        Confidence.UNCERTAIN: 0,
    }.get(parsed.confidence, 0) + min(len(parsed.evidence), 3)


def _format_response_block(parsed: AgentResponse) -> str:
    block = f"[{parsed.agent}] (confidence: {parsed.confidence.value})\n"
    block += f"Answer: {parsed.answer}\n"
    if parsed.evidence:
        block += f"Evidence: {', '.join(parsed.evidence)}\n"
    if parsed.uncertainties:
        block += f"Uncertainties: {', '.join(parsed.uncertainties)}\n"
    return block


def _pick_best_valid(responses: list[AgentResponse]) -> AgentResponse | None:
    best = None
    best_score = -1
    for parsed in responses:
        if parsed.degraded:
            continue
        score = _score_response(parsed)
        if score > best_score:
            best_score = score
            best = parsed
    return best


async def _query_agent(agent, prompt: str, timeout: float) -> tuple:
    t0 = time.time()
    try:
        reply = await asyncio.wait_for(
            agent.send_and_receive(prompt + FULL_MODE_SUFFIX, use_full_session=True),
            timeout=timeout,
        )
    except Exception as e:
        reply = f"Error: {e}"
    ms = int((time.time() - t0) * 1000)
    parsed = parse_structured_response(agent.name, reply, ms)
    return agent, reply, ms, parsed


def _pick_synthesizer(included: list[AgentResponse], explicit, connected: list):
    if explicit is not None:
        return explicit

    valid_names = {resp.agent for resp in included if not resp.degraded}
    candidates = [agent for agent in connected if agent.name in valid_names]
    if not candidates:
        return connected[0]

    latency_by_name = {resp.agent: resp.latency_ms for resp in included if not resp.degraded}
    return min(candidates, key=lambda agent: latency_by_name.get(agent.name, 10**9))


async def _run_synthesis(prompt: str, synth, included: list[AgentResponse], timeout: float):
    synthesis_prompt = CONSENSUS_PROMPT.format(
        question=prompt,
        responses="\n---\n".join(_format_response_block(resp) for resp in included if not resp.degraded),
    )

    t_synth = time.time()
    try:
        synth_reply = await asyncio.wait_for(
            synth.send_and_receive(synthesis_prompt, use_full_session=True),
            timeout=timeout,
        )
    except Exception as e:
        synth_reply = f"Synthesis failed: {e}"

    synth_ms = int((time.time() - t_synth) * 1000)
    consensus = parse_structured_response(
        agent=f"consensus ({synth.name})",
        raw=synth_reply,
        latency_ms=synth_ms,
    )
    return synth_reply, consensus


async def run_consensus(
    prompt: str,
    agents: list,
    synthesizer=None,
    on_phase: Callable[[str], Awaitable[None]] | None = None,
    on_agent_result: Callable[[AgentResponse, bool], Awaitable[None]] | None = None,
    on_late_response: Callable[[AgentResponse], Awaitable[None]] | None = None,
    timeout: float = 30.0,
    min_responses: int = 2,
) -> dict:
    """
    Run consensus mode with streaming Phase 1.

    Returns dict with:
      - phase1_responses: list of (name, reply, ms) seen before return
      - included_phase1: list of (name, reply, ms) used in synthesis
      - late_phase1: list of (name, reply, ms) that arrived after synthesis started
      - consensus: the synthesized final answer (AgentResponse)
      - synthesizer_name: which agent did the synthesis
      - total_ms: end-to-end time
    """
    connected = [a for a in agents if a.is_connected]
    if not connected:
        return {"error": "No connected agents"}

    min_responses = max(1, min_responses)
    t_start = time.time()

    await _maybe_call(on_phase, f"Phase 1: Dispatching to {len(connected)} agents...")

    pending_queries = {
        asyncio.create_task(_query_agent(agent, prompt, timeout)): agent
        for agent in connected
    }
    synthesis_task = None
    synth = None
    synthesis_started = False
    included: list[tuple[str, str, int, AgentResponse]] = []
    phase1_seen: list[tuple[str, str, int]] = []
    late_phase1: list[tuple[str, str, int]] = []
    consensus = None

    while pending_queries or synthesis_task is not None:
        wait_set = set(pending_queries)
        if synthesis_task is not None:
            wait_set.add(synthesis_task)

        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        if synthesis_task is not None and synthesis_task in done:
            _, consensus = synthesis_task.result()
            synthesis_task = None
            for task in list(done):
                if task in pending_queries:
                    agent, reply, ms, parsed = task.result()
                    phase1_seen.append((agent.name, reply, ms))
                    late_phase1.append((agent.name, reply, ms))
                    await _maybe_call(on_agent_result, parsed, False)
                    if not parsed.degraded:
                        await _maybe_call(on_late_response, parsed)
                    pending_queries.pop(task, None)
            break

        for task in done:
            if task not in pending_queries:
                continue
            agent, reply, ms, parsed = task.result()
            pending_queries.pop(task, None)
            phase1_seen.append((agent.name, reply, ms))

            if synthesis_started:
                late_phase1.append((agent.name, reply, ms))
                await _maybe_call(on_agent_result, parsed, False)
                if not parsed.degraded:
                    await _maybe_call(on_late_response, parsed)
                continue

            include_now = not parsed.degraded
            if include_now:
                included.append((agent.name, reply, ms, parsed))

            await _maybe_call(on_agent_result, parsed, include_now)

            if include_now and len(included) >= min_responses and synthesis_task is None:
                synthesis_started = True
                synth = _pick_synthesizer([item[3] for item in included], synthesizer, connected)
                await _maybe_call(on_phase, "Phase 2: Synthesizing consensus...")
                synthesis_task = asyncio.create_task(
                    _run_synthesis(prompt, synth, [item[3] for item in included], timeout)
                )

    if synthesis_task is None and consensus is None:
        valid = [item[3] for item in included if not item[3].degraded]
        if not valid:
            return {
                "error": f"No valid responses received within {timeout:.0f}s",
                "phase1_responses": phase1_seen,
                "included_phase1": [],
                "late_phase1": late_phase1,
                "total_ms": int((time.time() - t_start) * 1000),
            }

        synth = _pick_synthesizer(valid, synthesizer, connected)
        await _maybe_call(on_phase, "Phase 2: Synthesizing consensus...")
        _, consensus = await _run_synthesis(prompt, synth, valid, timeout)

    if consensus.degraded:
        best = _pick_best_valid([item[3] for item in included])
        if best:
            best.agent = f"fallback ({best.agent})"
            consensus = best

    for task in pending_queries:
        task.cancel()

    total_ms = int((time.time() - t_start) * 1000)

    return {
        "phase1_responses": phase1_seen,
        "included_phase1": [(name, reply, ms) for name, reply, ms, _ in included],
        "late_phase1": late_phase1,
        "consensus": consensus,
        "synthesizer_name": synth.name if synth else "",
        "total_ms": total_ms,
    }
