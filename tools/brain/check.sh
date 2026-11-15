#!/usr/bin/env bash
# The brain tools' check, the same in CI and locally: compile, lint (ruff 0.6.9), tests (loopback fakes only, no Docker).
#   npm run check:brain
# Uses `ruff` from PATH when it is 0.6.9, otherwise `pipx run ruff==0.6.9` (as CI does).
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m py_compile tools/brain/*.py
if [ "$(ruff --version 2>/dev/null)" = "ruff 0.6.9" ]; then
  ruff check tools/brain
else
  pipx run ruff==0.6.9 check tools/brain
fi
python3 -I -m unittest discover -s tools/brain -p 'test_*.py'
