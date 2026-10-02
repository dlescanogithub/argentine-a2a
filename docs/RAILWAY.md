# Railway hosting (public gate)

The public gate is https://argentine-a2a-production.up.railway.app. `agent-card.json` and `.well-known/agent-card.json` (version 1.2.0) name that origin. The description says the public gate is live on Railway. Fly (`https://argentine-a2a.fly.dev`) is a legacy host. Fly steps stay in [OPS.md](OPS.md). This page has no secret values.

## What a new Railway service reads

Railway stopped adopting Config as Code for new services on 2026-08-28. Existing `railway.toml` and `railway.json` files stop being read on 2026-12-01. This repo does not add those files. A new project would ignore them, and a service cannot be managed by both Config as Code and Infrastructure as Code.

Two ways to deploy:

1. Click deploy from GitHub. Railway builds the root `Dockerfile`. You set the health check, the volume, and the variables in the dashboard. That is enough to run the gate.
2. Optional later: `railway config apply` using [`.railway/railway.ts`](../.railway/railway.ts). A git push does not apply that file.

The image already binds `0.0.0.0`, writes `/data/gate-log.jsonl`, reads `/data/diego.off`, and sets `ARGENTINE_REQUIRE_ALLOWLIST_SECRET=1`. Do not set a start command. `docker/entrypoint.sh` prepares `/data`, drops to user `gate`, and runs `python3 -m argentine serve`.

## Click deploy

1. In Railway, create a project and choose **Deploy from GitHub repo**. Select `dlescanogithub/argentine-a2a`.
2. Confirm the builder is the root `Dockerfile`. Leave the start command empty.
3. Leave `PORT` unset. Railway injects it. The entrypoint copies `PORT` into `ARGENTINE_PORT` so the process and the health check use the same port. If `PORT` is unset, the image keeps `ARGENTINE_PORT=8080` (what Fly uses). Do not set `PORT` on the Fly app.
4. Service settings → health check path: `/health`. A 30 second timeout is enough. `GET /health` stays HTTP 200 when the off-switch is engaged. The body field `diego_off` reports the switch, so a deliberate shutdown does not fail the deploy check. Railway calls this path only to decide when a new deploy is ready. It does not keep polling afterward. The process does not filter on the `Host` header, so checks from `healthcheck.railway.app` are accepted.
5. Do not set a non-root Railway run user (`RAILWAY_RUN_UID`). The entrypoint must start as root long enough to `chown` `/data`, then it drops to `gate`.
6. Add a volume and set the mount path to `/data`. That path is absolute. It is not `/app/data`. Use one replica. A volume mounts on a single instance, and a redeploy of a service with a volume has a short downtime.
7. Set the variables in the next section, then redeploy if the first build ran before they existed.

A missing `ARGENTINE_ALLOWLIST` makes the process exit. The health check fails and Railway does not send traffic. That is the same fail-closed behavior as Fly.

`.railway/railway.ts` asks Railway for the same shape when you apply it: Dockerfile builder, `/health`, one replica, volume `argentine_gate_log` (1 GiB) mounted at `/data`, and `requiredMountPath=/data` so a deploy without that mount does not go live. The file tracks GitHub repo `dlescanogithub/argentine-a2a` branch `main`. It does not set a public hostname.

## Variables

Set these on the service. Do not commit the values.

| Key | Value |
| --- | --- |
| `ARGENTINE_ALLOWLIST` | JSON allowlist. Required. Same shape as the Fly secret. |
| `ARGENTINE_REQUIRE_ALLOWLIST_SECRET` | `1`. Already in the image. Set it here as well so a dashboard edit cannot drop it. |
| `ARGENTINE_DIEGO_OFF` | `1` until smoke passes, then `0` to open the gate. |
| `ARGENTINE_BIND` | `0.0.0.0`. Already in the image. |
| `ARGENTINE_LOG_PATH` | `/data/gate-log.jsonl` |
| `ARGENTINE_DIEGO_OFF_FILE` | `/data/diego.off` |
| `ARGENTINE_STDOUT_LOG` | `1` |
| `ARGENTINE_LOG_MAX_BYTES` | `5242880` |
| `ARGENTINE_LOG_BACKUPS` | `3` |

`config/allowlist.json` is a localhost fixture. It is not this allowlist.

Example shape, with placeholders, matching the Fly command in the README:

```json
{"callers":[{"id":"diego","token":"REPLACE_DIEGO"},{"id":"ops","token":"REPLACE_OPS"}]}
```

Generate real tokens in the password manager. The log stores the caller id, not the token.

Leave `PORT` unset. Do not invent a public URL variable.

## Token rotation

Same two updates as Fly ([OPS.md](OPS.md#token-rotation)). Only the publish step differs. A variable change restarts the service.

1. Generate a new caller token and store it in the password manager.
2. Add that token to the `ARGENTINE_ALLOWLIST` JSON. Leave the old token in place.
3. Save the variable in Railway and wait for the restart.
4. Smoke with the new token. Expect a decision, not `unauthorized`.
5. Remove the old token from the JSON and save again. That second update revokes it.

## Off-switch

Custodian: Diego Lescano. Either control refuses every caller with HTTP 503 `{"decision":"NO_GO","fails":["diego_off"]}`.

- Variable `ARGENTINE_DIEGO_OFF` set to `1`, `true`, `yes`, or `on`. Saving it restarts the service. Set `0` to clear this switch.
- Flag file `/data/diego.off`. Presence shuts the gate on the next request. Deleting the file clears it with no restart.

From a linked CLI, after an SSH key is registered:

```bash
railway ssh -- touch /data/diego.off
railway ssh -- rm -f /data/diego.off
```

The dashboard service console can run the same `touch` and `rm`. The volume browser lists `/data` as well (`railway volume browse /`).

## Smoke

The public hostname is https://argentine-a2a-production.up.railway.app. Use that origin for the live gate. Do not commit a placeholder hostname. If the service is recreated, substitute the hostname Railway assigns (`https://<railway-hostname>/health`) and update the agent card only after that hostname exists.

```bash
curl -fsS "https://argentine-a2a-production.up.railway.app/health"
curl -fsS -H "Authorization: Bearer <token>" "https://argentine-a2a-production.up.railway.app/v1/gate/stats"
```

`/health` needs no token. Expect `"ok": true`. `diego_off` is `true` while the switch is engaged.

`/v1/gate/stats` needs an allowlist bearer token. Expect `human_reject`, `decisions`, and `ratio`. `unauthorized` means the token is not in `ARGENTINE_ALLOWLIST`.

A decision smoke is the same `POST` as Fly, to `https://argentine-a2a-production.up.railway.app/v1/gate` or `https://argentine-a2a-production.up.railway.app/`. Expect `GO`, `NO_GO`, or `NEED_HUMAN`, not `unauthorized`.

Count the volume copy from the service, with the working directory that holds the package:

```bash
railway ssh -- sh -c "cd /app && python3 -m argentine count --log /data/gate-log.jsonl"
```

Stdout lines are the same JSONL records because `ARGENTINE_STDOUT_LOG=1`. Railway's log view shows that mirror. The volume file is the copy you control.

## Optional Infrastructure as Code

Click-deploy does not require this. Use it when you want the repo file to create or update the service, volume, health check, and non-secret variables.

```bash
npm install railway
railway login
railway link
railway config plan
```

Read the plan before `railway config apply`. `preserve()` keeps `ARGENTINE_ALLOWLIST` and `ARGENTINE_DIEGO_OFF` at whatever is already stored in Railway. It does not invent a token. Set those two in the dashboard before you expect a healthy deploy.

The file lists the variables it manages. An apply can remove a service variable that is not listed and not covered by `preserve()`. `PORT` and `RAILWAY_*` are platform variables; leave them alone.

`npm install` creates `node_modules/`, which is gitignored. Do not commit that directory or any lockfile that contains nothing but a local install. Do not commit secret values if a plan is printed with values shown.

The partial name is `argentine-a2a`. The Railway project name in the file is `argentine-a2a`. If the linked project has another name, edit that string so the plan does not rename it. The service name in the file is `argentine-a2a`. A click-deploy service with a different name will show up as a second service unless you rename one side before applying.

## Cutover checklist

The assigned production hostname is https://argentine-a2a-production.up.railway.app. This commit points the agent card and the canonical docs at that origin. Card version stays 1.2.0. Do not commit a placeholder hostname.

Done in this change:

1. `agent-card.json` and `.well-known/agent-card.json` use the Railway origin in `supportedInterfaces[0].url` and in the description.
2. `README.md`, `docs/EVIDENCE.md`, `docs/OPS.md`, `index.html`, and `scripts/call_gate.py` treat that origin as the public gate.
3. `fly.toml` is unchanged. The Fly app (`https://argentine-a2a.fly.dev`) is a legacy host.

After merge, on the live Railway service:

1. `GET https://argentine-a2a-production.up.railway.app/health` returns `"ok": true`.
2. `GET https://argentine-a2a-production.up.railway.app/.well-known/agent-card.json` serves this card. `supportedInterfaces[0].url` is the Railway origin, and the description says the public gate is live on Railway.
3. Authenticated `GET /v1/gate/stats` returns counts, not `unauthorized`.
4. A decision `POST` with a current allowlist token returns a decision.
5. The off-switch engages and clears (`ARGENTINE_DIEGO_OFF` and `/data/diego.off`).
6. `/data/gate-log.jsonl` is on the volume and survives a restart.
7. The owned registry listing at https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582 (`github.dlescanogithub/argentine-a2a`) was observed on 2026-10-01 21:01 ART naming the Railway origin. The citeable pack is [docs/evidence/2026-10-01-railway/](evidence/2026-10-01-railway/).
8. Keep the Fly app until traffic has moved. Do not run `fly destroy`.
