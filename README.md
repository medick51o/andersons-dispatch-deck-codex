# Anderson's Dispatch Deck — Codex Edition 🟡➤

A Codex-first orchestration harness for substantial coding missions. Codex is the conductor;
native Codex agents are OpenAI-lineage workers, and optional Claude, Grok, Gemini, and Cursor
CLI adapters provide persistent external seats when a genuinely independent lane helps.

This repository is intentionally separate from
[andersons-dispatch-deck](https://github.com/medick51o/andersons-dispatch-deck), which remains the
Claude Code edition. The repositories do not share history, configuration, or release branches.

## What is included

- `SPINE.md` — orchestration doctrine, gates, lineage rules, and the emoji notation.
- `skills/dispatch/` — the Codex dispatch skill.
- `agents/` — bounded native explorer and reviewer profiles.
- `mcp-seats/` — persistent stdio MCP adapters for optional external model CLIs.
- `profile/AGENTS.md` — an optional global Codex conductor charter.
- `missions/`, `handoffs/`, and `scratch/` — durable control-room work areas.

## Quick start

```powershell
git clone https://github.com/medick51o/andersons-dispatch-deck-codex.git
Set-Location .\andersons-dispatch-deck-codex

# Installs the skill and native agent profiles. Add -InstallProfile if you also
# want the global conductor charter; an existing AGENTS.md is backed up first.
.\scripts\install.ps1
```

Restart Codex after installing skills, agents, or MCP registrations. For ordinary coding, open
the actual project repository as the Codex workspace. Open this repository when the mission spans
projects or when the dispatch deck itself owns the work.

External seats are optional. See [SETUP.md](SETUP.md) for CLI prerequisites, MCP registration,
verification, environment overrides, and uninstall instructions.

## Dispatch notation

`🟡➤` Codex conductor · `🔵` Codex/OpenAI worker · `🟠` Claude · `⚫` Grok · `🟢` Gemini ·
`🟣➤` Cursor transport · `⚪` user · `❓` unknown lineage

`🔎` explore · `🔨` build · `📝` review · `🪞` same-lineage self-check ·
`🛡️` independent review · `🧪` gates · `🚩` finding · `⛔` blocked ·
`⚖️` ruling · `🏁` user validation · `🚢` shipped

The complete rules live in [SPINE.md](SPINE.md).

## Release boundary

The free armcheck validates adapter startup and path/argument guards without calling a model:

```powershell
python -m compileall .\mcp-seats
python .\mcp-seats\armcheck.py
```

`armcheck.py --deep` makes live vendor calls and consumes quota. Run it only with deliberate
spend authorization.

## License and provenance

Copyright © 2026 medick51o. All rights reserved. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
