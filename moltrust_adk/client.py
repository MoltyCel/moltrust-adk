"""Direct HTTP client for the MolTrust trust-score API.

The interceptor depends only on ``get_trust_score(did) -> Optional[float]``,
which reads the agent's **0-100 behavioral trust score** from
``GET /skill/trust-score/{did}``.

Tiers:
- **Tier 1 (keyless):** no API key needed — the endpoint serves scores without
  authentication (rate-limited). This is the default.
- **Tier 2 (free account):** pass ``api_key=...`` (or set ``MOLTRUST_API_KEY``)
  for higher rate limits. Sent as the ``X-API-Key`` header when present.

Every request carries ``User-Agent: moltrust-adk/<version>`` so MolTrust can
attribute API traffic to this framework integration.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

from .exceptions import AgentNotRegistered, MolTrustADKError
from . import __version__

DEFAULT_BASE_URL = "https://api.moltrust.ch"


class TrustClient:
    """Fetch a DID's MolTrust trust score (0-100) via ``/skill/trust-score/{did}``.

    Args:
        api_key: Optional MolTrust API key (Tier 2). Falls back to the
            ``MOLTRUST_API_KEY`` environment variable. If neither is set, runs
            keyless (Tier 1).
        base_url: API base URL (default ``https://api.moltrust.ch``).
        timeout: Per-request timeout in seconds.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
    ):
        # Optional by design: None => keyless Tier-1 mode.
        self._api_key = api_key or os.environ.get("MOLTRUST_API_KEY")
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout

    def get_trust_score(self, did: str) -> Optional[float]:
        """Return the agent's 0-100 trust score, or ``None`` if withheld/unscored.

        Returns ``None`` when the response has ``withheld == true`` or
        ``trust_score == null`` (a registered agent with no score yet).

        Raises:
            AgentNotRegistered: the DID is unknown to the registry (HTTP 404).
            MolTrustADKError: on any other HTTP / transport error.
        """
        url = f"{self._base_url}/skill/trust-score/{did}"
        headers = {"User-Agent": f"moltrust-adk/{__version__}"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        try:
            resp = requests.get(url, headers=headers, timeout=self._timeout)
        except requests.RequestException as exc:
            raise MolTrustADKError(f"MolTrust request failed for {did}: {exc}") from exc

        if resp.status_code == 404:
            raise AgentNotRegistered(did)
        if resp.status_code >= 400:
            raise MolTrustADKError(f"MolTrust returned HTTP {resp.status_code} for {did}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise MolTrustADKError(f"MolTrust returned non-JSON for {did}") from exc

        if data.get("withheld") or data.get("trust_score") is None:
            return None
        return float(data["trust_score"])
