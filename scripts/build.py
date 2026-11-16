#!/usr/bin/env python3
"""Build a single AdGuard-DNS-syntax blocklist sized for AdGuard for iOS.

Why a single, capped list: AdGuard for iOS runs DNS filtering inside a Network
Extension and gives the filtering engine (DnsLibs) a hard 8 MiB budget for ALL
DNS filters together. Each unique domain rule costs ~16 bytes there, and rules
past the budget are silently dropped. So instead of stacking several Pi-hole
lists (which overflows and loses rules) we merge, de-duplicate, collapse
subdomains and keep the most-agreed-upon domains first.

Safety rules (to avoid breaking apps):
  * never block a public suffix (e.g. com.mx, github.io, cloudfront.net)
  * allowlists (ours + AdGuard's own exceptions + the Pi-hole community
    whitelist) are applied as exception rules
  * every host in lists/protect-hosts.txt must stay resolvable; if an upstream
    list starts blocking one, an exact exception is added automatically
  * the build refuses to publish when a core source fails or the size moves
    abnormally, so the previous good list stays online

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "dns-blocklist-builder/1.0 (+https://github.com)"

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9_])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})$")
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
HOSTS_RE = re.compile(r"^(?:0\.0\.0\.0|127\.0\.0\.1|::1?|0:0:0:0:0:0:0:0)\s+([^\s#]+)")
ADBLOCK_RE = re.compile(r"^(@@)?(\|\||\|)([a-z0-9._*-]+)\^(?:\$(.*))?$")
HOSTS_IGNORE = {
    "localhost", "localhost.localdomain", "local", "broadcasthost", "ip6-localhost",
    "ip6-loopback", "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters",
    "ip6-allhosts", "0.0.0.0",
}


# --------------------------------------------------------------------------- parsing
def normalize_domain(raw: str) -> str | None:
    d = raw.strip().lower().rstrip(".")
    if d.startswith("*."):
        d = d[2:]
    if not d or d in HOSTS_IGNORE or IPV4_RE.match(d) or ":" in d:
        return None
    try:
        d = d.encode("idna").decode("ascii") if not d.isascii() else d
    except UnicodeError:
        return None
    return d if DOMAIN_RE.match(d) else None


def parse_line(line: str, fmt: str, allowed_modifiers: frozenset[str]):
    """Return (kind, domain) where kind is block | allow | allow_exact, or None."""
    line = line.strip()
    if not line or line[0] in "!#[":
        return None
    if fmt == "auto":
        if line.startswith(("||", "@@", "|")):
            fmt = "adblock"
        elif HOSTS_RE.match(line):
            fmt = "hosts"
        else:
            fmt = "domains"
    if fmt == "adblock":
        m = ADBLOCK_RE.match(line.lower())
        if not m:
            return None
        exception, anchor, pattern, mods = m.groups()
        if "*" in pattern:
            return None
        if mods:
            mod_set = {x.strip() for x in mods.split(",") if x.strip()}
            if not mod_set <= allowed_modifiers:
                return None
        d = normalize_domain(pattern)
        if not d:
            return None
        if exception:
            return ("allow" if anchor == "||" else "allow_exact", d)
        if anchor != "||":
            return None  # exact-only block rules are rare; skip rather than over-block
        return ("block", d)
    if fmt == "hosts":
        m = HOSTS_RE.match(line)
        if not m:
            return None
        d = normalize_domain(m.group(1))
        return ("block", d) if d else None
    if fmt == "domains":
        token = line.split()[0].split("#")[0]
        d = normalize_domain(token)
        return ("block", d) if d else None
    if fmt == "allow-domains":  # Pi-hole style exact whitelist
        token = line.split()[0].split("#")[0]
        d = normalize_domain(token)
        return ("allow_exact", d) if d else None
    if fmt == "allow-adblock":
        m = ADBLOCK_RE.match(line.lower())
        if m and m.group(1):
            d = normalize_domain(m.group(3))
            if d:
                return ("allow" if m.group(2) == "||" else "allow_exact", d)
        return None
    raise ValueError(f"unknown format {fmt}")


def parse_text(text: str, fmt: str, allowed_modifiers=frozenset({"important"})):
    out = defaultdict(set)
    for line in text.splitlines():
        r = parse_line(line, fmt, allowed_modifiers)
        if r:
            out[r[0]].add(r[1])
    return out


# --------------------------------------------------------------------------- domain set helpers
def ancestors(domain: str):
    """Yield proper parent domains: a.b.c -> b.c, c (TLD included; harmless)."""
    parts = domain.split(".")
    for i in range(1, len(parts)):
        yield ".".join(parts[i:])


def covered(domain: str, wildcard_set) -> bool:
    """True when the domain or one of its parents is in wildcard_set."""
    if domain in wildcard_set:
        return True
    return any(a in wildcard_set for a in ancestors(domain))


def compress(domains) -> set[str]:
    """Drop domains already covered by a parent wildcard rule (||parent^)."""
    s = set(domains)
    return {d for d in s if not any(a in s for a in ancestors(d))}


def load_psl(text: str) -> set[str]:
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        rule = line.split()[0]
        if rule.startswith("!"):
            continue
        if rule.startswith("*."):
            rule = rule[2:]
        try:
            rule = rule.encode("idna").decode("ascii")
        except UnicodeError:
            continue
        out.add(rule.lower())
    return out


# --------------------------------------------------------------------------- fetching
def fetch(url: str, retries: int = 3, timeout: int = 60) -> str:
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def read_source(src: dict) -> str:
    if "path" in src:
        return (ROOT / src["path"]).read_text(encoding="utf-8")
    return fetch(src["url"])


def expand_index(src: dict) -> list[dict]:
    """A source of type 'index' lists other list URLs (e.g. Firebog 'ticked')."""
    text = fetch(src["index"])
    urls = [u.strip() for u in text.splitlines() if u.strip().startswith("http")]
    skip = set(src.get("skip", []))
    priority = [p.lower() for p in src.get("priority_patterns", [])]
    return [
        {"name": f"{src['name']}: {u}", "url": u, "format": "auto",
         "tier": src["tier"], "required": False,
         "weight": src.get("priority_weight", 2) if any(p in u.lower() for p in priority) else 1}
        for u in urls if u not in skip
    ]


# --------------------------------------------------------------------------- build
def build(config: dict, texts: dict[str, str], psl: set[str], protect_hosts: list[str],
          must_block: list[str], cap: int) -> dict:
    """Pure function: given downloaded texts, return rules + stats. (Testable offline.)"""
    tiers = defaultdict(lambda: defaultdict(set))  # tier -> source name -> domains
    weights = {}
    reference = set()  # domains already blocked by a filter the app keeps enabled (not repeated here)
    allow_wild, allow_exact = set(), set()
    curated_wild, curated_exact = set(), set()  # local hand-reviewed allowlist ("emit_always")
    per_source = {}
    for src in config["sources"]:
        name = src["name"]
        if name not in texts:
            per_source[name] = {"status": "missing"}
            continue
        mods = frozenset(src.get("modifiers", ["important"]))
        parsed = parse_text(texts[name], src["format"], mods)
        blocks = parsed.get("block", set())
        role = src.get("role", "block")
        if role == "allow":
            wild = parsed.get("allow", set()) | (blocks if src["format"] == "domains" else set())
            exact = parsed.get("allow_exact", set())
            allow_wild |= wild
            allow_exact |= exact
            if src.get("emit_always") and "path" in src:  # only local, reviewed files qualify
                curated_wild |= wild
                curated_exact |= exact
        elif role == "reference":
            reference |= blocks
        else:
            tiers[src["tier"]][name] |= blocks
            weights[name] = src.get("weight", 1)
        if src.get("import_exceptions"):
            allow_wild |= parsed.get("allow", set())
            allow_exact |= parsed.get("allow_exact", set())
        per_source[name] = {"status": "ok", "block": len(blocks),
                            "allow": len(parsed.get("allow", ())) + len(parsed.get("allow_exact", ()))}

    psl_dropped = set()

    def drop_psl(ds):
        keep = set()
        for d in ds:
            (psl_dropped.add(d) if d in psl else keep.add(d))
        return keep

    # 1) core tiers (0 = our curated list, 1 = maintained ad/tracker lists) are always included
    core = set()
    for t in sorted(tiers):
        if t <= 1:
            for ds in tiers[t].values():
                core |= ds
    core = compress(drop_psl(core))
    core = {d for d in core if not covered(d, reference)}
    if len(core) > cap:
        raise RuntimeError(f"core lists alone exceed the cap ({len(core)} > {cap})")

    # 2) extra tiers (Pi-hole community lists) fill the remaining budget, most-agreed first
    votes = defaultdict(int)
    for t in sorted(tiers):
        if t >= 2:
            for name, ds in tiers[t].items():
                w = weights.get(name, 1)
                for d in ds:
                    votes[d] += w
    candidates = [d for d in drop_psl(votes) if not covered(d, core) and not covered(d, reference)]
    candidates.sort(key=lambda d: (-votes[d], d.count("."), d))
    selected = set(core)
    budget_hit_at = None
    for d in candidates:
        if len(selected) >= cap:
            budget_hit_at = votes[d]
            break
        if not covered(d, selected):
            selected.add(d)
    blocked = compress(selected)

    # 3) apply allowlists: drop rules fully inside an allowed subtree, emit exceptions where needed
    blocked = {d for d in blocked if not covered(d, allow_wild)}

    # Exceptions in this list also override rules of the reference filter: DnsLibs merges the
    # matches of every enabled filter before choosing (exception beats block).
    def blocked_anywhere(h):
        return covered(h, blocked) or covered(h, reference)

    # Curated local exceptions (lists/allow.txt, "emit_always") are ALWAYS emitted: the built-in filter
    # differs per platform/version (AdGuard Android 4.15's built-in DNS filter blocks lptag.liveperson.net,
    # the iOS one does not) and users may enable other lists.
    # Remote/community allowlists are only emitted when something here or in the reference actually
    # blocks them, so a compromised upstream allowlist cannot unblock domains across all filters.
    allowed_with_blocked_children = {x for r in reference for x in ancestors(r) if x in allow_wild}
    remote_wild = {a for a in allow_wild - curated_wild if blocked_anywhere(a) or a in allowed_with_blocked_children}
    exceptions_wild = sorted(compress(curated_wild | remote_wild))
    wild_emitted = set(exceptions_wild)
    remote_exact = {a for a in allow_exact - curated_exact if blocked_anywhere(a)}
    exceptions_exact = sorted(a for a in curated_exact | remote_exact if not covered(a, wild_emitted))

    # 4) protected hosts must stay resolvable
    auto_unblocked = []
    exact_set = set(exceptions_exact)
    for h in protect_hosts:
        if blocked_anywhere(h) and not covered(h, wild_emitted) and h not in exact_set:
            exact_set.add(h)
            auto_unblocked.append(h)
    exceptions_exact = sorted(exact_set)
    wild_set = set(exceptions_wild)

    def is_blocked(h):
        return blocked_anywhere(h) and not covered(h, wild_set) and h not in exact_set

    missing_blocks = [h for h in must_block if not is_blocked(h)]
    still_blocked_protected = [h for h in protect_hosts if is_blocked(h)]

    return {
        "blocked": sorted(blocked),
        "exceptions_wild": exceptions_wild,
        "exceptions_exact": exceptions_exact,
        "stats": {
            "rules_block": len(blocked),
            "rules_exception": len(exceptions_wild) + len(exceptions_exact),
            "core_domains": len(core),
            "reference_domains": len(reference),
            "estimated_dnslibs_mib_with_reference": round((len(blocked) + len(reference)) * 16 / 1048576, 2),
            "pihole_candidates": len(candidates),
            "cap": cap,
            "cap_reached_at_votes": budget_hit_at,
            "psl_dropped": sorted(psl_dropped)[:200],
            "psl_dropped_count": len(psl_dropped),
            "auto_unblocked_protected_hosts": auto_unblocked,
            "must_block_not_blocked": missing_blocks,
            "protected_still_blocked": still_blocked_protected,
            "sources": per_source,
        },
    }


def render(result: dict, meta: dict) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    s = result["stats"]
    lines = [
        f"! Title: {meta['title']}",
        f"! Description: {meta['description']}",
        f"! Homepage: {meta['homepage']}",
        "! Expires: 12 hours",
        f"! Version: {now:%Y.%m.%d.%H%M}",
        f"! Last modified: {now.isoformat(timespec='seconds')}",
        f"! Block rules: {s['rules_block']} | Exceptions: {s['rules_exception']}",
        "!",
        "! ---- Exceptions (keep apps working) ----",
    ]
    lines += [f"@@||{d}^" for d in result["exceptions_wild"]]
    lines += [f"@@|{d}^" for d in result["exceptions_exact"]]
    lines.append("! ---- Blocked ----")
    lines += [f"||{d}^" for d in result["blocked"]]
    return "\n".join(lines) + "\n"


def read_list(path: Path) -> list[str]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            out.append(line)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "sources.json"))
    ap.add_argument("--out", default=str(ROOT / "dist" / "adguard-dns.txt"))
    ap.add_argument("--stats", default=str(ROOT / "dist" / "stats.json"))
    ap.add_argument("--force", action="store_true", help="skip the size-change safety check")
    args = ap.parse_args(argv)

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    sources = []
    for src in config["sources"]:
        if "index" in src:
            try:
                sources += expand_index(src)
            except RuntimeError as e:
                print(f"WARN index unavailable, skipping: {e}", file=sys.stderr)
        else:
            sources.append(src)
    config = {**config, "sources": sources}

    texts, failures = {}, []
    for src in sources:
        try:
            texts[src["name"]] = read_source(src)
        except Exception as e:  # noqa: BLE001
            (failures.append(src["name"]) if src.get("required", True) else None)
            print(f"WARN {src['name']}: {e}", file=sys.stderr)
    if failures:
        print(f"ABORT: required sources failed: {failures}", file=sys.stderr)
        return 2

    try:
        psl = load_psl(fetch(config["public_suffix_list"]))
    except RuntimeError:
        psl = set(read_list(ROOT / "lists" / "public-suffix-fallback.txt"))
    psl |= set(read_list(ROOT / "lists" / "never-block.txt"))

    result = build(
        config, texts, psl,
        protect_hosts=read_list(ROOT / "lists" / "protect-hosts.txt"),
        must_block=read_list(ROOT / "tests" / "must-block.txt"),
        cap=int(config["max_rules"]),
    )
    s = result["stats"]

    out = Path(args.out)
    prev = None
    if out.exists():
        m = re.search(r"Block rules: (\d+)", out.read_text(encoding="utf-8")[:2000])
        prev = int(m.group(1)) if m else None
    if prev and not args.force and s["rules_block"] < prev * 0.6:
        print(f"ABORT: rule count fell from {prev} to {s['rules_block']}", file=sys.stderr)
        return 3
    if s["protected_still_blocked"]:
        print(f"ABORT: protected hosts still blocked: {s['protected_still_blocked']}", file=sys.stderr)
        return 4

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(result, config["meta"]), encoding="utf-8")
    Path(args.stats).write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in s.items() if k != "sources" and k != "psl_dropped"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
