#!/usr/bin/env bash
# dev-loop launcher — opens a tmux session PER PROJECT, one window per agent, each a
# headless `claude` loop. Reads project/mode/autonomy/models from projects.json.
#
# CANONICAL COPY: this file is the template. It is NOT executed in-place from the
# plugin repo. The operator copies (or symlinks) it to the data dir, where the
# launcher actually runs:
#
#   cp scripts/run-loop.sh ~/.claude/plugins/data/dev-loop/run-loop.sh
#   chmod +x ~/.claude/plugins/data/dev-loop/run-loop.sh
#
# bash 3.2-compatible (macOS).
#
# Usage:
#   ~/.claude/plugins/data/dev-loop/run-loop.sh                # defaultProject: PM/QA/Dev + Sweep, looping
#   ~/.claude/plugins/data/dev-loop/run-loop.sh boardku        # one project (positional)
#   ~/.claude/plugins/data/dev-loop/run-loop.sh a b c          # many projects (positional)
#   PROJECT=foo            ...run-loop.sh                      # one project (env)
#   PROJECTS="a b c"       ...run-loop.sh                      # many projects (env, space-separated)
#   PROJECTS=all           ...run-loop.sh                      # every project in projects.json (alphabetical)
#   PROJECTS=""            ...run-loop.sh                      # same as PROJECTS=all
#   MODE=once              ...run-loop.sh                      # one pass each, then stop (best first test)
#   REFLECT=1              ...run-loop.sh                      # also run daily Reflect
#   SWEEP=0                ...run-loop.sh                      # omit the janitor
#   OPS=1 ARCHITECT=1 SIGNAL=1 ...run-loop.sh                  # also run the opt-in OUTWARD agents
#   RESTART=1              ...run-loop.sh                      # kill+relaunch a listed project's session if already running
#                                                              # (default: skip listed projects whose session already runs)
#
# Each project gets its OWN tmux session named "dev-loop-<project>", so parallel
# loops never clobber each other. A second invocation that lists the SAME project
# is a no-op by default (logs "already running, skipping"); set RESTART=1 to
# explicitly relaunch only that one — sibling sessions are never touched.
#
# Logs are namespaced per project: logs/<project>/.
#   List loops : tmux ls | grep '^dev-loop-'
#   Attach     : tmux attach -t dev-loop-<project>   ·   Detach: Ctrl-b d
#   Stop one   : tmux kill-session -t dev-loop-<project>
#   Stop all   : tmux ls -F '#{session_name}' 2>/dev/null | grep '^dev-loop-' | xargs -n1 tmux kill-session -t
#
# Test-overridable env (used by scripts/smoke-run-loop.sh — operators should
# rarely set these by hand):
#   DATA_DIR       — override the data dir root (default $HOME/.claude/plugins/data/dev-loop)
#   CLAUDE_BIN     — override the `claude` binary (default `claude` on PATH)

set -euo pipefail

DATA_DIR="${DATA_DIR:-$HOME/.claude/plugins/data/dev-loop}"
CONFIG="$DATA_DIR/projects.json"
LOG_DIR="$DATA_DIR/logs"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

MODE_ONCE="${MODE:-loop}"     # MODE=once → single pass each
SWEEP="${SWEEP:-1}"
REFLECT="${REFLECT:-0}"
OPS="${OPS:-0}"
ARCHITECT="${ARCHITECT:-0}"
SIGNAL="${SIGNAL:-0}"
RESTART="${RESTART:-0}"

# --restart long-option alias for RESTART=1 (consumed before positional parsing)
KEEP_ARGS=""
for a in "$@"; do
  if [ "$a" = "--restart" ]; then
    RESTART=1
  else
    KEEP_ARGS="$KEEP_ARGS $a"
  fi
done
# shellcheck disable=SC2086
set -- $KEEP_ARGS

command -v "$CLAUDE_BIN" >/dev/null || { echo "✗ claude CLI not on PATH ($CLAUDE_BIN)"; exit 1; }
command -v tmux   >/dev/null || { echo "✗ tmux not found — install: brew install tmux"; exit 1; }
command -v python3 >/dev/null || { echo "✗ python3 not found"; exit 1; }
[ -f "$CONFIG" ] || { echo "✗ config not found: $CONFIG (run /dev-loop:init first)"; exit 1; }

cfg() { python3 -c "import json,sys; d=json.load(open('$CONFIG')); print(eval(sys.argv[1]))" "$1"; }

# Resolve the project list.
# Precedence: positional args > PROJECTS env > PROJECT env > defaultProject.
# PROJECTS="" and PROJECTS="all" both expand to every project (alphabetical).
if [ "$#" -gt 0 ]; then
  PROJECT_LIST="$*"
elif [ "${PROJECTS+set}" = "set" ]; then
  if [ -z "$PROJECTS" ] || [ "$PROJECTS" = "all" ]; then
    PROJECT_LIST="$(cfg "' '.join(sorted(d['projects'].keys()))")"
  else
    PROJECT_LIST="$PROJECTS"
  fi
else
  PROJECT_LIST="${PROJECT:-$(cfg "d.get('defaultProject') or next(iter(d['projects']))")}"
fi

cadence() {  # seconds between fires per agent
  case "$1" in
    pm|qa|dev) echo 300;; sweep) echo 1800;; reflect) echo 86400;;
    ops) echo 600;; architect) echo 86400;; signal) echo 3600;; *) echo 300;;
  esac
}

# Assemble the agent list (shared across projects)
AGENTS="pm qa dev"
[ "$SWEEP" = "1" ]     && AGENTS="$AGENTS sweep"
[ "$REFLECT" = "1" ]   && AGENTS="$AGENTS reflect"
[ "$OPS" = "1" ]       && AGENTS="$AGENTS ops"
[ "$ARCHITECT" = "1" ] && AGENTS="$AGENTS architect"
[ "$SIGNAL" = "1" ]    && AGENTS="$AGENTS signal"

# Globals set per project by launch_project, read by model()/pane_cmd().
P=""; PMODE=""; PAUTO=""; PLOG=""
model()   { cfg "(d['projects']['$P'].get('models') or {}).get('$1','opus')"; }
pane_cmd() {  # build the shell command for one agent's window (uses globals P, PLOG)
  a="$1"; m="$(model "$a")"
  prompt="/dev-loop:${a}-agent for project ${P}"
  log="$PLOG/${a}-\$(date +%Y%m%d).log"
  once="$CLAUDE_BIN --model $m --dangerously-skip-permissions -p \"$prompt\" 2>&1 | tee -a \"$log\""
  if [ "$MODE_ONCE" = "once" ]; then
    echo "echo '[$P/$a · one pass · $m]'; $once; echo; echo '[done: $P/$a — press enter]'; read _; exec \$SHELL"
  else
    sec="$(cadence "$a")"
    echo "while true; do echo '[$P/$a · fire · $m]'; $once; echo '[$P/$a sleeping ${sec}s]'; sleep $sec; done"
  fi
}

# Validate every requested project exists, and collect their modes for one confirm.
# This pre-flight runs BEFORE any tmux kill/launch — an invalid key aborts with
# zero partial state.
LIVE_PROJECTS=""
for P in $PROJECT_LIST; do
  exists="$(cfg "'$P' in d['projects']")"
  [ "$exists" = "True" ] || { echo "✗ unknown project key: '$P' — not in projects.json"; exit 1; }
  [ "$(cfg "d['projects']['$P'].get('mode','dry-run')")" = "live" ] && LIVE_PROJECTS="$LIVE_PROJECTS $P"
done

mkdir -p "$LOG_DIR"

# Blast-radius banner (all projects at once)
echo "──────────────────────────────────────────────────────"
echo "  dev-loop launcher"
echo "  projects: $PROJECT_LIST"
echo "  run     : $MODE_ONCE        agents : $AGENTS"
[ "$RESTART" = "1" ] && echo "  restart : ON (will kill+relaunch any listed project's existing session)"
for P in $PROJECT_LIST; do
  echo "    · $P  [mode=$(cfg "d['projects']['$P'].get('mode','dry-run')") autonomy=$(cfg "d['projects']['$P'].get('autonomy','ask')")]  → session dev-loop-$P"
done
echo "──────────────────────────────────────────────────────"
if [ -n "$LIVE_PROJECTS" ]; then
  echo "  ⚠ mode=live for:$LIVE_PROJECTS"
  echo "    Live agents may create/transition tickets (and, if git flags on, commit/push/deploy)."
  printf "  Continue? [y/N] "; read -r ans; [ "$ans" = "y" ] || { echo "aborted"; exit 0; }
fi

launch_project() {  # start one tmux session for project $P
  PMODE="$(cfg "d['projects']['$P'].get('mode','dry-run')")"
  PAUTO="$(cfg "d['projects']['$P'].get('autonomy','ask')")"
  PLOG="$LOG_DIR/$P"
  local sess="dev-loop-$P"
  mkdir -p "$PLOG"

  # Pre-flight: already-running guard. Default = skip; RESTART=1 = relaunch
  # ONLY this project's session (never touches siblings).
  if tmux has-session -t "$sess" 2>/dev/null; then
    if [ "$RESTART" = "1" ]; then
      tmux kill-session -t "$sess" 2>/dev/null || true
      echo "↻ $P → session '$sess' restarted (RESTART=1)"
    else
      echo "= $P → session '$sess' already running, skipping (set RESTART=1 to relaunch)"
      return 0
    fi
  fi

  set -- $AGENTS
  local first="$1"; shift
  tmux new-session -d -s "$sess" -n "$first" "$(pane_cmd "$first")"
  for a in "$@"; do
    tmux new-window -t "$sess" -n "$a" "$(pane_cmd "$a")"
  done
  echo "✓ $P → session '$sess'  (attach: tmux attach -t $sess  ·  logs: $PLOG/)"
}

for P in $PROJECT_LIST; do
  launch_project
done

echo "──────────────────────────────────────────────────────"
echo "✓ Started ${MODE_ONCE} loops for: $PROJECT_LIST"
echo "  List   : tmux ls | grep '^dev-loop-'"
echo "  Stop 1 : tmux kill-session -t dev-loop-<project>"
echo "  Stop * : tmux ls -F '#{session_name}' | grep '^dev-loop-' | xargs -n1 tmux kill-session -t"
