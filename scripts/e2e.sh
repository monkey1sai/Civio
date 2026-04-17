#!/usr/bin/env bash
# e2e.sh — end-to-end scenario runner.
# Spins up the full stack in docker-compose.e2e.yml and runs the 5 must-have
# scenarios from docs/05-test-strategy.md.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

COMPOSE="docker compose -f docker-compose.e2e.yml"

cleanup() {
  echo ""
  echo "→ cleanup"
  $COMPOSE down -v --remove-orphans || true
}
trap cleanup EXIT

echo "=== Civio E2E suite ==="
echo "→ starting stack"
$COMPOSE up -d --wait

echo "→ waiting for API"
for i in {1..30}; do
  if curl -fs http://localhost:8000/health >/dev/null; then
    break
  fi
  sleep 2
  [[ $i -eq 30 ]] && { echo "API failed to start"; $COMPOSE logs; exit 1; }
done

SCENARIOS_DIR="$ROOT/tests/e2e"
FAILED=0

run() {
  local name="$1"
  shift
  echo ""
  echo "=== $name ==="
  if "$@"; then
    echo "✓ $name"
  else
    echo "✗ $name"
    FAILED=$((FAILED + 1))
  fi
}

run "Scenario 1: new community onboarding" \
  pytest "$SCENARIOS_DIR/scenario_1_onboarding.py" -x -v

run "Scenario 2: cross-community deny" \
  pytest "$SCENARIOS_DIR/scenario_2_cross_community.py" -x -v

run "Scenario 3: ownership transfer" \
  pytest "$SCENARIOS_DIR/scenario_3_ownership_transfer.py" -x -v

run "Scenario 4: token depletion" \
  pytest "$SCENARIOS_DIR/scenario_4_token_depletion.py" -x -v

run "Scenario 5: edge recovery" \
  pytest "$SCENARIOS_DIR/scenario_5_edge_recovery.py" -x -v

echo ""
if [[ $FAILED -eq 0 ]]; then
  echo "✓ All E2E scenarios passed"
  exit 0
else
  echo "✗ $FAILED scenario(s) failed"
  $COMPOSE logs
  exit 1
fi
