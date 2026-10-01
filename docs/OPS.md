# ArGENTine operations policy

How Diego operates the gate. The public gate is still https://argentine-a2a.fly.dev. Railway is an alternate host for the same image when Fly limits block a deploy. It is not the URL in the agent card. This note has no secrets.

Click-deploy, the `/data` volume, variables, smoke calls, and the cutover checklist are in [docs/RAILWAY.md](RAILWAY.md).

Behavior, decision types, and the kill-path table are in [docs/EVIDENCE.md](EVIDENCE.md). The hashed 2026-10-01 export (log, kill drill, health, stats, and checksums) is in [docs/evidence/2026-10-01/](evidence/2026-10-01/).

## Token rotation

Allowlist tokens live only in the Fly secret `ARGENTINE_ALLOWLIST` and in the operator password manager. They are never committed to git.

`config/allowlist.json` is a localhost fixture. It is not the production allowlist.

Rotate one caller in two secret updates so the new token is proven before the old one is revoked:

1. Generate a new caller token and store it in the password manager.
2. Add that token to the `ARGENTINE_ALLOWLIST` JSON. Leave the old token in place for this update.
3. Publish the JSON with `fly secrets set`. Fly restarts the machine.
4. Verify with a smoke call that presents the new token. Expect a decision, not `unauthorized`.
5. Remove the old token from the JSON and publish again with `fly secrets set`. That second update revokes it.

The same two updates apply on Railway. Save `ARGENTINE_ALLOWLIST` as a service variable instead of `fly secrets set`. Railway restarts the service when the variable changes. Details are in [docs/RAILWAY.md](RAILWAY.md#token-rotation).

The log stores the caller id, not the token.

## Off-switch custodian

Custodian: Diego Lescano. He is the only person with authority to engage or clear `ARGENTINE_DIEGO_OFF` and the optional flag file.

Engaging either control refuses every caller. The response is HTTP 503:

```json
{"decision":"NO_GO","fails":["diego_off"]}
```

The gate does not post or execute. Both controls are read on every request. The engage and clear table is in [Diego off-switch](EVIDENCE.md#diego-off-switch). At a high level the two paths are:

- Environment secret `ARGENTINE_DIEGO_OFF`. On Fly, `fly secrets set` restarts the machine. On Railway, saving the service variable restarts the service.
- Flag file `/data/diego.off` (`ARGENTINE_DIEGO_OFF_FILE` on the Fly volume, and on the Railway volume mounted at the same path). Presence shuts the gate. Deleting the file clears it on the next request, with no restart.

## Fly fail-closed

`fly.toml` sets `ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1`. A missing or unreadable `ARGENTINE_ALLOWLIST` makes the process exit, so the gate stays closed. The Railway image sets the same variable (`Dockerfile`, and `.railway/railway.ts`). A missing allowlist exits there too.

An unknown bearer token is refused with `unauthorized`. Knowing the hostname does not authorize a call. The public URL is not the trust boundary.

## Railway alternate

Railway is not live in the agent card. Deploy it from the GitHub repo, mount a volume at `/data`, and set `ARGENTINE_ALLOWLIST`, `ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1`, and `ARGENTINE_DIEGO_OFF` in the Railway dashboard. Smoke `GET /health` and `GET /v1/gate/stats` on the hostname Railway assigns. Move `agent-card.json`, `.well-known/agent-card.json`, and the a2a-registry listing only after that hostname exists. The checklist is in [docs/RAILWAY.md](RAILWAY.md). Fly remains the public host until that cutover.
