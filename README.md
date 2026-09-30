# ArGENTine

Local [A2A](https://a2a-protocol.org/) v1 checklist gate for Diego Lescano (Head/Director AI track).

A caller sends a proposed action: a text brief, plus optional `blast_class`, `tools`, and `egress`. The gate answers with a decision and the gaps. It does not post, spend, execute the caller's tools, send mail, or call the network. The only outputs are the HTTP reply and a local JSONL log.

This is not a chatbot. There is no public deploy. GitHub Pages serves the discovery card only.

## Run locally

From the repository root, with Python 3.12 and no extra packages:

```bash
python3 -m argentine serve
```

The process listens on `http://127.0.0.1:8787` and refuses any other bind address. Stop it with Ctrl-C.

```bash
curl -s http://127.0.0.1:8787/v1/gate \
  -H 'Authorization: Bearer dev-diego' \
  -H 'Content-Type: application/json' \
  -d '{"brief":"digest: Read-only summary of local decisions for the caller.\nkill_path: Diego off-switch file var/diego.off\nside_effects: none\n","blast_class":"low","tools":[],"egress":["reply"]}'
```

```json
{"decision":"GO","fails":[]}
```

Check the scored fixtures:

```bash
python3 -m argentine decide
```

Useful flags: `--port`, `--allowlist`, `--log`, `--off-file`, `--rate-limit`. Defaults are `config/allowlist.json`, `var/gate-log.jsonl`, and `var/diego.off` inside this repository.

## Request and response

`POST /v1/gate` with `Authorization: Bearer <token>`:

| Field | Required | Meaning |
| --- | --- | --- |
| `brief` | yes | Proposed action. Checklist markers are `key: value` lines. |
| `blast_class` | no | `low`, `medium`, or `high`. |
| `tools` | no | Tool names the proposal would use. This service never calls them. |
| `egress` | no | Where the proposal sends data. `reply` means the caller only. |
| `human_reject` | no | `true` records a human rejection. |

The response body is only:

```json
{"decision":"NEED_HUMAN","fails":["hitl","approved_until","digest","kill_path"]}
```

`decision` is `GO`, `NO_GO`, or `NEED_HUMAN`. `fails` lists checklist ids that did not pass. Operational refuses use the same shape: `unauthorized`, `rate_limited`, `diego_off`, `timeout`, `concurrency_limit`, `invalid_request`, `allowlist_unavailable`.

`POST /` accepts an A2A JSON-RPC `message/send`. Put the brief in a text part and `blast_class`, `tools`, and `egress` in a data part. The `result` object is only `decision` and `fails`. Callback and push-notification URLs are ignored.

## Rubric

Each item is `PASS`, `FAIL`, or `MISSING`. Any `FAIL` is `NO_GO`, including every failure on a high-blast action. If nothing failed but a pass still needs information, the decision is `NEED_HUMAN`. Every item `PASS` is `GO`.

| Id | Pass when |
| --- | --- |
| `blast_class` | One valid class, and the field matches the brief if both are present. An invalid or conflicting class fails closed. |
| `hitl` | High-blast actions include `HITL: approved` or `approved_by`. `HITL: rejected` or `human_reject: true` fails. Low and medium do not require approval. |
| `approved_until` | Present and in the future when the class is high or an approval was claimed. ISO-8601, `Z` allowed. |
| `digest` | A `digest:` line of at least 15 characters for the approver. |
| `egress` | Declared, and every value is `reply`, `caller`, or `reply_to_caller`. An empty list means no egress beyond this reply. |
| `kill_path` | A `kill_path:` (or `abort:` / `rollback:`) line. `none` or `disabled` fails. |
| `least_privilege` | No tools, or only `read`, `read_brief`, `read_log`, `summarize`, `draft`, `checklist`. Post, mail, spend, execute, and similar tools fail. An unknown tool is `NEED_HUMAN`. |
| `side_effects` | The proposal does not ask this call to post, spend, or reach past the caller. `side_effects: none` with scoped egress and no privileged tools passes. |

The gate does not grade the prose with a model. Markers are exact lines.

High-blast `GO` needs approval, a future `approved_until`, a digest, a kill path, reply-only egress, least privilege, and no side effects. The same action with those lines missing is `NEED_HUMAN`. A rejected approval, expired time, wide egress, or privileged tool is `NO_GO`.

## Diego off-switch

Either control shuts the gate. The next request is refused. Nothing is posted or executed.

File flag, effective without a restart:

```bash
touch var/diego.off
# {"decision":"NO_GO","fails":["diego_off"]}
rm var/diego.off
```

The file is `var/diego.off` in the repository (override with `--off-file`). Presence shuts the gate, including an empty file. Delete the file to open the gate.

Environment variable, read on every request from the process environment. Set it before starting:

```bash
ARGENTINE_DIEGO_OFF=1 python3 -m argentine serve
```

Accepted values are `1`, `true`, `yes`, and `on`. Unset it and restart to open the gate that way. To shut a process that is already running, use the file.

`GET /health` on localhost reports `diego_off`.

## Allowlist

`config/allowlist.json`:

```json
{
  "callers": [
    {"id": "diego", "token": "dev-diego"},
    {"id": "ops", "token": "dev-ops"}
  ]
}
```

The committed tokens are for localhost development. Replace them before sharing a machine. The file is re-read on every request, so edits apply without a restart. A missing or unreadable file fails closed with `allowlist_unavailable`.

Send `Authorization: Bearer <token>`. The log stores the caller id, not the token. Unknown callers receive `unauthorized`.

Override the path with `--allowlist`.

## Rate limit, timeout, concurrency

- Rate limit: 10 requests per caller per hour (`--rate-limit` or `ARGENTINE_RATE_LIMIT_PER_HOUR`). The window is 3600 seconds, counted in memory, and resets when the process starts. Request 11 in the window is `429` with `rate_limited`.
- Timeout: 15 seconds. The response is `timeout`.
- Concurrency: 2 requests in flight. The next one is `concurrency_limit` and does not wait.

`GET /health` and `GET /v1/gate/stats` do not consume the rate limit. Stats requires the same bearer token.

## Gate log

Every gate request appends one line to `var/gate-log.jsonl` (gitignored). The brief is stored only as a SHA-256 hash.

```json
{"id":"...","ts":"...","caller":"diego","brief_hash":"sha256:...","blast_class":"low","decision":"GO","fails":[],"human_reject":false,"notes":"blast_class=PASS ..."}
```

`human_reject` is true only when a person rejected the proposal. Other `NO_GO` rows stay false.

Count `N` human rejections over `M` decisions:

```bash
python3 -m argentine count --log var/gate-log.jsonl
python3 -m argentine count --log fixtures/sample-gate-log.jsonl
```

The sample file prints:

```text
human_reject=1
decisions=5
ratio=1/5
```

`GET /v1/gate/stats` returns the same counts for the live log as `{"human_reject": N, "decisions": M, "ratio": "N/M"}`.

`fixtures/sample-gate-log.jsonl` has five rows: two `GO`, one `NEED_HUMAN`, two `NO_GO`, and one `human_reject`. `fixtures/briefs.json` is the matching briefs. `python3 -m argentine decide` checks every fixture, including `low-complete` (`GO`), `high-missing` (`NEED_HUMAN`), and `high-reject` (`NO_GO`).

## What this process will not do

It will not post, spend, send mail, call Moltbook, fetch a URL from the brief, or run a tool named in the request. Egress from this service is the reply to the caller. Logs stay in the local JSONL file.

## Discovery card

`agent-card.json` and `.well-known/agent-card.json` are the public listing. Their interface URL points at the card itself. It is not a live message endpoint. Do not register a public runtime until Diego says so.

The local process serves its own card at `http://127.0.0.1:8787/.well-known/agent-card.json` with a loopback URL.

## License

MIT
