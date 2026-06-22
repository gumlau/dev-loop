#!/usr/bin/env bash
# Plugin self-test gate — wired into projects.json `build.test` for the
# dev-loop project. Pure-stdlib (python3 + bash). Add new test modules to
# the `TEST_MODULES` list as the suite grows.

set -euo pipefail

cd "$(dirname "$0")/.."

# 1. JSON integrity (mirrors `build.typecheck`, but cheap to repeat here so a
#    plain `bash tools/test.sh` is a complete gate).
python3 -c "
import json, glob
for f in glob.glob('.claude-plugin/*.json') + ['config/projects.example.json']:
    with open(f) as fh:
        json.load(fh)
    print(f'ok  {f}')
"

# 2. Python integration tests.
TEST_MODULES=(
  tests.test_dashboard
)

python3 -m unittest -v "${TEST_MODULES[@]}"

echo "ok  all plugin self-tests passed"
