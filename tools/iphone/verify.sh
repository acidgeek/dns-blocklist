#!/bin/zsh
# One-command verification against the real iPhone (USB, unlocked, Developer Mode on).
# Lists installed apps, opens each for ~11 s while recording which hosts every app contacts,
# then simulates the current list + AdGuard's built-in filter and writes a per-app report.
# Everything personal is written to ../../private/ (git-ignored).
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PMD3_PYTHON:-$HOME/Library/Application Support/pipx/venvs/pymobiledevice3/bin/python}"
OUT="$REPO/private/verify-$(date +%Y%m%d-%H%M)"
mkdir -p "$OUT/ref"
cd "$REPO/tools/iphone"

"$PY" list_apps.py "$OUT"
N=$(wc -l < "$OUT/sweep_list.tsv")
SECS=$(( N * 14 + 60 ))
echo "Recording for ~$((SECS / 60)) min. Keep the iPhone unlocked and do not touch it."
"$PY" capture.py "$OUT/capture.jsonl" "$SECS" &
CAP=$!
sleep 5
./sweep.sh "$OUT"
wait $CAP || true

python3 -I "$REPO/scripts/build.py" --out "$OUT/list.txt" --stats "$OUT/stats.json" --force >/dev/null
curl -s -A "dns-blocklist-verify/1.0" -o "$OUT/ref/filter_1_ios.txt" https://filters.adtidy.org/dns/filter_1_ios.txt
python3 -I analyze.py "$OUT/capture.jsonl" "$OUT/sweep_log.tsv" "$OUT/exec_map.json" \
  "$OUT/list.txt" "$OUT/ref/filter_1_ios.txt" "$OUT/report.json" > "$OUT/report.txt"
echo "Report: $OUT/report.txt  (review every BLOCK in banking/health/payment/government apps)"
