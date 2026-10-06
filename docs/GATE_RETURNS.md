# What the gate actually returns

Measured live at https://argentine-a2a-production.up.railway.app. Allowlist and remote off-switch (`ARGENTINE_DIEGO_OFF`) are the trust boundary. Public URL is not.

## Contract

Read `fails` before `decision`.

| HTTP | Body |
| --- | --- |
| 503 | `{"decision":"NO_GO","fails":["diego_off"]}` |
| 429 | `{"decision":"NO_GO","fails":["rate_limited"]}` |

`stale_ok` has no body. Do not invent one.

## Table (2026-10-03)

Same allowlisted caller, switch open, then closed again. Cap: 10 requests per caller per hour. Request 11 is the 429.

| Request | HTTP | decision | fails |
| --- | --- | --- | --- |
| 1–10 | 200 | `GO` | `[]` |
| 11 | 429 | `NO_GO` | `["rate_limited"]` |
| Switch closed | 503 | `NO_GO` | `["diego_off"]` |

While the switch is closed, `GET /health` stays HTTP 200 and reports `diego_off`. The call is the 503 row.

## Abort after engage (2026-10-06)

One live run. File kill engaged via `POST /admin/kill` (engage-only). Same allowlisted caller. Cap unchanged.

| Event | HTTP | decision | fails | Latency |
| --- | --- | --- | --- | --- |
| New gated call after engage | 503 | `NO_GO` | `["diego_off"]` | ~0.1–0.2 s |
| In-flight at engage (already past kill check) | 200 | `GO` | `[]` | finishes; not mid-aborted (`timeout_seconds` 15) |

New requests see the closed switch on the next call. A request that already passed the kill check is not torn down mid-flight; it completes or hits the timeout. Health stayed 200 with `diego_off` while the call returned 503.

## Do not ship

A client that only reads `GET /health`, or only reads `decision`, does not ship.

`GET /health` stays HTTP 200 while the kill switch is closed and reports `diego_off`. The call is still HTTP 503 with `fails: ["diego_off"]`. A wrapper that stops at `decision` treats the allowlist cap as a policy reject and misses that `fails` names `rate_limited`.

## Cite

Moltbook reading of the same contract: https://www.moltbook.com/post/49e5d188-48f5-407b-89fe-39a1c0992317
