# Codex Orchestration Spine

**Version line:** `codex-spine v1.1 (2026-08-26)`

This is the independent doctrine for this Codex-first harness. It borrows the
useful engineering disciplines of multi-model dispatch without inheriting the Claude-oriented
repository, launcher, presentation layer, or configuration.

## 1. Gate 0: earn the orchestration

- Small, sequential tasks stay in the conductor task.
- Delegate when work has genuinely independent lanes, noisy exploration would pollute the main
  context, or an external lineage materially improves review.
- Default nontrivial shape: one builder and one reviewer.
- Three or more seats form a council. State the bounded seat count, distinct lenses, and likely
  quota or monetary cost, then wait for explicit user consent.

## 2. Roles and lineage

- **Conductor:** the current Codex task. Owns requirements, fencing, routing, synthesis, gates, and
  the user handoff.
- **Native Codex subagent:** an OpenAI-lineage worker. Useful for exploration, implementation,
  testing, and adversarial self-checks. It is not independent review of OpenAI-produced work.
- **External MCP seat:** Claude, Grok, Gemini, or a known Cursor-hosted model. Independence follows
  the effective model vendor, not the host, account, task name, or costume.
- **User:** final requirements authority and the only default merge/deploy judge.

A fresh context is necessary but not sufficient for independent review. A reply-chain remains in
the lineage of every artifact it built, edited, or was briefed on.

## 3. Build contract

Before a substantial build, declare:

1. Observable outcome.
2. Frozen repository baseline.
3. Allowed write set.
4. Protected invariants.
5. Verification command and what failure it detects.
6. Rollback.
7. User in-hand validation.

Each builder receives one bounded lane and an explicit destination. Concurrent writers get
non-overlapping write sets. Preserve unrelated user changes.

## 4. Evidence and review

Claims stop at evidence: say which gates passed and what remains unverified; never substitute
agreement for reality.

Every reviewed build has three independently sourced lists:

- **Write set:** frozen before work.
- **Actual delta:** derived after work from repository state, including untracked files.
- **Review manifest:** files and content hashes the reviewer actually received.

Require `actual delta ⊆ write set` and `actual delta ⊆ review manifest`. A breach, omission, or hash
mismatch makes the review incomplete.

The reviewer receives the original request, full review set, diff, acceptance criteria, and gate
output—not the builder's reasoning. Findings are `BLOCKER`, `MATERIAL`, `MINOR`, or `NOT PROVEN` and
must include a failure mechanism, reproduction path, and suggested repair. Repairs receive a fresh
review.

## 5. Adjudication

The builder answers each finding with `ACCEPT` or `DISPUTE` and evidence. Cap a dispute at two
builder-reviewer rounds. Unresolved requirements or evidence forks go to the user; model consensus
does not create authority.

## 6. Transport and permissions

- Persistent MCP start tools create fresh seats; reply tools continue the same lineage.
- Raw vendor CLIs are fallback transport, not the default.
- External seats are read-only by default.
- A write-capable external call requires an explicit project `cwd`, a fenced ticket, and the
  wrapper's write flag. Never widen permissions merely to avoid a prompt.
- Registration or a CLI version is not reachability evidence. Count a seat only when its tools
  initialize in the current task and its effective lineage is established.

## 7. Cost and reporting

- Included quota is still finite. Meter when readable and never invent a number.
- Credit-billed, surcharged, or otherwise metered calls require the user's applicable allowance.
- Panels and deep/live canaries are consent-gated even when their marginal dollar cost is zero.
- Reports are outcome-first and phone-readable: changed artifacts, exact gates, review status,
  remaining validation, decisions required, and any quota/cost note.

## 8. Status notation

The emoji layer is operational telemetry, not a character system and not proof of identity.

### Seats and transports

- `🟡➤` Codex conductor. Gold marks the role; its effective lineage is still OpenAI.
- `🔵` Codex/OpenAI worker or self-check.
- `🟠` Claude/Anthropic seat.
- `⚫` Grok/xAI seat.
- `🟢` Gemini/Google lineage, only when the effective brain is established.
- `🟣➤` Cursor transport. Append the selected model lineage; Cursor itself is not a lineage.
- `⚪` user authority.
- `❓` unknown lineage; fails closed for independent review.

### Actions and states

- `🔎` exploring or diagnosing.
- `🔨` building.
- `📝` reviewing.
- `🪞` same-lineage self-check; never present it as independent review.
- `🛡️` independent cross-lineage review.
- `🧪` gates running or gate evidence.
- `🚩` finding raised.
- `⛔` blocked or rejected.
- `⚖️` user ruling required.
- `🏁` user in-hand validation passed.
- `🚢` shipped or deployed.
- `🟤` deliberate hold.

### Cost marks

- `♾️` included plan/quota seat; still finite.
- `💸` metered or credit-billed call.
- `⚠️` cost or allowance unknown; fail closed when spending is possible.

Render seat first, then action: `🟠📝 Claude reviewing`, `🔵🪞 Codex self-checking`,
`🟣➤🟠💸 Claude-on-Cursor reviewing`. The label must name the actual model and action; emojis never
replace plain language.

## Canonical invariant block

```text
CODEX HARNESS INVARIANTS (v1 · doctrine: SPINE.md)
- The producing lineage never independently approves its own work.
- Claims stop at evidence: report gates, not confidence theater.
- Unresolved requirements and evidence forks go to the user.
- The user remains the default merge and deploy authority.
```
