"""Per-app simulation: which hosts each app contacted, and which would be blocked.

usage: python analyze.py CAPTURE.jsonl SWEEP_LOG.tsv EXEC_MAP.json LIST.txt REFERENCE.txt OUT.json
"""
import bisect
import json
import sys
from collections import defaultdict

cap_path, sweep_path, exec_path, list_path, ref_path, out_path = sys.argv[1:7]


def load_rules(path):
    block, wild, exact = set(), set(), set()
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line.startswith("@@||") and line.endswith("^"):
            wild.add(line[4:-1])
        elif line.startswith("@@|") and line.endswith("^"):
            exact.add(line[3:-1])
        elif line.startswith("||") and line.endswith("^"):
            block.add(line[2:-1])
    return block, wild, exact


def chain(h):
    parts = h.split(".")
    return [".".join(parts[i:]) for i in range(len(parts))]


blk, wild, exact = load_rules(list_path)
rblk, rwild, rexact = load_rules(ref_path)
wild |= rwild
exact |= rexact


def verdict(h):
    c = chain(h)
    if h in exact or any(x in wild for x in c):
        hit = [x for x in c if x in blk or x in rblk]
        return "allowed-by-exception" if hit else "ok"
    for x in c:
        if x in blk:
            return "BLOCK(new:%s)" % x
        if x in rblk:
            return "BLOCK(adguard:%s)" % x
    return "ok"


exec_map = json.load(open(exec_path))
by_comm = defaultdict(set)
for exe, entries in exec_map.items():
    for bundle, name in entries:
        by_comm[exe[:16]].add(name)
        by_comm[exe[:15]].add(name)

launches = []
for line in open(sweep_path):
    parts = line.rstrip("\n").split("\t")
    if len(parts) >= 4:
        launches.append((float(parts[0]), parts[3]))
launches.sort()
times = [t for t, _ in launches]
last_launch = defaultdict(list)
for t, name in launches:
    last_launch[name].append(t)


def resolve(proc, t):
    names = by_comm.get(proc)
    if not names:
        return None
    if len(names) == 1:
        return next(iter(names))
    # several apps share an executable name (Flutter apps are all "Runner"): pick the one opened last
    best, best_t = None, -1
    for n in names:
        for lt in last_launch.get(n, []):
            if lt <= t + 1 and lt > best_t:
                best, best_t = n, lt
    return best or "/".join(sorted(names))

apps = defaultdict(lambda: defaultdict(set))  # app -> host -> kinds
for line in open(cap_path):
    r = json.loads(line)
    host = r.get("host") or ""
    if not host or host.endswith(".arpa") or "." not in host:
        continue
    proc = r.get("proc") or ""
    app = resolve(proc, r["t"])
    kind = r["kind"]
    if app is None and kind == "dns":
        i = bisect.bisect_right(times, r["t"]) - 1
        if i >= 0 and r["t"] - times[i] < 12:
            app = launches[i][1] + " (dns, window)"
    if app is None:
        app = "[system] " + (proc or "?")
    apps[app][host].add(kind)

report = {}
for app, hosts in sorted(apps.items()):
    rows = []
    for h, kinds in sorted(hosts.items()):
        rows.append({"host": h, "kinds": sorted(kinds), "verdict": verdict(h)})
    report[app] = rows
json.dump(report, open(out_path, "w"), indent=1, ensure_ascii=False)

for app, rows in report.items():
    flagged = [r for r in rows if r["verdict"] != "ok"]
    print(f"\n== {app}  ({len(rows)} hosts, {sum(r['verdict'].startswith('BLOCK') for r in rows)} blocked)")
    for r in flagged:
        print(f"   {r['verdict']:40s} {r['host']}  {','.join(r['kinds'])}")
