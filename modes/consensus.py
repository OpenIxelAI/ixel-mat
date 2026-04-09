"""
/consensus mode — Multi-agent convergence to a single best answer.

Flow:
  1. Send prompt to all agents in parallel (same as /full)
  2. Collect all responses
  3. Send ALL responses back to a designated "synthesizer" agent with instructions
     to produce one final answer that represents the best of all inputs
  4. Display the synthesized consensus answer

The synthesizer can be any agent — by default the first connected one,
or user can pick with /consensus --lead <agent>.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Awaitable

from schema.response import (
    FULL_MODE_SUFFIX,
    parse_structured_response,
    AgentResponse,
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


async def run_consensus(
    prompt: str,
    agents: list,
    synthesizer=None,
    on_phase: Callable[[str], Awaitable[None]] | None = None,
    timeout: float = 60.0,
) -> dict:
    """
    Run consensus mode.
    
    Returns dict with:
      - phase1_responses: list of (name, reply, ms) from all agents
      - consensus: the synthesized final answer (AgentResponse)
      - synthesizer_name: which agent did the synthesis
      - total_ms: end-to-end time
    """
    connected = [a for a in agents if a.is_connected]
    if not connected:
        return {"error": "No connected agents"}

    t_start = time.time()

    # ── Phase 1: Parallel dispatch (same as /full) ────────────────────────
    if on_phase:
        await on_phase(f"Phase 1: Dispatching to {len(connected)} agents...")

    async def query(agent) -> tuple[str, str, int]:
        t0 = time.time()
        try:
            reply = await asyncio.wait_for(
                agent.send_and_receive(prompt + FULL_MODE_SUFFIX, use_full_session=True),
                timeout=timeout,
            )
            ms = int((time.time() - t0) * 1000)
            return (agent.name, reply, ms)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            return (agent.name, f"Error: {e}", ms)

    phase1 = await asyncio.gather(*(query(a) for a in connected))

    # ── Phase 2: Synthesize ───────────────────────────────────────────────
    if on_phase:
        await on_phase("Phase 2: Synthesizing consensus...")

    # Pick synthesizer — user override, or first connected agent
    synth = synthesizer or connected[0]

    # Format all responses for the synthesizer
    response_blocks = []
    for name, reply, ms in phase1:
        parsed = parse_structured_response(name, reply, ms)
        if parsed.degraded:
            response_blocks.append(f"[{name}] (degraded): {reply[:500]}")
        else:
            block = f"[{name}] (confidence: {parsed.confidence.value})\n"
            block += f"Answer: {parsed.answer}\n"
            if parsed.evidence:
                block += f"Evidence: {', '.join(parsed.evidence)}\n"
            if parsed.uncertainties:
                block += f"Uncertainties: {', '.join(parsed.uncertainties)}\n"
            response_blocks.append(block)

    synthesis_prompt = CONSENSUS_PROMPT.format(
        question=prompt,
        responses="\n---\n".join(response_blocks),
    )

    t_synth = time.time()
    try:
        synth_reply = await asyncio.wait_for(
            synth.send_and_receive(synthesis_prompt, use_full_session=True),
            timeout=timeout,
        )
        synth_ms = int((time.time() - t_synth) * 1000)
    except Exception as e:
        synth_ms = int((time.time() - t_synth) * 1000)
        synth_reply = f"Synthesis failed: {e}"

    consensus = parse_structured_response(
        agent=f"consensus ({synth.name})",
        raw=synth_reply,
        latency_ms=synth_ms,
    )

    # Fallback: if synthesizer degraded, pick the best individual response
    # by confidence score instead of returning a broken consensus
    if consensus.degraded:
        from schema.response import Confidence
        best = None
        best_score = -1
        for name, reply, ms in phase1:
            parsed = parse_structured_response(name, reply, ms)
            if not parsed.degraded:
                score = {
                    Confidence.HIGH: 3,
                    Confidence.MEDIUM: 2,
                    Confidence.LOW: 1,
                    Confidence.UNCERTAIN: 0,
                }.get(parsed.confidence, 0)
                # Bonus for having evidence
                score += min(len(parsed.evidence), 3)
                if score > best_score:
                    best_score = score
                    best = parsed
        if best:
            best.agent = f"fallback ({best.agent})"
            consensus = best

    total_ms = int((time.time() - t_start) * 1000)

    return {
        "phase1_responses": phase1,
        "consensus": consensus,
        "synthesizer_name": synth.name,
        "total_ms": total_ms,
    }
