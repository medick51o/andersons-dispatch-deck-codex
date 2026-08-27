# Persistent external seats for Codex

These stdio MCP adapters let the Codex conductor start and resume conversations with external
model CLIs. They are owned by this standalone Codex Edition harness.

| Effective seat | Server | Start tool | Continue tool |
|---|---|---|---|
| Claude / Anthropic | `wmw-claude` | `claude` | `claude-reply` |
| Grok / xAI | `wmw-grok` | `grok` | `grok-reply` |
| Gemini / reported effective brain | `wmw-gemini` | `gemini` | `gemini-reply` |
| Cursor reserve / selected model lineage | `wmw-cursor` | `cursor` | `cursor-reply` |

Do not register Codex back into itself. Native Codex subagents are the local OpenAI-lineage lane;
a self-MCP hop adds recursion without independent review.

## Registration

From the repository root:

```powershell
$python = (python -c "import sys; print(sys.executable)")
$seats = (Resolve-Path ".\mcp-seats").Path

codex mcp add wmw-claude -- $python "$seats\wmw_claude_mcp.py"
codex mcp add wmw-grok -- $python "$seats\wmw_grok_mcp.py"
codex mcp add wmw-gemini -- $python "$seats\wmw_gemini_mcp.py"
codex mcp add wmw-cursor -- $python "$seats\wmw_cursor_mcp.py"
```

Restart Codex after changing registrations. `codex mcp list` proves configuration; the seat counts
as reachable only after its tools initialize in the current task.

## Transport rules

- Start calls are fresh contexts. Reviews always use a fresh start call.
- Reply calls retain prior context and remain in the owning lineage of work they touched.
- Read-only is the default. Write-capable calls require an explicit project `cwd` and the adapter's
  `always_approve` flag.
- The shared path guard refuses filesystem roots, system areas, user-profile subtrees, credential
  directories, and application-data roots.
- Gemini and Cursor are hosts that may expose different effective brains. Independence follows the
  reported or selected model lineage, not the transport name.
- Cursor credit models retain the allowance and dispatch guards in this folder.

## Verification

```powershell
python -m compileall .\mcp-seats
python .\mcp-seats\armcheck.py
```

The ordinary armcheck is free and validates protocol and argument/path guards. `--deep` makes live
vendor calls, consumes quota, and requires explicit consent. A codeword start/reply acceptance test
is still required before trusting persistence in a production mission.

Undo a registration with `codex mcp remove <server-name>`.
