# Codex control room

This repository is the cross-project orchestration home. Use it for mission briefs, dispatch
state, external-seat handoffs, and temporary investigation artifacts. Production code remains in
its own repository.

## Working rules

- Resolve the target repository before changing code. If a task names one project, work from that
  repository root when practical.
- A task launched here does not automatically inherit another repository's `AGENTS.md`. Read the
  target's applicable instruction chain before editing it.
- Put durable cross-project mission state in `missions/<slug>/`.
- Put external model packets and resumable handoffs in `handoffs/<slug>/`.
- Put disposable experiments in `scratch/<slug>/`; never treat scratch output as shipped work.
- Do not copy application repositories into this control room. Pass their actual root as `cwd` to
  builders and MCP seats.
- Use `$dispatch` for substantial multi-lane work. Handle small sequential work directly.
- Keep Codex-native doctrine, skills, agent profiles, and MCP adapters in this repository. Do not
  depend on the separate Claude Code edition.

When a mission spans repositories, every write lane names a target repository, frozen baseline,
non-overlapping write set, verification command, and rollback. Repository-specific gates outrank
control-room defaults.

```text
CODEX HARNESS INVARIANTS (v1 · doctrine: SPINE.md)
- The producing lineage never independently approves its own work.
- Claims stop at evidence: report gates, not confidence theater.
- Unresolved requirements and evidence forks go to the user.
- The user remains the default merge and deploy authority.
```
