# ArGENTine kill drill — argentine-a2a

**App:** https://argentine-a2a.fly.dev (`argentine-a2a` on Fly)  
**When:** 2026-09-30 late evening ART (UTC−3); document date 2026-10-01  
**Operator notes:** No allowlist tokens or secret values logged. Times below are America/Buenos_Aires (ART).

## Success criteria

| Criterion | Result |
|-----------|--------|
| Proven off → reject → on with ART timestamps | **PASS** |
| App left with `diego_off: false` | **PASS** |

## Off-switch mechanism

- Env/secret: `ARGENTINE_DIEGO_OFF` (`1`/`true`/`yes`/`on` engages; `0` leaves switch open).
- Optional flag file: `ARGENTINE_DIEGO_OFF_FILE` = `/data/diego.off` (Fly volume); not used in this drill.
- Confirmed via local README/`killswitch.py` and `fly secrets list` (names only):
  - `ARGENTINE_ALLOWLIST` (Deployed)
  - `ARGENTINE_DIEGO_OFF` (Deployed)
- Kill path used: `fly secrets set ARGENTINE_DIEGO_OFF=1 -a argentine-a2a` then restore with `=0`.

## Timeline (ART)

| Step | Timestamp (ART) | Notes |
|------|-----------------|-------|
| Baseline health | 2026-09-30 23:29:51 | `diego_off: false` |
| `secrets set …=1` started | 2026-09-30 23:29:51 | rolling machine update |
| `secrets set …=1` done | 2026-09-30 23:31:02 | exit 0; DNS AAAA warn (non-blocking) |
| Off confirmed via `/health` | 2026-09-30 23:31:05 | `diego_off: true` |
| Gate reject smoke | 2026-09-30 23:31:21 | 503 / `NO_GO` / `diego_off` |
| `secrets set …=0` started | 2026-09-30 23:31:26 | restore |
| `secrets set …=0` done | 2026-09-30 23:32:37 | exit 0 |
| On confirmed via `/health` | 2026-09-30 23:32:42 | `diego_off: false` |
| Post-restore GO smoke | 2026-09-30 23:32:42 | `decision: GO` |

## Health JSON

**Before (baseline):**
```json
{"ok":true,"diego_off":false,"max_concurrent":2,"timeout_seconds":15.0}
```

**During (off):**
```json
{"ok":true,"diego_off":true,"max_concurrent":2,"timeout_seconds":15.0}
```

**After (restored):**
```json
{"ok":true,"diego_off":false,"max_concurrent":2,"timeout_seconds":15.0}
```

`/health` stayed HTTP 200 while shut (expected; Fly check does not restart-loop on off-switch).

## Reject while off

- Endpoint: `POST https://argentine-a2a.fly.dev/v1/gate`
- Auth: Bearer from env (`ARGENTINE_CALLER_TOKEN_DIEGO` mapped to `ARGENTINE_CALLER_TOKEN`); token not printed.
- Fixture: `low-complete` / `scripts/call_gate.py go`
- **HTTP status:** `503`
- **Body shape:**
```json
{"decision":"NO_GO","fails":["diego_off"]}
```
- `call_gate.py go` while off: same body (exit 0; script prints decision/fails only).

## Post-restore smoke

- `scripts/call_gate.py go` → `{"decision":"GO","fails":[]}` (proves gate accepts again).

## Stats / counts

`GET /v1/gate/stats` requires allowlist auth.

| Moment | HTTP | Body |
|--------|------|------|
| Before kill (no auth) | 401 | `{"decision":"NO_GO","fails":["unauthorized"]}` |
| While off (with auth) | 503 | `{"decision":"NO_GO","fails":["diego_off"]}` (stats gated by kill switch) |
| After restore (with auth) | 200 | `{"human_reject":2,"decisions":16,"ratio":"2/16"}` |

## Restore

- Restored with `fly secrets set ARGENTINE_DIEGO_OFF=0 -a argentine-a2a`.
- Health polled until `diego_off: false` at **2026-09-30 23:32:42 ART**.
- Final health re-check: `diego_off: false`. App left open.

## Notes

- Fly reported DNS AAAA verification warning (`expected 1 AAAA … got 0`) on both secret rollouts; HTTPS/`/health` remained reachable.
- Machine `e2865560ea3798` (iad) rolled stopped→started→healthy on each secret change (~70s).
