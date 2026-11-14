"""Write sweep_list.tsv (bundle, executable, name) and exec_map.json for the installed user apps.

usage: python list_apps.py OUT_DIR
Skips VPN / ad-blocker / authenticator apps: launching a VPN app can switch the active VPN.
"""
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from pymobiledevice3.lockdown import create_using_usbmux
from pymobiledevice3.services.installation_proxy import InstallationProxyService

SKIP_WORDS = ("vpn", "tailscale", "hotspot", "wireguard", "adguard", "authenticator", "bitwarden", "1password")


async def main(out: Path):
    lockdown = await create_using_usbmux()
    apps = await InstallationProxyService(lockdown=lockdown).get_apps(application_type="User")
    rows, exec_map = [], defaultdict(list)
    for bundle, info in apps.items():
        name = info.get("CFBundleDisplayName") or info.get("CFBundleName") or bundle
        exe = info.get("CFBundleExecutable", "")
        exec_map[exe].append([bundle, name])
        if any(w in (bundle + name).lower() for w in SKIP_WORDS):
            continue
        rows.append((bundle, exe, name))
    rows.sort(key=lambda r: r[2].lower())
    out.mkdir(parents=True, exist_ok=True)
    (out / "sweep_list.tsv").write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    (out / "exec_map.json").write_text(json.dumps(exec_map, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} apps to sweep ({len(apps) - len(rows)} skipped)")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
