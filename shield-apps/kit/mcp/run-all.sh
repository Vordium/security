#!/usr/bin/env bash
# Run every check in tests/ (or the ones named) and write results/run-N/. Exit codes: 0 holds, 1 attack works, 3 cannot run.
# Usage: ./run-all.sh [--owner-key-file PATH --agent-key-file PATH] [test.py ...]
# The trading checks need a funded test-network owner and an agent file path; without them they report CANNOT RUN.
here="$(cd "$(dirname "$0")" && pwd)"
py="${PYTHON:-python3}"
extra=()
while [ "${1#--}" != "$1" ]; do extra+=("$1" "$2"); shift 2; done
n=1; while [ -e "$here/results/run-$n" ]; do n=$((n+1)); done
out="$here/results/run-$n"; mkdir -p "$out"
"$py" -c 'import vordium_mcp,sys;print("vordium-mcp", vordium_mcp.__version__, vordium_mcp.__file__)' > "$out/server.txt" 2>&1
tests=("$@"); [ ${#tests[@]} -eq 0 ] && tests=($(cd "$here/tests" && ls b[0-9][0-9]_*.py))
for t in "${tests[@]}"; do
  name="${t%.py}"
  args=(--out "$out/$name.json")
  case "$name" in b1[2-4]_*) args+=("${extra[@]}");; esac
  case "$name" in b14_*) args=(--out "$out/$name.json" --keys-dir "${SHIELD_KEYS_DIR:-$here/keys}");; esac
  ( cd "$here/tests" && timeout -k 10 300 "$py" "$t" "${args[@]}" ) > "$out/$name.log" 2>&1
  rc=$?
  case $rc in 0) w="DEFENCE HOLDS";; 1) w="ATTACK WORKS";; 3) w="CANNOT RUN";; *) w="ERROR rc=$rc";; esac
  printf '%-40s exit=%s  %s\n' "$name" "$rc" "$w" | tee -a "$out/summary.txt"
done
echo "results: $out"
