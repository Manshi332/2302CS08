#!/usr/bin/env bash
# Verifies hashlab against sha256sum on a 100 MB file and reports peak memory.
# Usage (from the assignment folder; Linux / macOS / WSL):  ./scripts/verify_100mb.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:src"

F="$(mktemp /tmp/hashlab_100mb.XXXXXX)"
TIMEFILE="$(mktemp /tmp/hashlab_time.XXXXXX)"
trap 'rm -f "$F" "$TIMEFILE"' EXIT

head -c 104857600 /dev/urandom > "$F"
echo "file size : $(wc -c < "$F") bytes"

if command -v sha256sum >/dev/null 2>&1; then
  EXPECTED="$(sha256sum "$F" | cut -d' ' -f1)"
else
  EXPECTED="$(shasum -a 256 "$F" | cut -d' ' -f1)"
fi
echo "reference : $EXPECTED"

if /usr/bin/time -v true >/dev/null 2>&1; then
  OUT="$(/usr/bin/time -v python3 -m hashlab file "$F" 2>"$TIMEFILE")"
  PEAK_KB="$(grep 'Maximum resident' "$TIMEFILE" | awk '{print $NF}')"
  echo "peak RSS  : ${PEAK_KB} KB (loading the file whole would add about 102400 KB)"
else
  OUT="$(python3 -m hashlab file "$F")"
  echo "peak RSS  : skipped (GNU time not available); the pytest tracemalloc test covers this"
fi

GOT="$(echo "$OUT" | awk '/^sha256:/ {print $2}')"
echo "hashlab   : $GOT"
if [ "$GOT" = "$EXPECTED" ]; then echo "RESULT: MATCH"; else echo "RESULT: MISMATCH"; exit 1; fi
