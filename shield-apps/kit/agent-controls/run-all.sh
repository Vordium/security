#!/usr/bin/env bash
# Run every check in tests/ (or the ones named) and write results/run-N/. Exit codes: 0 holds, 1 attack works, 3 cannot run.
# Usage: ./run-all.sh [--owner-key-file PATH] [test.py ...]
here="$(cd "$(dirname "$0")" && pwd)"
py="${PYTHON:-python3}"
extra=()
if [ "$1" = "--owner-key-file" ]; then extra=(--owner-key-file "$2"); shift 2; fi
n=1; while [ -e "$here/results/run-$n" ]; do n=$((n+1)); done
out="$here/results/run-$n"; mkdir -p "$out"
keys="${SHIELD_KEYS_DIR:-$here/keys}"
tests=("$@"); [ ${#tests[@]} -eq 0 ] && tests=($(cd "$here/tests" && ls [a-z][0-9][0-9]_*.py))
for t in "${tests[@]}"; do
  name="${t%.py}"
  ( cd "$here/tests" && timeout -k 10 300 "$py" "$t" --keys-dir "$keys" --out "$out/$name.json" "${extra[@]}" ) > "$out/$name.log" 2>&1
  rc=$?
  case $rc in 0) w="DEFENCE HOLDS";; 1) w="ATTACK WORKS";; 3) w="CANNOT RUN";; *) w="ERROR rc=$rc";; esac
  printf '%-40s exit=%s  %s\n' "$name" "$rc" "$w" | tee -a "$out/summary.txt"
done
echo "results: $out"
