"""Trust-decision logic — ADK-free and fully unit-testable.

Mirrors the semantics of the sibling ``moltrust-crewai`` / ``moltrust-langchain``
guardrails so behaviour is identical across frameworks.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from .client import TrustClient
from .exceptions import AgentNotRegistered, MolTrustADKError
from ._trust_cache import TrustScoreCache

logger = logging.getLogger("moltrust_adk")

_ACTIONS = ("block", "warn", "log")


def _decide(
    score: Optional[float], min_score: float, action: str, reason_suffix: str
) -> "Decision":
    """Turn a score that came from the cache into a Decision."""
    if score is None:
        return Decision(block=(action == "block"), score=None, reason=f"withheld_{reason_suffix}")
    if score < min_score:
        return Decision(block=(action == "block"), score=score, reason=f"low_score_{reason_suffix}")
    return Decision(block=False, score=score, reason=f"ok_{reason_suffix}")


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
    fail_open: Optional[bool] = None,
    cache: Optional["TrustScoreCache"] = None,
) -> Decision:
    """Evaluate a target DID's trust and decide whether to block.

    Fail-**closed** on registry/transport errors as of 0.2.0 — a gate that
    opens when the registry is unreachable is not a gate. Two things keep that
    from turning a hiccup into an outage:

    * ``cache`` serves a recent score without a network call, and serves a
      slightly older one when the live lookup has just failed (reason gains a
      ``_stale`` suffix);
    * ``fail_open=True`` (or ``MOLTRUST_FAIL_OPEN=1`` in the environment)
      restores the old behaviour per integration.

    Fail-closed on an authoritative negative (low score, withheld,
    unregistered) when ``action="block"`` is unchanged.
    """
    if fail_open is None:
        fail_open = os.getenv("MOLTRUST_FAIL_OPEN", "").strip().lower() in {"1", "true", "yes"}
    if action not in _ACTIONS:
        raise ValueError(f"action must be one of {_ACTIONS}, got {action!r}")

    if not did:
        # Nothing to verify. Block only if explicitly required.
        return Decision(
            block=(action == "block") and (not pass_without_did),
            score=None,
            reason="no_did",
        )

    if cache is not None:
        hit, cached = cache.get_fresh(did)
        if hit:
            return _decide(cached, min_score, action, "cached")

    try:
        score = client.get_trust_score(did)
    except AgentNotRegistered:
        return Decision(block=(action == "block"), score=None, reason="unregistered")
    except MolTrustADKError as exc:
        if cache is not None:
            hit, cached = cache.get_stale(did)
            if hit:
                logger.warning(
                    "MolTrust: lookup failed for %s (%s); using cached score", did, exc
                )
                return _decide(cached, min_score, action, "cached_stale")
        if fail_open:
            logger.warning(
                "MolTrust: lookup failed for %s (%s); allowing (fail_open)", did, exc
            )
            return Decision(block=False, score=None, reason="lookup_error_failopen")
        logger.warning(
            "MolTrust: lookup failed for %s (%s); blocking (fail_closed)", did, exc
        )
        return Decision(block=True, score=None, reason="lookup_error_failclosed")

    if cache is not None:
        cache.put(did, score)

    if score is None:
        return Decision(block=(action == "block"), score=None, reason="withheld")
    if score < min_score:
        return Decision(block=(action == "block"), score=score, reason="low_score")
    return Decision(block=False, score=score, reason="ok")
