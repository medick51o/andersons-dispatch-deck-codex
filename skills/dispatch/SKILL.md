---
name: dispatch
description: Orchestrate substantial coding missions in Codex with lean delegation, fenced write sets, persistent external model seats, independent review, and evidence-backed gates. Use when the user asks to dispatch, orchestrate, delegate, run a council/panel, or coordinate multiple independent coding lanes. Do not use for a small question or a straightforward one-file fix that Codex should handle inline.
---

# Codex Dispatch

Run the smallest orchestration shape that earns its cost. Codex is the conductor in this
harness; the method remains model-agnostic.

On explicit invocation, print a first-line receipt using the version parsed from the local spine:

```text
🟡➤ Codex Dispatch loaded · codex-spine <parsed>
```

Read [references/codex-native.md](references/codex-native.md) on every activation. When the user
requests a multi-vendor panel/council, spend or lineage adjudication, or a doctrine change, read
the active spine at `$CODEX_HOME/dispatch/SPINE.md` (default `~/.codex/dispatch/SPINE.md`).
While developing this repository, the top-level `SPINE.md` is authoritative. Verify its version
line starts with `codex-spine`.

## Operating shape

1. Apply Gate 0. If the task is small, do it directly and say no delegation was warranted.
2. For a real build, state the observable outcome, protected invariants, write set, verification
   command, rollback, and the user's in-hand check before dispatching.
3. Freeze a repository baseline. Give each builder one bounded lane and a non-overlapping write
   set. Native Codex subagents are useful workers but remain OpenAI lineage.
4. Use persistent MCP reply tools only to continue a seat's existing lane. Use a fresh start tool
   for review. Never turn a reply-chain into the independent reviewer of work it touched.
5. A reviewer receives the original task, full review set, diff, acceptance criteria, and gate
   output—not the builder's reasoning. Require a ranked failure mechanism and reproduction path.
6. Compare the repository-derived delta against both the frozen write set and review manifest.
   Run the relevant gates, report their exact evidence, and leave merge/deploy to the user unless
   they explicitly authorize it.

Default to one builder plus one reviewer for nontrivial code. Three or more seats are a council:
state the seat count, distinct lenses, and likely quota/cost shape, then wait for explicit consent.
Do not spawn undeclared helper fleets.

## Rendering

Use the seat/action notation in the active `SPINE.md` during dispatch runs. Always pair emojis
with the real model and action in words. Mark native Codex review of OpenAI-built work as `🪞`
same-lineage self-check; reserve `🛡️` for genuinely independent lineage. Do not add emoji ceremony
to ordinary small tasks where this skill did not activate.

## Canonical invariants

```
CODEX HARNESS INVARIANTS (v1 · doctrine: SPINE.md)
- The producing lineage never independently approves its own work.
- Claims stop at evidence: report gates, not confidence theater.
- Unresolved requirements and evidence forks go to the user.
- The user remains the default merge and deploy authority.
```
