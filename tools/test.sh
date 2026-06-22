#!/usr/bin/env bash
# Plugin self-test gate — wired into projects.json `build.test` for the
# dev-loop project. Pure-stdlib (python3 + bash). Add new test modules to
# the `TEST_MODULES` list as the suite grows.

set -euo pipefail

cd "$(dirname "$0")/.."

# 1. Plugin self-lint (LOOP-4) — replaces the old one-line JSON load. Covers
#    JSON integrity, SKILL frontmatter, conventions §N cross-refs, markdown
#    link integrity, lessons.md skeleton parity, and README/CHANGELOG/
#    conventions agent consistency. Folded into this gate so a plain
#    `bash tools/test.sh` is the complete typecheck+test gate.
python3 scripts/lint-plugin.py

# 2. Python integration tests.
TEST_MODULES=(
  tests.test_dashboard
  tests.test_lint_plugin
  tests.test_run_loop_smoke
)

python3 -m unittest -v "${TEST_MODULES[@]}"

echo "ok  all plugin self-tests passed"
