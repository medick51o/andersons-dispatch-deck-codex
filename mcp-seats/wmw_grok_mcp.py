#!/usr/bin/env python3
"""wmw-grok — MCP stdio adapter for the Grok Build CLI."""
import json
import os
import tempfile

import seat_core as core

GROK_TIMEOUT_S = 3600
DENY_RULES = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
              "MCPTool", "WebFetch", "WebSearch")


def find_grok():
    home = os.path.expanduser("~")
    return core.discover_executable((
        os.path.join(home, ".grok", "bin", "grok.exe"),
        os.path.join(home, ".grok", "bin", "grok"),
        os.path.join(home, ".local", "bin", "grok"),
    ), "grok")


def _extract_json(raw):
    """First complete object wins; Grok may print a banner before its JSON."""
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


def run_grok(prompt, session_id=None, cwd=None, model=None, always_approve=False,
             allow_web_search=False):
    exe = find_grok()
    if not exe:
        return True, "grok CLI not found on PATH or in ~/.grok/bin — is Grok Build installed?"
    if cwd and not os.path.isdir(cwd):
        return True, f"cwd is not a directory: {cwd}"

    prompt_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md",
                                         delete=False) as handle:
            handle.write(prompt)
            prompt_path = handle.name

        # Vendor policy stays explicit here. Grok's sandbox fails open on Windows;
        # deny rules are the read-only boundary, including cross-seat MCP laundering.
        command = [exe]
        if session_id:
            command += [f"--resume={session_id}"]
        if model:
            command += ["-m", model]
        if cwd:
            command += ["--cwd", cwd]
        if always_approve:
            command += ["--always-approve"]
        else:
            for rule in DENY_RULES:
                command += ["--deny", rule]
            command += ["--disallowed-tools", "Agent", "--permission-mode", "default",
                        "--no-subagents", "--no-memory"]
            if not allow_web_search:
                command += ["--disable-web-search"]
        command += ["--prompt-file", prompt_path, "--output-format", "json"]
        proc, failure = core.run_process(command, GROK_TIMEOUT_S)
    finally:
        if prompt_path:
            try:
                os.unlink(prompt_path)
            except OSError:
                pass

    if failure:
        if failure.kind == "timeout":
            return True, f"grok timed out after {GROK_TIMEOUT_S}s"
        return True, f"could not launch grok: {failure.detail}"

    raw, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    data = _extract_json(raw)
    if data is None:
        return True, (f"grok exited {proc.returncode} with no parseable JSON.\n"
                      f"stdout: {raw[:2000]}\nstderr: {err[:2000]}")
    if data.get("type") == "error":
        return True, f"grok error: {data.get('message', '(no message)')}\nstderr: {err[:1000]}"
    text, session_id = data.get("text"), data.get("sessionId")
    if proc.returncode != 0 or not isinstance(session_id, str) or not session_id:
        return True, (f"grok run failed (exit {proc.returncode}, sessionId={session_id!r}).\n"
                      f"text: {str(text)[:1000]}\nstderr: {err[:1000]}")
    text = core.truncate_reply(text, "wmw-grok")
    model_used = next(iter(data.get("modelUsage") or {}), "unknown-model")
    return False, (text + f"\n\n---\n[wmw-grok] sessionId: {session_id} · "
                    f"model: {model_used} · turns: {data.get('num_turns', '?')}")


TOOLS = [
    {
        "name": "grok",
        "description": (
            "Start a NEW persistent conversation with Grok (Grok Build CLI, xAI subscription seat). "
            "Returns Grok's reply plus a sessionId footer. To continue the same conversation with "
            "full context, call grok-reply with that sessionId. DEFAULT IS READ-ONLY: file writes, "
            "edits and shell are denied, and web search is off unless allow_web_search is true. "
            "Set always_approve true ONLY for build tickets — it lets Grok write files and run "
            "commands under cwd. Use for build dispatches, research, and council seats."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "The task or message for Grok."},
            "cwd": {"type": "string", "description": "Working directory for the session (repo path for build work). Required when always_approve is true; must not be a home/system directory."},
            "model": {"type": "string", "description": "Optional Grok model ID override."},
            "always_approve": {"type": "boolean", "description": "DANGEROUS: auto-approve all of Grok's tool use, including file writes and shell commands under cwd. Required for build work; default false = deny-listed read-only."},
            "allow_web_search": {"type": "boolean", "description": "Allow web search/fetch on a read-only call (default false; ignored when always_approve is true)."},
        }, "required": ["prompt"]},
    },
    {
        "name": "grok-reply",
        "description": (
            "Continue an existing Grok conversation by sessionId (from a prior grok call's footer). "
            "Grok retains the full prior context of that session."
        ),
        "inputSchema": {"type": "object", "properties": {
            "sessionId": {"type": "string", "description": "The sessionId returned by a previous grok/grok-reply call."},
            "prompt": {"type": "string", "description": "The follow-up message."},
            "cwd": {"type": "string", "description": "Working directory. REQUIRED when always_approve is true; must not be a home, system or credential directory."},
            "always_approve": {"type": "boolean", "description": "Auto-approve Grok's tool use this turn (file writes, shell). Requires cwd."},
        }, "required": ["sessionId", "prompt"]},
    },
]


def _tool_call(name, args):
    if name not in ("grok", "grok-reply"):
        return None
    approve = core.optional_boolean(args, "always_approve")
    cwd = core.safe_write_cwd(
        core.safe_argv_string(core.optional_string(args, "cwd"), "cwd"), approve)
    return run_grok(
        core.required_string(args, "prompt"),
        session_id=(core.safe_uuid(args.get("sessionId"), "sessionId")
                    if name == "grok-reply" else None),
        cwd=cwd,
        model=(core.safe_argv_string(core.optional_string(args, "model"), "model")
               if name == "grok" else None),
        always_approve=approve,
        allow_web_search=core.optional_boolean(args, "allow_web_search"),
    )


def main():
    core.serve("wmw-grok", "1.6.0", TOOLS, _tool_call)


if __name__ == "__main__":
    main()
