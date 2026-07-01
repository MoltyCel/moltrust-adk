# moltrust-adk

Trust verification interceptor for **Google ADK** — gate outbound
Agent-to-Agent (A2A) calls on a target agent's **MolTrust trust score** using
ADK's `RequestInterceptor` hook.

When a `RemoteA2aAgent` is about to call a remote agent, this interceptor checks
the remote's 0–100 behavioral trust score at
`GET /skill/trust-score/{did}` and — in `block` mode — **aborts the call**
(returning an ADK `Event`) if the score is below your threshold.

## Install

```bash
pip install moltrust-adk
```

This pulls `google-adk[a2a]` (the A2A extra provides the `RemoteA2aAgent` /
`RequestInterceptor` machinery).

## Usage

```python
from google.adk.agents import RemoteA2aAgent
from google.adk.a2a.agent.config import A2aRemoteAgentConfig
from moltrust_adk import create_trust_interceptor

agent = RemoteA2aAgent(
    name="my-remote-agent",
    agent_card="https://example.com/.well-known/agent.json",
    config=A2aRemoteAgentConfig(
        request_interceptors=[
            create_trust_interceptor(
                did="did:moltrust:...",   # target remote agent's DID
                min_score=60,
                action="block",           # "block" | "warn" | "log"
            )
        ]
    ),
)
```

`create_trust_interceptor` returns an ADK `RequestInterceptor` whose
`before_request` hook runs before every A2A `send_message`.

## What it does

- **`block`** — if the target's score is `< min_score`, is withheld, or the
  agent is unregistered, the interceptor returns an `Event` and the remote call
  never happens (fail-closed). A high enough score passes the request through
  unchanged.
- **`warn`** / **`log`** — never blocks; emits a warning / info log on a
  negative check (dry-run / observability mode).
- **Fail-open on errors** — a MolTrust transport/registry hiccup allows the call
  (a monitoring dependency must not break your agent graph).

### Target identity (DID)

The outbound `A2AMessage` does not carry the remote's identity, so the target
`did` is supplied at wiring time (you know which remote you're calling).
Alternatively, pass `did_key="..."` to read it from `a2a_request.metadata[...]`.

## Tiers — keyless by default

- **Tier 1 (keyless):** no API key required (rate-limited). This is the default.
- **Tier 2 (free account):** pass `api_key=...` (or set `MOLTRUST_API_KEY`) for
  higher rate limits — sent as the `X-API-Key` header.

Every request carries `User-Agent: moltrust-adk/<version>` so MolTrust can
attribute traffic to this integration.

## Trust score vs. AGT

The **trust score** (0–100) is a *recomputable behavioral* signal — its on-chain
solvency component is independently verifiable at `/credits/solvency/{did}`. It
is **not** the AGT token; no token is required to read a score.

## ⚠️ Experimental

`RemoteA2aAgent` and the `RequestInterceptor` API are marked `@a2a_experimental`
in google-adk — the API may change between ADK releases. Pin your `google-adk`
version if you need stability.

## License

MIT — see [LICENSE](LICENSE).
