#!/usr/bin/env python3
"""wmw-gemini — MCP stdio adapter for the Antigravity CLI."""
import json
import os

import seat_core as core

PRINT_TIMEOUT = "60m"
PROC_TIMEOUT_S = 3900
MAX_ARGV_PROMPT = 25_000


def find_agy():
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    return core.discover_executable((
        os.path.join(local, "agy", "bin", "agy.exe"),
        os.path.join(home, ".antigravity", "bin", "agy"),
        os.path.join(home, ".local", "bin", "agy"),
        os.path.join(home, "agy", "bin", "agy"),
    ), "agy")


def _extract_json(raw):
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


def run_gemini(prompt, conversation_id=None, cwd=None, model=None, always_approve=False):
    exe = find_agy()
    if not exe:
        return True, "Antigravity CLI not found (PATH or %LOCALAPPDATA%\\agy\\bin\\agy.exe)."
    if cwd and not os.path.isdir(cwd):
        return True, f"cwd is not a directory: {cwd}"
    if len(prompt) > MAX_ARGV_PROMPT:
        return True, (f"prompt is {len(prompt)} chars; this seat's CLI takes the prompt on the "
                      f"command line and Windows caps that at ~32K. Keep prompts under "
                      f"{MAX_ARGV_PROMPT} chars — write long material to a file and (with "
                      "always_approve: true) ask Gemini to read the file instead.")

    # Antigravity's read-only boundary is its own plan mode. This must stay local:
    # omitting the write flag alone would inherit potentially permissive user settings.
    command = [exe]
    if conversation_id:
        command += [f"--conversation={conversation_id}"]
    if model:
        command += ["--model", model]
    command += (["--dangerously-skip-permissions"] if always_approve
                else ["--mode", "plan"])
    command += ["-p", prompt, "--output-format", "json", "--print-timeout", PRINT_TIMEOUT]
    proc, failure = core.run_process(command, PROC_TIMEOUT_S, cwd=cwd or None)
    if failure:
        if failure.kind == "timeout":
            return True, f"Antigravity timed out after {PROC_TIMEOUT_S}s"
        return True, f"could not launch agy: {failure.detail}"

    raw, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    data = _extract_json(raw)
    if data is None:
        return True, (f"agy exited {proc.returncode} with no parseable JSON.\n"
                      f"stdout: {raw[:2000]}\nstderr: {err[:2000]}")
    text, conversation_id = data.get("response"), data.get("conversation_id")
    status = data.get("status", "unknown")
    if (proc.returncode != 0 or status != "SUCCESS" or
            not isinstance(conversation_id, str) or not conversation_id):
        return True, (f"agy run failed (exit {proc.returncode}, status {status}, "
                      f"conversationId={conversation_id!r}).\n"
                      f"text: {str(text)[:1000]}\nstderr: {err[:1000]}")
    text = core.truncate_reply(text, "wmw-gemini")

    # Only the CLI-reported brain counts; requested model is never promoted to evidence.
    reported = data.get("model") or data.get("model_name")
    brain = reported if isinstance(reported, str) and reported else (
        f"UNREPORTED (requested: {model})" if model else "UNREPORTED")
    footer = (f"\n\n---\n[wmw-gemini] conversationId: {conversation_id} · status: {status}"
              f" · brain: {brain} · turns: {data.get('num_turns', '?')}")
    return False, text + footer


TOOLS = [
    {
        "name": "gemini",
        "description": (
            "Start a NEW conversation with Gemini via the Antigravity CLI (Google "
            "subscription seat). Returns the reply plus a conversationId footer (including the "
            "effective brain — check it before counting this seat as an independent Gemini vote); "
            "continue the same conversation with gemini-reply. Each fresh call is an independent, "
            "blind session. Set always_approve true when Gemini must edit files or run commands "
            "(headless permission prompts otherwise stall the run). Keep prompts under ~25K chars; "
            "put long material in a file for Gemini to read."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "The task or message for Gemini."},
            "cwd": {"type": "string", "description": "Working directory (repo path for build work)."},
            "model": {"type": "string", "description": "Optional model override (agy models lists them; exact-match strings)."},
            "always_approve": {"type": "boolean", "description": "Skip tool-permission prompts. Required for build work; default false."},
        }, "required": ["prompt"]},
    },
    {
        "name": "gemini-reply",
        "description": (
            "Continue an existing Gemini/Antigravity conversation by conversationId (from a "
            "prior gemini call's footer). Gemini retains the full prior context."
        ),
        "inputSchema": {"type": "object", "properties": {
            "conversationId": {"type": "string", "description": "conversationId from a previous gemini/gemini-reply call."},
            "prompt": {"type": "string", "description": "The follow-up message."},
            "cwd": {"type": "string", "description": "Working directory. REQUIRED when always_approve is true."},
            "always_approve": {"type": "boolean", "description": "Skip tool-permission prompts this turn. Requires cwd."},
        }, "required": ["conversationId", "prompt"]},
    },
]


def _tool_call(name, args):
    if name not in ("gemini", "gemini-reply"):
        return None
    approve = core.optional_boolean(args, "always_approve")
    cwd = core.safe_write_cwd(
        core.safe_argv_string(core.optional_string(args, "cwd"), "cwd"), approve)
    return run_gemini(
        core.required_string(args, "prompt"),
        conversation_id=(core.safe_uuid(args.get("conversationId"), "conversationId")
                         if name == "gemini-reply" else None),
        cwd=cwd,
        model=(core.safe_argv_string(core.optional_string(args, "model"), "model")
               if name == "gemini" else None),
        always_approve=approve,
    )


def main():
    core.serve("wmw-gemini", "1.6.0", TOOLS, _tool_call)


if __name__ == "__main__":
    main()
