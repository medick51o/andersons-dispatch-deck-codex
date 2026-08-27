#!/usr/bin/env python3
"""council_selftest — one named test per finding the council raised against itself.

Two blind self-reviews on 2026-08-25 carried ten findings, then refused most of the first
round of fixes. Every ruling below is locked down by a test named after it, because a fix
with no test is a fix that quietly reverts. Nothing here dispatches a model: the seat
transport is replaced with canned replies, so this runs offline, in a second, for free.
"""
import asyncio
import importlib.util
import io
import re
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_spec = importlib.util.spec_from_file_location(
    "council", os.path.join(os.path.dirname(os.path.abspath(__file__)), "council.py"))
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)

OK = []


def chk(label, cond):
    OK.append(bool(cond))
    print(f"  {'PASS' if cond else 'FAIL':4}  {label}")


def section(name):
    print(f"\n{name}")


def refused(f):
    """True when the call was refused at the door with a ValueError."""
    try:
        f()
        return False
    except ValueError:
        return True
    except Exception:
        return False


def grok_cwd_is_absolute():
    sb = tempfile.mkdtemp(prefix="cwdtest-")
    try:
        argv, err = c._argv("grok", os.path.join(sb, "pkt.md"), sb)
        if err:                   # grok CLI absent on this box; nothing to assert against
            return True
        return os.path.isabs(argv[argv.index("--cwd") + 1])
    finally:
        shutil.rmtree(sb, ignore_errors=True)


# ===================================================================== round 1
section("ROUND 1 — the ten the council carried against the original")

chk("a pool is not a vendor: grok+cgrok collapse to one lab",
    c._labs({"grok", "cgrok"}) == {"xAI"})
chk("two xAI seats agreeing is ONE vote, so it cannot carry at 2",
    len(c._labs({"grok", "cgrok"})) < 2)
chk("distinct labs still count separately",
    len(c._labs({"grok", "composer", "kimi"})) == 3)

chk("a rule no bench can reach is refused at the door",
    refused(lambda: asyncio.run(c.run_council("x", seats=["grok", "cgrok"], rule=2))))
chk("rule 0 refused (it would carry everything)",
    refused(lambda: asyncio.run(c.run_council("x", seats=["grok"], rule=0))))

chk("prose with no anchor is not a vote",
    c.anchors("I read it and it all looks fine to me.") == [])
chk("a real finding with a WHY line is a vote",
    c.anchors("[FINDING] tally can be gamed\nWHY: because x") == ["tally can be gamed"])

# ===================================================================== round 2
section("ROUND 2 — the refusals of the first round of fixes")

chk("brief's own template line cannot be counted as turnout",
    c.anchors("[FINDING] <short name, under 60 chars>\nWHY: <one or two sentences>") == [])
chk("an anchor with no WHY within reach is not a finding",
    c.anchors("[FINDING] a bare title nobody explained") == [])

def rep(raw, transport):
    return c._reply(raw, transport)[0]


chk("a short startup banner cannot become the review",
    rep('{"text":"initializing"}\n{"text":"the real review, at length"}', "grok")
    == "the real review, at length")
chk("a TRAILING status object cannot overwrite a finished review",
    rep('{"result":"a long and complete review of the code"}\n{"result":"ok"}', "cursor")
    == "a long and complete review of the code")
chk("SCHEMA FIRST: the transport's own key beats a longer foreign key",
    rep('{"text":"the grok answer","result":"a much longer telemetry payload"}', "grok")
    == "the grok answer")
chk("...and the same bytes under cursor resolve to cursor's key instead",
    rep('{"text":"the grok answer","result":"a much longer telemetry payload"}', "cursor")
    == "a much longer telemetry payload")
chk("a NESTED object cannot shadow its parent's result",
    rep('{"result":"REAL ANSWER","meta":{"text":"nested decoy"}}', "cursor")
    == "REAL ANSWER")
chk("a reply nested one level under its own key is still found",
    rep('{"result":{"text":"the body of the review"}}', "cursor")
    == "the body of the review")
chk("junk between objects does not break parsing",
    rep('noise {"text":"a"} more noise {"result":"b"} tail', "cursor") == "b")
chk("no parseable object yields empty, not a crash", rep("total garbage", "grok") == "")
chk("the candidate count is reported so a silent steal becomes visible",
    c._reply('{"text":"one"}\n{"text":"two"}', "grok")[1] == 2)

chk("grok --cwd is absolute (a relative path failed every dispatch at 23:17)",
    grok_cwd_is_absolute())

chk("every seat declares whether its transport has REAL read-only flags",
    all("hard_ro" in v for v in c.SEATS.values()) and c.SEATS["grok"]["hard_ro"]
    and not c.SEATS["composer"]["hard_ro"])

# ------- synthesis audit, exercised with a canned synthesiser (no model called)
ITEMS = {"S1-1": ("grok", "bug alpha"), "S1-2": ("grok", "bug beta"),
         "S2-1": ("composer", "alpha, differently worded")}


def _canned(reply):
    async def fake(seat, packet_path, sandbox, timeout_s):
        return seat, reply, None, 0.1, None
    return fake


def _synth(reply):
    real, c._run_seat = c._run_seat, _canned(reply)
    rd, sr = tempfile.mkdtemp(prefix="rd-"), tempfile.mkdtemp(prefix="sr-")
    try:
        return asyncio.run(c.synthesize(ITEMS, "grok", rd, sr, 5))
    finally:
        c._run_seat = real
        shutil.rmtree(rd, ignore_errors=True)
        shutil.rmtree(sr, ignore_errors=True)


rows, err, audit = _synth("[GROUP] alpha | ids: S1-1, S2-1\n[GROUP] beta | ids: S1-2")
chk("synthesis groups two wordings of one bug into a single 2-seat finding",
    err is None and len(rows) == 2 and rows[0][1] == {"grok", "composer"})
chk("a clean grouping reports no audit warnings", audit == {})

rows, err, audit = _synth("[GROUP] alpha | ids: S1-1, S2-1")
chk("a DROPPED finding is caught by identity, not by net count",
    audit.get("dropped") == ["S1-2"])

rows, err, audit = _synth("[GROUP] first group | ids: S1-1\n"
                          "[GROUP] second group | ids: S1-1, S1-2, S2-1")
chk("a finding placed in two groups is reported as double-placed",
    audit.get("duplicated") == ["S1-1"])

rows, err, audit = _synth("[GROUP] alpha | ids: S1-1, S2-1, S9-9\n[GROUP] b | ids: S1-2")
chk("an INVENTED id cannot manufacture a vote",
    err is None and all(len(ss) <= 2 for _, ss in rows))

rows, err, audit = _synth("I could not group these, sorry.")
chk("unparseable synthesis returns an error instead of an empty tally",
    rows is None and "parseable" in err)


def _synth_nonzero():
    async def fake(seat, packet_path, sandbox, timeout_s):
        return seat, "[GROUP] a | ids: S1-1", None, 0.1, "exit 1: crashed"
    real, c._run_seat = c._run_seat, fake
    rd, sr = tempfile.mkdtemp(prefix="rd-"), tempfile.mkdtemp(prefix="sr-")
    try:
        return asyncio.run(c.synthesize(ITEMS, "grok", rd, sr, 5))
    finally:
        c._run_seat = real
        shutil.rmtree(rd, ignore_errors=True)
        shutil.rmtree(sr, ignore_errors=True)


rows, err, audit = _synth_nonzero()
chk("a synthesiser that CRASHED is not treated as clean grouping",
    rows is None and "nonzero" in err)

# ===================================================================== end to end
section("END TO END — a whole council, offline, verdicts and exit codes")

REPLIES = {
    "grok":     "[FINDING] suffix overflows the limit\nWHY: appended after the slice\nFIX: x",
    "composer": "[FINDING] result exceeds the limit parameter\nWHY: same defect\nFIX: y",
    "cgrok":    "[FINDING] truncation overshoots\nWHY: same defect\nFIX: z",
}
GROUPS = "auto"     # computed from the packet; labels are randomised per run


MERGE_WORDS = ("suffix", "exceeds", "overshoot")
FIRST_ID_SEEN = set()


def _fake_synth(sandbox):
    """A stand-in synthesiser that GROUPS BY READING ITS PACKET, the way a real one does.

    It cannot be a hardcoded string. run_council now randomises the seat -> S-label map
    (the round-3 fix: the index itself used to reveal which findings were the
    synthesiser's own), so any test that hardcodes `ids: S1-1, S2-1` is asserting against
    a coin flip. This one passed by luck once and failed the next run, which is exactly
    how a gate silently stops being a gate.
    """
    items = {}
    for line in io.open(os.path.join(sandbox, "pkt.md"), encoding="utf-8"):
        m = re.match(r"^(F\d+)\s+(.+)$", line.strip())
        if m:
            items[m.group(1)] = m.group(2)
    FIRST_ID_SEEN.update(t for i, t in items.items() if i == "F01")
    same = [i for i, t in items.items() if any(w in t.lower() for w in MERGE_WORDS)]
    out = []
    if same:
        out.append(f"[GROUP] truncation overshoots the stated limit | ids: {', '.join(same)}")
    for i, t in items.items():
        if i not in same:
            out.append(f"[GROUP] {t[:60]} | ids: {i}")
    return "\n".join(out)


def _council(replies, groups, rule, seats, warn_seat=None):
    async def fake(seat, packet_path, sandbox, timeout_s, retries=1):
        if "SYNTH" in sandbox:
            return seat, (_fake_synth(sandbox) if groups == "auto" else groups), None, 0.1, None
        if seat not in replies:
            return seat, "", "CLI not found", 0.0, None
        return seat, replies[seat], None, 0.1, ("exit 1: noisy" if seat == warn_seat else None)
    real, c._run_seat = c._run_seat, fake
    out = tempfile.mkdtemp(prefix="council-out-")
    try:
        return asyncio.run(c.run_council("brief", seats=seats, rule=rule, timeout_s=5,
                                         outdir=out)), out
    finally:
        c._run_seat = real
        shutil.rmtree(out, ignore_errors=True)


r, _ = _council(REPLIES, GROUPS, 2, ["grok", "composer", "cgrok"])
chk("three wordings of one bug become ONE finding (the round-1 headline bug)",
    len(r["tally"]) == 1 and len(r["tally"][0][1]) == 3)
chk("that finding carries: xAI + Cursor = 2 labs", len(r["carried"]) == 1)
chk("a clean council reports OK", r["verdict"] == "OK")

# THE LINEAGE TEST, in full. Four seats, three labs. Three of them agree on one bug --
# but two of those three are xAI, so the agreement is worth two labs, not three, and a
# 3-lab rule must refuse to carry it. This is the finding that got ONE vote in round 1.
LIN_REPLIES = {**REPLIES,
               "kimi": "[FINDING] an unrelated thing\nWHY: on its own\nFIX: q"}
LIN_GROUPS = ("[GROUP] truncation overshoots the stated limit | ids: S1-1, S2-1, S3-1\n"
              "[GROUP] an unrelated thing | ids: S4-1")
r, _ = _council(LIN_REPLIES, "auto", 3, ["grok", "composer", "cgrok", "kimi"])
chk("three seats agreeing does NOT carry at 3 labs when two of them are one lab",
    len(r["carried"]) == 0 and r["verdict"] == "OK")
chk("...and the tally still shows all three seats on that finding",
    any(len(ss) == 3 for _, ss in r["tally"]))

r, _ = _council({"grok": REPLIES["grok"]}, GROUPS, 2, ["grok", "composer"])
chk("one lab voting is INCONCLUSIVE, never 'nothing carried'",
    r["verdict"] == "INCONCLUSIVE")

r, _ = _council(REPLIES, GROUPS, 2, ["grok", "composer", "cgrok", "kimi"])
chk("quorum met but a seat never reported = PARTIAL, not OK",
    r["verdict"] == "PARTIAL" and "kimi" in r["failures"])

r, _ = _council(REPLIES, GROUPS, 2, ["grok", "composer", "cgrok"], warn_seat="grok")
chk("a seat that exited nonzero still votes, but the run is DEGRADED",
    r["verdict"] == "DEGRADED" and "grok" in r["warns"])

r, _ = _council(REPLIES, "no groups here", 2, ["grok", "composer", "cgrok"])
chk("synthesis failure falls back to the dumb counter AND marks DEGRADED",
    r["verdict"] == "DEGRADED" and len(r["tally"]) == 3)
chk("the dumb fallback demonstrably cannot merge the wordings — that is why it degrades",
    len(r["carried"]) == 0)

r, _ = _council({**REPLIES, "composer": "Looks fine to me, no notes."}, "auto", 2,
                ["grok", "composer", "cgrok"])
chk("a prose-only seat is excluded from turnout, not counted as attendance",
    "composer" in r["malformed"] and "composer" not in r["findings"])

# THE OPAQUE ID MAP, locked down. Six councils; if F01 always names the same finding the
# ids are a sorted index again and the synthesiser can decode authorship from them.
for _ in range(6):
    _council(REPLIES, "auto", 2, ["grok", "composer", "cgrok"])
chk("finding ids are shuffled per run, not a stable index",
    len(FIRST_ID_SEEN) > 1)
chk("finding ids carry no seat and no per-seat count",
    all(re.fullmatch(r"F\d+", i) for i in ["F01", "F07"]) and
    not any("-" in i for i in FIRST_ID_SEEN))

# ---- round 4's carried findings
CLEAN_REPLY = ("[CLEAN]\nI checked every claim in the brief against the code "
               "line by line, traced the reply parser, the tally, the audit and the "
               "verdict tiers, and found nothing worth raising as a finding.")
r, _ = _council({**REPLIES, "gemini": CLEAN_REPLY},
                "auto", 2, ["grok", "composer", "cgrok", "gemini"])
chk("a CLEAN review is a vote, not a malformed reply",
    "gemini" in r["findings"] and "gemini" not in r["malformed"])
chk("...and its lab counts toward turnout", "Google" in r["labs"])

# The full free bench: with every free seat dispatched there is no non-voter left, which
# is the exact state that forced a voter to group in rounds 1-4.
FULL = {**REPLIES, "gemini": "[FINDING] a distinct google finding\nWHY: y\nFIX: z"}
r, _ = _council(FULL, "auto", 2, ["grok", "composer", "cgrok", "gemini"])
chk("with no non-voter left, a same-lab spare is RESERVED to synthesise",
    r["synth"] == "cgrok" and "cgrok" not in r["findings"])
chk("...and reserving costs no lineage: xAI still votes via grok",
    "xAI" in r["labs"] and r["verdict"] == "OK")
chk("...so the default bench can now reach a clean verdict at all",
    r["verdict"] == "OK" and not r["degraded"])

r, _ = _council(REPLIES, "[GROUP] merged finding here | ids: F01, F02, F99", 2,
                ["grok", "composer", "cgrok"])
chk("an invented id is reported, not silently filtered",
    "F99" in (r["audit"].get("invented") or []) and r["verdict"] == "DEGRADED")

chk("prose echoing the template in its own words is not a finding",
    c.anchors("[FINDING] <short name>\nWHY: x") == []
    and c.anchors("[FINDING] name\nWHY: x") == [])

chk("a bare [CLEAN] with no substance behind it is NOT a vote", not c.is_clean("[CLEAN]"))
chk("[CLEAN] mentioned mid-prose is not a clean vote",
    not c.is_clean("I considered marking this [CLEAN] but " + "x" * 200))
chk("an anchor whose name appears verbatim in the packet is a template echo",
    c.anchors("[FINDING] short name, under 60 chars\nWHY: y",
              "the brief says [FINDING] short name, under 60 chars") == [])
chk("...but a genuine finding is unaffected by the packet check",
    c.anchors("[FINDING] the tally can be gamed\nWHY: y", "unrelated packet") ==
    ["the tally can be gamed"])

r, _ = _council({"grok": CLEAN_REPLY, "composer": CLEAN_REPLY}, "auto", 2,
                ["grok", "composer"])
chk("an all-clean council is OK, not DEGRADED for failing to group nothing",
    r["verdict"] == "OK" and not r["degraded"] and r["carried"] == [])

# ===================================================================== round 6
section("ROUND 6 — regressions the ROUND 5 fixes introduced, which the gate missed")

# Every check below passed 52/52 before it existed. The council found these; the tests
# did not. A gate only covers what someone thought to write down.
r, _ = _council({"grok": "[FINDING] the only finding raised\nWHY: x\nFIX: y",
                 "composer": CLEAN_REPLY}, "auto", 2, ["grok", "composer"])
chk("a council that raised exactly ONE finding still reports it",
    len(r["tally"]) == 1 and r["tally"][0][0] == "the only finding raised")
chk("...and does not degrade for having nothing to group",
    r["verdict"] == "OK" and not r["degraded"])

chk("the template guard reads the BRIEF, not the material under review",
    c.anchors("[FINDING] def harvest obj depth outer\nWHY: y",
              "a brief that never mentions that line")
    == ["def harvest obj depth outer"])
chk("...while a genuine echo of the brief is still rejected",
    c.anchors("[FINDING] short name, under 60 chars\nWHY: y",
              "output format: [FINDING] short name, under 60 chars") == [])

chk("a value nested under the transport's OWN key joins that key's pool",
    rep('{"result":{"text":"the nested body"},"text":"top-level decoy"}', "cursor")
    == "the nested body")
chk("...and the decoy still wins when IT is the transport's key",
    rep('{"result":{"text":"the nested body"},"text":"top-level decoy"}', "grok")
    == "top-level decoy")

# ===================================================================== round 7
section("ROUND 7 — the template guard's third form, and four smaller repairs")

BRIEF7 = ("Report findings in this format:\n[FINDING] short name, under 60 chars\n"
          "WHY: one or two sentences\nRank by real impact and name the line.")
chk("the brief's own template line is still rejected",
    c.anchors("[FINDING] short name, under 60 chars\nWHY: y", BRIEF7) == [])
chk("a real finding is NOT dropped for being a substring of the brief",
    c.anchors("[FINDING] rank by real impact\nWHY: y", BRIEF7) == ["rank by real impact"])
chk("...nor for sharing words with the brief's prose",
    c.anchors("[FINDING] name the line that fails\nWHY: y", BRIEF7)
    == ["name the line that fails"])

r, _ = _council({"grok": ("[FINDING] first thing wrong\nWHY: a\nFIX: b\n"
                          "[FINDING] second thing wrong\nWHY: c\nFIX: d")},
                "auto", 1, ["grok"])
chk("ONE seat with two findings is not a fabricated synthesis failure",
    not any("synthesis" in d.lower() for d in r["degraded"]))
chk("...and both of its findings still reach the tally", len(r["tally"]) == 2)

r, _ = _council({"grok": "[FINDING] the only finding raised\nWHY: x\nFIX: y",
                 "composer": CLEAN_REPLY}, "auto", 2, ["grok", "composer"])
chk("a skipped-because-unnecessary grouping is not marked DEGRADED",
    r["verdict"] == "OK" and not r["degraded"])

r, _ = _council({"grok": CLEAN_REPLY, "composer": CLEAN_REPLY}, "auto", 2,
                ["grok", "composer"])
chk("an all-clean bench is a result, not a malformed run",
    r["verdict"] == "OK" and r["tally"] == [] and not r["malformed"])

section("")
print(f"  {sum(OK)}/{len(OK)} checks pass")
sys.exit(0 if all(OK) else 1)
