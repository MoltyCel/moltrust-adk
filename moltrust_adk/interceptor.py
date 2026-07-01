"""ADK ``RequestInterceptor`` adapter — the trust gate for outbound A2A calls.

Verified against google/adk-python@main:
- ``RequestInterceptor.before_request(ctx, a2a_request, params)`` returns
  ``tuple[Union[A2AMessage, Event], ParametersConfig]`` — returning an ``Event``
  aborts the request and yields that Event to the caller
  (``a2a/agent/utils.execute_before_request_interceptors`` +
  ``agents/remote_a2a_agent.py``: ``if isinstance(a2a_request, Event): yield ...; return``).

Importing this module requires ``google-adk[a2a]`` (the ``a2a`` extra pulls
``a2a-sdk``, which ``google.adk.a2a.agent.config`` imports at module load).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from google.adk.a2a.agent.config import ParametersConfig, RequestInterceptor
from google.adk.events import Event
from google.genai import types as genai_types

from ._policy import evaluate_trust
from .client import TrustClient

logger = logging.getLogger("moltrust_adk")

# Author stamped on the synthetic Event returned when a call is blocked.
_BLOCK_AUTHOR = "moltrust-trust-guardrail"


class MolTrustInterceptor:
    """Builds an ADK ``RequestInterceptor`` that gates A2A calls on trust.

    The target agent's ``did`` is supplied at wiring time (it is *not* carried
    by the outbound ``A2AMessage``); optionally, when ``did`` is omitted, it is
    read from ``a2a_request.metadata[did_key]``.

    Args:
        did: Target remote agent's MolTrust DID (primary source of identity).
        min_score: Minimum acceptable 0-100 trust score (inclusive).
        action: ``"block"`` (return a blocking Event), ``"warn"`` (allow + warn
            log), or ``"log"`` (allow + info log).
        client: Optional preconstructed :class:`TrustClient`.
        api_key / base_url: Forwarded to a new :class:`TrustClient` when
            ``client`` is not given.
        did_key: Metadata key to read the DID from when ``did`` is None.
        pass_without_did: When no DID is resolvable, allow (True) or block
            (False, only in ``action="block"``).
    """

    def __init__(
        self,
        did: Optional[str] = None,
        *,
        min_score: float = 60,
        action: str = "block",
        client: Optional[TrustClient] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        did_key: Optional[str] = None,
        pass_without_did: bool = True,
    ):
        if action not in ("block", "warn", "log"):
            raise ValueError(
                f"action must be 'block' | 'warn' | 'log', got {action!r}"
            )
        self._did = did
        self._min_score = min_score
        self._action = action
        self._client = client or TrustClient(api_key=api_key, base_url=base_url)
        self._did_key = did_key
        self._pass_without_did = pass_without_did

    def _resolve_did(self, a2a_request: Any) -> Optional[str]:
        if self._did:
            return self._did
        if self._did_key:
            metadata = getattr(a2a_request, "metadata", None) or {}
            try:
                return metadata.get(self._did_key)
            except AttributeError:
                return None
        return None

    async def before_request(self, ctx, a2a_request, params):
        """ADK ``before_request`` hook. Returns ``(Event, params)`` to block or
        ``(a2a_request, params)`` to allow."""
        did = self._resolve_did(a2a_request)
        decision = evaluate_trust(
            self._client,
            did,
            min_score=self._min_score,
            action=self._action,
            pass_without_did=self._pass_without_did,
        )

        if decision.block:
            logger.warning(
                "MolTrust BLOCKED A2A request (did=%s, reason=%s, score=%s)",
                did, decision.reason, decision.score,
            )
            return self._block_event(ctx, did, decision), params

        # allowed — but surface a warn/log line when the check was negative
        if decision.reason not in ("ok", "no_did") and self._action in ("warn", "log"):
            emit = logger.warning if self._action == "warn" else logger.info
            emit(
                "MolTrust %s: A2A request ALLOWED despite %s (did=%s, score=%s)",
                self._action, decision.reason, did, decision.score,
            )
        return a2a_request, params

    def _block_event(self, ctx, did, decision) -> Event:
        message = (
            f"Request blocked by MolTrust trust guardrail: target agent "
            f"{did or '<unknown>'} did not pass the trust check "
            f"(reason={decision.reason}, score={decision.score}, "
            f"min_score={self._min_score})."
        )
        return Event(
            author=_BLOCK_AUTHOR,
            invocation_id=getattr(ctx, "invocation_id", "") or "",
            branch=getattr(ctx, "branch", None),
            content=genai_types.Content(
                role="model",
                parts=[genai_types.Part(text=message)],
            ),
        )

    def as_request_interceptor(self) -> RequestInterceptor:
        """Return an ADK ``RequestInterceptor`` wrapping this instance."""
        return RequestInterceptor(before_request=self.before_request)


def create_trust_interceptor(
    did: Optional[str] = None,
    *,
    min_score: float = 60,
    action: str = "block",
    client: Optional[TrustClient] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    did_key: Optional[str] = None,
    pass_without_did: bool = True,
) -> RequestInterceptor:
    """Convenience factory: build a ready-to-wire ADK ``RequestInterceptor``.

    Pass the result into ``A2aRemoteAgentConfig(request_interceptors=[...])``.
    """
    return MolTrustInterceptor(
        did,
        min_score=min_score,
        action=action,
        client=client,
        api_key=api_key,
        base_url=base_url,
        did_key=did_key,
        pass_without_did=pass_without_did,
    ).as_request_interceptor()
