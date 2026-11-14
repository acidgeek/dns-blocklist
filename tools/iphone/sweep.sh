#!/bin/zsh
# Launch each app in the list for ~11s so its startup traffic is captured.
S="$1"
while IFS=$'\t' read -r bundle exe name; do
  echo "$(date +%s)\t$bundle\t$exe\t$name" >> "$S/sweep_log.tsv"
  pymobiledevice3 developer core-device launch-application "$bundle" "" --native >/dev/null 2>&1 || echo "FAIL $bundle" >> "$S/sweep_log.tsv"
  sleep 11
done < "$S/sweep_list.tsv"
echo "$(date +%s)\tDONE" >> "$S/sweep_log.tsv"
