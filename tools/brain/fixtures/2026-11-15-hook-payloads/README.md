# PreToolUse payloads, Claude Code 2.1.325

What Claude Code sends `tools/brain/guard.py` on stdin, captured on 2026-11-15 with a temporary hook (`cat > <file>`) in a worktree's `.claude/settings.local.json`, then one harmless call each:

- `bash.json`: `echo capture-probe`.
- `read.json`: Read of `tools/brain/ruff.toml`.
- `grep.json`: Grep for `DEFAULT_TEST_DIR` in `tools/brain/common.py`.

Scrubbed: `session_id`, `prompt_id`, `tool_use_id` and `transcript_path` replaced; the worktree path replaced by the repo root. `test_guard.py` feeds these to the hook as captured, and builds its refused cases by swapping only the `tool_input` path or command (and `cwd`).
