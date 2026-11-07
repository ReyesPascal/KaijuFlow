# Findings records: how to write and maintain them

Findings are separate from the original Usenet Ultimate source code. This folder holds **one Markdown document per substantive observation**, with stable IDs; all findings must also have a matching atomic entry in `../index/claims.jsonl` and evidence in `../index/manifest.jsonl`. The [root evidence index](../README.md) is the navigation entry point.

## Required fields

- **Finding ID** / short title / affected subsystem ID(s); first observed date and source baseline commit.
- **Classification:** `source-observed`, `REA-observed`, `test-observed`, `measured`, or `unverified`.
- **Status:** e.g. confirmed-code-fact, open-question, reproduction-needed, fixed-in-branch, verified-regression, superseded, stale-on-new-source. Keep security *severity* separate from technical confidence.
- **Exact source anchor:** GitHub permalink with full commit SHA and `#Lx-Ly`, path, optional symbol and verified Git blob SHA. Relative paths without pinned commit are insufficient for assertions that must survive future refactors.
- **What was directly observed:** narrowly worded, no speculation. Identify tool/version and evidence IDs.
- **Scope and limitations:** what it does *not* show (e.g., unknown runtime effects); any contradictory evidence.
- **Impact/hypothesis:** clearly marked as an inference if not tested; security priority is not a proof of exploit.
- **Proposed test or change:** isolated, synthetic reproduction, expected result, fallback and rollback; no production writes.
- **Revalidation:** if source path/blob, dependency version, config or runtime changes, record a new test/evidence ID and mark superseded claims, do not rewrite historical evidence silently.

## Storage and review

The original app code and binary assets must stay byte/mode identical to pinned upstream throughout this baseline. Keep new docs, evidence indices, reports and test harness separate from original paths. Source changes, if later approved, get their own reviewed PR and a regression evidence record.

Commit only reviewed and sanitized findings. Never include passwords, live NZBs, article bodies, credential-bearing URLs, authentication tokens, session IDs or Brain host logs. Local raw REA Evidence needs SHA-256 identity, access-controlled storage and a real backup/retention policy before it can be claimed durable. Short-lived CI artifacts don't substitute for archival.

## Active example

- [F-KF-SEC-001 — NNTP TLS certificate validation disabled](F-KF-SEC-001.md): source-observed, not yet runtime-exploited or fixed.

## Suggested review loop

1. Assign a stable finding and claim ID; pin the exact source version.
2. Check the code and independently reproduce the *specific* claim using the appropriate tool.
3. Store support and contradiction IDs; log negative results and coverage limitations.
4. Reproduce behavior in a fake service if behavioral consequence matters.
5. Review a proposed fix separately; only declare verified after an isolated regression test.
