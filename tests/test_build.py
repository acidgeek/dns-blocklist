"""Offline tests for scripts/build.py (no network). Run: python3 -m unittest discover -s tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build as b  # noqa: E402


def cfg(*sources):
    return {"sources": list(sources)}


def src(name, fmt="adblock", tier=1, **kw):
    return {"name": name, "format": fmt, "tier": tier, **kw}


class ParseTests(unittest.TestCase):
    def test_hosts_domains_adblock(self):
        p = b.parse_text("0.0.0.0 ads.example.com\n127.0.0.1 localhost\n# c\n", "hosts")
        self.assertEqual(p["block"], {"ads.example.com"})
        p = b.parse_text("tracker.example.org\n*.wild.example.net\n", "domains")
        self.assertEqual(p["block"], {"tracker.example.org", "wild.example.net"})
        p = b.parse_text("||ads.example.com^\n@@||ok.example.com^\n@@|exact.example.com^\n||x.com^$third-party\n", "adblock")
        self.assertEqual(p["block"], {"ads.example.com"})
        self.assertEqual(p["allow"], {"ok.example.com"})
        self.assertEqual(p["allow_exact"], {"exact.example.com"})

    def test_rejects_ips_wildcards_and_paths(self):
        p = b.parse_text("||1.2.3.4^\n||ad*.example.com^\n||example.com/ads^\n0.0.0.0 0.0.0.0\n", "auto")
        self.assertFalse(p.get("block"))

    def test_important_modifier_is_kept(self):
        p = b.parse_text("||ads.example.com^$important\n", "adblock")
        self.assertEqual(p["block"], {"ads.example.com"})


class BuildTests(unittest.TestCase):
    def run_build(self, texts, sources, psl=frozenset(), protect=(), must=(), cap=1000):
        return b.build(cfg(*sources), texts, set(psl), list(protect), list(must), cap)

    def test_compresses_subdomains(self):
        r = self.run_build({"A": "||ads.com^\n||x.ads.com^\n"}, [src("A")])
        self.assertEqual(r["blocked"], ["ads.com"])

    def test_never_blocks_public_suffix(self):
        r = self.run_build({"A": "||github.io^\n||evil.github.io^\n"}, [src("A")], psl={"github.io"})
        self.assertEqual(r["blocked"], ["evil.github.io"])

    def test_reference_domains_are_not_repeated(self):
        texts = {"REF": "||dup.com^\n", "A": "||dup.com^\n||sub.dup.com^\n||new.com^\n"}
        r = self.run_build(texts, [src("REF", role="reference"), src("A")])
        self.assertEqual(r["blocked"], ["new.com"])

    def test_exception_emitted_when_parent_blocked_even_in_reference(self):
        texts = {"REF": "||vendor.com^\n", "ALLOW": "@@||chat.vendor.com^\n"}
        r = self.run_build(texts, [src("REF", role="reference"), src("ALLOW", fmt="allow-adblock", role="allow")])
        self.assertEqual(r["exceptions_wild"], ["chat.vendor.com"])

    def test_exception_emitted_when_reference_blocks_a_child(self):
        texts = {"REF": "||live.fraudcheck.click^\n", "ALLOW": "@@||fraudcheck.click^\n"}
        r = self.run_build(texts, [src("REF", role="reference"), src("ALLOW", fmt="allow-adblock", role="allow")])
        self.assertEqual(r["exceptions_wild"], ["fraudcheck.click"])

    def test_exceptions_always_emitted_for_other_platforms_filters(self):
        # nothing here blocks the chat host, but another platform's built-in filter might
        texts = {"A": "||ads.com^\n", "ALLOW": "@@||chatvendor.net^\n@@|api.bank.example^\n"}
        allow = src("ALLOW", fmt="allow-adblock", role="allow", emit_always=True, path="lists/allow.txt")
        r = self.run_build(texts, [src("A"), allow])
        self.assertEqual(r["exceptions_wild"], ["chatvendor.net"])
        self.assertEqual(r["exceptions_exact"], ["api.bank.example"])

    def test_remote_allowlist_only_emitted_when_needed(self):
        # a remote/community allowlist must not unblock domains nobody here blocks (supply-chain safety)
        texts = {"A": "||ads.com^\n||tracker.com^\n", "REMOTE": "doubleclick.net\ntracker.com\n"}
        remote = src("REMOTE", fmt="allow-domains", role="allow", url="https://example.invalid/list.txt")
        r = self.run_build(texts, [src("A"), remote])
        self.assertEqual(r["exceptions_exact"], ["tracker.com"])
        self.assertEqual(r["exceptions_wild"], [])

    def test_emit_always_ignored_for_remote_sources(self):
        texts = {"A": "||ads.com^\n", "REMOTE": "@@||doubleclick.net^\n"}
        remote = src("REMOTE", fmt="allow-adblock", role="allow", emit_always=True, url="https://example.invalid/x")
        r = self.run_build(texts, [src("A"), remote])
        self.assertEqual(r["exceptions_wild"], [])

    def test_allowed_subtree_removed_from_blocklist(self):
        texts = {"A": "||cdn.chat.com^\n||chat.com^\n", "ALLOW": "@@||chat.com^\n"}
        r = self.run_build(texts, [src("A"), src("ALLOW", fmt="allow-adblock", role="allow")])
        self.assertEqual(r["blocked"], [])

    def test_protected_host_gets_auto_exception(self):
        texts = {"A": "||checker.net^\n"}
        r = self.run_build(texts, [src("A")], protect=["api.checker.net"])
        self.assertIn("api.checker.net", r["exceptions_exact"])
        self.assertEqual(r["stats"]["auto_unblocked_protected_hosts"], ["api.checker.net"])
        self.assertEqual(r["stats"]["protected_still_blocked"], [])

    def test_cap_prefers_most_agreed_pihole_domains(self):
        texts = {"P1": "0.0.0.0 a.com\n0.0.0.0 b.com\n", "P2": "0.0.0.0 b.com\n", "CORE": "||core.com^\n"}
        r = self.run_build(texts, [src("CORE"), src("P1", fmt="hosts", tier=2), src("P2", fmt="hosts", tier=2)], cap=2)
        self.assertEqual(r["blocked"], ["b.com", "core.com"])

    def test_must_block_reported(self):
        r = self.run_build({"A": "||ads.com^\n"}, [src("A")], must=["x.ads.com", "missing.com"])
        self.assertEqual(r["stats"]["must_block_not_blocked"], ["missing.com"])

    def test_render_syntax(self):
        r = self.run_build({"A": "||ads.com^\n", "ALLOW": "@@|ok.ads.com^\n"},
                           [src("A"), src("ALLOW", fmt="allow-adblock", role="allow")])
        out = b.render(r, {"title": "t", "description": "d", "homepage": "h"})
        self.assertIn("\n@@|ok.ads.com^\n", out)
        self.assertIn("\n||ads.com^\n", out)


if __name__ == "__main__":
    unittest.main()
