# ArGENTine evidence pack — 2026-10-01

Timed, hashed export of the live gate log, kill-drill report, health, stats, and live agent card.

## What a reviewer can verify

1. Open `SUMMARY.json` for counts and commit pointer.
2. Re-hash files with `sha256sum -c SHA256SUMS`.
3. Compare `git_commit_at_export` to https://github.com/dlescanogithub/argentine-a2a/commit/4a0e8f7bb23c688549db6f8c967181b0c7759264.
4. Re-fetch live card/health and compare to the snapshots (card may advance; this pack is a point-in-time).

## Trust notes

- Gate log never stores the brief plaintext or bearer tokens (`brief_hash` only).
- Kill drill PASS is documented in `kill-drill-2026-10-01.md` (off → 503 `diego_off` → restore).
- At drill restore, authenticated stats were **2/16**. This export's live log/stats are **2/66** (same human rejects, more later traffic).
- Public URL is not the trust boundary; allowlist + off-switch are.

## Files

| File | Role |
| --- | --- |
| `gate-log.jsonl` | Full live log export from Fly `/data/gate-log.jsonl` |
| `kill-drill-2026-10-01.md` | Operator drill report |
| `gate-stats.json` | Authenticated `GET /v1/gate/stats` at export |
| `health.json` | Public `/health` at export |
| `agent-card.live.json` | Public `/.well-known/agent-card.json` at export |
| `SHA256SUMS` | Per-file SHA-256 |
| `MANIFEST.json` | Machine-readable attestation (hashes + commit + clocks) |
