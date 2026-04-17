#!/usr/bin/env bash
# wait-for.sh — wait for a TCP port to accept connections, then exec the rest.
# Usage: wait-for.sh host:port [-- command args...]

set -euo pipefail

HOSTPORT="$1"
shift
HOST="${HOSTPORT%:*}"
PORT="${HOSTPORT#*:}"
TIMEOUT="${TIMEOUT:-60}"

echo -n "Waiting for $HOST:$PORT (timeout ${TIMEOUT}s)"
for _ in $(seq 1 "$TIMEOUT"); do
  if (echo >/dev/tcp/"$HOST"/"$PORT") 2>/dev/null; then
    echo " ✓"
    if [[ "${1:-}" == "--" ]]; then
      shift
      exec "$@"
    fi
    exit 0
  fi
  echo -n "."
  sleep 1
done

echo " ✗ timeout"
exit 1
