"""Trust-decision logic — ADK-free and fully unit-testable.

Mirrors the semantics of the sibling ``moltrust-crewai`` / ``moltrust-langchain``
guardrails so behaviour is identical across frameworks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .client import TrustClient
from .exceptions import AgentNotRegistered, MolTrustADKError

_ACTIONS = ("block", "warn", "log")


@dataclass
class Decision:
    """Outcome of a trust evaluation.

    Attributes:
        block: True only when the request should be blocked (``action="block"``
            and the check failed). Always False for ``warn``/``log``.
        score: The 0-100 trust score, or None when withheld/unavailable.
        reason: Machine-readable reason — one of ``ok``, ``low_score``,
            ``withheld``, ``unregistered``, ``no_did``, ``lookup_error_failopen``.
    """

    block: bool
    score: Optional[float]
    reason: str


def evaluate_trust(
    client: "TrustClient",
    did: Optional[str],
    *,
    min_score: float = 60,
    action: str = "block",
    pass_without_did: bool = True,
) -> Decision:
    """Evaluate a target DID's trust and decide whether to block.

    Fail-**open** on transport/registry errors (a MolTrust hiccup must not break
    the agent graph); fail-**closed** on an authoritative negative (low score,
    withheld, unregistered) when ``action="block"``.
    """
    if action not in _ACTIONS:
        raise ValueError(f"action must be one of {_ACTIONS}, got {action!r}")

    if not did:
        # Nothing to verify. Block only if explicitly required.
        return Decision(
            block=(action == "block") and (not pass_without_did),
            score=None,
            reason="no_did",
        )

    try:
        score = client.get_trust_score(did)
    except AgentNotRegistered:
        return Decision(block=(action == "block"), score=None, reason="unregistered")
    except MolTrustADKError:
        # registry/transport error -> fail open (allow)
        return Decision(block=False, score=None, reason="lookup_error_failopen")

    if score is None:
        return Decision(block=(action == "block"), score=None, reason="withheld")
    if score < min_score:
        return Decision(block=(action == "block"), score=score, reason="low_score")
    return Decision(block=False, score=score, reason="ok")
