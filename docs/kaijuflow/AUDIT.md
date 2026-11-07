# Audit findings

One row per finding, in fix order. Update the Status column when a fix merges. Older audit notes are in git history.

| # | What's wrong | Where | How bad | Status |
| --- | --- | --- | --- | --- |
| 1 | Self-requests use `localhost`, which can resolve to IPv6 `::1` inside Docker, where nothing listens. Auto-queue fails (`Auto-queue failed… ::1:1337`), so top sources aren't pre-queued and first plays are slower. | `src/addon/healthCheckCoordinator.ts:26`, `src/addon/index.ts:302`, `src/addon/streamBuilder.ts:42` | High | Fixed (PR #6) |
| 2 | A HEAD request deletes library items. The delete route is a GET, and Express also runs GET handlers for HEAD. | `src/routes/nzbdav.ts` (D14) | High (data loss) | Fixed (PR #7), test A4-DELETE-003 |
| 3 | Failed deletes (503) are marked as done, so a retry is skipped. | `src/routes/nzbdav.ts` (D14) | Medium | Fixed (PR #7), test A4-DELETEALL-007 |
| 4 | Settings autosave race: an older save response overwrites a newer setting in the UI. | `ui/src/hooks/useAppConfig.ts` | Medium | Fixed (PR #8), test A4-REACT-ORDER |
| 5 | No time limit when preparing a first play (`getAttemptBudgetMs` returns 0). PTP gives up after about 42 s before KaijuFlow falls back. Target: a 25–30 s budget. | D06 | High | Open |
| 6 | Health checks have no total NNTP connection cap (workers × providers). They can starve playback. | N05 | Medium | Open |
| 7 | TLS certificate checks are off (`rejectUnauthorized: false`). Make it a setting, defaulting to on. | `src/health/nntpConnection.ts` | Medium (security) | Open |
| 8 | Part of a TVDB login response is logged when the token is missing. | `src/idResolver.ts` | Low | Open |

IDs like D06, D14 and N05 point to the [NzbDAV](references/nzbdav/README.md) and [NNTP](references/nntp/README.md) references.
