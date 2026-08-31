# Changelog

## 0.2.0 — 2026-08-31

### Changed — behaviour, not API (read before upgrading)

**A failed trust lookup now denies instead of allowing.**

Until 0.1.x, a registry or transport error returned `lookup_error_failopen` and
let the call through. A gate that opens when the registry is unreachable does
not gate anything, so the default is now to deny with
`lookup_error_failclosed`.

Nothing in the signature changed and no call site has to be touched. What
changes is what happens during an outage: previously every agent passed, now
every agent is refused unless one of the two release valves applies.

**Two release valves.**

1. A short cache. A successful lookup is reused for `cache_ttl` seconds
   (default 60) with no network call. If a live lookup then fails, a score up
   to `cache_stale_grace` seconds old (default 300) is still used and the
   decision is made on it — the reason gains a `_cached_stale` suffix so it is
   visible in the logs that the answer was not fresh. A registry blip of a few
   minutes therefore changes nothing for agents that were seen recently.

2. Per-integration opt-out:

   ```python
   MolTrustInterceptor(..., fail_open=True)
   ```

   or, without a code change, `MOLTRUST_FAIL_OPEN=1` in the environment. The
   explicit argument wins over the environment variable.

### Migration

- Upgrading and doing nothing gets you fail-closed. Decide whether that is what
  you want **before** deploying: during a MolTrust outage your agents stop
  rather than continue.
- If continuity matters more than enforcement for your integration, set
  `fail_open=True` at construction and keep it in code review rather than in
  the environment.
- The cache is per process. A fleet that restarts often gets less benefit from
  it; raise `cache_stale_grace` if that matters.
- Authoritative negatives are unchanged: unregistered agents and scores below
  the threshold blocked before and block now, and `fail_open` does not affect
  them.

## 0.1.x

Initial releases. Lookup errors allowed the call through.
