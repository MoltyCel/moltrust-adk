"""Exception types for moltrust-adk."""

from __future__ import annotations

from typing import Optional


class MolTrustADKError(Exception):
    """Base class for all moltrust-adk errors (HTTP / transport / registry)."""


class AgentNotRegistered(MolTrustADKError):
    """Raised when a DID is unknown to the MolTrust registry (HTTP 404)."""

    def __init__(self, did: str):
        self.did = did
        super().__init__(f"Agent not registered with MolTrust: {did}")


class TrustCheckFailed(MolTrustADKError):
    """A verifiable trust check failed (score below ``min_score``).

    Not raised by the default interceptor flow — which blocks by returning an
    ADK ``Event`` — but exported for callers that prefer raise semantics.
    """

    def __init__(self, did: Optional[str], score: Optional[float], min_score: float):
        self.did = did
        self.score = score
        self.min_score = min_score
        super().__init__(
            f"Trust check failed for {did}: score {score} < min_score {min_score}"
        )
