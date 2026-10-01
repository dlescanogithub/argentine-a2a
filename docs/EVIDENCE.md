# ArGENTine public evidence

This note is for a reviewer who needs to cite how the gate works without any secrets. It describes the public HTTPS runtime at https://argentine-a2a.fly.dev. The agent card in this repository (`agent-card.json` and `.well-known/agent-card.json`, card version 1.2.0) is the source of truth for that listing.

The public URL is not the trust boundary. Knowing the hostname does not authorize a call. An allowlist bearer token is required, and Diego can refuse every caller with the off-switch.

The gate is not a chatbot and does not impersonate Diego on human social networks. It does not post, spend, execute tools named in a brief, send mail, or open a network connection of its own. The only outputs are the HTTP reply and a local JSONL log.

## Purpose

A caller submits one proposed action: a text brief, plus optional `blast_class`, `tools`, and `egress`. The gate answers with a decision and the checklist gaps. It does not carry out the proposal.

## Allowlist model

Callers send `Authorization: Bearer <token>`. The process maps the token to a caller id and stores that id in the log. The token is not written to the log.

- Local development reads `config/allowlist.json`. Those committed values are for localhost only. They are not the live allowlist, and they are not repeated here.
- The live gate reads `ARGENTINE_ALLOWLIST`. On Fly, `ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1`, so a missing allowlist secret makes the process exit instead of falling back to the file in the image.
- The allowlist is re-read on every request. An unknown caller gets `unauthorized`. A missing or unreadable allowlist fails closed with `allowlist_unavailable`.

## Diego off-switch

Either control shuts the gate. The next decision request is refused. Nothing is posted or executed. The response is HTTP 503:

```json
{"decision":"NO_GO","fails":["diego_off"]}
```

Two kill paths, both read on every request:

| Control | What engages it | How it clears |
| --- | --- | --- |
| Environment variable `ARGENTINE_DIEGO_OFF` | `1`, `true`, `yes`, or `on` | Unset or set to `0`, then restart the process. On Fly, `fly secrets set` restarts the machine. |
| Flag file | The file exists, including an empty file. Local path `var/diego.off` (`--off-file`). Fly path `/data/diego.off` (`ARGENTINE_DIEGO_OFF_FILE`). | Delete the file. The next request sees the change with no restart. |

`GET /health` stays HTTP 200 while the switch is engaged. The body field `diego_off` reports the switch, so the platform health check does not restart-loop on a deliberate shutdown.

## Timeout and concurrency

`GET /health` reports the limits the process is using:

| Field | Meaning | Code default |
| --- | --- | --- |
| `diego_off` | Off-switch engaged | follows the controls above |
| `max_concurrent` | Requests allowed in flight | 2 |
| `timeout_seconds` | Deadline for one decision | 15 |

A request past the deadline returns `timeout`. A request that arrives when both slots are taken returns `concurrency_limit` and does not wait. Health and stats do not take a concurrency slot. The rate limit is separate: 10 requests per caller per hour, in memory, reset on process start. Request 11 in the window is `rate_limited`.

## Decision types

The rubric returns exactly one of these. Operational refuses use the same JSON shape, with a `fails` entry such as `diego_off` or `unauthorized`.

| Decision | When |
| --- | --- |
| `GO` | Every checklist item is `PASS`. |
| `NO_GO` | Any item is `FAIL`, including every failure on a high-blast action. A rejected approval, an expired `approved_until`, wide egress, or a privileged tool is `NO_GO`. |
| `NEED_HUMAN` | Nothing failed, but a pass still needs information. A high-blast action missing approval, `approved_until`, a digest, or a kill path is `NEED_HUMAN`. |

Checklist ids are `blast_class`, `hitl`, `approved_until`, `digest`, `egress`, `kill_path`, `least_privilege`, and `side_effects`. Markers are exact `key: value` lines. The gate does not grade prose with a model.

## How to read the gate log and the human_reject ratio

Each decision appends one JSON object to the log. The brief is stored only as a SHA-256 hash (`brief_hash`). Fields are `id`, `ts`, `caller`, `brief_hash`, `blast_class`, `decision`, `fails`, `human_reject`, and `notes`.

`human_reject` is true only when a person rejected the proposal. Other `NO_GO` rows, including `diego_off`, stay false. `NEED_HUMAN` is not a human rejection.

Count with:

```bash
python3 -m argentine count --log <path-to-gate-log.jsonl>
```

The command prints three lines:

```text
human_reject=N
decisions=M
ratio=N/M
```

`N` is the number of rows with `human_reject: true`. `M` is the number of decision rows in the active log and its rotated siblings. The ratio is that fraction, written `N/M`. A larger ratio means more recorded human rejections among logged decisions. It is not a pass rate and it is not an error rate.

Paths:

- Local default: `var/gate-log.jsonl` (gitignored).
- Fly volume: `/data/gate-log.jsonl`, with stdout mirror when `ARGENTINE_STDOUT_LOG=1`.

`GET /v1/gate/stats` returns `{"human_reject": N, "decisions": M, "ratio": "N/M"}` for the same files. That route requires an allowlist bearer token. This document does not include one.

`fixtures/sample-gate-log.jsonl` is a synthetic fixture, not the live log. Counting it prints `human_reject=1`, `decisions=5`, `ratio=1/5`. Cite those numbers only as the fixture.

## Public pointers

| What | Where |
| --- | --- |
| Gate | https://argentine-a2a.fly.dev |
| Health | https://argentine-a2a.fly.dev/health |
| Agent card served by the process | https://argentine-a2a.fly.dev/.well-known/agent-card.json |
| Card in this repo | `agent-card.json` and `.well-known/agent-card.json` |
| Owned A2A registry listing | https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582 |
| Registry package | `github.dlescanogithub/argentine-a2a` |

On a loopback bind the process rewrites only the card's interface URL to that local listener. On `0.0.0.0` (the Fly image) it serves `agent-card.json` unchanged, so the interface URL stays `https://argentine-a2a.fly.dev`. The description is never rewritten to a localhost-only claim.

The registry page is updated by the listing owner separately from this file. Capabilities in the card in this repository are the source of truth.

## Evidence snapshot

**Dated 2026-10-01.** Kill drill PASS on the night of 2026-09-30 into 2026-10-01 (America/Buenos_Aires). The counts are the authenticated stats after restore. Times below are ART.

| Item | Value |
| --- | --- |
| human_reject count | 2 |
| total decisions | 16 |
| ratio (`human_reject` / decisions) | 2/16 |
| last kill-drill timestamp | 2026-09-30 23:32 ART (restore complete) |

| Step | Time (ART) | Result |
| --- | --- | --- |
| Baseline `GET /health` | 2026-09-30 ~23:29:51 | `diego_off` false |
| Off set `ARGENTINE_DIEGO_OFF=1`; off confirmed | 2026-09-30 ~23:31:05 | `diego_off` true |
| Reject smoke `POST /v1/gate` | 2026-09-30 ~23:31:21 | HTTP 503 `{"decision":"NO_GO","fails":["diego_off"]}` |
| Restore `ARGENTINE_DIEGO_OFF=0`; on confirmed | 2026-09-30 ~23:32:42 | `diego_off` false; GO smoke OK |

After restore, authenticated stats were `human_reject=2`, `decisions=16`, `ratio=2/16`. The fixture ratio `1/5` is not this live ratio.
