#!/usr/bin/env bash
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
ROOT="$PWD"
# KaijuFlow: fixes are allowed now, so test the committed app source (HEAD)
# instead of requiring the untouched v1.4.1 import. Uncommitted edits are refused.
git diff --quiet HEAD -- src ui/src || { echo "SOURCE-DIFF: uncommitted app changes; commit first"; exit 10; }
before="$(mktemp)"
after="$(mktemp)"
git ls-files -- src ui/src | LC_ALL=C sort | while IFS= read -r f; do sha256sum "$f"; done > "$before"
parent_ns="$(readlink /proc/self/ns/net)"
[[ -n "$parent_ns" ]] || exit 11
sudo -n true
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
  A4_PARENT_NETNS="$parent_ns" A4_FORCE_FAIL=0 \
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
