# ArGENTine operations policy

How Diego operates the live gate at https://argentine-a2a.fly.dev. This note has no secrets.

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

The log stores the caller id, not the token.

## Off-switch custodian

Custodian: Diego Lescano. He is the only person with authority to engage or clear `ARGENTINE_DIEGO_OFF` and the optional flag file.

Engaging either control refuses every caller. The response is HTTP 503:

```json
{"decision":"NO_GO","fails":["diego_off"]}
```

The gate does not post or execute. Both controls are read on every request. The engage and clear table is in [Diego off-switch](EVIDENCE.md#diego-off-switch). At a high level the two paths are:

- Environment secret `ARGENTINE_DIEGO_OFF`. On Fly, `fly secrets set` restarts the machine.
- Flag file `/data/diego.off` (`ARGENTINE_DIEGO_OFF_FILE` on the Fly volume). Presence shuts the gate. Deleting the file clears it on the next request, with no restart.

## Fly fail-closed

`fly.toml` sets `ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1`. A missing or unreadable `ARGENTINE_ALLOWLIST` makes the process exit, so the gate stays closed.

An unknown bearer token is refused with `unauthorized`. Knowing the hostname does not authorize a call. The public URL is not the trust boundary.
