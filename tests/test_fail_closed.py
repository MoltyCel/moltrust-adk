"""M7 — lookup errors deny by default; opt-out and cache are the release valves."""
import pytest

from moltrust_adk._policy import evaluate_trust
from moltrust_adk._trust_cache import TrustScoreCache
from moltrust_adk.exceptions import AgentNotRegistered, MolTrustADKError

DID = "did:moltrust:aaaabbbbccccdddd"


class _Client:
    def __init__(self, behaviour):
        self.behaviour = behaviour
        self.calls = 0

    def get_trust_score(self, did):
        self.calls += 1
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return self.behaviour


def test_lookup_error_now_blocks(monkeypatch):
    monkeypatch.delenv("MOLTRUST_FAIL_OPEN", raising=False)
    d = evaluate_trust(_Client(MolTrustADKError("registry down")), DID)
    assert d.block is True
    assert d.reason == "lookup_error_failclosed"


def test_opt_out_restores_the_old_behaviour(monkeypatch):
    monkeypatch.delenv("MOLTRUST_FAIL_OPEN", raising=False)
    d = evaluate_trust(_Client(MolTrustADKError("registry down")), DID, fail_open=True)
    assert d.block is False
    assert d.reason == "lookup_error_failopen"


def test_env_var_opts_out_without_a_code_change(monkeypatch):
    monkeypatch.setenv("MOLTRUST_FAIL_OPEN", "1")
    d = evaluate_trust(_Client(MolTrustADKError("registry down")), DID)
    assert d.block is False


def test_explicit_argument_beats_the_env_var(monkeypatch):
    monkeypatch.setenv("MOLTRUST_FAIL_OPEN", "1")
    d = evaluate_trust(_Client(MolTrustADKError("down")), DID, fail_open=False)
    assert d.block is True


def test_a_brief_outage_rides_on_the_cached_score(monkeypatch):
    monkeypatch.delenv("MOLTRUST_FAIL_OPEN", raising=False)
    cache = TrustScoreCache(ttl=0, stale_grace=300)
    cache.put(DID, 90.0)

    d = evaluate_trust(_Client(MolTrustADKError("down")), DID, cache=cache)
    assert d.block is False
    assert d.reason == "ok_cached_stale"


def test_a_stale_score_is_still_measured_against_the_threshold(monkeypatch):
    monkeypatch.delenv("MOLTRUST_FAIL_OPEN", raising=False)
    cache = TrustScoreCache(ttl=0, stale_grace=300)
    cache.put(DID, 10.0)

    d = evaluate_trust(_Client(MolTrustADKError("down")), DID, min_score=60, cache=cache)
    assert d.block is True
    assert d.reason == "low_score_cached_stale"


def test_a_fresh_cache_entry_skips_the_lookup():
    cache = TrustScoreCache(ttl=60, stale_grace=300)
    cache.put(DID, 90.0)
    client = _Client(90.0)

    d = evaluate_trust(client, DID, cache=cache)
    assert d.block is False
    assert client.calls == 0, "a fresh entry must not hit the network"


def test_a_successful_lookup_populates_the_cache():
    cache = TrustScoreCache(ttl=60)
    evaluate_trust(_Client(90.0), DID, cache=cache)
    hit, score = cache.get_fresh(DID)
    assert hit is True and score == 90.0


def test_unregistered_still_blocks_regardless_of_fail_open():
    d = evaluate_trust(_Client(AgentNotRegistered(DID)), DID, fail_open=True)
    assert d.block is True
    assert d.reason == "unregistered"


def test_low_score_still_blocks():
    d = evaluate_trust(_Client(10.0), DID, min_score=60)
    assert d.block is True
    assert d.reason == "low_score"


def test_warn_action_never_blocks():
    d = evaluate_trust(_Client(10.0), DID, min_score=60, action="warn")
    assert d.block is False
