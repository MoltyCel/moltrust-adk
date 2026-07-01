"""moltrust-adk — trust verification interceptor for Google ADK (A2A).

Gate outbound Agent-to-Agent calls made by ``RemoteA2aAgent`` on a target
agent's MolTrust trust score, using ADK's ``RequestInterceptor`` hook::

    from google.adk.agents import RemoteA2aAgent
    from google.adk.a2a.agent.config import A2aRemoteAgentConfig
    from moltrust_adk import create_trust_interceptor

    agent = RemoteA2aAgent(
        name="my-remote-agent",
        agent_card="https://example.com/.well-known/agent.json",
        config=A2aRemoteAgentConfig(
            request_interceptors=[create_trust_interceptor(did="did:moltrust:...", min_score=60)]
        ),
    )

``MolTrustInterceptor`` / ``create_trust_interceptor`` are imported lazily so the
trust-policy logic and HTTP client can be imported and unit-tested without
``google-adk`` (and its ``a2a`` extra) installed.
"""

__version__ = "0.1.0"

from .client import TrustClient
from .exceptions import (
    MolTrustADKError,
    AgentNotRegistered,
    TrustCheckFailed,
)
from ._policy import Decision, evaluate_trust

__all__ = [
    "MolTrustInterceptor",
    "create_trust_interceptor",
    "TrustClient",
    "Decision",
    "evaluate_trust",
    "MolTrustADKError",
    "AgentNotRegistered",
    "TrustCheckFailed",
    "__version__",
]


def __getattr__(name: str):  # PEP 562 — lazy import of the ADK-dependent adapter
    if name in ("MolTrustInterceptor", "create_trust_interceptor"):
        from . import interceptor

        return getattr(interceptor, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
