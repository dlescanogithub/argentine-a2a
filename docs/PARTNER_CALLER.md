# Partner caller runbook

How an external allowlisted caller (id `partner`) hits the live Railway gate. For coach and portfolio demos. This file has no secrets.

## Live gate

Base URL: https://argentine-a2a-production.up.railway.app

The public URL is not the trust boundary. A call needs an allowlist bearer token: `Authorization: Bearer <token>`.

## Obtain a token

Diego issues the token into the live `ARGENTINE_ALLOWLIST` value. That value is JSON. `callers` is a list of objects, each with `id` and `token`. The id for this runbook is `partner`.

Ask Diego for the token out of band. Leave it out of this file, chat, tickets, and commits. `config/allowlist.json` is a localhost fixture. It is not the live allowlist.

## POST /v1/gate

`Content-Type: application/json` and `Authorization: Bearer <token>`. The two demo cases are in `fixtures/briefs.json`. `scripts/call_gate.py` maps `go` to `low-complete` and `need-human` to `high-missing`.

The bodies below are those fixture requests. With the gate open, the partner capture in the Railway pack returned the decisions shown. With the off-switch engaged, both calls return the body in [Diego off](#diego-off).

### go (`low-complete`)

```bash
curl -sS https://argentine-a2a-production.up.railway.app/v1/gate \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"brief":"digest: Read-only summary of local decisions for the caller.\nkill_path: Diego off-switch file var/diego.off\nside_effects: none\n","blast_class":"low","tools":[],"egress":["reply"]}'
```

Open-gate response (fixture `low-complete`, and the partner `go` capture, HTTP 200):

```json
{"decision":"GO","fails":[]}
```

### need-human (`high-missing`)

```bash
curl -sS https://argentine-a2a-production.up.railway.app/v1/gate \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"brief":"Review whether to draft a participation note.","blast_class":"high","tools":[],"egress":["reply"]}'
```

Open-gate response (fixture `high-missing`, and the partner `need-human` capture, HTTP 200):

```json
{"decision":"NEED_HUMAN","fails":["hitl","approved_until","digest","kill_path"]}
```

## Stats

Optional. Same bearer.

```bash
curl -sS https://argentine-a2a-production.up.railway.app/v1/gate/stats \
  -H 'Authorization: Bearer <token>'
```

When the gate is open the body is:

```json
{"human_reject": N, "decisions": M, "ratio": "N/M"}
```

`human_reject` counts log rows where a person rejected that proposal. `decisions` counts decision rows in the active log and its rotated siblings. `ratio` is that fraction, written `N/M`. A larger ratio means more recorded human rejections among logged decisions. It is not a pass rate and it is not an error rate. `NEED_HUMAN` is not a human rejection. Other `NO_GO` rows, including `diego_off`, stay `human_reject: false`.

The Railway pack records authenticated stats after the 2026-10-02 partner human_reject drill as `human_reject=1`, `decisions=28`, `ratio=1/28`. Cite that from [docs/EVIDENCE.md](EVIDENCE.md) and [docs/evidence/2026-10-01-railway/](evidence/2026-10-01-railway/) (`human-reject-2026-10-02.json`). A later `GET /v1/gate/stats` returns the log at request time.

The same pack still holds the earlier partner capture: `human_reject` 0, `decisions` 11, ratio `0/11` (`partner-decisions.json`). Cite `1/5` only for `fixtures/sample-gate-log.jsonl`.

## Diego off

When `ARGENTINE_DIEGO_OFF` is `1` (`true`, `yes`, and `on` also engage it), an authenticated `POST /v1/gate` or `GET /v1/gate/stats` is HTTP 503:

```json
{"decision":"NO_GO","fails":["diego_off"]}
```

The flag file `/data/diego.off` engages the same response. While the switch is engaged, those routes return `diego_off` before the allowlist is checked.

Check the switch with `GET /health`. That route stays HTTP 200, and it does not require a bearer token. The body field `diego_off` reports the switch.

```bash
curl -sS https://argentine-a2a-production.up.railway.app/health
```

After the human_reject drill, the pack's public health body was `{"ok":true,"diego_off":true,"max_concurrent":2,"timeout_seconds":15.0}` (`diego_off` restored true). Read the live body before a demo. `diego_off: true` means the gate is shut.

## Where to look

| What | Where |
| --- | --- |
| Caller script (`go`, `need-human`) | [`scripts/call_gate.py`](../scripts/call_gate.py) |
| How to brief an agent | [docs/COACH.md](COACH.md) |
| Portfolio one-pager | [docs/PORTFOLIO.md](PORTFOLIO.md) |
| Evidence, allowlist, kill path, how to read `human_reject` | [docs/EVIDENCE.md](EVIDENCE.md) |
| Railway pack | [docs/evidence/2026-10-01-railway/](evidence/2026-10-01-railway/) |

`scripts/call_gate.py` reads the token from `ARGENTINE_CALLER_TOKEN` and prints `decision` and `fails` only. It does not print the token. `ARGENTINE_GATE_URL` overrides the endpoint and defaults to `https://argentine-a2a-production.up.railway.app/v1/gate`.

```bash
export ARGENTINE_CALLER_TOKEN="<token>"
python3 scripts/call_gate.py go
python3 scripts/call_gate.py need-human
```
