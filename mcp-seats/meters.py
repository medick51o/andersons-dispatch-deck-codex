#!/usr/bin/env python3
"""Read vendor meters, or deliberately spend Cursor allowance to calibrate one.

    python meters.py read [--grok|--cursor] [--json]   # observational only
    python meters.py calibrate cursor --probe          # SPENDS: one call
    python meters.py calibrate cursor --calls 6        # SPENDS: measured burn

The command boundary is intentional: ``read`` never calls a model, while
``calibrate`` consumes real Cursor Models allowance on purpose.
"""
import argparse
import datetime
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

TIMEOUT = 45
CURSOR_USAGE_URL = (
    "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage")
CALIBRATION_MODEL = "composer-2.5"
CALIBRATION_RATE_PER_MTOK = 0.077  # measured percentage points per million tokens
PLAYPEN = os.path.abspath(os.environ.get(
    "WMW_CURSOR_PLAYPEN",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".playpen", "cursor")))


def _get(url, headers, data=None):
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        return json.load(response)


def _as_epoch(value):
    """expires_at may be a unix number or an ISO-8601 string; accept either."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        text = str(value).replace("Z", "+00:00")
        if "." in text:
            head, _, tail = text.partition(".")
            fraction = "".join(ch for ch in tail if ch.isdigit())[:6]
            rest = tail[len(fraction):].lstrip("0123456789")
            text = f"{head}.{fraction}{rest}"
        return datetime.datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return None


def _grok_token(auth):
    for node in auth.values():
        if isinstance(node, dict) and isinstance(node.get("key"), str):
            return node.get("key"), node.get("expires_at")

    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                if isinstance(child, str) and child.count(".") == 2 and len(child) > 100:
                    return child
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return None

    return walk(auth), None


def read_grok():
    path = os.path.expanduser(r"~\.grok\auth.json")
    if not os.path.exists(path):
        return {"error": "no ~/.grok/auth.json — is the Grok CLI logged in?"}
    try:
        with io.open(path, encoding="utf-8") as handle:
            token, expires_at = _grok_token(json.load(handle))
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        return {"error": f"grok auth read failed: {exc}"}
    if not token:
        return {"error": "no bearer token found in ~/.grok/auth.json"}
    expiry = _as_epoch(expires_at)
    if expiry and expiry < time.time():
        age = int(time.time() - expiry)
        return {"error": (f"the CLI's access token expired {age // 60} min ago. It "
                          "refreshes itself on use — run any grok command (e.g. `grok -p "
                          "hi`) and read again.")}
    try:
        data = _get("https://cli-chat-proxy.grok.com/v1/billing?format=credits",
                    {"Authorization": "Bearer " + token, "User-Agent": "grok-cli"})
    except Exception as exc:
        return {"error": f"grok billing request failed: {exc}"}
    config = data.get("config", data)
    return {
        "weekly_percent_used": config.get("creditUsagePercent"),
        "by_product": {item.get("product"): item.get("usagePercent")
                       for item in config.get("productUsage", [])},
        "period_start": str(config.get("billingPeriodStart"))[:19],
        "period_end": str(config.get("billingPeriodEnd"))[:19],
        "prepaid_balance": (config.get("prepaidBalance") or {}).get("val"),
        "on_demand_cap": (config.get("onDemandCap") or {}).get("val"),
    }


def _cursor_usage():
    """Fetch and decode the Cursor dashboard once for all Cursor meter consumers."""
    path = os.path.expandvars(r"%APPDATA%\Cursor\auth.json")
    if not os.path.exists(path):
        raise OSError("no %APPDATA%/Cursor/auth.json — sign in to the Cursor app once")
    token = json.load(io.open(path, encoding="utf-8")).get("accessToken")
    if not token:
        raise ValueError("no accessToken in Cursor auth.json")
    return _get(CURSOR_USAGE_URL, {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Connect-Protocol-Version": "1",
    }, data=b"{}")


def _cursor_raw(data):
    usage = data.get("planUsage", {}) or {}
    return (usage.get("autoPercentUsed") or 0.0,
            usage.get("apiPercentUsed") or 0.0,
            usage.get("totalSpend") or 0)


def read_cursor_raw():
    """Return raw full-precision (auto%, api%, totalSpend_cents)."""
    return _cursor_raw(_cursor_usage())


def read_cursor():
    try:
        data = _cursor_usage()
    except Exception as exc:
        return {"error": f"cursor usage request failed: {exc}"}
    usage = data.get("planUsage", {}) or {}

    def milliseconds(value):
        try:
            return datetime.datetime.fromtimestamp(int(value) / 1000).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            return str(value)

    return {
        "cursor_models_percent_used": usage.get("autoPercentUsed"),
        "other_models_percent_used": usage.get("apiPercentUsed"),
        "total_percent_used": usage.get("totalPercentUsed"),
        "included_spend_usd": (usage.get("includedSpend") or 0) / 100,
        "bonus_spend_usd": (usage.get("bonusSpend") or 0) / 100,
        "total_spend_usd": (usage.get("totalSpend") or 0) / 100,
        "cycle_start": milliseconds(data.get("billingCycleStart")),
        "cycle_end": milliseconds(data.get("billingCycleEnd")),
        "display_message": data.get("displayMessage"),
    }


def read(want_grok=True, want_cursor=True, as_json=False):
    out = {"read_at": datetime.datetime.now().isoformat(timespec="seconds")}
    if want_grok:
        out["grok"] = read_grok()
    if want_cursor:
        out["cursor"] = read_cursor()
    if as_json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"METERS — {out['read_at']}\n")
    grok = out.get("grok")
    if grok:
        if grok.get("error"):
            print(f"  xAI / Grok    : {grok['error']}")
        else:
            print(f"  xAI / Grok    weekly pool {grok['weekly_percent_used']}% used"
                  f"   (resets {grok['period_end'][:10]})")
            for product, percent in (grok.get("by_product") or {}).items():
                print(f"                    {product:14} {percent}%")
            print("                    ONE tank: Build, Chat and Imagine all drain it")
    cursor = out.get("cursor")
    if cursor:
        print()
        if cursor.get("error"):
            print(f"  Cursor        : {cursor['error']}")
        else:
            print(f"  Cursor        cycle {cursor['cycle_start']} -> {cursor['cycle_end']}")
            print(f"                    Cursor Models (free)  "
                  f"{cursor['cursor_models_percent_used']}%   <- Composer + Cursor Grok")
            print(f"                    Other Models (credit) "
                  f"{cursor['other_models_percent_used']}%   <- everything else")
            print(f"                    spend: ${cursor['total_spend_usd']:.2f} total = "
                  f"${cursor['included_spend_usd']:.2f} paid + "
                  f"${cursor['bonus_spend_usd']:.2f} bonus")
            if cursor.get("display_message"):
                print(f"                    vendor says: {cursor['display_message']}")
    return 0


def find_cursor_agent():
    local, home = os.environ.get("LOCALAPPDATA", ""), os.path.expanduser("~")
    for candidate in (os.path.join(local, "cursor-agent", "cursor-agent.cmd"),
                      os.path.join(home, ".local", "bin", "cursor-agent"),
                      os.path.join(home, ".cursor", "bin", "cursor-agent")):
        if os.path.exists(candidate):
            return candidate
    raise SystemExit("cursor-agent not found")


def _burn_once(cli, payload, number):
    os.makedirs(PLAYPEN, exist_ok=True)
    path = os.path.join(PLAYPEN, f"burn-{number}-{number * 7919}.txt")
    with io.open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(f"NONCE {number * 7919}\n\n{payload}")
    prompt = (f"Read the file {path} in full. Then reply with only the word OK and the "
              "nonce at its top. Do not summarize or analyze it.")
    process = subprocess.run(
        [cli, "--model", CALIBRATION_MODEL, "--mode", "ask", "--trust", "-p", prompt,
         "--output-format", "json"], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600)
    try:
        data = json.loads((process.stdout or "").strip())
    except (TypeError, json.JSONDecodeError):
        return None
    usage = data.get("usage") or {}
    return {key: usage.get(key, 0) for key in
            ("inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens")}


def calibrate_cursor(calls):
    cli = find_cursor_agent()
    source_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SPINE.md")
    source = io.open(source_path, encoding="utf-8").read()
    before_auto, before_api, before_spend = read_cursor_raw()
    print(f"BEFORE   cursor-models {before_auto:.9f}%   other {before_api:.9f}%   "
          f"spend {before_spend}c")

    estimated_tokens = calls * (len(source) // 4)
    estimated_percent = estimated_tokens / 1_000_000 * CALIBRATION_RATE_PER_MTOK
    print("\n" + "!" * 72)
    print("!!! SPENDING CURSOR ALLOWANCE — DELIBERATE METERED CALIBRATION !!!")
    print(f"!!! MODEL: {CALIBRATION_MODEL}")
    print(f"!!! ESTIMATED COST: ~{estimated_tokens:,} input tokens across {calls} call(s), "
          f"~{estimated_percent:.6f}% of the included Cursor Models pool")
    print("!!! REAL INCLUDED ALLOWANCE WILL BE CONSUMED; $0 CREDIT SPEND EXPECTED")
    print("!" * 72, flush=True)

    totals = {"inputTokens": 0, "outputTokens": 0,
              "cacheReadTokens": 0, "cacheWriteTokens": 0}
    for index in range(calls):
        usage = _burn_once(cli, source, index)
        if not usage:
            print(f"  call {index + 1}: FAILED (not counted)")
            continue
        for key in totals:
            totals[key] += usage[key]
        print(f"  call {index + 1}: in={usage['inputTokens']:,} "
              f"out={usage['outputTokens']:,} cacheR={usage['cacheReadTokens']:,}")

    time.sleep(20)
    after_auto, after_api, after_spend = read_cursor_raw()
    print(f"AFTER    cursor-models {after_auto:.9f}%   other {after_api:.9f}%   "
          f"spend {after_spend}c")
    billable = (totals["inputTokens"] + totals["outputTokens"] +
                totals["cacheReadTokens"])
    delta_percent, delta_spend = after_auto - before_auto, after_spend - before_spend
    print(f"\nBURNED   {billable:,} tokens (in {totals['inputTokens']:,} / "
          f"out {totals['outputTokens']:,} / cacheR {totals['cacheReadTokens']:,})")
    print(f"NEEDLE   moved {delta_percent:.9f} percentage points; spend +{delta_spend}c")
    if delta_percent <= 0:
        print("\nNeedle did not move — burn more (raise --calls) or the meter lags.")
        return 1
    pool_tokens = billable / (delta_percent / 100.0)
    print(f"\n  POOL SIZE  ~{pool_tokens / 1e6:,.0f}M tokens/month  "
          f"(at {CALIBRATION_MODEL} rates)")
    if delta_spend > 0:
        print(f"  POOL VALUE ~${delta_spend / 100.0 / (delta_percent / 100.0):,.0f}/month")
    print(f"  this burn cost {delta_percent:.4f}% of the month's allowance")
    return 0


def _positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("calls must be at least 1")
    return number


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    read_parser = commands.add_parser("read", help="READ-ONLY vendor meter observation")
    vendor = read_parser.add_mutually_exclusive_group()
    vendor.add_argument("--grok", action="store_true")
    vendor.add_argument("--cursor", action="store_true")
    read_parser.add_argument("--json", action="store_true")

    calibrate = commands.add_parser("calibrate", help="SPENDS allowance deliberately")
    calibrate_vendors = calibrate.add_subparsers(dest="vendor", required=True)
    cursor = calibrate_vendors.add_parser("cursor", help="burn Cursor Models allowance")
    burn = cursor.add_mutually_exclusive_group()
    burn.add_argument("--probe", action="store_true", help="one call, precision check")
    burn.add_argument("--calls", type=_positive_int, default=6)
    return parser


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = _parser().parse_args(argv)
    if args.command == "read":
        return read(not args.cursor, not args.grok, args.json)
    if args.command == "calibrate" and args.vendor == "cursor":
        return calibrate_cursor(1 if args.probe else args.calls)
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    sys.exit(main())
