#!/usr/bin/env python3
"""wmw-claude — MCP stdio adapter for a persistent Claude Code seat."""

import json
import os

import seat_core as core


CLAUDE_TIMEOUT_S = 3600
READ_ONLY_TOOLS = "Read,Glob,Grep"
WEB_TOOLS = "Read,Glob,Grep,WebSearch,WebFetch"


def find_claude():
    home = os.path.expanduser("~")
    return core.discover_executable((
        os.path.join(home, ".local", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude"),
    ), "claude")


def _extract_json(raw):
    """Return the first complete JSON object; launchers may print a banner first."""
    decoder, index = json.JSONDecoder(), raw.find("{")
    while index != -1:
        try:
            value, _ = decoder.raw_decode(raw[index:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
        index = raw.find("{", index + 1)
    return None


def run_claude(prompt, session_id=None, cwd=None, model=None,
               always_approve=False, allow_web_search=False):
    exe = find_claude()
    if not exe:
        return True, "Claude Code CLI not found on PATH or in ~/.local/bin."
    if cwd and not os.path.isdir(cwd):
        return True, f"cwd is not a directory: {cwd}"

    # Safe mode keeps a blind seat blind: no CLAUDE.md, skills, hooks, plugins,
    # agents, memories, browser, or inherited MCP servers. The prompt and the
    # explicitly selected built-in tools are its entire brief.
    command = [exe, "--print", "--output-format", "json", "--safe-mode",
               "--no-chrome", "--disable-slash-commands"]
    if session_id:
        command += ["--resume", session_id]
    if model:
        command += ["--model", model]
    if always_approve:
        command += ["--dangerously-skip-permissions", "--tools", "default"]
    else:
        command += ["--permission-mode", "plan", "--tools",
                    WEB_TOOLS if allow_web_search else READ_ONLY_TOOLS]

    # Supplying the prompt on stdin avoids Windows' ~32K command-line ceiling.
    proc, failure = core.run_process(
        command, CLAUDE_TIMEOUT_S, cwd=cwd or None, input_text=prompt)
    if failure:
        if failure.kind == "timeout":
            return True, f"Claude timed out after {CLAUDE_TIMEOUT_S}s"
        return True, f"could not launch Claude: {failure.detail}"

    raw, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    data = _extract_json(raw)
    if data is None:
        return True, (f"Claude exited {proc.returncode} with no parseable JSON.\n"
                      f"stdout: {raw[:2000]}\nstderr: {err[:2000]}")

    text, returned_id = data.get("result"), data.get("session_id")
    failed = (proc.returncode != 0 or data.get("is_error") is True or
              data.get("subtype") not in (None, "success") or
              not isinstance(returned_id, str) or not returned_id)
    if failed:
        return True, (f"Claude run failed (exit {proc.returncode}, "
                      f"subtype={data.get('subtype')!r}, session_id={returned_id!r}).\n"
                      f"result: {str(text)[:1500]}\nstderr: {err[:1000]}")

    text = core.truncate_reply(text, "wmw-claude")
    reported = data.get("model") or data.get("model_name")
    brain = reported if isinstance(reported, str) and reported else (
        f"UNREPORTED (requested: {model})" if model else "UNREPORTED")
    usage = data.get("usage") or {}
    footer = (f"\n\n---\n[wmw-claude] sessionId: {returned_id} · "
              f"brain: {brain} · input: {usage.get('inputTokens', '?')} · "
              f"output: {usage.get('outputTokens', '?')}")
    return False, text + footer


TOOLS = [
    {
        "name": "claude",
        "description": (
            "Start a NEW blind Claude Code conversation on the Anthropic subscription seat. "
            "Returns Claude's reply plus a sessionId footer; continue it with claude-reply. "
            "Default is read-only and isolated from Claude customizations/MCP. Set "
            "always_approve true only for a fenced build ticket with an explicit project cwd."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "The complete task or message for Claude."},
            "cwd": {"type": "string", "description": "Project working directory. Required for write-capable calls."},
            "model": {"type": "string", "description": "Optional Claude model ID or installed alias."},
            "always_approve": {"type": "boolean", "description": "DANGEROUS: bypass Claude tool permissions for fenced build work. Requires cwd."},
            "allow_web_search": {"type": "boolean", "description": "Enable WebSearch/WebFetch on a read-only call."},
        }, "required": ["prompt"]},
    },
    {
        "name": "claude-reply",
        "description": (
            "Continue an existing Claude conversation by sessionId. The reply-chain remains "
            "in the same owning-seat lineage and cannot independently review work it touched."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "sessionId": {"type": "string", "description": "sessionId from a prior claude/claude-reply call."},
            "prompt": {"type": "string", "description": "The follow-up message."},
            "cwd": {"type": "string", "description": "Project working directory. Required when always_approve is true."},
            "always_approve": {"type": "boolean", "description": "Bypass Claude tool permissions for this turn. Requires cwd."},
            "allow_web_search": {"type": "boolean", "description": "Enable WebSearch/WebFetch on a read-only follow-up."},
        }, "required": ["sessionId", "prompt"]},
    },
]


def _tool_call(name, args):
    if name not in ("claude", "claude-reply"):
        return None
    approve = core.optional_boolean(args, "always_approve")
    cwd = core.safe_write_cwd(
        core.safe_argv_string(core.optional_string(args, "cwd"), "cwd"), approve)
    return run_claude(
        core.required_string(args, "prompt"),
        session_id=(core.safe_uuid(args.get("sessionId"), "sessionId")
                    if name == "claude-reply" else None),
        cwd=cwd,
        model=(core.safe_argv_string(core.optional_string(args, "model"), "model")
               if name == "claude" else None),
        always_approve=approve,
        allow_web_search=core.optional_boolean(args, "allow_web_search"),
    )


def main():
    core.serve(
        "wmw-claude", "1.0.0", TOOLS, _tool_call,
        instructions=(
            "Claude is an external Anthropic seat. Fresh calls are blind; reply calls preserve "
            "lineage. Read-only is the default. Never count a reply-chain as independent review "
            "of work it touched. Write-capable calls require always_approve plus a fenced cwd."
        ),
    )


if __name__ == "__main__":
    main()
