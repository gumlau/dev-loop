#!/usr/bin/env bash
# Smoke test for scripts/run-loop.sh — proves the multi-project, no-clobber
# launch behavior end-to-end. Spins up a SANDBOXED data dir with two stub
# projects, PATH-shims `claude` to a no-op long-runner, launches the pair,
# asserts both tmux sessions exist with the documented names, then asserts a
# second launch of one project does NOT touch the sibling. Tears down.
#
# Exit codes: 0 = pass · 1 = fail · 77 = skipped (tmux or python3 missing —
# matches autotools convention so test wrappers can skip cleanly in CI).
set -u

command -v tmux    >/dev/null || { echo "skip: tmux not on PATH"; exit 77; }
command -v python3 >/dev/null || { echo "skip: python3 not on PATH"; exit 77; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_LOOP="$SCRIPT_DIR/run-loop.sh"
[ -x "$RUN_LOOP" ] || { echo "✗ canonical run-loop.sh not executable at $RUN_LOOP"; exit 1; }

# Unique session prefix so a CI run never collides with the operator's real
# sessions (named `dev-loop-<projectkey>` by the script).
TAG="$$-$(date +%s)"
PA="smokeA-$TAG"
PB="smokeB-$TAG"
SESS_A="dev-loop-$PA"
SESS_B="dev-loop-$PB"

SANDBOX="$(mktemp -d -t devloop-smoke.XXXXXX)"

cleanup() {
  rc=$?
  tmux kill-session -t "$SESS_A" 2>/dev/null || true
  tmux kill-session -t "$SESS_B" 2>/dev/null || true
  rm -rf "$SANDBOX"
  exit "$rc"
}
trap cleanup EXIT INT TERM

mkdir -p "$SANDBOX/logs"

# Minimal stub projects.json — two dry-run projects so the launcher does not
# block on the live-mode confirm prompt.
cat > "$SANDBOX/projects.json" <<EOF
{
  "defaultProject": "$PA",
  "projects": {
    "$PA": {
      "linearTeam": "local", "linearProject": "local",
      "repoPath": "/tmp", "strategyDoc": ".x",
      "mode": "dry-run", "autonomy": "ask", "backend": "local",
      "build": {}, "git": {}
    },
    "$PB": {
      "linearTeam": "local", "linearProject": "local",
      "repoPath": "/tmp", "strategyDoc": ".x",
      "mode": "dry-run", "autonomy": "ask", "backend": "local",
      "build": {}, "git": {}
    }
  }
}
EOF

# claude shim — long-running no-op so the tmux pane stays alive long enough for
# `tmux has-session` to observe it.
SHIM="$SANDBOX/bin"
mkdir -p "$SHIM"
cat > "$SHIM/claude" <<'EOF'
#!/usr/bin/env bash
sleep 30
EOF
chmod +x "$SHIM/claude"

fail() { echo "✗ $*"; exit 1; }

echo "→ launching both projects ($PA, $PB)"
DATA_DIR="$SANDBOX" PATH="$SHIM:$PATH" PROJECTS="$PA $PB" SWEEP=0 \
  "$RUN_LOOP" </dev/null >"$SANDBOX/launch1.log" 2>&1 \
  || { cat "$SANDBOX/launch1.log"; fail "launch 1 exited non-zero"; }

# tmux sessions register immediately after `tmux new-session -d`; a tiny
# settle delay keeps this robust under CI scheduling jitter.
sleep 0.3

tmux has-session -t "$SESS_A" 2>/dev/null || { cat "$SANDBOX/launch1.log"; fail "$SESS_A not running after launch 1"; }
tmux has-session -t "$SESS_B" 2>/dev/null || { cat "$SANDBOX/launch1.log"; fail "$SESS_B not running after launch 1"; }
echo "✓ both sessions exist with the expected names"

# Capture session creation timestamps to prove RESTART relaunches A but not B.
A_TS_1="$(tmux display-message -p -t "$SESS_A" '#{session_created}')"
B_TS_1="$(tmux display-message -p -t "$SESS_B" '#{session_created}')"

echo "→ default second launch of just $PA → should SKIP (no clobber)"
DATA_DIR="$SANDBOX" PATH="$SHIM:$PATH" PROJECTS="$PA" SWEEP=0 \
  "$RUN_LOOP" </dev/null >"$SANDBOX/launch2.log" 2>&1 \
  || { cat "$SANDBOX/launch2.log"; fail "launch 2 (skip case) exited non-zero"; }

grep -q "already running, skipping" "$SANDBOX/launch2.log" \
  || { cat "$SANDBOX/launch2.log"; fail "expected 'already running, skipping' message"; }

A_TS_2="$(tmux display-message -p -t "$SESS_A" '#{session_created}')"
B_TS_2="$(tmux display-message -p -t "$SESS_B" '#{session_created}')"
[ "$A_TS_1" = "$A_TS_2" ] || fail "$SESS_A was clobbered by a default re-launch (created changed: $A_TS_1 → $A_TS_2)"
[ "$B_TS_1" = "$B_TS_2" ] || fail "$SESS_B was clobbered by a sibling re-launch (created changed: $B_TS_1 → $B_TS_2)"
echo "✓ default re-launch of $PA is a no-op (sibling $PB untouched, $PA preserved)"

echo "→ RESTART=1 second launch of just $PA → should restart A, leave B alone"
# tmux's `#{session_created}` is whole-second epoch. The kill+relaunch round-trip
# is sub-second on a fast machine, so without this sleep A_TS_3 can equal A_TS_1
# (same second) even though a real restart happened — the assertion below would
# false-negative on every run. Wait > 1s so the post-RESTART timestamp lands in
# a different epoch second.
sleep 1.1
DATA_DIR="$SANDBOX" PATH="$SHIM:$PATH" PROJECTS="$PA" RESTART=1 SWEEP=0 \
  "$RUN_LOOP" </dev/null >"$SANDBOX/launch3.log" 2>&1 \
  || { cat "$SANDBOX/launch3.log"; fail "launch 3 (RESTART) exited non-zero"; }
sleep 0.3

tmux has-session -t "$SESS_A" 2>/dev/null || { cat "$SANDBOX/launch3.log"; fail "$SESS_A not running after RESTART"; }
tmux has-session -t "$SESS_B" 2>/dev/null || { cat "$SANDBOX/launch3.log"; fail "$SESS_B clobbered by sibling RESTART"; }
A_TS_3="$(tmux display-message -p -t "$SESS_A" '#{session_created}')"
B_TS_3="$(tmux display-message -p -t "$SESS_B" '#{session_created}')"
[ "$A_TS_3" != "$A_TS_1" ] || fail "$SESS_A was not actually restarted under RESTART=1 (created unchanged: $A_TS_1)"
[ "$B_TS_3"  = "$B_TS_1" ] || fail "$SESS_B's created changed under sibling RESTART (clobber: $B_TS_1 → $B_TS_3)"
echo "✓ RESTART=1 relaunches only the listed project ($SESS_A new, $SESS_B preserved)"

echo "→ invalid project key → must abort cleanly before any tmux mutation"
NOT_REAL="not-a-real-project-$TAG"
SESS_NR="dev-loop-$NOT_REAL"
if DATA_DIR="$SANDBOX" PATH="$SHIM:$PATH" PROJECTS="$NOT_REAL" SWEEP=0 \
     "$RUN_LOOP" </dev/null >"$SANDBOX/launch4.log" 2>&1; then
  cat "$SANDBOX/launch4.log"; fail "invalid project key did not abort with non-zero exit"
fi
grep -q "unknown project key" "$SANDBOX/launch4.log" \
  || { cat "$SANDBOX/launch4.log"; fail "expected 'unknown project key' diagnostic"; }
tmux has-session -t "$SESS_NR" 2>/dev/null && fail "unknown project key created a tmux session"
tmux has-session -t "$SESS_A" 2>/dev/null || fail "$SESS_A killed by invalid-key abort (partial state!)"
tmux has-session -t "$SESS_B" 2>/dev/null || fail "$SESS_B killed by invalid-key abort (partial state!)"
echo "✓ invalid project key aborts cleanly, no partial state"

echo "ok  scripts/run-loop.sh smoke passed"
