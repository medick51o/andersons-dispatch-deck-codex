#!/usr/bin/env python3
"""Shared transport, validation, path safety, and process boundary for MCP seats."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


MAX_REPLY_CHARS = 400_000
_UUID_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_MODEL_ID_RE = re.compile(r"\A[a-z0-9][a-z0-9._-]{0,63}\Z")
_CREDENTIAL_SEGMENTS = {
    ".ssh", ".aws", ".grok", ".gemini", ".claude", ".cursor",
    ".config", ".azure", ".kube", ".gnupg",
}

def required_string(args, key):
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty string")
    return value


def optional_string(args, key):
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' must be a non-empty string when given")
    return value


def optional_boolean(args, key):
    value = args.get(key)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ValueError(f"'{key}' must be a boolean")


def safe_uuid(value, label):
    if not isinstance(value, str) or not _UUID_RE.match(value):
        raise ValueError(f"'{label}' must be a UUID as returned in a prior reply footer")
    return value


def safe_argv_string(value, label):
    """Validate an optional free-form string before placing it in argv."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value.lstrip().startswith("-"):
        raise ValueError(f"'{label}' must be a non-empty string that does not start with '-'")
    return value


def is_model_id(value):
    return isinstance(value, str) and bool(_MODEL_ID_RE.match(value.strip().lower()))


def safe_model_id(value, label="model"):
    if value is None:
        return None
    if not is_model_id(value):
        raise ValueError(f"'{label}' must be a plain model id such as 'composer-2.5' "
                         "(letters, digits, dot, dash, underscore only)")
    return value.strip().lower()


def truncate_reply(value, seat, limit=MAX_REPLY_CHARS):
    text = value if isinstance(value, str) else ("" if value is None else str(value))
    if len(text) > limit:
        return text[:limit] + f"\n\n[{seat}] ...truncated at {limit} chars]"
    return text


def discover_executable(candidates, path_name):
    """Prefer adapter-declared absolute installs; use PATH only as a fallback."""
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return shutil.which(path_name)


@dataclass(frozen=True)
class ProcessFailure:
    kind: str
    detail: str


def run_process(argv, timeout_s, cwd=None, input_text=None):
    """The single subprocess timeout/launch boundary used by every seat."""
    try:
        kwargs = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout_s,
            "cwd": cwd,
        }
        if input_text is None:
            kwargs["stdin"] = subprocess.DEVNULL
        else:
            kwargs["input"] = input_text
        proc = subprocess.run(argv, **kwargs)
        return proc, None
    except subprocess.TimeoutExpired:
        return None, ProcessFailure("timeout", f"timed out after {timeout_s}s")
    except OSError as exc:
        return None, ProcessFailure("launch", str(exc))


def _normalized(path):
    return os.path.normpath(os.path.realpath(path)).casefold()


def _within(child, parent):
    child_norm, parent_norm = _normalized(child), _normalized(parent)
    try:
        return os.path.commonpath([child_norm, parent_norm]) == parent_norm
    except ValueError:  # different drives
        return False


def safe_write_cwd(cwd, write_capable, safe_exceptions=()):
    """Return a resolved cwd after applying the union of all seat write guards.

    Read-only calls do not acquire generic vendor policy here; they only receive a
    normalized cwd. Vendor-specific read-only enforcement remains in each adapter.
    """
    if not write_capable:
        return os.path.realpath(cwd) if cwd else None
    if cwd is None:
        raise ValueError("a write-capable session requires an explicit cwd naming the "
                         "project directory the seat may write in")

    real = os.path.realpath(cwd)
    if not os.path.isdir(real):
        raise ValueError(f"cwd is not a directory: {cwd}")

    # Adapter-declared sandboxes (Cursor's playpen) are intentionally allowed.
    for exception in safe_exceptions:
        if exception and _within(real, exception):
            return real

    anchor = Path(real).anchor
    if anchor and _normalized(real) == _normalized(anchor):
        raise ValueError("refusing a write-capable session at the filesystem root — "
                         "point cwd at a project directory")

    for env_name in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)",
                     "ProgramData"):
        root = os.environ.get(env_name)
        if root and _within(real, root):
            raise ValueError("refusing a write-capable session inside a system directory "
                             f"({root}) — point cwd at a project directory")

    # These contain credentials and the installed CLIs. Containment is deliberate:
    # equality-only checks once allowed APPDATA/System32 descendants.
    for env_name in ("APPDATA", "LOCALAPPDATA"):
        root = os.environ.get(env_name)
        if root and _within(real, root):
            raise ValueError(f"refusing a write-capable session at or inside {env_name} — "
                             "credentials and the CLIs themselves live there")

    # Gemini learned that a profile subtree, not just the profile root, is unsafe.
    profile_roots = {os.path.expanduser("~")}
    if os.environ.get("USERPROFILE"):
        profile_roots.add(os.environ["USERPROFILE"])
    for root in profile_roots:
        if root and _within(real, root):
            raise ValueError(f"refusing a write-capable session at or inside {root} — "
                             "point cwd at a project directory")

    parts = {part.casefold() for part in Path(real).parts}
    for secret in _CREDENTIAL_SEGMENTS:
        if secret in parts:
            raise ValueError(f"refusing a write-capable session inside {secret}")
    return real


def configure_utf8_stdio():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def result_envelope(request_id, is_error, text):
    return {
        "jsonrpc": "2.0", "id": request_id,
        "result": {"content": [{"type": "text", "text": text}], "isError": is_error},
    }


def error_envelope(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def dispatch(msg, server_name, version, tools, tool_call, instructions=None):
    method, request_id = msg.get("method"), msg.get("id")
    if method == "initialize":
        params = msg.get("params", {})
        result = {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": server_name, "version": version},
        }
        if instructions:
            result["instructions"] = instructions
        return {
            "jsonrpc": "2.0", "id": request_id,
            "result": result,
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(args, dict):
            result = (True, "arguments must be an object")
        else:
            try:
                result = tool_call(name, args)
            except ValueError as exc:
                result = (True, f"invalid arguments: {exc}")
        if result is None:
            return error_envelope(request_id, -32602, f"unknown tool: {name}")
        return result_envelope(request_id, *result)
    if "id" in msg:
        return error_envelope(request_id, -32601, f"method not found: {method}")
    return None


def serve(server_name, version, tools, tool_call, startup=None, instructions=None):
    configure_utf8_stdio()
    if startup:
        startup()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            response = error_envelope(None, -32700, "parse error")
        else:
            if not isinstance(msg, dict):
                continue
            try:
                response = dispatch(
                    msg, server_name, version, tools, tool_call,
                    instructions=instructions,
                )
            except Exception as exc:  # one malformed request must not kill the seat
                print(f"[{server_name}] internal error: {exc}", file=sys.stderr)
                response = (error_envelope(msg.get("id"), -32603,
                                           f"internal error: {exc}")
                            if "id" in msg else None)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
