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
- **Dashboard 点评 panel shipped (LOOP-12, `48c06c0`, 2026-06-23).** Every report page
  (`/reports/<key>/<agent>/<period>/<filename>`) now renders an "Operator review (点评)"
  block below the report body: the **exact local drop path** of the sibling
  `<filename>.review.md` (reflecting the configured `--data-dir`) and a three-state
  indicator — **none** (drop path + nudge), **awaiting** (`*.review.md` exists, agent
  hasn't acted), **acted** (`*.review.acted` sidecar is newer, with agent + ts parsed
  from mtime). Purely filesystem-derived (existence + mtime — never reads sidecar
  content), no new route, no writes. Path safety unchanged (LOOP-7 AC5 invariant
  held). +5 `ReviewPanelTests` in `tests/test_dashboard.py` (62/62 OK). Closes the
  ux-flows friction surfaced under the lens sweep at `6c97677`.
- **Dashboard index blocked-count parity shipped (LOOP-20, `3cac50c`, 2026-06-23).**
  Each project card on the dashboard index (`/`) now surfaces an `N blocked` line
  when ≥1 ticket is in `state:"Todo"` with the `blocked` label (zero is silent — no
  chip); count matches `tools/dl-status.py` exactly per §9. Self-contained
  `Project.blocked_count` helper on `tools/dashboard/board.py` (+11) + a conditional
  render in `render_index` on `tools/dashboard/server.py` (+23) — no new route,
  dashboard invariants preserved (127.0.0.1, read-only, path-traversal still 404).
  +7 `IndexBlockedCountTests` in `tests/test_dashboard.py` (`bash tools/test.sh`
  79/79). Closes the CLI↔GUI parity gap surfaced under the `ux-flows` lens at
  `d12a4f0`; operator can now triage stalled loops at-a-glance without one click
  per project.

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
- **2026-06-23** — LOOP-7 (dashboard v2 — live activity / state-move history /
  throughput) verified Done against `b42dd6c`. All 8 ACs PASS: 20 newest-first
  state-move events with agent attribution; one chip per agent under
  `<key>/reports/` with `Nm ago` mtime + weekly/monthly link; idle-today path
  ("agent · idle today") covered by test; throughput 10 filed / 6 shipped /
  4 verified (7d) with "Nothing stuck ≥3 days. ✓"; index sorted newest-first;
  4 path-traversal probes → 404, POST/DELETE → 501, bound 127.0.0.1 only;
  re-measured 1000×90 fixture at 3.1ms cold (≥16× under 500ms ceiling); README
  extended with 3 sub-sections + ASCII mocks; `bash tools/test.sh` 51/51 PASS.
  Operator priority #1 (dashboard) is now **fully closed**: (a) kanban shipped
  LOOP-1, (b)/(c)/(d) shipped LOOP-7. Dev also shipped **LOOP-11** mid-fire at
  `6c97677` (QA-filed null-byte FENCED-sentinel collision in the markdown
  renderer — per-render random token defeats both crash and silent-substitution
  vectors). `ux-flows` lens at `6c97677`: **filed LOOP-12** (P4 Improvement, pm,
  related to LOOP-7) — the dashboard report page surfaces the rendered markdown
  + crumb + meta but offers no help for the §22 点评 channel; operators must
  manually construct the sibling `*.review.md` path and have no visibility on
  whether the agent has acted (the `*.review.acted` sidecar). LOOP-12 adds an
  "Operator review (点评)" footer with the exact local drop-path and a
  three-state indicator (none / awaiting / acted), purely filesystem-derived
  and strictly read-only on top of `render_report_page`. Backlog at close:
  Done 7 · In Review 0 pm · 2 pm Todo (LOOP-8, LOOP-10) + 1 pm Todo new
  (LOOP-12) + 3 qa Todo (LOOP-5, LOOP-9, LOOP-11-fixed-pending-QA-verify).
- **2026-06-23 (T15:00Z)** — 9th PM fire. Non-material HEAD move: `e443d1c` →
  `e5ae06c`, but the only diff is PM's own prior-fire strategy-doc commit
  (+31 lines, `docs/STRATEGY.md` only — no product code moved). Per the
  established pattern (a PM doc commit is bookkeeping, not a product move),
  `reviewedShas[dev-loop]` stays pinned to `e443d1c`; `strategy-gaps` remains
  swept clean at that SHA. Rotated to the next un-swept lens at `e443d1c`:
  **`ux-flows`**. Job A: 0 In Review pm (LOOP-13 is qa-owned). Job B: 0
  pm-owned blocked; 0 stale `needs-pm` without `blocked`. Job C
  (`ux-flows` at `e443d1c`): filed **LOOP-16** (P4 Improvement, pm-owned,
  related to LOOP-2 + LOOP-8). Finding: `scripts/run-loop.sh` carries a rich
  head-comment usage block (lines 1–44) but offers no runtime `--help`/`-h`
  handler — `bash scripts/run-loop.sh --help` is parsed as a positional
  project key, falls through to the project-resolution preflight at line
  131, and exits 1 with `✗ unknown project key: '--help'`. First-impression
  CLI dead-end against the north-star goal "Onboarding is a near-no-op"
  (the CLI-layer continuation of the README-layer fix shipped in LOOP-8).
  Dedupe: 0 matches in the board for `run-loop.sh --help`; 0 matches in
  `scripts/run-loop.sh` for `--help|-h)`. Strictly safe-to-edit per
  `testEnv.notes` (scripts/ is not §17-protected). Other `ux-flows`
  surfaces examined and explicitly de-prioritized this fire: (a) report-page
  prev/next-day navigation — minor friction, crumb navigation already works
  and the reports-strip's weekly/monthly chips cover discovery, lower-value;
  (b) reports-strip "idle today" agents have no link to last non-idle daily
  — minor, weekly/monthly chips cover discovery; (c) dashboard surfacing
  agent logs — genuinely high-value but significant scope (live tailing,
  truncation, security boundary) and crosses out of pure ux-flows, kept as
  a Candidate idea. Backlog at close: Done 9 (LOOP-1/2/3/4/6/7/8/9/11) ·
  In Review 1 qa (LOOP-13) · Todo pm 3 (LOOP-10, LOOP-12, **LOOP-16**) ·
  Todo qa 2 (LOOP-14, LOOP-15) · Blocked qa 1 (LOOP-5) · In Progress 0.
  pm Todo backlog now at 3 (still depth-adequate for one Dev fire); the
  bottleneck remains QA verification on LOOP-13 + working LOOP-14/15.
  Next un-swept lens at `e443d1c` is **`consistency`** (then
  `conversion-retention`, `polish-performance`, etc.). Next-fire decision
  tree: (a) Dev moves any pm Todo → In Review → Job A pickup; (b) HEAD
  moves with NEW product code beyond `e443d1c` → reset `sweptLensesAtSha`
  and re-rotate from `strategy-gaps`; (c) operator edits STRATEGY.md
  (length ≠ current) → doc-watch re-entry; (d) manual `/pm-agent` with
  no a/b/c → rotate to `consistency` at `e443d1c`. §17 boundary held:
  pre-existing skills/+conventions dirty tree persists across fires
  (operator WIP), still not scooped per §7 staging discipline (this fire
  stages only `docs/STRATEGY.md`).

- **2026-06-22 (T14:19Z)** — 8th PM fire. HEAD moved `a1f5e95` → `e443d1c` with one
  new product commit in the window: **LOOP-13** (qa-filed Bug; Dev shipped at
  `e443d1c` — `docs/RUNNING.md` §5/§6 now use per-project `dev-loop-<project>`
  tmux session names, closing the post-LOOP-2 doc-drift hazard where a bare
  `tmux kill-session -t dev-loop` silently left autonomous loops running). PM
  doc commit `efe0dcb` is the only other commit; no other product code moved.
  Per new-SHA branch: reset `sweptLensesAtSha`, re-rotated to `strategy-gaps`
  first at `e443d1c`. Diff-focused review: LOOP-13 is a docs fix on the
  multi-project parallelism surface — it closes drift, it does not open a new
  capability surface, so `strategy-gaps` finds **0 net-new tickets**. Dedupe-
  against-reality at `e443d1c`: operator priorities #1 (dashboard, a/b/c/d)
  and #2 (multi-project parallelism, a/b/c) remain FULLY closed; #3a self-lint
  shipped (LOOP-4), #3b conventions audit filed (LOOP-10) awaiting Dev,
  #3c data-dir uniformity implicit/done, #3d §17-binding-check parked
  (Candidate idea — spec-fuzzy). LOOP-13's structural lint follow-up (docs-vs-
  script tmux naming consistency) is QA-tracked as **LOOP-15** (`[coverage]`,
  qa-owned, P4) — a §15(B) coverage ticket, not a strategy gap. PM Todo backlog
  at close depth-adequate (LOOP-10 audit + LOOP-12 点评 footer). Filing zero
  per PM guardrails. Bottleneck: QA verification on LOOP-13 In Review + working
  LOOP-14/15 unblocks more than another PM fire would. Job A: 0 In Review pm
  (LOOP-13 is qa-owned, not mine). Job B: 0 blocked pm. Board at close:
  Done 8 (LOOP-1/2/3/4/6/7/8) · In Review 1 qa (LOOP-13) · Todo pm 2 (LOOP-10,
  LOOP-12) · Todo qa 2 (LOOP-14, LOOP-15) · Blocked qa 1 (LOOP-5) · In Progress
  0. Next un-swept lens at `e443d1c` is `ux-flows`; next-fire decision tree
  unchanged from prior fire — (a) Dev moves LOOP-10/12 → In Review → Job A
  pickup; (b) HEAD moves with NEW product code beyond `e443d1c` → reset and
  re-rotate from `strategy-gaps`; (c) operator edits STRATEGY.md (length ≠
  current) → doc-watch re-entry; (d) manual `/pm-agent` with no a/b/c → rotate
  to `ux-flows` at `e443d1c`. §17 boundary held: pre-existing skills/+conventions
  dirty tree persists across fires (operator WIP), still not scooped per §7
  staging discipline (this fire stages only `docs/STRATEGY.md`).
- **2026-06-23 (T03:55Z)** — LOOP-8 (README backend-pluggable framing) verified Done
  against ship `a1f5e95`. All 7 ACs PASS: opener softened ("ticket state" + parenthetical
  §18 link), How-it-works bullet rebranded "Ticket state is the only channel" naming
  both substrates, Requirements rewritten as a **Per backend** block (`linear` needs
  MCP + team/project, `local` needs neither), no other section altered, `docs/RUNNING.md`
  line 5's "Linear MCP — for the `linear` backend" stays consistent, `CHANGELOG.md`
  one-line entry under Unreleased, §17 boundary respected (diff confined to
  `README.md` + `CHANGELOG.md`, zero skills/conventions touches). `bash tools/test.sh`
  → 57/57 PASS (no docs-only regression on the lint `md-links` rule that watches the
  new conventions §18 reference). Grep evidence: `"Linear is the only channel\|
  coordination substrate"` → **0 matches** in README (was 2). First-impression onboarding
  friction closed (north-star goal "Onboarding is a near-no-op").
  `strategy-gaps` lens at new product SHA `a1f5e95`: **0 new tickets filed.** Dedupe-
  against-reality at this SHA: operator priorities #1 (dashboard) and #2 (multi-project)
  are FULLY closed (a/b/c/d shipped per Candidate ideas 1+2); priority #3a (plugin
  self-lint) shipped via LOOP-4, #3b (conventions audit) is filed as LOOP-10 awaiting
  Dev, #3c (data-dir uniformity post-#2) is implicit/done via the per-key layout, and
  #3d (§17-binding-check for Dev) remains parked as Candidate idea (spec-fuzzy,
  meta-meta). No additional strategy-gap surfaces appeared in the LOOP-7/8/9/11
  ship window beyond what LOOP-10/12 already cover. pm Todo backlog (LOOP-10 audit
  + LOOP-12 点评 footer) is depth-adequate; the next fire's natural rotation is
  `ux-flows` (or `consistency`) at `a1f5e95`. QA-filed **LOOP-13** noted (2026-06-23
  RUNNING.md tmux-session ref drifted post-LOOP-2) — properly typed/owned by QA,
  not mine. Board at close: Done 8 (LOOP-1/2/3/4/6/7/8) · In Review 2 qa (LOOP-9,
  LOOP-11) · Todo pm 2 (LOOP-10, LOOP-12) · Todo qa 1 (LOOP-13) · Blocked qa 1
  (LOOP-5). Bottleneck is now QA verification capacity on LOOP-9/11 → a QA fire
  would unblock more than another PM fire would.

- **2026-06-23 (T21:35Z)** — 11th PM fire. **LOOP-10 (conventions audit / §17 proposal
  payload) verified Done** against ship `16165ba`, and **LOOP-16 (`run-loop.sh
  --help`/`-h`) verified Done** against ship `4203d60`. Both 6/6 ACs PASS. LOOP-10
  AC#4 mechanically held: `git diff cd833ec..16165ba --stat -- references/conventions.md`
  is empty; Dev executed an audit of a §17-protected file *without touching it*. That
  is a real binding-test of the §17 firewall against an autonomous Dev fire — answering
  operator priority **#3d** (§17-binding-check) informally; the formal check stays
  parked as spec-fuzzy per the prior Candidate-ideas notes. LOOP-16 closes the
  CLI-layer first-impression onboarding friction (continuation of LOOP-8's README
  layer): `--help`/`-h` is now precondition-free (no `projects.json` / claude / tmux /
  python3 needed), wins over `--restart` in either order, and the unknown-key error
  path is unchanged. Product HEAD moved `48c06c0` → `18a2864` with **9 commits in
  window** — beyond LOOP-10 + LOOP-16, QA shipped LOOP-13/14/15/17/18/19 and Dev
  shipped a smoke-harness fix `7d5ff47` (`A_TS_3 != A_TS_1` race on fast Macs).
  Per the new-product-SHA branch: reset `sweptLensesAtSha` and re-rotated to
  `strategy-gaps` first at `18a2864`. **Operator priority #3b (conventions audit)
  is now ✅ shipped** — `docs/CONVENTIONS_AUDIT.md` sits as the §17 proposal
  payload (R-1..R-6, M-1..M-6, C-1..C-7, P-1..P-7 + 8 KEEP markers, ≈ −238 / ≈ 15%
  projected delta) awaiting **operator/Reflect** selective application; refiling
  P-1..P-7 as Dev tickets would cross §17 and is deliberately NOT done. The audit's
  C-6 finding (TOC missing §12a entry) explicitly dedupes to LOOP-5 — already filed,
  blocked needs-qa, not refiled. Diff-focused review at `18a2864`: 0 net-new
  `strategy-gaps` tickets — every shipped commit either closes a known gap (LOOP-10
  #3b, LOOP-16 onboarding, LOOP-13/14 doc accuracy, LOOP-17 TOCTOU hardening,
  LOOP-18 audit honesty, LOOP-15/19 coverage) or is a §15 coverage follow-up. None
  open a new capability surface. Dedupe-against-reality at `18a2864`: priorities
  #1/#2 remain FULLY closed; #3a (LOOP-4), #3b (LOOP-10), #3c (per-key data-dir
  layout) all shipped; #3d parked. Job A: 2 In Review pm both → Done. Job B: 0 blocked
  pm; 0 stale `needs-pm` without `blocked`. Board at close: **Done 14** (LOOP-1/2/3/
  4/6/7/8/9/10/11/12/13/16 + the QA-side 14/15/17/18/19 also Done = 17 actually
  Done) · In Review 0 · Todo pm 0 · Todo qa 0 · Blocked qa 1 (LOOP-5) · In Progress
  0. Counter unchanged (no new tickets). **pm Todo backlog at 0** — this is the
  cleanest the board has been; per the PM guardrails *"filing zero is a valid
  run"*, lens-rotation is *not* a license to flood `Todo` with vague work to keep
  busy. Next un-swept lens at `18a2864` is `ux-flows` (then `consistency`,
  `conversion-retention`, `data-analytics`, `trust-safety`, `competitive-parity`,
  `polish-performance`). Next-fire decision tree: (a) Dev/QA work resumes (LOOP-5
  unblock) → Job A/B pickup; (b) HEAD moves with NEW product code beyond `18a2864`
  → reset `sweptLensesAtSha` and re-rotate from `strategy-gaps`; (c) operator
  edits STRATEGY.md (length ≠ persisted) → doc-watch re-entry; (d) manual
  `/pm-agent` with no a/b/c → rotate to `ux-flows` at `18a2864`. §17 boundary
  held: pre-existing skills/+conventions dirty tree persists across fires
  (operator/Reflect WIP), still not scooped per §7 staging discipline (this fire
  stages only `docs/STRATEGY.md`). Bottleneck downstream of PM is now genuinely
  thin — operator review of the conventions audit (`docs/CONVENTIONS_AUDIT.md`)
  and unblock of LOOP-5 are the highest-leverage next moves.

- **2026-06-23 (T20:05Z)** — 10th PM fire. **LOOP-12 (dashboard 点评 panel) verified
  Done** against ship `48c06c0`. All 8 ACs PASS: panel renders below the report body;
  the **exact local drop path** under the configured `--data-dir` is shown in a
  `<code>` block; the three states (`none`/`awaiting`/`acted`) render with the
  exact wording from the ticket; state detection is purely filesystem-based (mtime +
  existence — leak check confirms the `.review.md` body never appears in the rendered
  page); path-traversal regression still 404; perf budget unchanged; `bash tools/test.sh`
  62/62 OK (5 new `ReviewPanelTests` > 3-min); README adds a paragraph under "Run the
  dashboard" with the `references/conventions.md#22-...` cross-link. Verification used
  mktemp + a live probe against the real data dir — the rendered drop path matched
  `~/.claude/plugins/data/dev-loop/dev-loop/reports/pm-agent/daily/2026-06-23.md.review.md`
  exactly. New product SHA `e443d1c` → `48c06c0` (LOOP-12 is the only product-code
  commit; PM bookkeeping aside). Per the new-product-SHA branch: reset
  `sweptLensesAtSha` and re-rotated to `strategy-gaps` first at `48c06c0`. Diff-focused
  review: LOOP-12 closes a known ux-flows gap (the §22 channel had no dashboard
  affordance) — it does not open a new capability surface, so `strategy-gaps` finds
  **0 net-new tickets**. Dedupe-against-reality at `48c06c0`: operator priorities
  #1 (dashboard, a–d) and #2 (multi-project, a–c) remain FULLY closed; #3a self-lint
  shipped (LOOP-4); #3b conventions audit filed (LOOP-10) awaiting Dev; #3c data-dir
  uniformity implicit/done; #3d §17-binding-check parked Candidate. The 点评 panel
  itself completes a coupled goal-pair — **Observability / steerability** (the
  operator can now see + know the drop path + know the agent has acted) and the
  realisation of the **"steer by reviewing, not by editing code"** north-star —
  without trading off the dashboard's read-only invariant (the LOOP-12 "out of scope"
  write-endpoint stays deliberately deferred; not refiled). Job A: 1 In Review pm
  (LOOP-12 → Done). Job B: 0 blocked pm; 0 stale `needs-pm` without `blocked`.
  Board at close: Done 10 (LOOP-1/2/3/4/6/7/8/9/11/12) + LOOP-13 already Done
  qa-side · In Review 0 · Todo pm 2 (LOOP-10, LOOP-16) · Todo qa 2 (LOOP-14,
  LOOP-15) · Blocked qa 1 (LOOP-5) · In Progress 0. Next un-swept lens at `48c06c0`
  is `ux-flows` (then `consistency`, `conversion-retention`, etc.). Next-fire
  decision tree: (a) Dev moves LOOP-10/16 → In Review → Job A pickup; (b) HEAD
  moves with NEW product code beyond `48c06c0` → reset `sweptLensesAtSha` and
  re-rotate from `strategy-gaps`; (c) operator edits STRATEGY.md
  (length ≠ persisted) → doc-watch re-entry; (d) manual `/pm-agent` with no
  a/b/c → rotate to `ux-flows` at `48c06c0`. §17 boundary held: pre-existing
  skills/ + references/ dirty tree persists across fires (operator/Reflect WIP),
  still not scooped per §7 staging discipline (this fire stages only
  `docs/STRATEGY.md`). pm Todo backlog at 2 — depth-adequate; Dev shipping
  LOOP-10/16 + QA verifying LOOP-14/15 unblocks more than another PM fire would.
- **2026-06-23 (T13:30Z)** — 13th PM fire on `dev-loop`. **LOOP-20 (dashboard index
  blocked-count parity) verified Done** by an **earlier same-day partial PM fire at
  T13:15Z** (run-id `pm-2026-06-23-LOOP20`) that wrote the state-move comment + flipped
  the ticket to Done with the full 8/8 verification trail, but did NOT write its
  close-report (no Decisions-log entry, no daily-report entry, no `pm-state.json`
  update — a partial fire that crashed/exited between Job-A write and §3 close).
  Honest-audit recovery this fire: re-confirmed all 8 LOOP-20 ACs against running
  product at HEAD `3cac50c` (index card for `dev-loop` renders `1 blocked` matching
  LOOP-5; other cards stay clean at 0; `tools/dl-status.py` parity exact at
  `boardku=0, citron-geo=0, citron-tool=0, dev-loop=1`; confined to
  `Project.blocked_count` helper + `render_index` render line; sort-by-last-activity
  unchanged; 127.0.0.1-only + read-only + path-traversal-404 invariants held; +7
  `IndexBlockedCountTests`; `bash tools/test.sh` 79/79). Product HEAD moved
  `d12a4f0` → `3cac50c` with one product-code commit in window (LOOP-20 ship).
  Per the new-product-SHA branch: reset `sweptLensesAtSha` and re-rotated to
  `strategy-gaps` first at `3cac50c`. Diff-focused review: LOOP-20 **closes** a
  known CLI↔GUI parity gap (`dl-status` already exposed per-project blocked count;
  the dashboard index now does too) — does NOT open a new capability surface.
  Dedupe-against-reality at `3cac50c`: operator priorities #1 (dashboard, a–d +
  parity polish) and #2 (multi-project, a–c) remain FULLY closed; #3a self-lint
  shipped (LOOP-4); #3b conventions audit shipped (LOOP-10, awaiting operator /
  Reflect selective-apply); #3c data-dir uniformity implicit/done; #3d
  §17-binding-check parked Candidate (informally answered by LOOP-10). **0 net-new
  strategy-gaps tickets** — board at close mirrors prior fire (19 Done, 1 blocked
  qa, 0 elsewhere), filing zero is right per PM guardrails ("filing zero is a valid
  run"). Job A at fire-open: 0 In Review pm (LOOP-20 already Done via the partial
  fire). Job B: 0 pm-owned blocked; 0 stale `needs-pm` without `blocked` (LOOP-5
  is qa-owned via `needs-qa`, not mine). §17 boundary held: pre-existing `skills/`
  + `references/` dirty tree persists across fires (operator/Reflect WIP), still
  not scooped per §7 staging discipline (this fire stages only `docs/STRATEGY.md`).
  Next un-swept lens at `3cac50c` is `ux-flows` (then `consistency`,
  `conversion-retention`, `polish-performance`, `data-analytics`, `trust-safety`,
  `competitive-parity` — 7 remain). Next-fire decision tree: (a) Dev/QA work
  resumes (LOOP-5 unblock is qa's lane); (b) HEAD moves with NEW product code
  beyond `3cac50c` → reset `sweptLensesAtSha` and re-rotate from `strategy-gaps`;
  (c) operator edits STRATEGY.md (length ≠ persisted) → doc-watch re-entry;
  (d) manual `/pm-agent` with no a/b/c → rotate to `ux-flows` at `3cac50c`.
  Bottleneck downstream of PM is unchanged: **operator review of
  `docs/CONVENTIONS_AUDIT.md`** (the §17 proposal payload from LOOP-10) and
  **QA unblock of LOOP-5** are the highest-leverage next moves.

- **2026-06-23 (T04:55Z)** — 12th PM fire on `dev-loop`. Manual `/pm-agent` against
  HEAD `d12a4f0` (the previous fire's own `docs(strategy)` commit recording
  LOOP-10/16 shipped — **no new product code** since `18a2864`, so the lens-reset
  rule deliberately did NOT fire here: a PM doc-only commit adds zero review
  surface). Strategy doc length unchanged (34684 B). Job A: 0 In Review pm. Job B:
  0 pm-owned blocked; 0 stale `needs-pm` without `blocked` (LOOP-5 remains the
  only blocked ticket, qa-owned). Job C: rotated to the **`ux-flows`** lens (next
  un-swept after `strategy-gaps`). Filed **LOOP-20** (P4, Improvement, pm-owned;
  related-to LOOP-1, LOOP-3, LOOP-7): dashboard index does not surface the
  per-project blocked-ticket count — a CLI↔GUI parity gap with `dl-status`
  (LOOP-3 exposes it; the dashboard does not). Today's board demonstrates the gap
  (LOOP-5 blocked in `dev-loop`, but the index card reads only
  `19 tickets · last activity: …`). Scope: self-contained render-only change in
  `render_index` + a small `Project.blocked_count` helper; no new routes, no fs
  changes, dashboard invariants (127.0.0.1, read-only, path-traversal probes →
  404) preserved. Board at close: **Done 18** (LOOP-1/2/3/4/6/7/8/9/10/11/12/
  13/14/15/16/17/18/19) · In Review 0 · Todo pm 1 (LOOP-20) · Todo qa 0 ·
  Blocked qa 1 (LOOP-5) · In Progress 0. Counter advanced LOOP-20 → next 21.
  §17 boundary held (pre-existing `skills/` + `references/` dirty tree persists;
  staged only `docs/STRATEGY.md` per §7). pm-state bumped: `reviewedShas.dev-loop`
  → `d12a4f0`; `sweptLensesAtSha` += `ux-flows@d12a4f0` (still keyed at the same
  product surface as `strategy-gaps` — no product code moved). Bottleneck downstream
  of PM: operator review of `docs/CONVENTIONS_AUDIT.md` (§17 proposal payload from
  LOOP-10), LOOP-5 unblock (QA's), and a Dev fire to pick up LOOP-20. 6 lenses
  remain un-swept at `d12a4f0` (consistency, conversion-retention, polish-
  performance, data-analytics, trust-safety, competitive-parity) — rotate as the
  product moves or the operator requests.

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
     ✅ **shipped via LOOP-7** (2026-06-22, commit `b42dd6c`). Recent activity
     panel (20 newest state moves with agent attribution), Agent reports strip
     (one chip per agent under `<key>/reports/` with `Nm ago` + weekly/monthly
     link; `idle today` for absent), Throughput mini-block (7-day filed/shipped/
     verified + "stuck ≥3 days" callout), and an index-page newest-first sort by
     `last activity`. 8/8 ACs verified; `bash tools/test.sh` 51/51 green; cold
     render 3.1ms on the 1000×360 fixture (≥16× under the 500ms ceiling).
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
3. **Other optimizations (operator's priority #3 — substantively closed).** Plugin
   self-lint/test harness (JSON valid, SKILL frontmatter present, conventions §N +
   markdown links resolve, README/CHANGELOG/conventions consistent) wired as the
   typecheck/test gate; audit conventions.md for length/redundancy (1,500+ lines)
   and tighten; verify the data-dir layout is uniform after idea #2; confirm the §17
   self-modification guardrail actually binds Dev (not just Reflect) when a ticket
   would touch skills/conventions.
   - **(a) plugin self-lint** — ✅ shipped via LOOP-4 (`tools/test.sh`, 72 tests
     covering SKILL frontmatter, JSON parse, conventions cross-refs, md-links incl.
     `#fragment` resolution per LOOP-19, README/CHANGELOG consistency, and the
     `tmux-session-name-consistency` rule per LOOP-15).
   - **(b) conventions audit** — ✅ shipped via LOOP-10 (2026-06-23, commit
     `16165ba`). `docs/CONVENTIONS_AUDIT.md` is the §17 proposal payload —
     R-1..R-6 (redundancies), M-1..M-6 (movable), C-1..C-7 (contradictions/
     staleness), P-1..P-7 (proposed cuts with concrete before/after + line
     deltas, ≈ −238 / ≈ 15% projected), 8 KEEP markers, all line-ref-cited.
     LOOP-18 amended the doc to honestly disclose the WT-snapshot reading
     frame. **Tightening is operator/Reflect's selective-apply call** — refiling
     P-1..P-7 as Dev tickets would cross §17 and is deliberately NOT done.
   - **(c) data-dir uniformity post-#2** — ✅ implicit/done via the per-key
     layout (`<key>/board/`, `<key>/reports/`, `<key>/pm-state.json` etc.).
   - **(d) §17-binding-check for Dev** — informally answered by LOOP-10: Dev
     audited a §17-protected file *without touching it*, and the AC#4 git-diff
     assertion held mechanically. A formal self-test that codifies this remains
     parked as spec-fuzzy (the deliverable would be a SKILL-edit proposal,
     itself §17-bound) — a future Reflect fire is the natural author.
