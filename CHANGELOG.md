# Changelog

All notable changes to `moltrust-adk` are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-07-01

Initial release.

### Added
- `MolTrustInterceptor` / `create_trust_interceptor` — an ADK
  `RequestInterceptor` (verified against google/adk-python@main) that gates
  outbound `RemoteA2aAgent` A2A calls on a target agent's MolTrust trust score.
  - `before_request` returns a blocking `Event` in `action="block"` when the
    score is `< min_score`, withheld, or the agent is unregistered; passes the
    request through otherwise.
  - `action` modes: `block` | `warn` | `log`. Fails open on transport/registry
    errors. Target DID supplied at wiring time or read from
    `a2a_request.metadata[did_key]`.
- `evaluate_trust` / `Decision` — ADK-free trust-decision logic (fully
  unit-testable).
- `TrustClient` — keyless-by-default HTTP client for
  `GET /skill/trust-score/{did}` (0–100 `trust_score`; `None` when withheld).
  Tier-2 `X-API-Key` sent only when a key is provided. Sends
  `User-Agent: moltrust-adk/<version>`.
