# Codex Edition setup

## Prerequisites

- Codex desktop or CLI
- Python 3.10 or newer
- Git
- Optional external seats: the corresponding Claude, Grok, Gemini/Antigravity, or Cursor CLI,
  already authenticated on the local machine

The core dispatch skill and native Codex agents do not require any external model CLI.

## Install the Codex policy layer

From the repository root:

```powershell
.\scripts\install.ps1
```

This copies the dispatch skill, native agent profiles, and a profile-readable copy of the spine
to the active Codex home. It does not overwrite the global `AGENTS.md` unless you opt in:

```powershell
.\scripts\install.ps1 -InstallProfile
```

If a different global charter already exists, the installer creates a timestamped backup first.
Set `CODEX_HOME` before running the installer to target a non-default Codex profile.

## Register persistent external seats

Use a real Python executable path on Windows rather than an app-execution alias:

```powershell
$pythonExe = (python -c "import sys; print(sys.executable)")
$seatRoot = (Resolve-Path ".\mcp-seats").Path

codex mcp add wmw-claude -- $pythonExe "$seatRoot\wmw_claude_mcp.py"
codex mcp add wmw-grok -- $pythonExe "$seatRoot\wmw_grok_mcp.py"
codex mcp add wmw-gemini -- $pythonExe "$seatRoot\wmw_gemini_mcp.py"
codex mcp add wmw-cursor -- $pythonExe "$seatRoot\wmw_cursor_mcp.py"
```

Register only the seats whose CLIs you use. Never register `codex mcp-server` back into Codex;
native Codex agents already provide the OpenAI-lineage worker lane.

The wrappers default to read-only. A build becomes write-capable only when the conductor passes
`always_approve: true` with an explicit project `cwd`. Shared guards reject broad system,
profile, credential, and application-data roots.

The Cursor scratch area defaults to `mcp-seats/.playpen/cursor` and is ignored by Git. Override it
with `WMW_CURSOR_PLAYPEN`. Override its spend ledger with `WMW_CURSOR_LEDGER`.

## Verify

```powershell
python -m compileall .\mcp-seats
python .\mcp-seats\armcheck.py
codex mcp list
```

The free armcheck validates protocol startup and argument/path guards. It does not spend tokens
and is not a live behavioral attack. `armcheck.py --deep` makes real vendor calls and costs quota.

Restart Codex after changing global instructions, skills, native agent profiles, or MCP
registrations. A registered MCP entry is not reachability evidence until its tools initialize in
the new task.

## Uninstall

```powershell
.\scripts\uninstall.ps1
```

Add `-RemoveProfile` to remove the global charter only when it still exactly matches the tracked
profile. The script leaves modified user-owned files and timestamped backups alone.

Remove optional MCP registrations separately:

```powershell
codex mcp remove wmw-claude
codex mcp remove wmw-grok
codex mcp remove wmw-gemini
codex mcp remove wmw-cursor
```
