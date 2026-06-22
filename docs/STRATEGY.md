# dev-loop — Strategy

> PM's north star (conventions §20). init scaffolded these headings and seeded
> **Current state** from a read-only map of the repo on 2026-06-22. PM owns this doc
> thereafter (append-only; never rewrites existing content). This is a **meta /
> dogfooding** project: the product *is* the dev-loop plugin itself.

## Vision

dev-loop is a Claude Code plugin: a set of autonomous agents that run a software
self-improvement loop coordinated entirely through ticket state (Linear or a
machine-local file board). The product we are building here is **the plugin itself** —
the agent instructions, the shared contract, the config surface, and the operator
ergonomics that let one operator run many self-improving product loops in parallel from
one machine. The north star is a loop an operator steers by **reviewing**, not by
editing code: correct, safe-by-gates, and pleasant to operate at multi-project scale.

## Goals (north star)

- **Trustworthy autonomy.** A red build never ships; self-modification of the agents'
  own instructions is surfaced, never auto-applied (§17); the `dev-loop` label / board
  dir firewall stays load-bearing.
- **Multi-project parallelism is first-class.** One operator runs N product loops at
  once with zero cross-project interference and one-command launch — not N manual,
  clobber-prone invocations.
- **Observability / steerability.** The operator can *see* the loop — agents, projects,
  ticket flow, throughput — and steer it through reports + 点评, not code edits.
- **Onboarding is a near-no-op.** `init` makes any repo loop-ready idempotently; a second
  run just re-prints readiness.
- **The contract stays lean.** conventions.md is the single source of truth all 8 agents
  read first; it should get *clearer*, not just longer.

## Non-goals

- **Not a hosted SaaS / multi-tenant control plane.** This is a local-first operator
  tool. No accounts, no server requirement, no cloud dependency for the core loop.
- **Not replacing Linear** when the operator wants it — `backend:"local"` is an option,
  not a mandate. Both backends stay first-class.
- **No agent auto-rewriting its own SKILL/conventions** (§17). Structural self-change is
  proposed for a human, never executed by the loop.
- **No new agent roles** unless an existing one genuinely can't cover the need — eight is
  already a lot of surface to keep coherent.

## Current state

*(Seeded by init 2026-06-22 from a read-only map; PM keeps this current.)*

- **v0.10.0.** Eight agents: five inward (**PM, QA, Dev, Sweep, Reflect**) + three
  outward observe-and-file (**Ops, Architect, Signal**, §21). Plus the `init` setup
  command (DETECT → MAP → ASSEMBLE → LOAD).
- **Coordination is backend-pluggable** (§18): `linear` (default, via Linear MCP) or
  `local` (a machine-local file board under `${CLAUDE_PLUGIN_DATA}/<key>/board/`). All
  state machine + protocols are identical across backends.
- **Multi-repo per product** (§19): `repos[]` routes each ticket to one repo via a
  `repo:<name>` label, with per-repo build/branch/deploy; single-repo is 100% unchanged.
- **Reports + operator review (点评)** (§22/§23): every agent writes daily/weekly/monthly
  reports under `<key>/reports/<agent>/`; a sibling `<report>.review.md` becomes a
  `lessons.md` rule. Optional `reports.sink:"linear"` hosts reports + 点评 in Linear for
  cloud/remote operation.
- **Layout** (the data dir, `~/.claude/plugins/data/dev-loop/`): `projects.json` and the
  shared per-operator `lessons.md` at the root; everything per-project lives under
  `<key>/` — `board/`, `reports/`, and (as of 2026-06-22) the agent state files
  `pm/qa/ops/architect/signal-state.json`, so concurrent multi-project loops no longer
  share-and-clobber state (§11). Legacy flat root `pm-state.json`/`qa-state.json` remain
  vestigial for back-compat reads and can be removed once each loop has fired once.
- **Launcher**: `run-loop.sh` (lives in the data dir, not the plugin) opens a tmux
  session, one pane per agent, for **one** project per invocation.
- **Multi-project launcher shipped (LOOP-2, `624e325`, 2026-06-22).** The canonical
  template now lives in the plugin repo at `scripts/run-loop.sh` (operator installs
  via `cp scripts/run-loop.sh ~/.claude/plugins/data/dev-loop/run-loop.sh`); one
  command launches N projects (`PROJECTS="a b c"` or `PROJECTS=all`), each in its
  own `dev-loop-<key>` tmux session, with a default skip-if-already-running guard
  and `RESTART=1`/`--restart` that rotates only the listed project (siblings never
  touched). Invalid keys abort pre-mutation. End-to-end coverage via
  `scripts/smoke-run-loop.sh` + `tests/test_run_loop_smoke.py` (wired into
  `tools/test.sh`). Single-project back-compat preserved.
- **Local dashboard MVP shipped (LOOP-1, `38549fb` + LOOP-6 fix `2707a63`, 2026-06-22).**
  Read-only multi-project kanban over `${CLAUDE_PLUGIN_DATA}/<key>/board/`, served from
  `tools/dashboard/` (pure stdlib, 127.0.0.1-only, zero deps). 4 canonical columns,
  cards with ID/title/type/owner/priority/age/non-routing labels. Per-request re-read
  (read-only invariant). Self-test suite `tests/test_dashboard.py` wired through
  `tools/test.sh` as `build.test`. Follow-up scope (live activity from logs / reports
  / state-move history / throughput) re-filed as **LOOP-7**.
- **No test/lint harness for the plugin itself yet beyond `tools/test.sh`** — the
  dashboard tests live there now, but a full plugin self-lint (SKILL frontmatter,
  cross-refs, README/CHANGELOG consistency) is still missing (tracked by LOOP-4).
- **Repo**: `git@github.com:gumlau/dev-loop.git`, branch `main`, MIT.
- **Onboarded loops on this machine**: `boardku`, `citron-geo`, `citron-tool`, and now
  `dev-loop` (this one) — all `backend:"local"`, `mode:"live"`, `autonomy:"full"`.

## Personas

- **Operator** — runs one or many product loops on their own machine; steers by
  reviewing reports and dropping 点评, rarely by editing the plugin. Wants to launch all
  their loops in one command and see what each is doing at a glance.
- **Loop maintainer** — extends the plugin: adds/edits agents, evolves conventions.md,
  ships releases. Needs the contract to stay coherent and changes to be reviewable.
- **The agents themselves** (PM/QA/Dev/…) — downstream readers of conventions.md +
  their SKILL; "UX" for them = an unambiguous, lean, non-contradictory contract.

## Glossary

- **Loop / project** — one onboarded product (one `projects.json` key) the agents drive.
- **Backend** — the coordination substrate: `linear` or `local` (a file board).
- **Data dir** — `${CLAUDE_PLUGIN_DATA}` (`~/.claude/plugins/data/dev-loop/`): all
  machine-local, never-committed runtime state (config, boards, reports, state files).
- **State files** — `pm-state.json` / `qa-state.json`: bounded look-back caches (per-repo
  SHA map + covered lenses/surfaces), §11.
- **点评 (operator review)** — a `<report>.review.md` the operator drops next to a report;
  the agent distills it into a `lessons.md` rule (§22).
- **Self-modification boundary** (§17) — agents may not auto-rewrite their own
  SKILLs/conventions; such change is proposed, not committed.

## Decisions (running log)

- **2026-06-22** — Onboarded the dev-loop plugin repo into dev-loop itself (dogfooding):
  `backend:"local"`, `mode:"live"`, `autonomy:"full"`, prefix `LOOP`. Rationale: let the
  loop drive its own improvement backlog (observability + multi-project ergonomics).
  Guardrail recorded in `testEnv.notes`: skills/ and references/conventions.md are
  off-limits to autonomous Dev edits per §17 — such changes are proposals only.
- **2026-06-22 (T18:55Z)** — LOOP-1 (dashboard MVP) verified Done. 8/8 ACs PASS against
  the running product (live HTTP smoke + 14-test suite green). Operator priority #1's
  kanban piece is now satisfied; the explicitly-carved-out follow-up scope (live agent
  activity / reports / state-move history / 7-day throughput) is **re-filed as LOOP-7
  (P3, Medium)** rather than collapsed into LOOP-1 — keeps the MVP shippable as one
  ticket and the enhancement scope as its own. LOOP-7 priority left below LOOP-2 /
  LOOP-4 (P2) because base capabilities (multi-project launcher, plugin self-lint)
  unblock more downstream work than richer dashboard surfaces do.
- **2026-06-22 (T20:30Z)** — `ux-flows` / `consistency` lens sweep at HEAD `52f8acc`
  (effective product SHA `2707a63` + PM doc commit). Filed **LOOP-8** (P3, Improvement,
  pm-owned, related to LOOP-4): README's first impressions still frame Linear as
  mandatory ("Linear is the only channel" L26; Linear MCP listed as a hard Requirement
  L75/L77), but `backend:"local"` is the default for every onboarded loop on this
  machine. README-prose-only fix (in the safe-to-edit zone per `testEnv.notes`); not a
  §17 conventions/SKILL touch. Other ux-flows / consistency surfaces (the 点评 helper,
  cross-project status surface, multi-project launcher canonical-in-repo) are already
  covered by LOOP-2/3/7 or are marginal — kept this fire to one ticket. Note for future
  fires: the README's `Requirements` list says "Linear MCP **the coordination
  substrate**" (singular), which is the same staleness as L26; LOOP-8 catches it.
- **2026-06-22 (T22:00Z)** — LOOP-2 (multi-project launcher) verified Done against the
  shipped commit `624e325`. Smoke (`scripts/smoke-run-loop.sh`) green end-to-end: both
  sessions exist, default re-launch is a no-op (no sibling clobber), `RESTART=1`
  rotates only the listed project, invalid key aborts pre-mutation. All 7 ACs pass.
  Coverage shipped same-diff and wired into `tools/test.sh`. Operator priority #2(b)
  is now closed; #2(c) is being implemented under **LOOP-3** (In Progress, dev WIP via
  `tools/dl-status.py` + `tests/test_dl_status.py` untracked in working tree).
  `strategy-gaps` lens at new SHA `624e325`: zero new tickets filed — the meaningful
  product move closes a known gap rather than opening one. Other Candidate ideas (§2(a)
  state-file namespacing — already shipped; §3a plugin self-lint — shipped via LOOP-4;
  §3b conventions length audit / §3d §17-binding-check for Dev) remain parked. Also
  noted: QA filed **LOOP-9** (P3, Bug, qa-owned, related to LOOP-2) for a
  `docs/RUNNING.md:138` doc-drift on the LOOP-2 ship (env-prefix + flag combination
  bash mis-parses) — properly typed/owned, does not regress LOOP-2's ACs.
- **2026-06-22 (T22:30Z)** — LOOP-3 (board-health / cross-project status CLI) verified
  Done against shipped commit `154b4e9`. All 7 ACs PASS: CLI surface +
  README **Status CLI** section (#1), auto-discovers every `<data-dir>/<key>/board/`
  (#2), per-project columns (Todo/IP/IR/Done/Other + oldestTodo + blocked +
  staleIR>24h) (#3), deterministic `--json` (#4), 0.40s wall-clock on the four-loop
  layout (#5, < 2s budget), exit 0 always (#6), 11 unit tests in
  `tests/test_dl_status.py` wired into `tools/test.sh` → 33 tests green (#7).
  Operator priority #2(c) is now closed; the priority #1 (dashboard) split into the
  shipped MVP **LOOP-1** + in-flight **LOOP-7** (dev/h0p1 actively working it).
  Operator priority #2 (multi-project parallelism) is now FULLY closed — (a)
  state-file namespacing, (b) `run-loop.sh` multi-project, (c) status CLI all shipped.
  Sealed a board-hygiene gap on LOOP-3 (the `In Review → Done` flip lacked a state-move
  comment per §18 — backfilled with the full verification trail on the ticket; the
  process drift itself is run-window noise for Reflect, not a ticket).
  `strategy-gaps` lens at new product SHA `154b4e9`: filed **LOOP-10** (P3,
  Improvement, pm-owned, related to LOOP-4) for operator priority #3b — audit
  `references/conventions.md` (1,632 lines today) for length/redundancy and produce
  a structured §17 PROPOSAL (`docs/CONVENTIONS_AUDIT.md`) the operator can apply
  selectively. Deliberately scoped as audit-only: the §17 self-modification firewall
  means Dev MUST NOT touch `references/conventions.md` itself — only produce the
  audit doc. Backlog depth check: pm Todo is now 2 (LOOP-8 README opener, LOOP-10
  audit) + pm In Progress 1 (LOOP-7 dashboard v2); not deep enough to throttle
  filing. Other priority #3 ideas (§3c data-dir uniformity post-#2 — implicit/done
  via the per-key layout already shipped; §3d §17-binding-check for Dev — kept
  parked, value is spec-fuzzy and the deliverable would be a SKILL-edit proposal,
  which is more meta-meta than #3b's audit) remain Candidate ideas.

## Candidate ideas

*(PM's parking lot — filed as tickets as the backlog drains. The first three are the
operator's stated priorities for this project.)*

1. **Visualization / local dashboard (operator's priority #1).** A read-only local web
   dashboard over the data dir: all projects at a glance, per-project kanban (Todo / In
   Progress / In Review / Done) read from each `<key>/board/tickets/`, live agent
   activity from `logs/` + reports, the ticket state machine, and throughput. Should tail
   files (no server dependency on the loop). See the reference-tool research the operator
   commissioned (Vibe Kanban / Conductor / Claude Squad / Crystal et al.) for prior art
   on multi-agent, board-style local UIs to borrow from or fork.
   - **(a) per-project kanban** — ✅ **shipped via LOOP-1** (2026-06-22, commit
     `38549fb` + non-UTF-8 fix `2707a63`). `tools/dashboard/`, 127.0.0.1-only,
     read-only, stdlib only.
   - **(b) live agent activity + (c) state-move history + (d) 7-day throughput** —
     filed as **LOOP-7** (P3); extends LOOP-1's dashboard with a Recent activity
     panel, Agent reports strip, Throughput mini-block, and an index-page
     "last activity" timestamp.
2. **First-class multi-project parallelism (operator's priority #2).** (a) Namespace
   `pm-state.json` / `qa-state.json` per-project under `<key>/` — exactly like `board/`
   and `reports/` already are — to remove the cross-project read-modify-write lost-update
   race when loops run concurrently, and to bound each file's size. (b) `run-loop.sh`:
   launch **N projects at once** (`PROJECTS="a b c"`), each in its own tmux
   session/window-group, without the fixed-session hard-kill clobbering a sibling loop. —
   ✅ **shipped via LOOP-2** (2026-06-22, commit `624e325`). Canonical
   `scripts/run-loop.sh` + smoke + test-gate wiring.
   (c) A board-health / cross-project status summary command. — ✅ **shipped via
     LOOP-3** (2026-06-23, commit `154b4e9`). `tools/dl-status.py`: pure-stdlib
     terminal companion to LOOP-1's dashboard, re-uses `dashboard.board` as a
     read-only consumer (no edits to the dashboard package). One line per
     project: counts by state, oldest-Todo age, blocked count, staleIR>24h
     stall signal. `--json` emits the same data for `jq` pipelines. 0.40s
     wall-clock across the current four-loop layout (AC#5 budget < 2s). 11
     unit tests in `tests/test_dl_status.py`, wired into `tools/test.sh`.
3. **Other optimizations (operator's priority #3 — ongoing).** Plugin self-lint/test
   harness (JSON valid, SKILL frontmatter present, conventions §N + markdown links
   resolve, README/CHANGELOG/conventions consistent) wired as the typecheck/test gate;
   audit conventions.md for length/redundancy (1,500+ lines) and tighten; verify the
   data-dir layout is uniform after idea #2; confirm the §17 self-modification guardrail
   actually binds Dev (not just Reflect) when a ticket would touch skills/conventions.
