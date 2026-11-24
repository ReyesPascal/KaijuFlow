# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## `gh` quirks on this machine (gh 2.46)

`tools/brain/guard.py` (a project hook) refuses the failing calls and names the working one:

- No `--parent` on `gh issue create`: create the issue, then `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<db id>`.
- `gh issue view <n>` fails without `--json` and with `--comments` (Projects classic GraphQL error): `gh issue view <n> --json number,title,body,labels,comments`.
- `gh pr checks` has no `--json`: a PR's CI is read by `tools/brain/prwatch.py <n>` (below).
- `gh pr edit` fails: `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>`.
- Sub-issue order and blocker links go through `gh api` (see **Blocking** and `tools/brain/frontier.py`).

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: create the child, then `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>` (database id, as in **Blocking** below; no `--parent` on gh 2.46, see above). Without sub-issues, put `Part of #<parent>` at the top of the child body.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`
- **The rules for tickets, PRs and merging** are in `tools/brain/docs/rules.md`, their one home: [Ticket first, order in the tracker](../../tools/brain/docs/rules.md#ticket-first-order-in-the-tracker), [One home per rule](../../tools/brain/docs/rules.md#one-home-per-rule), [Check before claiming](../../tools/brain/docs/rules.md#check-before-claiming), [Every pushed PR is watched, and plan PRs merge on green](../../tools/brain/docs/rules.md#every-pushed-pr-is-watched-and-plan-prs-merge-on-green), [Close when done](../../tools/brain/docs/rules.md#close-when-done), [The gh calls that work here](../../tools/brain/docs/rules.md#the-gh-calls-that-work-here). The steps they take:
- **Order**: record an order as a blocked-by link (see **Blocking**); `tools/brain/frontier.py` lists tickets in map order.
- **Watch a PR**: right after pushing, start `python3 -I tools/brain/prwatch.py <n>` with the shell's background mode. It prints one line at once and one line as soon as it knows (it polls every 5 s): `GREEN` once every check passed (ready to merge), `RED` with the failed checks as soon as one fails, or a gh error. Merge with `gh pr merge <n> --merge`.
- **Close**: `gh issue close <n> --comment "..."`, the parent too when its last sub-issue closes.

Infer the repo from `git remote -v`; `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **Edit a PR body**: the `gh api -X PATCH` call in the quirks above.
- **List external PRs for triage**: `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`.
- **Comment / label / close**: `gh pr comment`, `gh pr close`; labels via `gh issue edit <n> --add-label` (a PR is an issue; `gh pr edit` is refused here).

GitHub shares one number space across issues and PRs, so a bare `#42` may be either: resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `spec` (`docs/agents/triage-labels.md`), holding the spec as its body; this repo's map is spec #183 (since 2026-11-20; #159 before, #58 before that). `gh issue create --label spec`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (see **Make an issue a sub-issue of a parent**). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies**, the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only, the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. Where they are, the body holds no blocker list; `tools/brain/frontier.py` warns about one. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me`, the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
