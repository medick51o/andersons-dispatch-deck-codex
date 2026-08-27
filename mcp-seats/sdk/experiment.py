#!/usr/bin/env python3
"""EXPERIMENT — what does the transport actually cost, separated from the vendor?

The first A/B said stdio beat the SDK seat by 20 seconds. That was one sample of a
number dominated by Grok's own latency, which varies by tens of seconds. It measured
the vendor, not the transport, and was therefore close to worthless as evidence.

This isolates the transport. Both seats are exercised on paths that NEVER reach the
vendor CLI -- a guard refusal -- so what remains is exactly the cost each design adds:

  stdio seat   spawn a Python process, MCP initialize handshake, one JSON-RPC round
               trip over a pipe, per CALLER SESSION.
  SDK seat     import the module once, then an in-process await per call.

The honest question this answers: how many calls does a session need before the SDK's
in-process advantage repays the one-time cost of it existing?
"""
import asyncio, importlib.util, json, os, statistics, subprocess, sys, time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
N = 12
# A guard refusal: write-capable with no cwd. Refused before any CLI is located.
# BOTH seats must receive the SAME key. The first run of this experiment passed
# write_capable, which the stdio seat does not know -- so it ignored it, ran read-only,
# and made 12 REAL Grok dispatches while reporting them as "refusals". 20 seconds per
# refusal was the tell. An experiment whose control arm silently does different work
# than its test arm measures nothing.
REFUSE = {"prompt": "x", "always_approve": True}


def stdio_session(calls):
    """Full lifecycle: spawn, handshake, N calls, close. What a host really pays."""
    t0 = time.perf_counter()
    p = subprocess.Popen([sys.executable, "mcp-seats/wmw_grok_mcp.py"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         text=True, encoding="utf-8", bufsize=1)

    def rpc(msg):
        p.stdin.write(json.dumps(msg) + "\n"); p.stdin.flush()
        return json.loads(p.stdout.readline())

    rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "exp"}}})
    startup = time.perf_counter() - t0

    per = []
    for _ in range(calls):
        t = time.perf_counter()
        rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
             "params": {"name": "grok", "arguments": REFUSE}})
        per.append(time.perf_counter() - t)
    p.stdin.close(); p.wait(timeout=15)
    return startup, per


def sdk_session(calls):
    t0 = time.perf_counter()
    spec = importlib.util.spec_from_file_location("gsdk", "mcp-seats/sdk/grok_seat_sdk.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    startup = time.perf_counter() - t0

    async def run():
        out = []
        for _ in range(calls):
            t = time.perf_counter()
            await m.grok_start.handler(dict(REFUSE))
            out.append(time.perf_counter() - t)
        return out
    return startup, asyncio.run(run())


def ms(v):
    return f"{v * 1000:.1f}ms"


print(f"EXPERIMENT — transport cost, vendor excluded ({N} calls per session)\n")
s_start, s_calls = stdio_session(N)
k_start, k_calls = sdk_session(N)

print(f"{'':18}{'startup':>12}{'per call':>12}{'spread':>12}")
print(f"  {'stdio (subprocess)':16}{ms(s_start):>12}{ms(statistics.median(s_calls)):>12}"
      f"{ms(max(s_calls) - min(s_calls)):>12}")
print(f"  {'SDK (in-process)':16}{ms(k_start):>12}{ms(statistics.median(k_calls)):>12}"
      f"{ms(max(k_calls) - min(k_calls)):>12}")

s_med, k_med = statistics.median(s_calls), statistics.median(k_calls)
print(f"\n  per-call advantage to SDK: {ms(s_med - k_med)}")
print(f"  SDK startup penalty:       {ms(k_start - s_start)}")
if s_med > k_med:
    n = (k_start - s_start) / (s_med - k_med)
    print(f"  BREAK-EVEN: the SDK repays its startup after ~{n:.0f} calls in one session")
else:
    print("  stdio is faster per call too; the SDK never repays here")

print(f"\n  For scale, one real Grok dispatch took 6,300ms. Transport is "
      f"{max(s_med, k_med) / 6.3:.2f}% of that.")
print("  Whichever transport wins, the vendor's own latency dominates by ~2 orders of")
print("  magnitude. That is the finding, and it is why the first A/B measured nothing.")
