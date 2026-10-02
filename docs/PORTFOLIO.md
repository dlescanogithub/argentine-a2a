# Diego Lescano — Head / Director AI

HITL and governance gate, and an agent coach: the answer is `GO`, `NO_GO`, or `NEED_HUMAN`, and a person can shut the gate. Not a chatbot.

For AI Head, Director, COE, and Engineering Manager roles in Argentina, or remote from Argentina.

## Proof

- [docs/EVIDENCE.md](EVIDENCE.md) — purpose, allowlist, kill path, decision types, and how to read `human_reject`. No secrets.
- [docs/evidence/2026-10-01-railway/](evidence/2026-10-01-railway/) — partner `GO` and `NEED_HUMAN`; after the human-reject drill, authenticated stats were `human_reject=1`, `decisions=28`, `ratio=1/28`, and `diego_off` restored true.
- [docs/COACH.md](COACH.md) — how to brief an agent and how to use the gate.
- Live gate: https://argentine-a2a-production.up.railway.app. The public URL is not the trust boundary.
- A2A registry listing cited in EVIDENCE: https://www.a2a-registry.org/agent/18978b04-ecd1-4283-8449-060c71014582
- [LinkedIn](https://www.linkedin.com/in/diego-lescano-data-science)

## HITL story

A human rejection was recorded, then the kill switch was engaged. Caller `partner`, 2026-10-02T00:48:56Z: the gate was open (`diego_off` false) and the decision was HTTP 200 `NO_GO`. Authenticated stats after that call were `human_reject=1`, `decisions=28`, `ratio=1/28`. At 2026-10-02T00:52:12Z, `GET /health` showed `diego_off` restored true. Sequence: on, then human_reject, then off. Record: [`human-reject-2026-10-02.json`](evidence/2026-10-01-railway/human-reject-2026-10-02.json). The same pack still has the earlier partner `GO` and `NEED_HUMAN`.

## What it never does

It does not post, spend, or execute a tool named in the brief. It does not send mail or call the network. The only outputs are the HTTP reply and a local JSONL log.

## How I coach agents

Three questions from the [coach checklist](COACH.md#coach-checklist). A yes matches the bar this repository already meets. A gap is a coaching item. Do not invent a numeric score from the list.

- Can you name the closed set of decisions, and the rule that selects each one, without asking a model to improvise the verdict?
- Does a definitive failure become `NO_GO`, and does a missing required fact become `NEED_HUMAN`?
- Can a named person shut every caller on the next request, and is that kill stored separately from a `human_reject` on one proposal?
