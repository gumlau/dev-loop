# Running dev-loop

How to onboard a project, launch the eight agents, pick a model per agent, and
resume. Assumes the plugin is installed (`/plugin list` shows `dev-loop`) and the
[Requirements](../README.md#requirements) are met (Claude Code, Linear MCP — for the
`linear` backend — `gh`, a repo, a Linear team/project).

---

## 1. Onboard a project (new project)

Run the setup command **once** — it is idempotent and operator-present:

```
/dev-loop:init
```

It will, with you in the loop:
1. **Detect the project shape & confirm repos.** init detects greenfield (no code yet) /
   brownfield (existing code) / adopting (pre-existing human tickets), and single- vs
   multi-repo. It echoes back each `repoPath` / `repos[].path` (the loop *commits from
   them*, so this is a gate). Greenfield runs a short strategy interview; brownfield is
   read-only-mapped into the doc-base `Current state`.
2. **Ask the backend** — `linear` (coordinate through Linear) or `local` (a machine-local
   file board in the data dir; no Linear needed). See [conventions §18](../references/conventions.md#18-backend--linear-vs-local).
3. Gather/validate the per-project config and write it to
   `~/.claude/plugins/data/dev-loop/projects.json` (creating only what's missing).
4. **linear**: ensure the workflow labels + the Linear project exist (asking before
   creating the project), plus one `repo:<name>` label per `repos[]` entry when
   multi-repo. **local**: scaffold `board/` (`tickets/`, `counter.json`) and require a
   repo-file `strategyDoc`. Either way, scaffold the PM doc-base headings (Vision / Goals
   / Non-goals / Current state / Personas / Glossary / Decisions / Candidate ideas) in
   the doc-home repo, seeding `Current state` from brownfield mapping if available.
5. Smoke-check the test env + build, create the runtime files
   (`pm-state.json` / `qa-state.json` / `lessons.md`), note the per-agent **reports tree**
   (`<key>/reports/<agent>/{daily,weekly,monthly}/`, conventions §22 — scaffolded or created
   lazily), and print a **readiness checklist**.

When the checklist is green, set `"mode": "live"` in `projects.json` (init leaves new
projects in `dry-run` for first contact) and launch the agents (next section).

> Re-running `/dev-loop:init` on an existing project is safe — it re-checks and
> re-prints the readiness report, overwriting nothing.

---

## 2. Launch the agents

The plugin **ships no harness** — pick whichever fits. Both run the same eight skills:
`/dev-loop:pm-agent`, `qa-agent`, `dev-agent`, `sweep-agent`, `reflect-agent`, and the
three opt-in **outward** agents (conventions §21) `ops-agent`, `architect-agent`,
`signal-agent`.

### A. Agent View — native, recommended (`claude agents`)

[Agent View](https://code.claude.com/docs/agent-view) (Claude Code ≥ 2.1.139) is one
screen for all your background sessions — *Needs input / Running / Done* — that keep
running with no terminal attached.

```
claude agents            # open the view (scoped: claude agents --cwd ~/path)
```

Then dispatch each agent as its own self-looping row (a slash command typed in the view
becomes a new background session; `/loop` makes it recurring):

```
/loop 5m  /dev-loop:pm-agent
/loop 5m  /dev-loop:qa-agent
/loop 5m  /dev-loop:dev-agent
/loop 30m /dev-loop:sweep-agent
/loop 24h /dev-loop:reflect-agent
/loop 10m /dev-loop:ops-agent        # OUTWARD (§21), opt-in — watches running prod (anti-flap)
/loop 24h /dev-loop:architect-agent  # OUTWARD (§21), opt-in — whole-codebase tech-debt audit
/loop 1h  /dev-loop:signal-agent     # OUTWARD (§21), opt-in — real-user signal intake (no-op if no sources)
```

Manage from the shell: `claude attach <id>` (open), `claude logs <id>` (recent output),
`claude stop <id>` (stop). `Space` peeks a row, `Enter` attaches.

> **Model note:** a dispatched Agent View session uses the **view's** model (set the view
> with `claude agents --model <m>`). For *different* models per agent, use the launcher
> below (or open separate views). Agent View applies one model per view.

### B. Local tmux launcher — mixed models, one command

A small launcher opens a tmux session **per project**, one pane per agent, each a
headless `claude` loop, and reads your per-agent `models` from config so every pane
gets its own `--model`. The canonical copy is in the plugin repo
(`scripts/run-loop.sh`); operators **install** it by copying it into the data dir
(it is intentionally not run from the repo path):

```
cp scripts/run-loop.sh ~/.claude/plugins/data/dev-loop/run-loop.sh
chmod +x ~/.claude/plugins/data/dev-loop/run-loop.sh
```

When the canonical changes (a new `dev-loop` release), re-run the copy.

#### One project

```
~/.claude/plugins/data/dev-loop/run-loop.sh                # defaultProject: PM/QA/Dev + Sweep; Reflect off
~/.claude/plugins/data/dev-loop/run-loop.sh boardku        # positional: pick a project key
PROJECT=foo ~/.claude/plugins/data/dev-loop/run-loop.sh    # env equivalent
MODE=once   ~/.claude/plugins/data/dev-loop/run-loop.sh    # one pass each, then stop (good first test)
REFLECT=1   ~/.claude/plugins/data/dev-loop/run-loop.sh    # also run the daily Reflect pane
SWEEP=0     ~/.claude/plugins/data/dev-loop/run-loop.sh    # omit the janitor pane
OPS=1       ~/.claude/plugins/data/dev-loop/run-loop.sh    # also run the Ops (prod-watch) pane (~10m; off by default)
ARCHITECT=1 ~/.claude/plugins/data/dev-loop/run-loop.sh    # also run the Architect (tech-debt) pane (daily; off by default)
SIGNAL=1    ~/.claude/plugins/data/dev-loop/run-loop.sh    # also run the Signal (user-intake) pane (hourly; off; no-op if no sources)
```

#### Launch multiple projects (no cross-project clobber)

To run several onboarded loops in parallel — each in its own isolated tmux session
named **`dev-loop-<project-key>`**, so two sessions never share a name and a second
launch cannot hard-kill a sibling:

```
PROJECTS="boardku citron-geo" ~/.claude/plugins/data/dev-loop/run-loop.sh    # explicit set
PROJECTS=all                  ~/.claude/plugins/data/dev-loop/run-loop.sh    # every project in projects.json (alphabetical)
PROJECTS=""                   ~/.claude/plugins/data/dev-loop/run-loop.sh    # same as PROJECTS=all
~/.claude/plugins/data/dev-loop/run-loop.sh boardku citron-geo               # positional equivalent
```

Pre-flight, the launcher validates every requested project key against
`projects.json` **before** killing or launching anything — an unknown key aborts
with no partial state.

**Re-launch is opt-in.** A listed project whose `dev-loop-<key>` session is
*already running* is **skipped by default** (logged `already running, skipping`).
To explicitly relaunch one, set `RESTART=1` (or pass `--restart`) — it kills and
re-creates only the listed project's session; siblings are never touched:

```
PROJECTS="boardku" RESTART=1  ~/.claude/plugins/data/dev-loop/run-loop.sh    # restarts boardku, untouched otherwise
PROJECTS="boardku" ~/.claude/plugins/data/dev-loop/run-loop.sh --restart     # equivalent (positional flag — must come AFTER the script)
```

Operate on the running set with the standard tmux tools:

```
tmux ls | grep '^dev-loop-'                                                 # list every dev-loop session
tmux attach -t dev-loop-<project>                                           # attach (Ctrl-b d to detach)
tmux kill-session -t dev-loop-<project>                                     # stop one
tmux ls -F '#{session_name}' | grep '^dev-loop-' | xargs -n1 tmux kill-session -t   # stop all
```

It prints a blast-radius banner (per project: mode, autonomy, agent set, session
name) before starting. Logs tee to `~/.claude/plugins/data/dev-loop/logs/<project>/`.

---

## 3. Per-agent models

The model is chosen **at launch** (a SKILL can't set its own model), via a per-project
`models` map in `projects.json`:

```jsonc
"models": { "pm": "opus", "qa": "opus", "dev": "opus", "sweep": "opus", "reflect": "opus", "ops": "opus", "architect": "opus", "signal": "opus" }
```

**Every agent defaults to `opus`** — maximize correctness across the whole loop. Tune an
agent **down** only to economize; the table shows where `opus` matters most vs. where a
cheaper model is tolerable:

| Agent | Default | Could economize to | Why |
|---|---|---|---|
| **dev** | `opus` | — | hardest — implements, self-reviews the diff, fixes |
| **pm** | `opus` | — | product/scoping judgment + review |
| **architect** | `opus` | — | whole-codebase reasoning about debt/abstractions |
| **reflect** | `opus` | `sonnet` | careful curation, but runs only daily |
| **qa** | `opus` | `sonnet` | capable; runs often |
| **ops** | `opus` | `sonnet` | mechanical polling + anti-flap judgement; runs often |
| **signal** | `opus` | `sonnet` | triage + PII-safe summarization; periodic |
| **sweep** | `opus` | `haiku` | mechanical hygiene |

The tmux launcher applies this map automatically and **defaults each pane to `--model
opus`** when the map omits an agent. In Agent View, set the view's model (e.g.
`claude agents --model opus`); it's one model per view, so run mixed models through the
launcher if you economize some agents.

---

## 4. Cadence

Agents self-throttle (idle fires are cheap no-ops), so tighter intervals are safe:

| Agent(s) | Cadence | Why |
|---|---|---|
| PM / QA / Dev | ~5 min | the producing loop |
| Sweep | ~30 min | janitorial; re-walking an unchanged board is waste |
| Reflect | daily | reflects *after* a day of churn |
| Ops *(opt-in)* | ~10–15 min | watches running prod; tight polls are the point, but self-throttles |
| Architect *(opt-in)* | daily | whole-codebase audit; SHA-gate makes most fires no-ops |
| Signal *(opt-in)* | hourly / daily | real-user intake; no-op when no sources or no new signal |

---

## 5. Resume / restart

**There is no special resume step — the agents are stateless per fire** (conventions §0).
All state lives in Linear (or the local board), git, the `*-state.json` files, and the
per-agent **reports tree** (`<key>/reports/<agent>/…`, conventions §22), never in
conversation memory. So to resume after stopping (or a crash, a reboot, a laptop
sleep): **just launch the agents again** — each re-reads ground truth and continues
exactly where the board left off. To steer an agent, drop a `<report>.review.md` (点评)
next to one of its reports — it reads the un-acted review at its next run-start and turns it
into a `lessons.md` rule. *(Running in the cloud with no disk access? Set
`reports.sink:"linear"` (conventions §23) to read reports + write the 点评 in Linear
instead — opt-in, default-off, with §16 guardrails.)*

- **Agent View:** background sessions persist across sleep and reappear in `claude
  agents`; they stop only if the machine powers off. After a reboot, re-dispatch the
  `/loop …` lines from §2A. To rejoin a specific session: `claude attach <id>`.
- **tmux launcher:** if your project's `dev-loop-<project>` session is gone, re-run
  `run-loop.sh` (it picks up where it left off — per-fire stateless agents re-read
  ground truth from the board, git, and `*-state.json`). If it still exists,
  `tmux attach -t dev-loop-<project>` to rejoin. List every running loop with
  `tmux ls | grep '^dev-loop-'`.
- A single in-flight fire that died mid-ticket is **self-healing**: Dev's Step 0
  reclaims a ticket it left stranded `In Progress` on the next fire (orphan-recovery),
  and Sweep catches the rest.

---

## 6. Stop

- **Agent View:** `claude stop <id>` per session (or stop them all from the view).
- **tmux:** stop one project with `tmux kill-session -t dev-loop-<project>`, or stop
  every dev-loop session in one shot with
  `tmux ls -F '#{session_name}' | grep '^dev-loop-' | xargs -n1 tmux kill-session -t`.
  Don't use a bare `tmux kill-session -t dev-loop` — the launcher only creates
  per-project sessions, so that command always fails with "no session found" and
  **leaves the real `dev-loop-<project>` sessions running** (a hurried operator may
  read the silent failure as "already stopped" while `autoCommit`/`autoPush`/`autoDeploy`
  keep firing).

---

## Safety

`mode:"live"` + `autonomy:"full"` + `autoPush`/`autoDeploy` = **unattended commits,
pushes, and prod deploys with no human gate** — the intended power of the loop. Try
`mode:"dry-run"` or a single `MODE=once` pass first. The `dev-loop` label (or, in local
mode, the board directory) is the firewall that keeps the loop off your human backlog
(conventions §2).
