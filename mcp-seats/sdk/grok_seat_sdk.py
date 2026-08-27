#!/usr/bin/env python3
"""grok_seat_sdk — the Grok seat rebuilt on the Claude Agent SDK, for comparison.

THE TOOL ARGUMENT IS `always_approve`, MATCHING THE STDIO SEAT EXACTLY. The first draft
of this port called it `write_capable`, which read better and was wrong: a caller passing
always_approve would have had it IGNORED and got a silent read-only call. The seats must be
drop-in interchangeable or the port proves nothing. Caught by an experiment that measured
20 seconds per "refusal" -- the stdio seat was quietly dispatching for real.

WHY THIS EXISTS
A video argued that MCP tool schemas cost ~81.2 tokens per tool per turn and grow with
the server's tool count, while a hand-written SDK harness stays flat. The measured claim
is honest. It is also, for THIS shop, close to irrelevant: the Grok seat publishes two
tools, so the whole exposure is ~162 tokens either way. The 204 Cursor models cost nothing
extra because the model is a PARAMETER, not a tool -- one tool per model would have cost
~16,500 tokens per turn, which is more than the entire method loads.

So this is a LEARNING BUILD, not an optimisation. It answers a different question: what
changes when you own the loop instead of orchestrating through someone else's?

WHAT ACTUALLY DIFFERS
  stdio seat (wmw_grok_mcp.py)   a separate Python process; the host spawns it, frames
                                 cross a pipe as newline-delimited JSON-RPC, and every
                                 call pays process + serialisation overhead.
  this SDK seat                  create_sdk_mcp_server runs the tools IN-PROCESS. No
                                 subprocess to manage, no pipe, and a real stack trace
                                 when something breaks instead of a dead pipe.

WHAT DOES NOT DIFFER, ON PURPOSE
The guards. This imports `safe_write_cwd`, `run_process` and the validators from
`seat_core` -- the same module the stdio seats use. If a guard is wrong it is wrong in
both, and if it is fixed it is fixed in both. Rewriting them here would have recreated the
exact defect the shared core was built to end: a fix that lands on one seat and never
travels. The transport is the experiment; the safety is not.
"""
import asyncio
import json
import os
import sys
import tempfile
from typing import Annotated

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import seat_core as core                                    # noqa: E402
from claude_agent_sdk import tool, create_sdk_mcp_server     # noqa: E402

GROK_TIMEOUT_S = 3600
# The deny list is the load-bearing one: MCPTool stops a read-only seat asking a
# NEIGHBOURING seat to write for it, which was reproduced live on 2026-08-23.
DENY_RULES = ("Write", "Edit", "MultiEdit", "NotebookEdit", "Bash",
              "MCPTool", "WebFetch", "WebSearch")


def _text(body, is_error=False):
    """SDK tool return shape. seat_core's envelopes are JSON-RPC; these are not."""
    out = {"content": [{"type": "text", "text": body}]}
    if is_error:
        out["is_error"] = True
    return out


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


def _find_grok():
    home = os.path.expanduser("~")
    return core.discover_executable((
        os.path.join(home, ".grok", "bin", "grok"),
        os.path.join(home, ".grok", "bin", "grok.cmd"),
    ), "grok")


def _build(prompt, session_id, cwd, model, write_capable, allow_web_search):
    """Assemble argv. Vendor policy stays HERE, exactly as it does in the stdio seat."""
    exe = _find_grok()
    if not exe:
        return None, None, "Grok Build CLI not found — is it installed and logged in?"

    fd, spill = tempfile.mkstemp(prefix="grok_", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(prompt)

    cmd = [exe]
    if session_id:
        cmd += [f"--resume={session_id}"]
    if model:
        cmd += ["-m", model]
    if cwd:
        cmd += ["--cwd", cwd]
    if write_capable:
        cmd += ["--always-approve"]
    else:
        # Read-only is enforced by DENY RULES, not by --sandbox: that sandbox is
        # Landlock/Seatbelt only and fails OPEN on Windows.
        for rule in DENY_RULES:
            cmd += ["--deny", rule]
        # --no-subagents does NOT stop a spawn; removing the tool is the real kill switch.
        cmd += ["--disallowed-tools", "Agent"]
        cmd += ["--permission-mode", "default", "--no-subagents", "--no-memory"]
        if not allow_web_search:
            cmd += ["--disable-web-search"]
    cmd += ["--prompt-file", spill, "--output-format", "json"]
    return cmd, spill, None


async def _dispatch(prompt, session_id=None, cwd=None, model=None,
                    write_capable=False, allow_web_search=False):
    try:
        safe_cwd = core.safe_write_cwd(cwd, write_capable)
    except ValueError as e:
        return _text(f"⚫ REFUSED — {e}", is_error=True)

    cmd, spill, err = _build(prompt, session_id, safe_cwd, model,
                             write_capable, allow_web_search)
    if err:
        return _text(f"⚫ {err}", is_error=True)
    proc, failure = core.run_process(cmd, GROK_TIMEOUT_S, cwd=safe_cwd)
    try:
        if failure:
            return _text(f"⚫ {failure}", is_error=True)
    finally:
        try:
            os.unlink(spill)
        except OSError:
            pass

    data = _extract_json(proc.stdout or "")
    if not data:
        tail = ((proc.stderr or proc.stdout or "").strip() or "no output")[-600:]
        return _text(f"⚫ grok returned no parseable result.\n{tail}",
                                is_error=True)
    reply = str(data.get("text") or data.get("result") or "")
    sid = data.get("sessionId") or session_id or ""
    footer = f"\n\n---\n⚫ [grok-sdk] in-process seat · sessionId: {sid}"
    return _text(core.truncate_reply(reply, 'grok-sdk') + footer)


@tool("grok", "Start a Grok Build session. Read-only unless write_capable is true, which "
              "then REQUIRES an explicit cwd inside a project directory.",
      {"prompt": Annotated[str, "The task or question for Grok."],
       "cwd": Annotated[str, "Working directory. REQUIRED when write_capable is true."],
       "model": Annotated[str, "Optional model id."],
       "always_approve": Annotated[bool, "Allow Grok to write files. Requires cwd."],
       "allow_web_search": Annotated[bool, "Permit web search on a read-only call."]})
async def grok_start(args):
    return await _dispatch(
        args["prompt"], None, args.get("cwd"), args.get("model"),
        bool(args.get("always_approve")), bool(args.get("allow_web_search")))


@tool("grok-reply", "Continue an existing Grok session by sessionId, with full context.",
      {"sessionId": Annotated[str, "sessionId from a previous grok call."],
       "prompt": Annotated[str, "The follow-up message."],
       "cwd": Annotated[str, "Working directory. REQUIRED when write_capable is true."],
       "always_approve": Annotated[bool, "Allow writes. Requires cwd."]})
async def grok_reply(args):
    # A reply may escalate exactly like a fresh call, so it clears the SAME gate.
    # Forgetting this on the Gemini seat was a real finding on 2026-08-24.
    sid = args.get("sessionId") or ""
    try:
        core.safe_uuid(sid, "sessionId")
    except ValueError as e:
        return _text(f"⚫ REFUSED — {e}", is_error=True)
    return await _dispatch(args["prompt"], sid, args.get("cwd"), None,
                           bool(args.get("always_approve")), False)


grok_seat = create_sdk_mcp_server(name="grok-sdk", version="0.1.0",
                                  tools=[grok_start, grok_reply])


async def _selftest():
    """Prove the guards survived the port. No model is called."""
    print("grok_seat_sdk selftest — guards only, no dispatch\n")
    checks = []

    async def expect_refusal(label, coro):
        r = await coro
        ok = bool(r.get("is_error"))
        checks.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    await expect_refusal("write-capable with no cwd refused",
                         _dispatch("x", None, None, None, True))
    await expect_refusal("write-capable inside System32 refused",
                         _dispatch("x", None, os.path.join(sysroot, "System32"), None, True))
    await expect_refusal("write-capable inside APPDATA refused",
                         _dispatch("x", None, os.environ.get("APPDATA", ""), None, True))
    await expect_refusal("reply with a non-UUID sessionId refused",
                         grok_reply.handler({"sessionId": "--always-approve", "prompt": "x"}))
    await expect_refusal("reply escalating with no cwd refused",
                         grok_reply.handler({"sessionId": "01a02b9c-384b-72d0-9c6f-f5ab60147aba",
                                             "prompt": "x", "always_approve": True}))
    print(f"\n  {sum(checks)}/{len(checks)} guards held after the port to SDK")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_selftest()))
