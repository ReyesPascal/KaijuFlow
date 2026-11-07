#!/usr/bin/env python3
"""Dependency-free, read-only validation of KaijuFlow's source-adjacent audit index."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "evidence" / "index"
BASELINE = "c83a3c733b6394eb140a1c0a1dc500010a9f22e5"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
EVIDENCE_CLASSES = {"source-observed", "REA-observed", "test-observed", "measured", "unverified"}
DATASETS = {
    "subsystems": ("subsystem_id", {"schema_version", "subsystem_id", "name", "source_commit", "primary_path", "source_evidence_ids", "source_review", "rea_review", "behavior_test", "performance_test", "open_question"}),
    "manifest": ("evidence_id", {"schema_version", "evidence_id", "record_type", "classification", "source_commit", "producer", "state", "coverage", "storage"}),
    "claims": ("claim_id", {"schema_version", "claim_id", "statement", "classification", "status", "source_commit", "support_evidence_ids", "contradiction_ids", "confidence", "limitations"}),
    "artifacts": ("artifact_id", {"schema_version", "artifact_id", "kind", "source_commit", "state", "storage_class", "sha256", "raw_retained_locally", "retention_policy"}),
}
errors: list[str] = []


def bad(message: str) -> None:
    errors.append(message)


def local_path(relpath: str, description: str) -> Path | None:
    if not isinstance(relpath, str) or not relpath or relpath.startswith("/"):
        bad(f"{description}: empty/absolute path")
        return None
    candidate = (ROOT / relpath).resolve()
    if not candidate.is_relative_to(ROOT):
        bad(f"{description}: path escapes checkout: {relpath!r}")
        return None
    if not candidate.is_file():
        bad(f"{description}: file missing in checkout: {relpath!r}")
        return None
    return candidate


def load_dataset(name: str) -> dict[str, dict]:
    id_field, required = DATASETS[name]
    path = INDEX / f"{name}.jsonl"
    if not path.is_file():
        bad(f"required dataset missing: {path}")
        return {}
    items: dict[str, dict] = {}
    for line_num, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        where = f"{path.relative_to(ROOT)}:{line_num}"
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError as exc:
            bad(f"{where}: invalid JSON: {exc}")
            continue
        if not isinstance(rec, dict):
            bad(f"{where}: object expected")
            continue
        missing = required.difference(rec)
        if missing:
            bad(f"{where}: missing required fields: {sorted(missing)}")
            continue
        if rec.get("schema_version") != 1:
            bad(f"{where}: unsupported schema_version")
        if not isinstance(rec.get("source_commit"), str) or not SHA40.fullmatch(rec["source_commit"]):
            bad(f"{where}: missing/potentially truncated source commit")
        if name in {"manifest", "claims"} and rec.get("classification") not in EVIDENCE_CLASSES:
            bad(f"{where}: invalid evidence classification")
        ident = rec[id_field]
        if not isinstance(ident, str) or not ident:
            bad(f"{where}: invalid {id_field}")
            continue
        if ident in items:
            bad(f"{where}: duplicate ID {ident}")
        items[ident] = rec
    print(f"{name}: {len(items)} unique records")
    return items


def check_git_blob(commit: str, relpath: str, expected_blob: str, where: str) -> None:
    if not SHA40.fullmatch(expected_blob):
        bad(f"{where}: invalid Git blob SHA")
        return
    cp = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{commit}:{relpath}"], capture_output=True, text=True)
    if cp.returncode != 0:
        # A shallow checkout may not have original-history objects, so flag this.
        bad(f"{where}: source commit/path is not present in Git history: {commit}:{relpath}")
    elif cp.stdout.strip() != expected_blob:
        bad(f"{where}: pinned source blob does not match recorded identity")


def main() -> int:
    all_rows = {name: load_dataset(name) for name in DATASETS}
    subsystems = all_rows["subsystems"]
    evidence = all_rows["manifest"]
    claims = all_rows["claims"]
    artifacts = all_rows["artifacts"]

    for ident, entry in subsystems.items():
        if entry["source_commit"] == BASELINE:
            for relpath in [entry["primary_path"], *entry.get("related_paths", [])]:
                local_path(relpath, f"{ident} source")
        for ev in entry["source_evidence_ids"]:
            if ev not in evidence:
                bad(f"{ident}: missing source evidence ID {ev}")
        if entry.get("source_review") in {"completed", "verified"} and not entry["source_evidence_ids"]:
            bad(f"{ident}: source marked complete without evidence")

    for ident, entry in evidence.items():
        loc = entry.get("source_location")
        if loc:
            p = local_path(loc.get("path"), f"{ident} source_location")
            if p and loc.get("git_blob_sha"):
                check_git_blob(entry["source_commit"], loc["path"], loc["git_blob_sha"], ident)
        storage = entry["storage"]
        if not isinstance(storage, dict) or not storage.get("uri"):
            bad(f"{ident}: evidence has no storage URI")
            continue
        uri = storage["uri"]
        if isinstance(uri, str) and not uri.startswith(("https://", "http://")):
            local_path(uri, f"{ident} referenced evidence")
        if storage.get("raw_retained") is True:
            if not isinstance(storage.get("sha256"), str) or not SHA64.fullmatch(storage["sha256"]):
                bad(f"{ident}: raw retained without SHA-256")

    for ident, entry in claims.items():
        for ev in entry["support_evidence_ids"]:
            if ev not in evidence:
                bad(f"{ident}: missing support evidence {ev}")
        if entry["classification"] != "unverified" and not entry["support_evidence_ids"]:
            bad(f"{ident}: observed/measured claim has no evidence")
        for contrad in entry["contradiction_ids"]:
            if contrad not in claims:
                bad(f"{ident}: missing contradiction claim {contrad}")
        loc = entry.get("source_location")
        if loc:
            p = local_path(loc.get("path"), f"{ident} source_location")
            if p and loc.get("git_blob_sha"):
                check_git_blob(entry["source_commit"], loc["path"], loc["git_blob_sha"], ident)

    for ident, entry in artifacts.items():
        digest = entry["sha256"]
        if digest is not None and (not isinstance(digest, str) or not SHA64.fullmatch(digest)):
            bad(f"{ident}: invalid artifact SHA-256")
        if entry["state"] == "not-collected" and (digest is not None or entry.get("location") is not None or entry["raw_retained_locally"]):
            bad(f"{ident}: uncollected artifact cannot claim retained location/hash")
        if entry["raw_retained_locally"] and digest is None:
            bad(f"{ident}: retained local artifact missing SHA-256")
        if not entry["retention_policy"]:
            bad(f"{ident}: retention policy absent")

    if errors:
        print(f"FAIL: {len(errors)} audit-index problems", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"PASS: schema minima, pinned identities, referenced evidence and artifact honesty ({sum(len(v) for v in all_rows.values())} records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
