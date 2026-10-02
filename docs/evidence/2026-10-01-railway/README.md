# ArGENTine evidence pack — 2026-10-01 Railway

Canonical citeable export after the public origin cut over to Railway. The Fly export in `docs/evidence/2026-10-01/` stays as the historical pack. Its files and hashes are unchanged.

Collected 2026-10-01 21:01:12 ART (2026-10-02T00:01:12Z). Clock is the `Date` header on `GET /health`.

## What a reviewer can verify

1. Open `SUMMARY.json` for the export clock, the intentional off-switch, the partner caller id, the human_reject addendum, and the commit pointer.
2. Re-hash files with `sha256sum -c SHA256SUMS`. Checksums in this directory include the human_reject addendum. The historical Fly pack hashes are unchanged.
3. Compare `git_commit_at_export` to https://github.com/dlescanogithub/argentine-a2a/commit/7591860bb28b809e70588eb69cf2f341c1dc6c25. That value is the repository HEAD when the 21:01 ART export was collected. `GET /health` does not return a git SHA. The human_reject file is a later addendum; cite the git commit that adds it as the record of those bytes.
4. Re-fetch `GET /health` and `GET /.well-known/agent-card.json`. The card's interface URL in this pack is `https://argentine-a2a-production.up.railway.app`. At the 21:01 ART export, and again after the human_reject drill, `diego_off` was true on purpose. The drill file records `diego_off` false immediately before that call.

## Switch and kill path

`health.json` is the raw `GET /health` body: HTTP 200, `ok` true, `diego_off` true. Health stays HTTP 200 while the switch is engaged so the platform check does not restart-loop.

Kill path, read on every request:

- Environment variable `ARGENTINE_DIEGO_OFF` (`1`, `true`, `yes`, or `on`).
- Flag file `/data/diego.off`.

The 21:01 ART export did not engage or clear the switch. The Fly kill drill (off, then HTTP 503 `diego_off`, then restore open) remains the historical report, restore complete 2026-09-30 23:32 ART. The human_reject addendum records a later Railway window: switch open, partner `NO_GO`, then `diego_off` true again.

`public-probes.json` records unauthenticated calls at this export. No allowlist token was sent. `GET /v1/gate/stats` and `POST /v1/gate` with an empty JSON object returned HTTP 503 `{"decision":"NO_GO","fails":["diego_off"]}`. While the switch is engaged, those routes return `diego_off` before the allowlist is checked. The empty POST is that response. It is not a partner decision.

## Partner caller

Caller id: `partner`. The token is not in this directory.

`partner-decisions.json` is the parent-provided capture from 2026-10-01T21:15:05+00:00 (2026-10-01 18:15:05 ART), against `https://argentine-a2a-production.up.railway.app/v1/gate`, while the switch was open:

| Case | HTTP | Decision | Fails |
| --- | --- | --- | --- |
| go | 200 | GO | (none) |
| need-human | 200 | NEED_HUMAN | hitl, approved_until, digest, kill_path |

Authenticated stats in that capture: HTTP 200, `human_reject` 0, `decisions` 11. The ratio `0/11` is those two counts. The capture object has no `ratio` field. The 21:01 ART export sent no new authenticated POST, because the switch was off. Those `GO` and `NEED_HUMAN` rows stay in this pack.

## Human reject (2026-10-02 UTC)

`human-reject-2026-10-02.json` is the partner human_reject drill. Caller id `partner`. Timestamp `2026-10-02T00:48:56.560887+00:00` (2026-10-01 21:48:56 ART). No bearer token and no allowlist JSON are in the file.

| Step | Clock | Result |
| --- | --- | --- |
| Health before the call | recorded in the drill artifact | `ok` true, `diego_off` false |
| Decision | 2026-10-02T00:48:56.560887+00:00 | HTTP 200 `NO_GO`; fails `hitl`, `egress`, `kill_path`, `least_privilege`, `side_effects` |
| Authenticated stats after the call | same artifact | HTTP 200, `human_reject=1`, `decisions=28`, `ratio=1/28` |
| Health after Diego shut the gate | 2026-10-02T00:52:12Z (`Date` header `Fri, 02 Oct 2026 00:52:12 GMT`, 2026-10-01 21:52:12 ART) | HTTP 200, `ok` true, `diego_off` true |

`diego_off` restored true. That later health body is the public `GET /health` snapshot after the drill. The switch is engaged on purpose. The sequence is on, then human_reject, then off.

The earlier partner capture stays `0/11`. This addendum is the Railway-era `human_reject` row.

## Registry

`registry-listing.json` records `GET https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582` at this export. The listing names the Railway origin. The page did not mention `argentine-a2a.fly.dev`.

## Trust notes

- No allowlist token, bearer header, or secret value is in this directory.
- The gate log from the Fly host is not copied here. Brief plaintext is not in the partner capture or the human_reject addendum.
- Public URL is not the trust boundary. Allowlist and the off-switch are.

## Files

| File | Role |
| --- | --- |
| `health.json` | Raw `GET /health` body at export |
| `agent-card.live.json` | Raw `GET /.well-known/agent-card.json` body at export |
| `partner-decisions.json` | Partner caller capture (id `partner` only), 2026-10-01T21:15:05Z: `GO` and `NEED_HUMAN`, stats `0/11` |
| `human-reject-2026-10-02.json` | Partner human_reject drill, 2026-10-02T00:48:56Z: `NO_GO`, stats `1/28`, health on then off |
| `public-probes.json` | Unauthenticated health, stats, and empty POST while the switch was off |
| `registry-listing.json` | Public registry listing observation |
| `SUMMARY.json` | Counts, clocks (ART), commit pointer |
| `SHA256SUMS` | Per-file SHA-256 |
| `MANIFEST.json` | Machine-readable attestation |

Signing method: SHA-256 manifest plus git commit (no PGP). From this directory, `sha256sum -c SHA256SUMS` checks every file named in that list. The SHA-256 of `SHA256SUMS` stored in `MANIFEST.json` is the checksum file before the `MANIFEST.json` line was appended, same method as the historical Fly pack.
