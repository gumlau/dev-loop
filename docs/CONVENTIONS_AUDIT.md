# conventions.md audit — §17 proposal report

**Audit target:** `references/conventions.md` at HEAD `48c06c0`
(`feat(dashboard): surface 点评 channel on report page (LOOP-12)`).
**Pre-audit line count:** 1,569 lines (§0 → §23, plus Topology + ToC).
**Projected delta if every proposal in §4 were applied:** ≈ **−238 lines** (≈ 15%
reduction). Detailed math in §4.
**§17 boundary statement:** this is a **findings-only** report. Per LOOP-10
AC#4, `references/conventions.md` is **byte-identical** to HEAD pre-ticket
after this ship — no rule restated below is rewritten by Dev. The operator
(or Reflect via a `[reflect-proposal]`) applies findings selectively.

**Method.** Single pass through the committed file (no comparison against
WIP in the working tree). Every finding cites a `references/conventions.md:Lxxx-Lyyy`
range. Findings are bucketed into the four AC#1 categories — Redundancies,
Movable, Contradictions/Staleness, Proposed cuts/moves. Findings marked
**KEEP — no action** are ones that look redundant or movable in isolation
but are load-bearing on second look; they are listed so a future audit
doesn't re-raise them.

**Dedupe-against-reality (per AC and §8).** One finding overlaps with an
already-filed ticket:
- **C-6** (TOC missing §12a entry) duplicates **LOOP-5**, currently
  `Todo` + `blocked` + `needs-qa`. Listed here for completeness; **do not
  refile** — unblocking LOOP-5 is the existing path.

No findings overlap with shipped LOOP-7/-8/-9/-11/-12/-13.

---

## 1. Redundancies — rules restated across sections

### R-1 · Reflect curator rule appears three times
**Lines:** `references/conventions.md:L74-L75`, `L137-L143`, `L796-L819`.
The "Reflect autonomously edits only `lessons.md`; structural change to
SKILLs/conventions is a proposal, never auto-applied" rule appears in:
- The Topology-at-a-glance table (L74-75, one-liner)
- §1 *What the loop is* (L137-143, paragraph)
- §17 *Self-evolution boundary* (L796-819, the canonical full statement)

The three statements have drifted in phrasing already (the table says
"never auto-applies SKILL/conventions"; §1 says "drafted as proposals,
never auto-applied"; §17 spells out the `external-prereq` mechanic). Three
copies = three drift points. Proposed action under **P-3** (collapse to
one canonical statement in §17 + two short forward-references).

### R-2 · Operator-review carve-out appears three times
**Lines:** `references/conventions.md:L685-L691` (§14 lessons file),
`L821-L840` (§17), `L1410-L1432` (§22). The "any agent MAY add a rule
under ITS OWN section when distilling an operator review (点评) of its own
report" carve-out is stated three times — §14 in summary form (L685-691,
7 lines), §17 in full (L821-840, 20 lines), §22 again in full (L1410-1432,
23 lines). §17 and §22 list **the same five hard limits** in two places.
Proposed action under **P-3**.

### R-3 · "Verify against the running product / the diff, not the claim"
**Lines:** `references/conventions.md:L89-L91` (Topology "What NOT to
confuse"), and the rule is referenced obliquely in the PM/QA `Job A`
guidance via §1 (L126-131) and the Dev §5.5 self-review (skill body,
not conventions). Not a true duplication inside conventions — the
Topology table is the single statement; PM/QA SKILLs restate it.
**KEEP — no action** (the Topology line is the canonical statement;
agent SKILLs are allowed to restate the rule that applies to them).

### R-4 · "Stop-and-surface on broader-than-expected access"
**Lines:** `references/conventions.md:L787-L792` (§16) and
`L1184-L1189` (§21 outward-agent contract). §21 explicitly cross-refs
§16 ("The §16 stop-and-surface carve-out…"); the §21 restatement is a
narrowing for outward agents (a confirmed un-routable outage is *not*
a §16 case). Different scope. **KEEP — no action**.

### R-5 · "Never bulk-mutate / one ticket at a time"
**Lines:** `references/conventions.md:L171-L172` (§2) restated at
`L972-L980` (§18 local-mode firewall: "The §2 rules — never widen the
blast radius, no bulk-mutate, one ticket at a time — apply verbatim").
The §18 restatement is a deliberate portability statement (proves the
local-mode firewall enforces the §2 rules). **KEEP — no action**.

### R-6 · "PM verifies `pm`-tagged In Review; QA verifies `qa`-tagged"
**Lines:** `references/conventions.md:L152-L154` (§1, general form)
and `L259-L262` (§4, concrete form). Two phrasings of the same rule
serve different teaching purposes (§1 = mental model; §4 = label
mechanics). **KEEP — no action**.

---

## 2. Movable — deep detail that could live under `references/<topic>.md`

### M-1 · §6 ticket templates → `references/ticket-templates.md`
**Lines:** `references/conventions.md:L295-L352` (~58 lines, including
the two verbatim markdown blocks). Templates are reference material —
PM/QA copy them at filing time, the agents don't need them every fire to
make decisions. Moving them out keeps the §6 section as a 10-line
summary that says "Tickets must carry enough for Dev to act without
guessing (§9) — see `references/ticket-templates.md` for the Feature/Bug
markdown templates and the required fields" + the type/owner/repo rules.
Saves ≈48 lines from the every-fire-read file. **Move proposal** in §4
as **P-1**.

### M-2 · §23 *Reports in Linear* → `references/reports-linear-sink.md`
**Lines:** `references/conventions.md:L1455-L1569` (~115 lines). §23 is
opt-in (`reports.sink:"linear"`, default off). Per its own opening
(L1457-L1461): "prefer files whenever the operator's machine is
reachable" — so the every-fire reader of conventions.md, in the common
case, is paying ≈115 lines of context tax for a feature they're not
using. Moving the section to a reference doc and leaving a 5-line stub
in conventions ("If `reports.sink:"linear"` is set, see
`references/reports-linear-sink.md`. Default `files` — §22 applies as
written.") is safe **iff** the §22 reader can independently understand
the default-file behavior without §23 (true — §22 is self-contained).
Saves ≈108 lines. **Move proposal** as **P-2**. Strongest single move.

### M-3 · §22 cadence-math / catch-up / retention mechanics
**Lines:** `references/conventions.md:L1281-L1342` (~62 lines).
The deterministic cadence shell commands, the cold-start rule, the
catch-up-across-many-elapsed-periods discipline, and the 90-day
retention number are mechanical — agents read them on the day they
roll up a period, not every fire. The §22 main body (trust boundary,
operator review, lessons.md lock) is the high-frequency reading.
Move the mechanics to `references/reports.md`; keep §22's "what +
why + trust boundary" inline. **Move proposal** as **P-6**. Saves
≈50 lines.

### M-4 · §10 Linear-MCP write hazards subsection
**Lines:** `references/conventions.md:L487-L509` (~23 lines).
Candidate for `references/linear-mcp-quirks.md`. But these footguns
are mission-critical, every-fire reading for any Linear-backend
agent, and the section is short enough that inlining is the right
call — burying load-bearing safety in a separate doc that nobody
re-reads is worse than 23 lines in the main file. **KEEP — no
action**.

### M-5 · §18 *Operation mapping* table
**Lines:** `references/conventions.md:L922-L936` (~15 lines).
The Linear-MCP → local operation mapping table could live in
`references/backend-mapping.md`. But it is small and concrete, and
its job is to make the abstraction obvious to a reader of §18 in
one glance. Moving it out hurts §18's self-containment for a 15-line
saving. **KEEP — no action**.

### M-6 · §19 multi-repo deep subsections
**Lines:** `references/conventions.md:L1051-L1108` (~58 lines —
*Doc-home repo*, *Per-repo change-gate*, *Orphan reclaim*,
*Cross-repo work*, *Known state limitations*). §19's own opening
(L986-L991) makes the point that single-repo projects ignore §19
entirely. Could move these subsections to
`references/multi-repo.md`. **Proposed but cautious** — see **P-7**.
The deep detail is genuinely load-bearing for the multi-repo case,
and finding it all in one place (the same file you turn to to
understand the loop) has real value. Conservative recommendation:
move only the most niche subsection (*Known state limitations*,
L1096-L1107, ~12 lines) and keep the rest inline.

---

## 3. Contradictions / Staleness

### C-1 · §21 outward-agent state-file path is stale vs §11
**Lines:** `references/conventions.md:L1178-L1181` says outward agents
have "its own state file next to `projects.json` — `ops-state.json` /
`architect-state.json` / `signal-state.json`". But §11 was rewritten
(see L539-L555) to split runtime state into two scopes:
- Global root: `projects.json` + `lessons.md`
- Per-project: `${CLAUDE_PLUGIN_DATA}/<project-key>/` for the agent
  state files (pm, qa, ops, architect, signal) and reports-state.

The phrasing "next to `projects.json`" at L1178-1181 is now imprecise —
those files live in the per-project subdir, not at the data-dir root.
This is genuine staleness: §21 wasn't updated when §11 was split.
Recommended fix in **P-5** below: change L1180-1181 to
"… per-project state file under `${CLAUDE_PLUGIN_DATA}/<project-key>/`
(§11)".

### C-2 · §23 `reports-state.json` path is stale vs §11
**Lines:** `references/conventions.md:L1534-L1535` says
"A machine-local `reports-state.json` (next to `projects.json`)".
But §11 L547-L549 lists `reports-state.json` as a per-project file
under `${CLAUDE_PLUGIN_DATA}/<project-key>/`. Same staleness shape as
C-1 — §23 prose predates §11's split. Recommended fix in **P-5**:
change L1534 to "… `reports-state.json` (per-project, under
`${CLAUDE_PLUGIN_DATA}/<project-key>/` — §11)".

### C-3 · §14 "next to projects.json" is imprecise vs §11
**Lines:** `references/conventions.md:L673` opens §14 with
"A `lessons.md` next to the loaded `projects.json` (§11) lets the
operator…". §11 L541-L543 clarifies that `lessons.md` is at the
data-dir **root** (not per-project — it's "**shared across all
projects, never per-project**"). §14's phrasing is technically
correct (the root IS next to projects.json) but doesn't capture the
per-operator-shared aspect — a reader of §14 in isolation could
plausibly assume per-project. Minor — propose to qualify L673 to
"… next to the loaded `projects.json` at the data-dir root —
shared per-operator, not per-project (§11)". Not a hard
contradiction.

### C-4 · §13 step 4 "create the runtime files if absent" vs the
lazy-creation guarantee elsewhere
**Lines:** `references/conventions.md:L657-L661`. Step 4 says
"Create the runtime files if absent (§11, §14): the per-project
agent state files… **created lazily by each agent on first run** —
and a `lessons.md` skeleton at the data-dir root". The parenthetical
"created lazily" makes init's "Create the runtime files" a partial
tautology — the only file init must guarantee at setup is the
`lessons.md` skeleton at the root; the state files self-create on
first run. Recommend tightening L657-L661 to: "Create the
`lessons.md` skeleton at the data-dir root (§14). Per-project state
files self-create on first agent run (§11) — no init action needed
beyond ensuring the project subdir exists." Saves ~3 lines + removes
a contradiction-shaped misread.

### C-5 · Re-review affordance asymmetry in §22
**Lines:** `references/conventions.md:L1373-L1375` makes the re-review
affordance bidirectional: "if the operator deletes the sidecar, or the
`*.review.md` is newer than its sidecar, it is un-acted again". L1361-L1369
correctly states "agents never write a `*.review.md`" (the trust
boundary). Together these imply the **operator** controls both knobs:
deleting `*.review.acted` re-arms the loop, **and** editing
`*.review.md` (touching its mtime) re-arms it. Worth a brief explicit
callout — the second path (mtime-edit a *.review.md*) is less obvious
than deleting the sidecar. Not a contradiction; a coherence gap.
**KEEP — no action** (low ROI vs the risk of complicating L1373-1375,
which is already precise).

### C-6 · ToC missing §12a entry — **already tracked as LOOP-5**
**Lines:** `references/conventions.md:L11-L35` (the Table of contents)
omits an entry for `## 12a. Autonomy — how much to decide vs escalate`
at L608, even though L24 has `12. [Dry-run vs live]`. The missing
entry would be: `12a. [Autonomy — how much to decide vs escalate](#12a-autonomy--how-much-to-decide-vs-escalate)`.
**Do not refile** — LOOP-5 is the existing ticket; it is currently
`Todo` + `blocked` + `needs-qa`. Reported here so a future audit knows
it was already counted.

### C-7 · "8 agents" count vs lessons.md skeleton
**Lines:** `references/conventions.md:L693-L705`. §14's lessons-skeleton
layout shows 8 agent sections (Shared + PM/QA/Dev/Sweep/Reflect/Ops/
Architect/Signal). `scripts/lint-plugin.py` (the
`lessons-skeleton` rule, lines 252-280 of that file) enforces this set
exactly. **Consistent — KEEP.** Mentioned here only because the audit
naturally checks "does this layout still match the lint-enforced set?"
(it does).

---

## 4. Proposed cuts / moves (the §17 proposal payload)

Concrete proposals; before/after section names and rough line-count
deltas. Each is independent — the operator can apply any subset.

### P-1 · Move §6 templates to `references/ticket-templates.md`

| | Before | After |
|---|---|---|
| §6 contents | Full Feature and Bug markdown templates (verbatim) + filling rules. | 10-line summary: type/owner/repo rules + pointer to the reference doc. |
| New file | — | `references/ticket-templates.md` ≈ 60 lines (just the two verbatim templates + the filing prose). |
| Line range affected | `references/conventions.md:L295-L352` (58 lines) | §6 ≈ 10 lines |
| Delta in conventions.md | -48 lines |

Risk: low. The templates are pure reference material; no behavior
hangs off the prose. The lint rule for §N cross-refs is unaffected
(no §N changes).

### P-2 · Move §23 to `references/reports-linear-sink.md`

| | Before | After |
|---|---|---|
| §23 contents | Full Linear-sink design: config, primitive, provenance, safety, per-fire mechanics, degrade-safely. ≈ 115 lines. | 5-line stub: "If `reports.sink:"linear"`, see `references/reports-linear-sink.md`. Default `files` — §22 applies as written." |
| New file | — | `references/reports-linear-sink.md` ≈ 120 lines. |
| Line range affected | `references/conventions.md:L1455-L1569` (115 lines) | §23 stub ≈ 7 lines |
| Delta in conventions.md | -108 lines |

Risk: low **iff** §22 is genuinely self-contained for the default
`files` sink (it is — §22 never depends on §23 for its own behavior;
§23 only depends on §22). The strongest single move on the table —
≈ 7% of the file, for a feature that defaults off. Verify the lint's
`section-refs` rule still finds §23 (the stub will keep the heading,
so the §N anchor still resolves).

### P-3 · Collapse the triple operator-review-carve-out

| | Before | After |
|---|---|---|
| §14 (L685-691) | 7-line summary of the carve-out. | 2-line forward: "Operator-review carve-out: see §22's "The §17 carve-out — the operator review is the human authorization"; the five hard limits apply." |
| §17 (L821-840) | 20-line restatement of the same five-bullet rule. | 2-line forward: "Operator-review carve-out: see §22." |
| §22 (L1410-1432) | Canonical 23-line statement. | Unchanged — this becomes the single source of truth. |
| Total before | 50 lines | 27 lines |
| Delta in conventions.md | -23 lines (and eliminates 2 drift points) |

Risk: low. The five-limit rule has the same five bullets in both §17
and §22 today (verified by reading both); merging is mechanical. The
§N cross-refs from §14 and §17 to §22 work as written by the lint
(both already link to §22).

### P-4 · Trim Topology table's right-most column

| | Before | After |
|---|---|---|
| L68-77 table | 4 columns including "Hands off via" (= "Linear state + labels" repeated for every row). | 3 columns: Agent / Owns / Picks up. |
| Delta in conventions.md | -3 lines (table compaction) + reduces visual width |

Risk: trivial. The "Hands off via" column is uniform ("Linear state
+ labels" for every row) and the §0 "Topology at a glance" prose
already states the hand-off mechanism.

### P-5 · Reconcile §21 and §23 state-file paths to §11

Not a cut — a staleness fix. Three single-line edits:
- `L673` (§14 lessons.md path): qualify with "at the data-dir root
  — shared per-operator (§11)".
- `L1178-L1181` (§21 outward agents state-file path): change "next to
  `projects.json`" → "per-project under `${CLAUDE_PLUGIN_DATA}/<project-key>/` (§11)".
- `L1534-L1535` (§23 reports-state.json path): change "next to
  `projects.json`" → "per-project under `${CLAUDE_PLUGIN_DATA}/<project-key>/` (§11)".

Risk: low. Read-only-side path; agents already create these files in
the per-project subdir (see `pm-state.json`/`qa-state.json` paths in
the running data dir). Fixing the prose closes a "did you mean root
or subdir?" misread for a future agent.

### P-6 · Move §22 cadence-math mechanics to `references/reports.md`

| | Before | After |
|---|---|---|
| §22 subsections "Cadence — markers derived from the tree" (L1281-L1303), "Cold start" (L1305-L1307), "Daily = append-only" (L1309-L1321), "Weekly & monthly roll up" (L1323-L1342) | ≈ 62 lines of cadence math + catch-up rules + retention. | 5-line stub: "Cadence, roll-ups, catch-up, retention — see `references/reports.md`. Headline: dailies are the durable level; weeklies/monthlies roll up from dailies." |
| §22 main body | Unchanged: trust boundary, operator-review channel, lessons-lock, §17 carve-out. | Unchanged. |
| New file | — | `references/reports.md` ≈ 65 lines. |
| Line range affected | L1281-L1342 (62 lines) | stub ≈ 7 lines |
| Delta in conventions.md | -55 lines |

Risk: medium. The cadence math is needed at roll-up time; if a roll-up
fires and the agent skips reading the moved file, it'd get the
behavior wrong. Mitigation: the §22 stub MUST explicitly state "read
this before any roll-up." Recommendation: apply P-2 first (the
self-contained §23 move) before this one, to gauge how well stub-and-
reference works in practice.

### P-7 · Move §19 *Known state limitations* subsection out

| | Before | After |
|---|---|---|
| L1096-L1107 (Known state limitations) | 12 lines on no-cross-repo-deploy-barrier + testEnv-is-one-per-product gap. | 3-line stub: "Known limitations — see `references/multi-repo.md`." |
| New file | — | `references/multi-repo.md` ≈ 15 lines. |
| Line range affected | L1096-L1107 (12 lines) | stub ≈ 3 lines |
| Delta in conventions.md | -9 lines |

Risk: low. These are honest "we know this is broken" notes; moving
them doesn't change behavior. They're the most movable §19 subsection
because they're a one-time read for multi-repo operators, not
ongoing reference. The more aggressive "move all of §19's
subsections" is NOT proposed — finding multi-repo rules in one
place has real ROI for the multi-repo operator.

### Total projected delta

| Proposal | Lines saved in conventions.md |
|---|---|
| P-1 (move §6 templates) | -48 |
| P-2 (move §23) | -108 |
| P-3 (collapse triple carve-out) | -23 |
| P-4 (trim Topology column) | -3 |
| P-5 (staleness fixes) | 0 |
| P-6 (move §22 mechanics) | -55 |
| P-7 (move §19 limitations) | -9 |
| **Total** | **-246 lines** (1,569 → ≈ 1,323 ≈ -16%) |

P-2 + P-3 + P-1 alone are the easy first wave (≈ -179 lines, ≈ 11%
reduction) with the lowest risk — they're either moves of opt-in /
reference material (P-1, P-2) or pure dedup of a triple-stated rule
(P-3).

---

## 5. Findings explicitly NOT raised (the negative space)

For an honest audit, a few things I looked for and decided NOT to flag:

- **Section ordering** (e.g. "move §19 next to §11 because both
  describe per-project config"): there is a real coherence argument
  here, but section renumbering would invalidate every §N cross-ref
  in the codebase and the lint that protects them (`scripts/lint-plugin.py`
  `section-refs` rule). Out of scope for an audit; would need a
  separate ticket with a renumber-script.
- **`## Repo` template heading duplication** (L312, L338): both live
  inside fenced ```markdown blocks, so they don't render as real
  headings and the `md-links` lint doesn't see them. False positive
  for any "duplicate heading" rule.
- **§24 (Codex)** at the tail of the install's `~/.dev-loop/`
  conventions copy: that section is **NOT** in HEAD's
  `references/conventions.md` (which ends at §23, L1569). Auditing
  uncommitted content would violate the boundary of "what is the
  source of truth right now". If §24 lands in a later commit, a
  follow-up audit pass will catch any drift it introduces.
- **The §3 state-machine table** vs the §18 operation mapping: both
  describe state, but at orthogonal layers (semantic vs storage).
  No collapse opportunity.

---

## 6. Honest uncertainty (per AC#3)

Marked **KEEP — no action** above: R-3, R-4, R-5, R-6, M-4, M-5, C-5,
C-7. These all *look* like cuts or moves on first read but are
load-bearing on second reading (different scope, mission-critical
inline, or already-tracked). Listed so a future audit doesn't
re-raise them as new findings.

The proposals in §4 are deliberately ordered by **confidence**
(P-1/P-2/P-3 first; P-6/P-7 last). The operator can stop at any
point and still ship a meaningful reduction.
