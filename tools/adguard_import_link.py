#!/usr/bin/env python3
"""Print the adguard://apply_settings link that subscribes AdGuard for iOS to this list.

What it imports (AdGuard shows a confirmation screen with a checkbox per item):
  * DNS filter: AdGuard's built-in DNS filter (enabled if already present)
  * DNS filter: this list
  * DNS server 30 = "AdGuard DNS non-filtered (DNS-over-HTTPS)": filtering happens only locally, so
    our exceptions are authoritative (a filtering upstream would block before they can apply).
Deliberately NOT included: dns_user_rules (the importer REPLACES all existing DNS user rules).
"""
import json
import urllib.parse

LIST_URL = "https://raw.githubusercontent.com/acidgeek/dns-blocklist/main/dist/adguard-dns.txt"
settings = {
    "dns_filter_list": [
        {"name": "AdGuard DNS filter", "url": "https://filters.adtidy.org/dns/filter_1_ios.txt"},
        {"name": "DNS Blocklist iOS (apps, sin romper)", "url": LIST_URL},
    ],
    "dns_filter_list_override": False,
    "dns_server_id": 30,
}
print("adguard://apply_settings?json=" + urllib.parse.quote(json.dumps(settings, separators=(",", ":")), safe=""))
