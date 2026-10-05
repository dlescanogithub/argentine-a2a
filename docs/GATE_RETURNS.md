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

Same allowlisted caller, switch open, then closed again.

| Request | HTTP | decision | fails |
| --- | --- | --- | --- |
| 1–10 | 200 | `GO` | `[]` |
| 11 | 429 | `NO_GO` | `["rate_limited"]` |

## Do not ship

A client that only reads `GET /health`, or only reads `decision`, does not ship.

`GET /health` stays HTTP 200 while the kill switch is closed and reports `diego_off`. The call is still HTTP 503 with `fails: ["diego_off"]`. A wrapper that stops at `decision` treats the allowlist cap as a policy reject and misses that `fails` names `rate_limited`.

## Cite

Moltbook reading of the same contract: https://www.moltbook.com/post/49e5d188-48f5-407b-89fe-39a1c0992317
