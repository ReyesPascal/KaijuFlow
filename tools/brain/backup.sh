#!/usr/bin/env bash
# Back up the run records and the recording store to the private repo
# ReyesPascal/kaijuflow-notes (#114). Last step of every record or run.
# Secrets (~/kaijuflow-test/*.json) never go in; they live in the owner's
# password manager.
set -euo pipefail

notes="${KF_NOTES:-$HOME/kaijuflow-notes}"
store="${KF_STORE:-$HOME/kaijuflow-test/store}"

[ -d "$notes/.git" ] || { echo "No git repo at $notes: clone ReyesPascal/kaijuflow-notes there first." >&2; exit 1; }
[ -d "$store" ] || { echo "No recording store at $store." >&2; exit 1; }

# The stand-in stores no keys; refuse anyway if a key file's value shows up.
for f in "$HOME"/kaijuflow-test/*.json; do
  [ -f "$f" ] || continue
  python3 -I - "$f" "$store" "$notes/brain-runs" <<'PY'
import json, os, sys
src, *dirs = sys.argv[1:]
skip = {"name", "host", "port", "ssl", "url", "connections", "slug"}
def walk(o, k=""):
    if isinstance(o, dict):
        for kk, v in o.items(): yield from walk(v, kk)
    elif isinstance(o, list):
        for v in o: yield from walk(v, k)
    elif isinstance(o, str) and len(o) >= 10 and k.lower() not in skip:
        yield o
vals = [v.encode() for v in set(walk(json.load(open(src))))]
for d in dirs:
    for root, _, files in os.walk(d):
        for n in files:
            p = os.path.join(root, n)
            data = open(p, "rb").read()
            if any(v in data for v in vals):
                sys.exit(f"A value from {os.path.basename(src)} is in {p}; not backing up.")
PY
done

rsync -a --delete "$store/" "$notes/recordings/"
cd "$notes"
git add -A
if git diff --cached --quiet; then
  echo "Nothing new to back up."
else
  git commit -qm "Backup $(date -u +%Y-%m-%dT%H%MZ)"
fi
git push -q origin HEAD
echo "Backed up to $(git remote get-url origin) at $(git rev-parse --short HEAD)."
