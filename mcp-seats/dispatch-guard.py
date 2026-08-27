#!/usr/bin/env python3
"""dispatch-guard — the controls the 2026-08-24 council said were missing.

    python dispatch-guard.py preflight <repo>      # refuse a dispatch set up to fail
    python dispatch-guard.py yield <repo>          # cost per ACCEPTED change

Two findings drove this, neither of them mine:

  Boss   — the agents had nowhere to put the code. Eleven of thirteen produced zero
           lines into a repo staged deliberately empty. Hence `preflight`.

  Kimi   — "the rig optimizes the vendor's metric, not the shop's." Everything here
           measured spend against an allowance the vendor defines and reports, and
           nothing measured cost per accepted change. Hence `yield`.

A reservation subsystem also lived here and was DELETED 2026-08-24 by a council vote.
It capped concurrent write-capable MCP calls -- a lane that has never burned anything --
while the burn it was built for happened on vendor-hosted lanes it could not see. In one
day it produced dead code, a lock race, a claim that manufactured headroom, and an
ownership check that broke its own CLI. Concurrency is capped by the vendor, or not here.

WHAT THIS CANNOT DO, stated plainly so nobody mistakes it for a fence:
it governs dispatches that pass THROUGH it. Cloud agents, IDE agent mode, the web
dashboard, the mobile app and CI all execute on the vendor's infrastructure and obey
the vendor's settings, not this file. Those lanes are closed in the vendor's control
plane or not at all — see VENDOR-CHECKLIST.md.
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys
import time

HOME = os.path.expanduser("~")


BANNED_STACK = (("maxmode", "true"), ("effort", "xhigh"), ("speed", "fast"))


# ---------------------------------------------------------------- locking


def _now():
    return datetime.datetime.now()


# ---------------------------------------------------------------- preflight
def _git(repo, *args):
    p = subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "").strip()


def preflight(repo, model=None, mode_flags=None, min_files=1):
    """Refuse a dispatch that is set up to produce nothing, or to cost too much.

    This is the boss's finding turned into a gate: an agent with no destination
    still spends at full rate.
    """
    problems, notes = [], []

    if not os.path.isdir(repo):
        return 1, [f"target is not a directory: {repo}"], []

    rc, _ = _git(repo, "rev-parse", "--git-dir")
    if rc != 0:
        problems.append(f"{repo} is not a git repository — no write-set can be verified")
    else:
        rc, out = _git(repo, "ls-files")
        tracked = [l for l in out.splitlines() if l.strip()]
        code = [f for f in tracked
                if os.path.splitext(f)[1].lower() in
                (".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".go", ".rs", ".java",
                 ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt", ".sh", ".ps1")]
        if len(tracked) < min_files:
            problems.append(f"repo has {len(tracked)} tracked files — "
                            f"an agent dispatched here has nowhere to put code "
                            f"(this is the Aug 21-22 failure, exactly)")
        elif not code:
            problems.append(f"repo has {len(tracked)} tracked files but NO source files — "
                            f"staging pad, not a build target")
        else:
            notes.append(f"{len(tracked)} tracked files, {len(code)} source")

        rc, out = _git(repo, "status", "--porcelain")
        if out:
            notes.append(f"{len(out.splitlines())} uncommitted changes present")

    flags = {k.lower(): str(v).lower() for k, v in (mode_flags or {}).items()}
    stacked = [f"{k}={v}" for k, v in BANNED_STACK if flags.get(k) == v]
    if len(stacked) >= 2:
        problems.append("expensive mode stack: " + " + ".join(stacked) +
                        " — measured 5.5x the cheapest included model")
    elif stacked:
        notes.append("surcharged flag: " + stacked[0])

    if model and "-fast" in model.lower():
        notes.append(f"{model} is a FAST tier — measured 3.6x its non-fast twin")

    return (1 if problems else 0), problems, notes


# ---------------------------------------------------------------- reservation


# ---------------------------------------------------------------- yield
FAST_SURCHARGE = ("-fast",)          # measured 3.6x-5.5x their non-fast twins


def find_events_csv():
    """Newest Cursor usage export, if the operator dropped one somewhere obvious.

    Desktop is OneDrive-redirected on this fleet, so it is resolved, never guessed.
    """
    import glob
    home = os.path.expanduser("~")
    spots = [os.path.join(home, "Downloads"),
             os.path.join(home, "OneDrive", "Desktop"),
             os.path.join(home, ".claude", "uploads")]
    hits = []
    for s in spots:
        hits += glob.glob(os.path.join(s, "**", "*usageevents*.csv"), recursive=True)
    return max(hits, key=os.path.getmtime) if hits else None


def load_events(path, since=None):
    """Parse Cursor's per-event usage export — the ONLY meter that sees every lane.

    Our own ledger records what the MCP seats dispatched. This file records what the
    ACCOUNT spent, cloud agents and IDE included, which is precisely the 96% our
    ledger was blind to on 2026-08-24.
    """
    import csv
    rows = []
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            d = (r.get("Date") or "")[:10]
            if since and d < since:
                continue
            model = (r.get("Model") or "(unnamed)").strip()
            try:
                tok = int(r.get("Total Tokens") or 0)
            except ValueError:
                tok = 0
            cost = 0.0
            c = (r.get("Cost") or "").strip()
            if c and c.lower() != "included":
                try:
                    cost = float(c.lstrip("$"))
                except ValueError:
                    pass
            lane = ("cloud-agent" if (r.get("Cloud Agent ID") or "").strip()
                    else "automation" if (r.get("Automation ID") or "").strip()
                    else "interactive")
            rows.append({"date": d, "model": model, "tokens": tok, "cost": cost,
                         "lane": lane, "max": (r.get("Max Mode") or "").strip() == "Yes"})
    return rows


def yield_report(repo, days=7, events_csv=None):
    """Cost per ACCEPTED change — the shop's own metric, not the vendor's."""
    since = (_now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    rc, out = _git(repo, "log", f"--since={since}", "--pretty=%H", "--numstat")
    if rc != 0:
        return 1, f"not a git repo: {repo}"
    added = removed = commits = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            try:
                added += int(parts[0]); removed += int(parts[1])
            except ValueError:
                pass
        elif len(parts) == 1 and len(line) == 40:
            commits += 1


    # Token truth comes from the spend ledger the seats already write, not from
    # hand-entered numbers. A metric nobody has to remember to record is the only
    # kind that survives contact with a real week.
    # Must match where the seat actually writes (it moved out of the playpen today).
    # Reading the old path made this report a confident zero. (Codex, 2026-08-24.)
    ledger = os.environ.get(
        "WMW_CURSOR_LEDGER",
        os.path.join(os.path.expanduser("~"), ".anderson-method", "bench-spend.jsonl"))
    calls, toks = 0, 0
    if os.path.exists(ledger):
        for line in io.open(ledger, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ts", "") < since:
                continue
            calls += 1
            # _log_spend writes these at the TOP level, not nested under "usage".
            # Expecting the wrong shape made every row count as zero tokens.
            u = r.get("usage") if isinstance(r.get("usage"), dict) else r
            toks += sum(int(u.get(k, 0) or 0) for k in
                        ("inputTokens", "outputTokens", "cacheReadTokens",
                         "in", "out", "cache_read"))

    L = [f"YIELD — {os.path.basename(os.path.abspath(repo))}, last {days} days",
         "",
         f"  ACCEPTED OUTPUT:  {commits} commits, +{added}/-{removed} lines"]

    # ---- vendor ground truth, if an export is available ------------------
    ev = load_events(events_csv, since) if events_csv else []
    if ev:
        etok = sum(e["tokens"] for e in ev)
        ecost = sum(e["cost"] for e in ev)
        L.append(f"  ACCOUNT SPEND:    {len(ev)} events, {etok:,} tokens"
                 + (f", ${ecost:,.2f} billed" if ecost else " (all within included limits)"))
        if added and etok:
            L += ["", f"  >>> COST PER ACCEPTED LINE: {etok/added:,.0f} tokens <<<"]
        elif added and not etok:
            L += ["", "  (export contained no billable tokens — nothing to divide)"]
        else:
            L += ["", "  >>> COST PER ACCEPTED LINE: UNDEFINED — real spend, NO accepted",
                  "      output in this repo. The failed-work multiplier."]

        lanes = {}
        for e in ev:
            d = lanes.setdefault(e["lane"], [0, 0])
            d[0] += 1
            d[1] += e["tokens"]
        L += ["", "  BY LANE (this is what the seat ledger cannot see):"]
        for lane, (n, t) in sorted(lanes.items(), key=lambda x: -x[1][1]):
            gov = "guarded" if lane == "interactive" else "VENDOR-SIDE, ungoverned here"
            L.append(f"    {lane:14} {n:>5} events  {t:>13,} tok  {t/etok*100:>5.1f}%   {gov}")

        fast = [e for e in ev if any(s in e["model"] for s in FAST_SURCHARGE)]
        if fast:
            ft = sum(e["tokens"] for e in fast)
            L += ["", f"  ⚠ SURCHARGED FAST TIERS: {ft:,} tok ({ft/etok*100:.1f}% of spend)",
                  "    Fast tiers measured 3.6x-5.5x their non-fast twins. Same work,",
                  "    same models, a fraction of the bill if the default is changed."]
        mx = [e for e in ev if e["max"]]
        if mx:
            L.append(f"  ⚠ MAX MODE: {sum(e['tokens'] for e in mx):,} tok on top of the above")

        top = sorted({e["model"] for e in ev},
                     key=lambda m: -sum(e["tokens"] for e in ev if e["model"] == m))[:5]
        L += ["", "  TOP MODELS:"]
        for m in top:
            t = sum(e["tokens"] for e in ev if e["model"] == m)
            L.append(f"    {m:32} {t:>13,}  {t/etok*100:>5.1f}%")
    else:
        L.append(f"  SEAT LEDGER ONLY:  {calls} calls, {toks:,} tokens")
        if added and toks:
            L += ["", f"  >>> COST PER ACCEPTED LINE: {toks/added:,.0f} tokens (MCP lane only) <<<"]
        L += ["", "  NO VENDOR EXPORT SUPPLIED — this counts only what the MCP seats",
              "  dispatched. On 2026-08-24 that was 3% of real account spend. Download",
              "  the per-event CSV (vendor usage page -> Export CSV) and pass --events,",
              "  or the number below is your own corner of the bill, not the bill."]

    L += ["", "  Note: git output is local time, vendor events are UTC — a boundary day",
          "  can straddle. Widen --days before drawing a conclusion from one day."]
    return 0, "\n".join(L)


# ---------------------------------------------------------------- cli
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("preflight"); p.add_argument("repo")
    p.add_argument("--model"); p.add_argument("--max-mode", action="store_true")
    p.add_argument("--effort"); p.add_argument("--speed")
    p = sub.add_parser("yield"); p.add_argument("repo"); p.add_argument("--days", type=int, default=7)
    p.add_argument("--events", help="Cursor per-event usage CSV (vendor usage page -> Export CSV). "
                                    "Omit to auto-discover the newest one.")
    p.add_argument("--no-auto", action="store_true", help="do not auto-discover an export")

    a = ap.parse_args()

    if a.cmd == "preflight":
        flags = {"maxmode": a.max_mode, "effort": a.effort, "speed": a.speed}
        rc, problems, notes = preflight(a.repo, a.model, flags)
        for n in notes:
            print(f"  ok   {n}")
        for pr in problems:
            print(f"  STOP {pr}")
        print("\nPREFLIGHT: " + ("REFUSED — fix the above before dispatching."
                                 if rc else "clear."))
        return rc

    if a.cmd == "yield":
        csvp = a.events or (None if a.no_auto else find_events_csv())
        if csvp and not a.events:
            print(f"  (auto-discovered export: {csvp})\n")
        rc, out = yield_report(a.repo, a.days, csvp)
        print(out)
        return rc

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
