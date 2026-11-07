#!/usr/bin/env bash
# Import ALL files from pinned upstream v1.4.1 into an isolated KaijuFlow checkout.
# This script does NOT commit, push, deploy, run Docker, or access Brain containers.
set -euo pipefail

UPSTREAM='https://github.com/DSmart33/Usenet-Ultimate.git'
EXPECTED='499efbdeb631b1b059f8aa70d07c12beaf504876'
BRANCH='import/upstream-v1.4.1'
TAG='refs/tags/upstream-ultimate-v1.4.1'

for cmd in git tar python3; do
  command -v "$cmd" >/dev/null || { echo "Missing required command: $cmd" >&2; exit 1; }
done

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"
[[ -f docs/upstream-v1.4.1-manifest.json ]] || { echo 'Missing tracked upstream manifest' >&2; exit 1; }
[[ "$(git remote get-url origin 2>/dev/null)" == *ReyesPascal/KaijuFlow* ]] || {
  echo 'This does not look like a ReyesPascal/KaijuFlow clone; aborting' >&2; exit 1;
}
[[ -z "$(git status --porcelain --untracked-files=all)" ]] || {
  echo 'Working tree not clean; aborting without overwriting local files' >&2; exit 1;
}
[[ "$(git branch --show-current)" == 'main' ]] || {
  echo 'Run from an up-to-date main branch in an isolated checkout' >&2; exit 1;
}
[[ -z "$(git branch --list "$BRANCH")" ]] || {
  echo "Branch $BRANCH already exists; inspect/resume it instead of repeating import" >&2; exit 1;
}

BASE_COMMIT="$(git rev-parse HEAD)"
echo "Preserving pre-import main commit: $BASE_COMMIT"
echo "Fetching pinned upstream tag through Git (including binary file objects)..."
git fetch --no-tags --depth=1 "$UPSTREAM" "refs/tags/v1.4.1:$TAG"
ACTUAL="$(git rev-parse "$TAG^{commit}")"
if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "Upstream ref mismatch: $ACTUAL; expected $EXPECTED" >&2
  exit 1
fi

TMPDIR_IMPORT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_IMPORT"' EXIT
git archive --format=tar "$EXPECTED" | tar -xf - -C "$TMPDIR_IMPORT"
echo "Verified upstream commit: $ACTUAL"
echo "Preparing isolated import branch: $BRANCH"
git switch -c "$BRANCH"

python3 - "$TMPDIR_IMPORT" "$REPO_ROOT" "$BASE_COMMIT" <<'PY'
import json
import pathlib
import shutil
import subprocess
import sys
import stat
from datetime import datetime, timezone

source = pathlib.Path(sys.argv[1])
dest = pathlib.Path(sys.argv[2])
base_commit = sys.argv[3]
manifest = json.loads((dest / 'docs/upstream-v1.4.1-manifest.json').read_text())
entries = manifest['blob_paths']
assert manifest['blob_count'] == 192 and len(entries) == 192
assert manifest['upstream_commit'] == '499efbdeb631b1b059f8aa70d07c12beaf504876'

actual_paths = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
expected_paths = {e['path'] for e in entries}
if actual_paths != expected_paths:
    raise SystemExit(f"Source path inventory mismatch; missing={sorted(expected_paths-actual_paths)} extra={sorted(actual_paths-expected_paths)}")

remap = {
    'LICENSE': 'THIRD_PARTY_NOTICES/Usenet-Ultimate-LICENSE',
    'README.md': 'docs/upstream/README.v1.4.1.md',
}

def hash_blob(path: pathlib.Path) -> str:
    return subprocess.check_output(['git', 'hash-object', str(path)], text=True).strip()

# Verify the entire upstream tree before writing anything.
for entry in entries:
    rel = pathlib.PurePosixPath(entry['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise SystemExit(f"Unsafe upstream path: {entry['path']}")
    p = source / rel
    if hash_blob(p) != entry['sha']:
        raise SystemExit(f"Upstream blob mismatch: {entry['path']}")
    if p.stat().st_size != entry['size']:
        raise SystemExit(f"Upstream file size mismatch: {entry['path']}")
    expected_mode = int(entry['mode'], 8) & 0o111
    actual_mode = stat.S_IMODE(p.stat().st_mode) & 0o111
    if actual_mode != expected_mode:
        raise SystemExit(f"Upstream executable bit mismatch: {entry['path']}")

# Refuse any destination collisions beyond the two explicit remappings.
mapped = []
for entry in entries:
    target = dest / remap.get(entry['path'], entry['path'])
    if target.exists() or target.is_symlink():
        raise SystemExit(f"Destination already exists; refusing overwrite: {target}")
    mapped.append((source / entry['path'], target, entry))

# Copy byte-for-byte, preserve executable bits, then verify hashes again.
for original, target, entry in mapped:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)
for _, target, entry in mapped:
    if hash_blob(target) != entry['sha']:
        raise SystemExit(f"Imported blob differs from upstream: {entry['path']}")
    if (stat.S_IMODE(target.stat().st_mode) & 0o111) != (int(entry['mode'], 8) & 0o111):
        raise SystemExit(f"Imported mode differs: {entry['path']}")

report = {
    'status': 'imported-locally-hash-verified-not-committed',
    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    'upstream_commit': manifest['upstream_commit'],
    'pre_import_main_commit': base_commit,
    'branch': 'import/upstream-v1.4.1',
    'files_verified': len(mapped),
    'bytes_verified': sum(e['size'] for _, _, e in mapped),
    'path_remappings': remap,
    'license_preservation': 'Both original existing KaijuFlow LICENSE and mapped upstream LICENSE retained',
    'security_scan': 'PENDING',
    'runtime_tests': 'PENDING',
    'push_status': 'NOT PUSHED',
    'production_changes': 'NONE',
}
(dest / 'docs/upstream-import-verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(f"All {len(mapped)} upstream release file blobs matched their pinned Git hashes and modes.")
print(f"Saved local import verification report. No production systems were accessed.")
PY

echo
echo 'Import files are LOCAL ONLY, uncommitted and unpushed.'
echo 'Review git status and run a trusted secret/credential scan on all imported content.'
echo 'Run isolated backend/UI builds and regression checks. Inspect the full import diff.'
echo 'Only after verification, commit and push this import branch. Do NOT deploy to Brain.'
git status --short | tail -25
