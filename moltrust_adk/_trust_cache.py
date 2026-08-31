"""Short-lived cache of successful trust lookups.

Its job is to keep a fail-closed gate from turning every registry hiccup into a
customer outage. Two windows:

* within ``ttl`` seconds of a successful lookup the cached score is returned
  without a network call at all;
* between ``ttl`` and ``stale_grace`` seconds, the cached score is still usable
  but only when the live lookup has just failed. The decision is then made on
  the stale score and the reason carries a ``_stale`` suffix, so it is visible
  in the caller's logs that the answer was not fresh.

Past ``stale_grace`` there is nothing to fall back on and the fail-open flag
decides.

Deliberately a plain dict with a size cap rather than a dependency: the entries
are tiny, the process is the only consumer, and a shared cache would need
invalidation rules the SDK has no way to honour.
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

DEFAULT_TTL_SECONDS = 60.0
DEFAULT_STALE_GRACE_SECONDS = 300.0
DEFAULT_MAX_ENTRIES = 1024


class TrustScoreCache:
    """Per-process TTL cache with a stale-read grace window."""

    def __init__(
        self,
        ttl: float = DEFAULT_TTL_SECONDS,
        stale_grace: float = DEFAULT_STALE_GRACE_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
    ) -> None:
        if ttl < 0 or stale_grace < 0:
            raise ValueError("ttl and stale_grace must not be negative")
        self.ttl = ttl
        self.stale_grace = stale_grace
        self.max_entries = max(1, max_entries)
        # did -> (score, stored_at_monotonic)
        self._entries: dict[str, Tuple[Optional[float], float]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def put(self, did: str, score: Optional[float]) -> None:
        """Record a successful lookup. ``score`` may be None (withheld)."""
        if len(self._entries) >= self.max_entries and did not in self._entries:
            # Drop the oldest entry. The cap exists so a stream of junk DIDs
            # cannot grow the process; eviction order is not load-bearing.
            oldest = min(self._entries, key=lambda k: self._entries[k][1])
            self._entries.pop(oldest, None)
        self._entries[did] = (score, self._now())

    def get_fresh(self, did: str) -> Tuple[bool, Optional[float]]:
        """(hit, score) for an entry still inside the TTL."""
        if self.ttl <= 0:
            return False, None  # always look up live
        entry = self._entries.get(did)
        if entry is None:
            return False, None
        score, stored_at = entry
        if self._now() - stored_at <= self.ttl:
            return True, score
        return False, None

    def get_stale(self, did: str) -> Tuple[bool, Optional[float]]:
        """(hit, score) for an entry inside the grace window.

        Only for use after a live lookup has failed.
        """
        if self.stale_grace <= 0:
            return False, None  # grace disabled
        entry = self._entries.get(did)
        if entry is None:
            return False, None
        score, stored_at = entry
        if self._now() - stored_at <= self.stale_grace:
            return True, score
        self._entries.pop(did, None)
        return False, None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
