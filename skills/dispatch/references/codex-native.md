# Codex-native dispatch map

## Roles and lineage

| Lane | Transport | Effective lineage | What it is good for |
|---|---|---|---|
| 🟡➤ Conductor | Current Codex task | OpenAI | Planning, fencing, synthesis, gates, user handoff |
| 🔵 Native worker/explorer/reviewer | Codex subagent | OpenAI | Parallel exploration, bounded builds, same-lineage self-checks |
| 🟠 Claude seat | `wmw-claude` MCP | Anthropic | Architecture, root-cause analysis, independent review of OpenAI work |
| ⚫ Grok seat | `wmw-grok` MCP | xAI | UI/art direction, adversarial visual review |
| 🟢 Gemini seat | `wmw-gemini` MCP | Effective brain in footer | Budget build/review, image work; independence only when footer establishes Google lineage |
| 🟣➤ Cursor reserve | `wmw-cursor` MCP | Model family, never Cursor itself | Alien-lineage reserve or explicit bench work; obey allowance and pool guards |

The gold conductor role does not create a new lineage. If the current Codex task or any native
Codex subagent built the work, a fresh Codex subagent is a useful self-check but not independent
review. Use a fresh Claude, Grok, or established-Gemini start call when cross-vendor review matters.
If none is reachable, label the result `REVIEW UNAVAILABLE` or `SOLO-VENDOR DEGRADED`; do not
quietly promote a self-check.

Notation: `🔨` build, `🔎` explore/diagnose, `📝` review, `🪞` same-lineage self-check,
`🛡️` independent review, `🧪` gates, `🚩` finding, `⛔` blocked, `⚖️` user ruling,
`🏁` in-hand validation, `🚢` shipped, `♾️` included quota, `💸` metered, `⚠️` unknown.

## Preflight

Probe tools available in the current task first. Registration in `config.toml` only takes effect
after a Codex restart/new task. A CLI `--version` proves only the fallback path.

Declare only seats whose MCP tools are present and whose effective model lineage is established.
Cursor is a host, not a lineage. Gemini/Antigravity can host non-Google brains; read its footer.

## Routing

- Small, sequential work: conductor handles it inline.
- Read-heavy independent exploration: one native explorer; no cross-vendor call needed.
- Bounded implementation: conductor or one native worker. Add a fresh external reviewer when the
  change is nontrivial.
- Architecture/root cause: fresh Claude is the preferred external judgment seat.
- Code review of OpenAI-built work: fresh Claude or established-Gemini; Grok only when its fit is
  real. Code review of Anthropic-built work: Codex can independently review.
- UI/art direction: Grok. Raster image generation available to Codex should use the image skill;
  external Gemini is optional when the user specifically wants that seat.
- Three or more seats: council rules and explicit consent.

## Ticket

```text
MISSION:
ORIGINAL REQUEST (verbatim):
OBSERVABLE OUTCOME:
BASELINE:
WRITE SET:
PROTECTED INVARIANTS:
VERIFY COMMAND:
ROLLBACK:
DESTINATION:
STATUS FORMAT: DONE | NEEDS_CONTEXT | BLOCKED
```

For an external write-capable seat, pass `always_approve: true` only with an explicit repository
`cwd` inside the ticket's fence. Read-only is the default.

## Review packet

```text
ORIGINAL REQUEST (verbatim):
BUILDER LINEAGE:
REVIEW SET (whole files):
ACTUAL DIFF:
ACCEPTANCE CRITERIA:
VERIFY COMMAND + OUTPUT:

Return first:
REVIEW MANIFEST: <path> <content hash> ...

Then findings:
BLOCKER | MATERIAL | MINOR | NOT PROVEN
<failure mechanism, reproduction path, suggested fix>
```

Do not include the builder's reasoning. A repair receives another fresh review. Stop a dispute
after two builder-reviewer rounds and send the unresolved fork to the user.
