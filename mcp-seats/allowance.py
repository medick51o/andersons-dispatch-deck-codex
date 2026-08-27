#!/usr/bin/env python3
"""allowance — the record a metered seat checks before it spends.

    python allowance.py                       # show what is granted
    python allowance.py grant cursor 10/week --days 30
    python allowance.py grant cursor 25/week --forever
    python allowance.py revoke cursor
    python allowance.py check cursor          # exit 0 if a call is permitted

THE COUNCIL SEAT LAW (SPINE v2.5) gates SPENDING, not vendor class. Any seat may
sit on a council; a seat that CAN spend needs a recorded allowance first — asked
once, carrying a bound, and by default expiring, because a yes given once at
midnight should not silently govern next year.

The record lives on the operator's own machine, never in the method's repo, so
nobody inherits another shop's permission. Delete it and every metered seat goes
back to asking.
"""
import datetime
import io
import json
import os
import sys

HOME = os.path.expanduser("~")
STORE = os.environ.get(
    "WMW_ALLOWANCE_FILE",
    os.path.join(HOME, ".anderson-method", "allowances.json"))

DEFAULT_BOUND = "10/week"
DEFAULT_DAYS = 30          # a grant expires unless made permanent, on purpose

WINDOWS = {"day": 1, "week": 7, "month": 30}

def _load():
    try:
        return json.load(io.open(STORE, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def _save(d):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with io.open(STORE, "w", encoding="utf-8", newline="") as f:
        json.dump(d, f, indent=2)

def _parse_bound(text):
    """'10/week' -> (10, 'week'). Raises ValueError on anything else."""
    n, _, window = text.partition("/")
    window = (window or "week").strip().lower().rstrip("s")
    if window not in WINDOWS:
        raise ValueError(f"window must be day, week or month — got {window!r}")
    return int(n), window

def grant(seat, bound=DEFAULT_BOUND, days=DEFAULT_DAYS, forever=False):
    calls, window = _parse_bound(bound)
    d = _load()
    now = datetime.datetime.now()
    d[seat] = {
        "calls": calls,
        "window": window,
        "granted": now.isoformat(timespec="seconds"),
        "expires": None if forever else (now + datetime.timedelta(days=days)).isoformat(timespec="seconds"),
    }
    _save(d)
    return d[seat]

def revoke(seat):
    d = _load()
    existed = d.pop(seat, None) is not None
    _save(d)
    return existed

def snapshot(seat):
    """Return one validated authority record, freshly loaded for this dispatch."""
    refused = {"permitted": False, "reason": "", "calls": 0,
               "window_seconds": 0, "expires": None}
    records = _load()
    grant_record = records.get(seat) if isinstance(records, dict) else None
    if not isinstance(grant_record, dict):
        refused["reason"] = ("no allowance recorded — this seat may not spend. Ask the "
                             f"operator, then: python allowance.py grant {seat} {DEFAULT_BOUND}")
        return refused

    calls, window = grant_record.get("calls"), grant_record.get("window")
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 1:
        refused["reason"] = "allowance has an invalid call bound; re-grant it"
        return refused
    if window not in WINDOWS:
        refused["reason"] = "allowance has an invalid window; re-grant it"
        return refused

    expires = grant_record.get("expires")
    if expires is not None:
        if not isinstance(expires, str):
            refused["reason"] = "allowance has an unreadable expiry; re-grant it"
            return refused
        try:
            expiry = datetime.datetime.fromisoformat(expires)
        except ValueError:
            refused["reason"] = "allowance has an unreadable expiry; re-grant it"
            return refused
        if expiry < datetime.datetime.now(expiry.tzinfo):
            refused["reason"] = (f"the allowance expired on {expires[:10]} — grants expire "
                                 "on purpose. Re-ask the operator, then re-grant.")
            refused["expires"] = expires
            return refused

    return {"permitted": True,
            "reason": f"{calls} calls per {window}" + (
                "" if expires is None else f", until {expires[:10]}"),
            "calls": calls, "window_seconds": WINDOWS[window] * 86400,
            "expires": expires}


def status(seat):
    """Return (permitted, reason) from a fresh validated snapshot."""
    record = snapshot(seat)
    return record["permitted"], record["reason"]


def window_seconds(seat, fallback=600):
    """Return the validated grant window in seconds, or the caller's fallback."""
    record = snapshot(seat)
    return record["window_seconds"] if record["permitted"] else fallback

def main():
    a = sys.argv[1:]
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if not a or a[0] == "show":
        d = _load()
        print(f"ALLOWANCES  ({STORE})\n")
        if not d:
            print("  none recorded — every metered seat will ask before it spends.")
            return
        for seat in sorted(d):
            ok, why = status(seat)
            print(f"  {'OK  ' if ok else 'STOP'}  {seat:12} {why}")
        return

    cmd = a[0]
    if cmd == "grant":
        if len(a) < 2:
            print("usage: allowance.py grant <seat> [N/window] [--days N | --forever]"); return 2
        seat = a[1]
        bound = a[2] if len(a) > 2 and not a[2].startswith("--") else DEFAULT_BOUND
        forever = "--forever" in a
        days = DEFAULT_DAYS
        if "--days" in a:
            days = int(a[a.index("--days") + 1])
        g = grant(seat, bound, days, forever)
        when = "never expires" if g["expires"] is None else f"expires {g['expires'][:10]}"
        print(f"granted: {seat} may spend {g['calls']} calls per {g['window']} ({when})")
        return

    if cmd == "revoke":
        if len(a) < 2:
            print("usage: allowance.py revoke <seat>"); return 2
        print(f"revoked: {a[1]}" if revoke(a[1]) else f"no allowance was recorded for {a[1]}")
        return

    if cmd == "check":
        if len(a) < 2:
            print("usage: allowance.py check <seat>"); return 2
        ok, why = status(a[1])
        print(("PERMITTED — " if ok else "REFUSED — ") + why)
        return 0 if ok else 1

    print(__doc__)
    return 2

if __name__ == "__main__":
    sys.exit(main() or 0)
