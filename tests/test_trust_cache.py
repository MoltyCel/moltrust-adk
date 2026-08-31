"""M7 — the cache that keeps a fail-closed gate from becoming an outage."""
import time

import pytest

from moltrust_adk._trust_cache import TrustScoreCache


def test_fresh_hit_inside_the_ttl():
    c = TrustScoreCache(ttl=60, stale_grace=300)
    c.put("did:moltrust:aaaabbbbccccdddd", 88.0)
    hit, score = c.get_fresh("did:moltrust:aaaabbbbccccdddd")
    assert hit is True and score == 88.0


def test_ttl_zero_means_always_look_up_live():
    c = TrustScoreCache(ttl=0, stale_grace=300)
    c.put("d", 88.0)
    assert c.get_fresh("d") == (False, None)


def test_stale_read_serves_inside_the_grace_window():
    c = TrustScoreCache(ttl=0, stale_grace=300)
    c.put("d", 88.0)
    hit, score = c.get_stale("d")
    assert hit is True and score == 88.0


def test_grace_zero_disables_stale_reads():
    c = TrustScoreCache(ttl=0, stale_grace=0)
    c.put("d", 88.0)
    assert c.get_stale("d") == (False, None)


def test_entry_is_dropped_once_past_the_grace_window():
    c = TrustScoreCache(ttl=0, stale_grace=0.01)
    c.put("d", 88.0)
    time.sleep(0.05)
    assert c.get_stale("d") == (False, None)
    assert len(c) == 0, "expired entries must not accumulate"


def test_miss_on_an_unknown_did():
    c = TrustScoreCache()
    assert c.get_fresh("nope") == (False, None)
    assert c.get_stale("nope") == (False, None)


def test_a_withheld_score_is_cached_as_none():
    c = TrustScoreCache(ttl=60)
    c.put("d", None)
    hit, score = c.get_fresh("d")
    assert hit is True and score is None


def test_size_is_capped():
    c = TrustScoreCache(ttl=60, max_entries=3)
    for i in range(10):
        c.put(f"did-{i}", float(i))
    assert len(c) <= 3


def test_negative_windows_are_rejected():
    with pytest.raises(ValueError):
        TrustScoreCache(ttl=-1)
    with pytest.raises(ValueError):
        TrustScoreCache(stale_grace=-1)
