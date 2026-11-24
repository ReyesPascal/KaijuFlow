#!/usr/bin/env bash
# run-ci.sh [suite ...]: run the integration suites (tests/integration/<suite>.mjs) in an isolated network namespace;
# with names, only those (`npm run test:integration -- parity-altmount discovery-stream`).
set -euo pipefail
only="$*"
cd "$(git rev-parse --show-toplevel)"
ROOT="$PWD"
# KaijuFlow: fixes are allowed now, so test the committed app source (HEAD)
# instead of requiring the untouched v1.4.1 import. Uncommitted edits are refused.
git diff --quiet HEAD -- src ui/src || { echo "SOURCE-DIFF: uncommitted app changes; commit first"; exit 10; }
# dist/ is what the scenarios copy and run: refuse one older than src/ (use the npm scripts, they build first).
[[ -f dist/server.js && -z "$(find src -type f -newer dist/server.js -print -quit)" ]] || { echo "STALE-DIST: dist/ is missing or older than src/; run npm run build (npm run test:integration / test:a4 do it)"; exit 16; }
before="$(mktemp)"
after="$(mktemp)"
git ls-files -- src ui/src | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > "$before"
parent_ns="$(readlink /proc/self/ns/net)"
[[ -n "$parent_ns" ]] || exit 11
sudo -n true
# The scenarios run node as user nobody (in-namespace.sh), so node must be reachable outside /home (docs/agents/testing.md).
sudo -n runuser -u nobody -- env -i PATH="$PATH" node --version >/dev/null 2>&1 || { echo "NODE-UNREACHABLE: user nobody cannot run node from PATH (yours: $(command -v node)); see docs/agents/testing.md"; exit 17; }
sandbox="$(mktemp -d -t kaijuflow-a4-XXXXXXXX)"
chmod 755 "$sandbox"
trap 'sudo rm -rf "$sandbox"; rm -f "$before" "$after"' EXIT
echo "A4: parent network namespace = $parent_ns"
# Deliberately reject the gate. It MUST abort before the application-import sentinel exists.
negative_status=0
sudo -n env -i PATH="$PATH" A4_ROOT="$ROOT" A4_RUN_DIR="$sandbox/negative" \
    A4_PARENT_NETNS="$parent_ns" A4_FORCE_FAIL=1 \
    unshare --net -- bash "$ROOT/tests/integration/in-namespace.sh" || negative_status=$?
if [[ "$negative_status" -ne 77 ]]; then
  echo "FAIL-CLOSED CONTROL: expected injected exit 77 after complete probe, got $negative_status"; exit 12
fi
if [[ -e "$sandbox/negative/app-import.started" ]]; then
  echo "FAIL-CLOSED CONTROL: application began after failed gate"; exit 13
fi
echo "A4-ISO-000 negative-control PASS: no application import"
status=0
sudo -n env -i PATH="$PATH" A4_ROOT="$ROOT" A4_RUN_DIR="$sandbox/positive" \
  A4_PARENT_NETNS="$parent_ns" A4_FORCE_FAIL=0 INTEGRATION_ONLY="$only" \
  unshare --net -- bash "$ROOT/tests/integration/in-namespace.sh" || status=$?
for r in "$sandbox"/positive/results-*.json; do
  [[ -f "$r" ]] || continue
  name="integration-$(basename "$r")"
  sudo cp "$r" "$ROOT/$name"
  sudo chown "$(id -u):$(id -g)" "$ROOT/$name"
done
git ls-files -- src ui/src | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > "$after"
cmp -s "$before" "$after" || { echo "SOURCE HASHES CHANGED"; exit 14; }
git diff --quiet HEAD -- src ui/src || { echo "SOURCE-DIFF AFTER: FAIL"; exit 15; }
echo "A4: source SHA-256 before/after identical; behavior exit=$status"
exit "$status"
