#!/usr/bin/env python3
"""Print a Markdown issue body when dist/stats.json shows something a human should review.

Prints nothing (and the workflow opens no issue) when everything is fine.
usage: python scripts/attention.py dist/stats.json
"""
import json
import re
import sys

DOMAIN = re.compile(r"^[a-z0-9._-]+$")


def safe(items):
    # domains come from third-party lists: keep only plain hostnames, rendered as code
    return [f"- `{d}`" for d in items if isinstance(d, str) and DOMAIN.match(d)]


def main(path: str) -> int:
    s = json.load(open(path, encoding="utf-8"))
    parts = []
    auto = safe(s.get("auto_unblocked_protected_hosts", []))
    if auto:
        parts += ["### Hosts protegidos que una fuente empezó a bloquear",
                  "Se agregó una excepción automática. Revisa si debe quedarse en `lists/allow.txt`.", *auto, ""]
    missing = safe(s.get("must_block_not_blocked", []))
    if missing:
        parts += ["### Dominios de anuncios que ya no se bloquean",
                  "Revisa `lists/block-mobile-ads.txt` o las fuentes.", *missing, ""]
    mib = s.get("estimated_dnslibs_mib_with_reference")
    if isinstance(mib, (int, float)) and mib > 7.2:
        parts += [f"### Memoria estimada alta: {mib} MiB (tope de AdGuard: 8)", "Baja `max_rules` en `sources.json`.", ""]
    missing_src = [k for k, v in s.get("sources", {}).items() if v.get("status") != "ok"]
    if len(missing_src) > 3:
        parts += [f"### {len(missing_src)} fuentes opcionales no se pudieron descargar", ""]
    if parts:
        print("\n".join(["Generado por la compilación diaria.", "", *parts]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
