#!/usr/bin/env python3
"""wmw-cursor — MCP stdio adapter for the metered Cursor Agent model pool."""
import datetime
import io
import json
import os
import sys
import tempfile

# seat_core is loaded from THIS FILE'S directory, never from the working directory.
# The builder originally fell back to $CWD/mcp-seats so armcheck's copied-adapter canary
# could still import it; the cross-vendor reviewer flagged that as the load path for the
# module that IS the guard -- a planted seat_core.py under any cwd would be imported in
# preference to the real one. armcheck now copies seat_core alongside the adapter instead,
# so the fallback is unnecessary as well as unsafe. (Grok review, 2026-08-24.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seat_core as core

CURSOR_TIMEOUT_S = 3600
DEFAULT_MODEL = "composer-2.5"
COUNCIL_LOCK_ON = os.environ.get("WMW_CURSOR_COUNCIL_LOCK", "on").lower() != "off"
PLAYPEN = os.path.abspath(os.environ.get(
    "WMW_CURSOR_PLAYPEN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".playpen", "cursor")))
PROMPTS_DIR = os.path.join(PLAYPEN, "prompts")
# Guard state must not live where the guarded write-capable agent can erase it.
SPEND_LEDGER = os.environ.get(
    "WMW_CURSOR_LEDGER",
    os.path.join(os.path.expanduser("~"), ".anderson-method", "bench-spend.jsonl"))

INCLUDED_PREFIXES = ("composer-", "cursor-grok-")
CREDIT_PREFIXES = ("claude-", "gpt-", "gemini-", "kimi-", "glm-")
YOLO_ALLOWLIST = ("composer-", "cursor-grok-")
METER_MARK = {"INCLUDED": "♾️", "INCLUDED-FAST": "♾️💸",
              "CREDITS": "💸", "CREDITS-FAST": "🚨💳", "UNKNOWN": "⚠️"}
CURSOR_BANNER = "🟣➤"
BLOODLINE_MARK = {
    "Moonshot": "🌙", "Zhipu": "🔷", "Cursor": "🎼", "Anthropic": "🟠",
    "OpenAI": "🔵", "xAI": "⚫", "Google": "🟢", "UNKNOWN": "❓",
}


def _ensure_playpen():
    for directory in (PLAYPEN, PROMPTS_DIR, os.path.join(PLAYPEN, "scratch")):
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            return False
    readme = os.path.join(PLAYPEN, "README.md")
    if not os.path.exists(readme):
        try:
            with io.open(readme, "w", encoding="utf-8", newline="") as handle:
                handle.write("# Cursor's playpen\n\nScratch space for the `wmw-cursor` MCP seat. The seat writes prompt\nhandoffs (`prompts/`), scratch work (`scratch/`) and its spend ledger\nhere so none of that lands in a real project.\n\nSafe to delete when nothing is running; it is recreated on demand.\n")
        except OSError:
            pass
    return True


def yolo_allowed(model_id):
    return (model_id or "").strip().lower().startswith(YOLO_ALLOWLIST)


def meter_class(model_id):
    model = (model_id or "").strip().lower()
    if not model or model == "auto" or not core.is_model_id(model):
        return "UNKNOWN"
    fast = model.endswith("-fast")
    if model.startswith(INCLUDED_PREFIXES):
        return "INCLUDED-FAST" if fast else "INCLUDED"
    if model.startswith(CREDIT_PREFIXES):
        return "CREDITS-FAST" if fast else "CREDITS"
    return "UNKNOWN"


def _lineage(model_id):
    model = (model_id or "").lower()
    for prefix, vendor in (("claude-", "Anthropic"), ("gpt-", "OpenAI"),
                           ("cursor-grok-", "xAI"), ("gemini-", "Google"),
                           ("kimi-", "Moonshot"), ("glm-", "Zhipu"),
                           ("composer-", "Cursor")):
        if model.startswith(prefix):
            return vendor
    return "UNKNOWN"


def _log_spend(model, lineage, klass, usage, session_id, ok, write_capable):
    """Append one observation per launched call; logging never breaks a call."""
    try:
        _ensure_playpen()
        row = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": model, "lineage": lineage, "meter": klass,
            "billable": bool(klass and klass.startswith("CREDITS")),
            "surcharged": bool(klass and klass.endswith("FAST")),
            "in": (usage or {}).get("inputTokens"),
            "out": (usage or {}).get("outputTokens"),
            "cache_read": (usage or {}).get("cacheReadTokens"),
            "session": session_id, "ok": ok, "write_capable": write_capable,
        }
        with io.open(SPEND_LEDGER, "a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception as exc:
        print(f"[wmw-cursor] spend-ledger write failed: {exc}", file=sys.stderr)


def _guard():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_guard_mod", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "dispatch-guard.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception as exc:
        print(f"[wmw-cursor] dispatch-guard unavailable: {exc}", file=sys.stderr)
        return exc  # write dispatches fail closed when the guard cannot load


def _recent_billable(window_s):
    if not os.path.exists(SPEND_LEDGER):
        return 0
    cutoff, count = datetime.datetime.now() - datetime.timedelta(seconds=window_s), 0
    try:
        for line in io.open(SPEND_LEDGER, encoding="utf-8"):
            try:
                row = json.loads(line)
                timestamp = datetime.datetime.fromisoformat(row.get("ts", ""))
            except (json.JSONDecodeError, ValueError):
                continue
            if row.get("billable") and timestamp >= cutoff:
                count += 1
    except OSError:
        return 0
    return count


def find_cursor_agent():
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    return core.discover_executable((
        os.path.join(local, "cursor-agent", "cursor-agent.cmd"),
        os.path.join(home, ".local", "bin", "cursor-agent"),
        os.path.join(home, ".cursor", "bin", "cursor-agent"),
    ), "cursor-agent")


def _extract_json(raw):
    """Last complete result wins because Cursor streams status objects first."""
    decoder, found, index = json.JSONDecoder(), None, raw.find("{")
    while index != -1:
        try:
            value, _ = decoder.raw_decode(raw[index:])
            if isinstance(value, dict) and value.get("type") == "result":
                found = value
            elif isinstance(value, dict) and found is None:
                found = value
        except json.JSONDecodeError:
            pass
        index = raw.find("{", index + 1)
    return found


def run_cursor(prompt, session_id=None, cwd=None, model=None, always_approve=False,
               spend_credits=False):
    chosen, klass = model or DEFAULT_MODEL, meter_class(model or DEFAULT_MODEL)

    if klass == "UNKNOWN":
        return True, (f"{CURSOR_BANNER} ⚠️ REFUSED — '{chosen}' is not a recognised model id, "
                      "or is `auto` (which may route anywhere). Unknown lineage fails closed "
                      "and cannot be unlocked with spend_credits. Name an explicit model: "
                      "composer-2.5 (free) or cursor-grok-4.6-high (free).")
    if klass.startswith("CREDITS") and not spend_credits:
        return True, (f"{CURSOR_BANNER} 🚨 CREDIT GUARD — REFUSED BEFORE SPENDING\n\n"
                      f"'{chosen}' is meter class {klass} ({_lineage(chosen)} lineage). It "
                      "draws Cursor's third-party CREDIT pool. Pass spend_credits: true "
                      "deliberately, or use composer-2.5 / cursor-grok-4.6-high.")
    if always_approve and not yolo_allowed(chosen):
        return True, (f"{CURSOR_BANNER} 🛑 WRITE REFUSED — '{chosen}' is not on the YOLO "
                      "allowlist. Only composer-* and cursor-grok-* may write or execute.")

    allowance_record = None
    if klass.startswith("CREDITS"):
        try:
            import allowance
            allowance_record = allowance.snapshot("cursor")
        except Exception as exc:
            allowance_record = {
                "permitted": False,
                "reason": f"the allowance record could not be read ({exc}); failing closed",
            }
        if not allowance_record["permitted"]:
            return True, (f"{CURSOR_BANNER} 🛑 NO ALLOWANCE — REFUSED BEFORE SPENDING\n\n"
                          f"'{chosen}' bills the third-party credit pool, and "
                          f"{allowance_record['reason']}\n\n"
                          "Free INCLUDED models are unaffected and need no allowance.")
    if klass.startswith("CREDITS") and COUNCIL_LOCK_ON:
        window = allowance_record["window_seconds"]
        recent = _recent_billable(window)
        if recent >= allowance_record["calls"]:
            return True, (f"{CURSOR_BANNER} 🛑 COUNCIL LOCK — REFUSED\n\n{recent} billable "
                          f"Cursor calls already landed in the last {window // 60} minutes, "
                          "at the operator's granted bound. Councils use subscription seats.")

    _ensure_playpen()
    workdir = cwd or PLAYPEN
    if not os.path.isdir(workdir):
        return True, f"cwd is not a directory: {workdir}"

    guard = _guard()
    if isinstance(guard, Exception) and always_approve:
        return True, (f"{CURSOR_BANNER} 🛑 GUARD UNAVAILABLE — WRITE REFUSED\n\n"
                      f"dispatch-guard could not be loaded ({guard}).\n\n"
                      "A write-capable dispatch is refused while its guard is missing.")
    if guard and not isinstance(guard, Exception) and always_approve and cwd:
        rc, problems, _notes = guard.preflight(workdir, model=chosen)
        if rc:
            return True, (f"{CURSOR_BANNER} 🛑 PREFLIGHT REFUSED — dispatch would spend for "
                          "nothing\n\n" + "\n".join(f"  • {p}" for p in problems) +
                          "\n\nPoint the seat at a repo with real source, or run read-only.")

    # Transport discovery comes after every refusal that can be decided locally. This keeps
    # guard canaries meaningful on machines and CI runners that do not install Cursor.
    exe = find_cursor_agent()
    if not exe:
        return True, ("Cursor CLI not found. Install it, then `cursor-agent login`. "
                      "(Windows: %LOCALAPPDATA%\\cursor-agent\\cursor-agent.cmd)")

    # The Windows CLI is a .cmd shim: no caller-controlled string may reach argv.
    spill_path = None
    try:
        fd, spill_path = tempfile.mkstemp(prefix="prompt_", suffix=".md", dir=PROMPTS_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(prompt)
        except OSError as exc:
            return True, f"could not write the prompt handoff file: {exc}"
        pointer = ("Read the file at " + spill_path.replace("\\", "/") +
                   " which contains your full instructions. Follow them exactly and answer "
                   "them directly. Do not modify or delete that file; it is a scratch "
                   "handoff and is cleaned up automatically.")
        if not pointer.isascii():
            return True, ("the prompt handoff path contains non-ASCII characters; set "
                          "WMW_CURSOR_PLAYPEN to a plain ASCII path")

        command = [exe]
        if session_id:
            command += [f"--resume={session_id}"]
        command += ["--model", chosen]
        command += ["--yolo"] if always_approve else ["--mode", "ask", "--trust"]
        # Auto-approved MCPs are an escalation route and bind only after writes are enabled.
        if always_approve:
            command += ["--approve-mcps"]
        command += ["-p", pointer, "--output-format", "json"]
        proc, failure = core.run_process(command, CURSOR_TIMEOUT_S, cwd=workdir)
    finally:
        if spill_path:
            try:
                os.unlink(spill_path)
            except (FileNotFoundError, OSError):
                pass

    if failure:
        if failure.kind == "timeout":
            _log_spend(chosen, _lineage(chosen), klass, None, session_id, False,
                       always_approve)
            return True, f"cursor-agent timed out after {CURSOR_TIMEOUT_S}s"
        return True, f"could not launch cursor-agent: {failure.detail}"

    raw, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    data = _extract_json(raw)
    if data is None and ("Workspace Trust Required" in raw or
                         "Workspace Trust Required" in err):
        _log_spend(chosen, _lineage(chosen), klass, None, session_id, False, always_approve)
        return True, (f"Cursor refused {workdir} as untrusted. Point cwd at a project "
                      "directory you trust, or leave cwd unset to use the playpen.")
    if data is None:
        _log_spend(chosen, _lineage(chosen), klass, None, session_id, False, always_approve)
        return True, (f"cursor-agent exited {proc.returncode} with no parseable JSON.\n"
                      f"stdout: {raw[:2000]}\nstderr: {err[:2000]}")
    if data.get("is_error") or data.get("subtype") not in (None, "success"):
        _log_spend(chosen, _lineage(chosen), klass, data.get("usage"),
                   data.get("session_id") or session_id, False, always_approve)
        return True, (f"cursor-agent reported an error: {str(data.get('result'))[:1500]}\n"
                      f"stderr: {err[:800]}")
    text, returned_id = data.get("result"), data.get("session_id")
    if proc.returncode != 0 or not isinstance(returned_id, str) or not returned_id:
        _log_spend(chosen, _lineage(chosen), klass, data.get("usage"),
                   returned_id or session_id, False, always_approve)
        return True, (f"cursor-agent run failed (exit {proc.returncode}, "
                      f"session_id={returned_id!r}).\nresult: {str(text)[:1000]}\n"
                      f"stderr: {err[:1000]}")

    text, usage = core.truncate_reply(text, "wmw-cursor"), data.get("usage") or {}
    tokens = (f"{usage.get('inputTokens', '?')} in / {usage.get('outputTokens', '?')} out"
              if usage else "usage unreported")
    mark, vendor = METER_MARK.get(klass, "⚠️"), _lineage(chosen)
    pool = ("Cursor Models pool — INCLUDED, no credits spent" if klass == "INCLUDED" else
            "Cursor Models pool — included, but a FAST-tier surcharge applies"
            if klass == "INCLUDED-FAST" else
            "third-party CREDIT pool — billed at API prices")
    _log_spend(chosen, vendor, klass, usage, returned_id, True, always_approve)
    money = ((f"\n{CURSOR_BANNER} {mark} —— THIS CALL SPENT MONEY —— {mark} {CURSOR_BANNER}"
              f"\n   {pool}") if klass.startswith("CREDITS") or
             klass == "INCLUDED-FAST" else "")
    footer = (f"\n\n---\n{CURSOR_BANNER}{BLOODLINE_MARK.get(vendor, '❓')} [wmw-cursor] "
              f"{mark} {vendor} · {chosen}\n   sessionId: {returned_id} · meter: {klass} · "
              f"{tokens}{money}")
    return False, text + footer


_MODEL_NOTE = ("Model id (default composer-2.5 — the free, non-fast door). Free/INCLUDED: "
               "composer-2.5, cursor-grok-4.6-{low,medium,high,xhigh}, cursor-grok-4.5-*. "
               "Metered/CREDITS (need spend_credits): claude-*, gpt-*, gemini-*, kimi-*, "
               "glm-*. `auto` is refused. See BENCH-LEDGER.md; `cursor-agent models` lists all.")
TOOLS = [
    {
        "name": "cursor",
        "description": (
            "Start a NEW persistent conversation on the CURSOR MODEL POOL (Composer 2.5 by "
            "default; Cursor Grok, Codex, Kimi, GLM and other tiers via `model`). Returns the "
            "reply plus a sessionId footer; continue it with cursor-reply. ⚠ THE ONE METERED "
            "SEAT: composer-* and cursor-grok-* are INCLUDED (free); everything else bills "
            "Cursor's credit pool and is refused unless spend_credits is true. DEFAULT IS "
            "READ-ONLY (no code execution, no file writes). Set always_approve true only for "
            "build tickets, and then cwd is REQUIRED. With no cwd the seat works in its own "
            "playpen directory."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "prompt": {"type": "string", "description": "The task or message."},
            "cwd": {"type": "string", "description": "Working directory. REQUIRED when always_approve is true; must not be a home, system or credential directory. Omit to work in the playpen."},
            "model": {"type": "string", "description": _MODEL_NOTE},
            "always_approve": {"type": "boolean", "description": "DANGEROUS: pass --yolo so the agent may write files and run commands under cwd. Default false = read-only."},
            "spend_credits": {"type": "boolean", "description": "Required to reach any THIRD-PARTY model (claude-/gpt-/gemini-/kimi-/glm-), billed at API prices against Cursor's credit pool. Ask the boss first."},
        }, "required": ["prompt"]},
    },
    {
        "name": "cursor-reply",
        "description": (
            "Continue an existing Cursor-pool conversation by sessionId (from a prior cursor "
            "call's footer), with full prior context. Same meter rules apply."
        ),
        "annotations": {"destructiveHint": True, "openWorldHint": True},
        "inputSchema": {"type": "object", "properties": {
            "sessionId": {"type": "string", "description": "sessionId from a previous cursor/cursor-reply call."},
            "prompt": {"type": "string", "description": "The follow-up message."},
            "model": {"type": "string", "description": _MODEL_NOTE},
            "cwd": {"type": "string", "description": "Working directory for this turn."},
            "always_approve": {"type": "boolean", "description": "Pass --yolo for this turn (write-capable); requires cwd."},
            "spend_credits": {"type": "boolean", "description": "Required to reach a third-party (credit-billed) model."},
        }, "required": ["sessionId", "prompt"]},
    },
]


def _tool_call(name, args):
    if name not in ("cursor", "cursor-reply"):
        return None
    approve = core.optional_boolean(args, "always_approve")
    cwd = core.safe_write_cwd(core.optional_string(args, "cwd"), approve, (PLAYPEN,))
    return run_cursor(
        core.required_string(args, "prompt"),
        session_id=(core.safe_uuid(args.get("sessionId"), "sessionId")
                    if name == "cursor-reply" else None),
        cwd=cwd,
        model=core.safe_model_id(core.optional_string(args, "model")),
        always_approve=approve,
        spend_credits=core.optional_boolean(args, "spend_credits"),
    )


def main():
    core.serve("wmw-cursor", "2.7.1", TOOLS, _tool_call, startup=_ensure_playpen)


if __name__ == "__main__":
    main()
