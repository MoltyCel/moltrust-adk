"""Mock-based tests. No real API calls.

The trust-decision logic (``evaluate_trust``) and the HTTP client
(``TrustClient``) are ADK-free and always tested here. The ``MolTrustInterceptor``
adapter is tested behind ``importorskip("google.adk.a2a.agent.config")`` — it
runs wherever ``google-adk[a2a]`` is installed (CI), and is skipped in a
minimal env.
"""

import asyncio
from types import SimpleNamespace
from unittest import mock

import pytest
import requests as _requests

from moltrust_adk import TrustClient, evaluate_trust
from moltrust_adk.exceptions import AgentNotRegistered, MolTrustADKError

DID = "did:moltrust:0123456789abcdef"


class FakeClient:
    """Stand-in for TrustClient; returns a preset score or raises."""

    def __init__(self, score=None, raises=None):
        self._score = score
        self._raises = raises

    def get_trust_score(self, did):
        if self._raises is not None:
            raise self._raises
        return self._score


# -- evaluate_trust: block mode -------------------------------------------

def test_low_score_blocks():
    d = evaluate_trust(FakeClient(score=42), DID, min_score=60, action="block")
    assert d.block is True and d.reason == "low_score" and d.score == 42


def test_high_score_allows():
    d = evaluate_trust(FakeClient(score=88), DID, min_score=60, action="block")
    assert d.block is False and d.reason == "ok" and d.score == 88


def test_score_equal_min_allows():
    assert evaluate_trust(FakeClient(score=60), DID, min_score=60, action="block").block is False


def test_withheld_blocks_in_block_mode():
    d = evaluate_trust(FakeClient(score=None), DID, min_score=60, action="block")
    assert d.block is True and d.reason == "withheld"


def test_unregistered_blocks_in_block_mode():
    d = evaluate_trust(FakeClient(raises=AgentNotRegistered(DID)), DID, action="block")
    assert d.block is True and d.reason == "unregistered"


def test_transport_error_fails_open():
    d = evaluate_trust(FakeClient(raises=MolTrustADKError("boom")), DID, action="block")
    assert d.block is False and d.reason == "lookup_error_failopen"


# -- evaluate_trust: no DID / warn / log ----------------------------------

def test_no_did_passes_by_default():
    assert evaluate_trust(FakeClient(score=0), None, action="block").block is False


def test_no_did_blocked_when_pass_without_did_false():
    d = evaluate_trust(FakeClient(score=0), None, action="block", pass_without_did=False)
    assert d.block is True and d.reason == "no_did"


def test_warn_mode_allows():
    assert evaluate_trust(FakeClient(score=5), DID, action="warn").block is False


def test_log_mode_allows():
    assert evaluate_trust(FakeClient(score=5), DID, action="log").block is False


def test_invalid_action_rejected():
    with pytest.raises(ValueError):
        evaluate_trust(FakeClient(), DID, action="nope")


# -- TrustClient HTTP (mocked /skill/trust-score, keyless + keyed) --------

class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


@mock.patch("moltrust_adk.client.requests.get")
def test_client_keyless_sends_no_api_key(mget, monkeypatch):
    monkeypatch.delenv("MOLTRUST_API_KEY", raising=False)
    mget.return_value = FakeResponse(200, {"trust_score": 70, "withheld": False})
    assert TrustClient().get_trust_score(DID) == 70.0
    args, kwargs = mget.call_args
    assert args[0].endswith(f"/skill/trust-score/{DID}")
    assert "X-API-Key" not in kwargs["headers"]  # Tier-1 keyless


@mock.patch("moltrust_adk.client.requests.get")
def test_client_with_key_sends_header(mget):
    mget.return_value = FakeResponse(200, {"trust_score": 70, "withheld": False})
    TrustClient(api_key="mt_test").get_trust_score(DID)
    assert mget.call_args.kwargs["headers"]["X-API-Key"] == "mt_test"


@mock.patch("moltrust_adk.client.requests.get")
def test_client_withheld_returns_none(mget):
    mget.return_value = FakeResponse(200, {"trust_score": None, "withheld": True})
    assert TrustClient(api_key="k").get_trust_score(DID) is None


@mock.patch("moltrust_adk.client.requests.get")
def test_client_404_raises_not_registered(mget):
    mget.return_value = FakeResponse(404, {})
    with pytest.raises(AgentNotRegistered):
        TrustClient(api_key="k").get_trust_score(DID)


@mock.patch("moltrust_adk.client.requests.get")
def test_client_http_error_raises(mget):
    mget.return_value = FakeResponse(500, {})
    with pytest.raises(MolTrustADKError):
        TrustClient(api_key="k").get_trust_score(DID)


@mock.patch("moltrust_adk.client.requests.get")
def test_client_network_error_raises(mget):
    mget.side_effect = _requests.RequestException("boom")
    with pytest.raises(MolTrustADKError):
        TrustClient(api_key="k").get_trust_score(DID)


# -- branded User-Agent (moltrust-adk/<version>) --------------------------

@mock.patch("moltrust_adk.client.requests.get")
def test_client_sends_branded_user_agent_keyless(mget, monkeypatch):
    monkeypatch.delenv("MOLTRUST_API_KEY", raising=False)
    mget.return_value = FakeResponse(200, {"trust_score": 70, "withheld": False})
    TrustClient().get_trust_score(DID)
    from moltrust_adk import __version__
    assert mget.call_args.kwargs["headers"]["User-Agent"] == f"moltrust-adk/{__version__}"


@mock.patch("moltrust_adk.client.requests.get")
def test_client_sends_branded_user_agent_with_key(mget):
    mget.return_value = FakeResponse(200, {"trust_score": 70, "withheld": False})
    TrustClient(api_key="mt_test").get_trust_score(DID)
    from moltrust_adk import __version__
    h = mget.call_args.kwargs["headers"]
    assert h["User-Agent"] == f"moltrust-adk/{__version__}"
    assert h["X-API-Key"] == "mt_test"


# -- MolTrustInterceptor adapter (requires google-adk[a2a]) ---------------

def _run(coro):
    return asyncio.run(coro)


def test_interceptor_blocks_low_score_returns_event():
    pytest.importorskip("google.adk.a2a.agent.config")
    from google.adk.events import Event
    from moltrust_adk import create_trust_interceptor

    ri = create_trust_interceptor(DID, min_score=60, action="block",
                                  client=FakeClient(score=10))
    ctx = SimpleNamespace(invocation_id="inv-1", branch=None)
    req = SimpleNamespace(metadata=None)
    params = SimpleNamespace()

    out, out_params = _run(ri.before_request(ctx, req, params))
    assert isinstance(out, Event)               # blocked -> Event
    assert out.author == "moltrust-trust-guardrail"
    assert out.invocation_id == "inv-1"
    assert out_params is params


def test_interceptor_high_score_passes_request_through():
    pytest.importorskip("google.adk.a2a.agent.config")
    from google.adk.events import Event
    from moltrust_adk import create_trust_interceptor

    ri = create_trust_interceptor(DID, min_score=60, action="block",
                                  client=FakeClient(score=95))
    ctx = SimpleNamespace(invocation_id="inv-2", branch=None)
    req = SimpleNamespace(metadata=None)
    params = SimpleNamespace()

    out, _ = _run(ri.before_request(ctx, req, params))
    assert out is req                            # allowed -> original request
    assert not isinstance(out, Event)


def test_interceptor_withheld_fail_closed_in_block_mode():
    pytest.importorskip("google.adk.a2a.agent.config")
    from google.adk.events import Event
    from moltrust_adk import create_trust_interceptor

    ri = create_trust_interceptor(DID, action="block", client=FakeClient(score=None))
    ctx = SimpleNamespace(invocation_id="i", branch=None)
    out, _ = _run(ri.before_request(ctx, SimpleNamespace(metadata=None), SimpleNamespace()))
    assert isinstance(out, Event)                # withheld -> blocked


def test_interceptor_warn_mode_allows_low_score():
    pytest.importorskip("google.adk.a2a.agent.config")
    from google.adk.events import Event
    from moltrust_adk import create_trust_interceptor

    ri = create_trust_interceptor(DID, min_score=60, action="warn",
                                  client=FakeClient(score=1))
    req = SimpleNamespace(metadata=None)
    out, _ = _run(ri.before_request(SimpleNamespace(invocation_id="i", branch=None),
                                    req, SimpleNamespace()))
    assert out is req and not isinstance(out, Event)


def test_interceptor_resolves_did_from_metadata():
    pytest.importorskip("google.adk.a2a.agent.config")
    from google.adk.events import Event
    from moltrust_adk import create_trust_interceptor

    # No static did; DID pulled from a2a_request.metadata[did_key].
    ri = create_trust_interceptor(min_score=60, action="block",
                                  did_key="target_did", client=FakeClient(score=5))
    req = SimpleNamespace(metadata={"target_did": DID})
    out, _ = _run(ri.before_request(SimpleNamespace(invocation_id="i", branch=None),
                                    req, SimpleNamespace()))
    assert isinstance(out, Event)                # resolved DID -> low score -> block


def test_invalid_action_rejected_at_construction():
    pytest.importorskip("google.adk.a2a.agent.config")
    from moltrust_adk import MolTrustInterceptor
    with pytest.raises(ValueError):
        MolTrustInterceptor(DID, action="nope")
