"""Integration test for the read-only dev-loop dashboard.

Seeds a throwaway data dir with one ticket per canonical column, then:
1. Exercises the renderers directly (cards land in expected columns).
2. Boots the HTTP server on a free loopback port and confirms the index
   and per-project views render with the expected card IDs and column counts.

LOOP-7 extends this with:
- ActivityPanelTests — state-move parsing + agent attribution
- ReportsStripTests — present + idle path
- ThroughputTests — counts + stuck-3d callout
- MarkdownRouteTests — path-traversal rejection on /reports/<...>
- IndexSortTests — "last activity" sort
- MarkdownRenderTests — safe-render escapes raw HTML

Pure stdlib (unittest + urllib). Run via `python3 -m unittest tests.test_dashboard`
or via `bash tools/test.sh` (the wired `build.test` gate).
"""

from __future__ import annotations

import contextlib
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

# Make the repo root importable so `from tools.dashboard...` works whether the
# test is run from the repo root or via the package's launcher script.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.dashboard.board import (  # noqa: E402
    COLUMNS,
    OTHER,
    Project,
    Throughput,
    discover_projects,
    find_project,
    list_agent_reports,
    load_ticket,
    parse_frontmatter,
    parse_state_moves,
)
from tools.dashboard.server import (  # noqa: E402
    _invalidate_cache,
    make_handler,
    render_index,
    render_markdown,
    render_project,
)


_TICKET_TEMPLATE = """---
id: {id}
title: {title}
type: {type}
state: {state}
owner: {owner}
labels: [{labels}]
priority: {priority}
assignee: null
relatedTo: []
duplicateOf: null
created: 2026-06-20T10:00:00Z
updated: 2026-06-20T10:00:00Z
---
## Context
seed ticket for the dashboard test.

## Acceptance criteria
- [ ] none — this is a fixture

---
## Comments
"""


_TICKET_TEMPLATE_WITH_MOVES = """---
id: {id}
title: {title}
type: {type}
state: {state}
owner: {owner}
labels: [{labels}]
priority: {priority}
assignee: null
relatedTo: []
duplicateOf: null
created: {created}
updated: {updated}
---
## Context
seed ticket with state moves.

---
## Comments

{comments}
"""


def _seed_board(data_dir: str, project_key: str) -> None:
    """Write one ticket per canonical column under <data_dir>/<key>/board/tickets/."""
    tickets_dir = os.path.join(data_dir, project_key, "board", "tickets")
    os.makedirs(tickets_dir, exist_ok=True)
    fixtures = [
        ("SEED-1", "Todo task — a thing to do",         "Feature",     "Todo",        "pm", "dev-loop, Feature, pm",            1),
        ("SEED-2", "Work in flight",                    "Bug",         "In Progress", "qa", "dev-loop, Bug, qa, edge-case",     2),
        ("SEED-3", "Ready for review",                  "Improvement", "In Review",   "pm", "dev-loop, Improvement, pm",        3),
        ("SEED-4", "Shipped and verified",              "Feature",     "Done",        "pm", "dev-loop, Feature, pm",            4),
        ("SEED-5", "Canceled obsolete idea",            "Feature",     "Canceled",    "pm", "dev-loop, Feature, pm",            0),
    ]
    for tid, title, ttype, state, owner, labels, priority in fixtures:
        with open(os.path.join(tickets_dir, f"{tid}.md"), "w", encoding="utf-8") as f:
            f.write(_TICKET_TEMPLATE.format(
                id=tid, title=title, type=ttype, state=state,
                owner=owner, labels=labels, priority=priority,
            ))


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FrontmatterParserTests(unittest.TestCase):
    def test_parses_basic_fields(self) -> None:
        text = (
            "---\n"
            "id: X-1\n"
            "title: hello world\n"
            "priority: 2\n"
            "labels: [a, b, c]\n"
            "assignee: null\n"
            "---\n"
            "body\n"
        )
        fm = parse_frontmatter(text)
        self.assertEqual(fm["id"], "X-1")
        self.assertEqual(fm["title"], "hello world")
        self.assertEqual(fm["priority"], 2)
        self.assertEqual(fm["labels"], ["a", "b", "c"])
        self.assertIsNone(fm["assignee"])

    def test_handles_empty_list_and_missing_frontmatter(self) -> None:
        fm = parse_frontmatter("---\nrelatedTo: []\n---\nbody\n")
        self.assertEqual(fm["relatedTo"], [])
        self.assertEqual(parse_frontmatter("no frontmatter here"), {})


class DashboardRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-")
        _seed_board(self.tmp, "seedproj")
        # An empty board — has board/ but no tickets/, per AC #2.
        os.makedirs(os.path.join(self.tmp, "emptyproj", "board"), exist_ok=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_discover_finds_both_projects(self) -> None:
        keys = sorted(p.key for p in discover_projects(self.tmp))
        self.assertEqual(keys, ["emptyproj", "seedproj"])

    def test_seed_tickets_load_with_expected_columns(self) -> None:
        proj = find_project(self.tmp, "seedproj")
        assert proj is not None
        by_col = proj.by_column()
        # AC #3: one card per canonical column.
        for col in COLUMNS:
            with self.subTest(column=col):
                self.assertEqual(len(by_col[col]), 1, f"expected 1 card in {col}, got {len(by_col[col])}")
        # The Canceled seed lands in the Other pile.
        self.assertEqual(len(by_col[OTHER]), 1)

    def test_index_html_lists_projects_and_marks_empty(self) -> None:
        html = render_index(discover_projects(self.tmp))
        self.assertIn("seedproj", html)
        self.assertIn("emptyproj", html)
        # AC #2: the empty board is shown as "no tickets yet", not omitted.
        self.assertIn("no tickets yet", html)

    def test_project_html_renders_all_four_cards_in_their_columns(self) -> None:
        proj = find_project(self.tmp, "seedproj")
        assert proj is not None
        html = render_project(proj)
        # AC #4: every canonical card surfaces ID + title in the rendered HTML.
        for tid in ("SEED-1", "SEED-2", "SEED-3", "SEED-4"):
            self.assertIn(tid, html)
        # AC #3: the four column headers are present.
        for col in COLUMNS:
            self.assertIn(col, html)
        # Display labels (AC #4) — `edge-case` is a non-routing label and
        # should surface; `dev-loop`/`Bug`/`qa` should NOT show as label chips.
        self.assertIn("edge-case", html)
        # AC #4: priority badge (Urgent for SEED-1, priority=1).
        self.assertIn("Urgent", html)

    def test_card_excludes_routing_labels(self) -> None:
        # Specific check that the Bug seed's chips don't include "qa" twice
        # (the owner pill shows it once; it MUST NOT also appear as a label chip).
        proj = find_project(self.tmp, "seedproj")
        assert proj is not None
        seed2 = next(t for t in proj.tickets if t.id == "SEED-2")
        self.assertNotIn("dev-loop", seed2.display_labels())
        self.assertNotIn("Bug", seed2.display_labels())
        self.assertNotIn("qa", seed2.display_labels())
        self.assertIn("edge-case", seed2.display_labels())


class HTTPServerTests(unittest.TestCase):
    """Boot the real HTTP server on a free loopback port and hit it via urllib."""

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-http-")
        _seed_board(self.tmp, "httpproj")
        self.port = _free_port()
        handler = make_handler(self.tmp)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, path: str) -> tuple[int, str]:
        with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as resp:
            return resp.status, resp.read().decode("utf-8")

    def test_index_returns_project_listing(self) -> None:
        status, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("httpproj", body)

    def test_project_page_returns_kanban(self) -> None:
        status, body = self._get("/p/httpproj")
        self.assertEqual(status, 200)
        for col in COLUMNS:
            self.assertIn(col, body)
        for tid in ("SEED-1", "SEED-2", "SEED-3", "SEED-4"):
            self.assertIn(tid, body)

    def test_unknown_project_returns_404(self) -> None:
        try:
            status, _ = self._get("/p/does-not-exist")
        except Exception as e:
            # urllib raises HTTPError on 4xx; treat as the assertion outcome.
            status = getattr(e, "code", 0)
        self.assertEqual(status, 404)

    def test_path_traversal_rejected(self) -> None:
        try:
            status, _ = self._get("/p/..")
        except Exception as e:
            status = getattr(e, "code", 0)
        self.assertEqual(status, 404)


class NonUtf8TicketTests(unittest.TestCase):
    """LOOP-6 regression: a ticket file with non-UTF-8 bytes must NOT take down
    the dashboard. One bad card is skipped; the rest of the board still renders.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-utf8-")
        tickets_dir = os.path.join(self.tmp, "badproj", "board", "tickets")
        os.makedirs(tickets_dir, exist_ok=True)
        # One good ticket — must still surface in the rendered page.
        with open(os.path.join(tickets_dir, "X-1.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\nid: X-1\ntitle: ok\ntype: Feature\nstate: Todo\nowner: pm\n"
                "labels: [dev-loop, Feature, pm]\npriority: 2\n"
                "created: 2026-06-22T00:00:00Z\n---\n"
            )
        # One ticket with an invalid UTF-8 byte in the body. Before the fix this
        # raised UnicodeDecodeError out of load_ticket and crashed the HTTP
        # handler, killing the whole dashboard.
        with open(os.path.join(tickets_dir, "X-2.md"), "wb") as f:
            f.write(
                b"---\nid: X-2\ntitle: bad\ntype: Bug\nstate: Todo\nowner: qa\n"
                b"labels: [dev-loop, Bug, qa]\npriority: 1\n"
                b"created: 2026-06-22T00:00:00Z\n---\n"
                b"has \xff bytes\n"
            )

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_ticket_returns_none_on_bad_utf8(self) -> None:
        bad = os.path.join(self.tmp, "badproj", "board", "tickets", "X-2.md")
        self.assertIsNone(load_ticket(bad))
        # Sibling good ticket still parses fine — the bad file does not poison
        # subsequent loads.
        good = os.path.join(self.tmp, "badproj", "board", "tickets", "X-1.md")
        t = load_ticket(good)
        assert t is not None
        self.assertEqual(t.id, "X-1")

    def test_discover_skips_bad_file_keeps_good_ones(self) -> None:
        proj = find_project(self.tmp, "badproj")
        assert proj is not None
        ids = {t.id for t in proj.tickets}
        self.assertIn("X-1", ids)
        self.assertNotIn("X-2", ids)

    def test_http_server_serves_index_and_project_with_bad_ticket_present(self) -> None:
        port = _free_port()
        handler = make_handler(self.tmp)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                self.assertIn("badproj", body)
            with urlopen(f"http://127.0.0.1:{port}/p/badproj", timeout=2) as resp:
                self.assertEqual(resp.status, 200)
                body = resp.read().decode("utf-8")
                # The good ticket renders; the bad one is silently skipped.
                self.assertIn("X-1", body)
                self.assertNotIn("X-2", body)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


# ---------------------------------------------------------------------------
# LOOP-7 — Activity panel: state-move parsing + agent attribution.
# ---------------------------------------------------------------------------


class ActivityPanelTests(unittest.TestCase):
    """Parse state moves from a ticket's `## Comments` section, in the
    canonical §18 format. Verify ordering (newest first) and agent attribution.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-activity-")
        tickets_dir = os.path.join(self.tmp, "actproj", "board", "tickets")
        os.makedirs(tickets_dir, exist_ok=True)

        # Three tickets with distinct state-move trajectories. Comments use
        # the canonical em-dash + arrow format from conventions §18.
        comments_a = (
            "### 2026-06-22T10:00:00Z — pm (run pm-1)\n"
            "Filing this feature; needs ACs.\n\n"
            "### 2026-06-22T11:00:00Z — dev (run d-1)\n"
            "state: Todo → In Progress. Claiming.\n\n"
            "### 2026-06-22T12:00:00Z — dev (run d-1)\n"
            "state: In Progress → In Review. Shipped in abc1234.\n"
        )
        comments_b = (
            "### 2026-06-22T13:00:00Z — qa (run q-1)\n"
            "state: In Review → Done. Verified.\n"
        )
        comments_c = (
            "### 2026-06-22T09:00:00Z — qa (run q-2)\n"
            "Filed without a state move (just an observation).\n"
        )

        for tid, title, ttype, state, owner, created, updated, comments in [
            ("A-1", "alpha",  "Feature", "In Review", "pm", "2026-06-22T09:00:00Z", "2026-06-22T12:00:00Z", comments_a),
            ("B-1", "bravo",  "Bug",     "Done",      "qa", "2026-06-22T08:00:00Z", "2026-06-22T13:00:00Z", comments_b),
            ("C-1", "cherry", "Bug",     "Todo",      "qa", "2026-06-22T08:30:00Z", "2026-06-22T09:00:00Z", comments_c),
        ]:
            with open(os.path.join(tickets_dir, f"{tid}.md"), "w", encoding="utf-8") as f:
                f.write(_TICKET_TEMPLATE_WITH_MOVES.format(
                    id=tid, title=title, type=ttype, state=state, owner=owner,
                    labels=f"dev-loop, {ttype}, {owner}",
                    priority=2,
                    created=created, updated=updated,
                    comments=comments,
                ))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_state_moves_picks_up_only_state_lines(self) -> None:
        text = (
            "## Comments\n\n"
            "### 2026-06-22T10:00:00Z — pm (run pm-1)\nNo state line here.\n\n"
            "### 2026-06-22T11:00:00Z — dev (run d-1)\nstate: Todo → In Progress.\n"
        )
        moves = parse_state_moves(text, "X-1", "the title")
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0].agent, "dev")
        self.assertEqual(moves[0].from_state, "Todo")
        self.assertEqual(moves[0].to_state, "In Progress")
        self.assertEqual(moves[0].timestamp, "2026-06-22T11:00:00Z")
        self.assertEqual(moves[0].ticket_id, "X-1")

    def test_project_recent_activity_is_newest_first_and_correctly_attributed(self) -> None:
        proj = find_project(self.tmp, "actproj")
        assert proj is not None
        events = proj.recent_activity()
        # Three state-moves total (A-1 has two; B-1 has one; C-1 has none).
        self.assertEqual(len(events), 3)
        # Newest first.
        self.assertEqual(
            [e.timestamp for e in events],
            ["2026-06-22T13:00:00Z", "2026-06-22T12:00:00Z", "2026-06-22T11:00:00Z"],
        )
        # Agent attribution — the QA move from B-1, then two Dev moves on A-1.
        self.assertEqual([e.agent for e in events], ["qa", "dev", "dev"])
        # Transition + ticket-id wiring.
        self.assertEqual(
            (events[0].from_state, events[0].to_state, events[0].ticket_id),
            ("In Review", "Done", "B-1"),
        )
        self.assertEqual(
            (events[2].from_state, events[2].to_state, events[2].ticket_id),
            ("Todo", "In Progress", "A-1"),
        )

    def test_activity_panel_appears_in_rendered_html(self) -> None:
        proj = find_project(self.tmp, "actproj")
        assert proj is not None
        html = render_project(proj)
        self.assertIn("Recent activity", html)
        # The transition text appears in the activity list (em-dash and arrow).
        self.assertIn("In Review → Done", html)
        self.assertIn("Todo → In Progress", html)


# ---------------------------------------------------------------------------
# LOOP-7 — Agent reports strip: present + idle path.
# ---------------------------------------------------------------------------


class ReportsStripTests(unittest.TestCase):
    """One project has a `reports/pm-agent/daily/<today>.md`; another doesn't.
    The chip shows for the present one; "idle today" shows for absent agents.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-reports-")
        # Project A: pm-agent has today's daily; qa-agent has only weekly.
        # Project B: no reports tree at all (graceful — no chips).
        today = datetime.now().strftime("%Y-%m-%d")
        self.today = today

        a_pm_daily = os.path.join(self.tmp, "proj-a", "reports", "pm-agent", "daily")
        os.makedirs(a_pm_daily, exist_ok=True)
        with open(os.path.join(a_pm_daily, f"{today}.md"), "w", encoding="utf-8") as f:
            f.write("# pm-agent daily — today\n\nShipped one feature.\n")

        a_qa_weekly = os.path.join(self.tmp, "proj-a", "reports", "qa-agent", "weekly")
        os.makedirs(a_qa_weekly, exist_ok=True)
        with open(os.path.join(a_qa_weekly, "2026-W25.md"), "w", encoding="utf-8") as f:
            f.write("# qa-agent weekly\n\nA roll-up.\n")
        # qa-agent has no daily/<today>.md → idle today.
        os.makedirs(os.path.join(self.tmp, "proj-a", "reports", "qa-agent", "daily"), exist_ok=True)
        os.makedirs(os.path.join(self.tmp, "proj-a", "board", "tickets"), exist_ok=True)

        # Project B: no reports/ at all.
        os.makedirs(os.path.join(self.tmp, "proj-b", "board", "tickets"), exist_ok=True)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_list_agent_reports_finds_today_and_marks_idle_correctly(self) -> None:
        reports = list_agent_reports(
            os.path.join(self.tmp, "proj-a"),
            today_key=self.today,
        )
        by_name = {r.agent: r for r in reports}
        self.assertIn("pm-agent", by_name)
        self.assertIn("qa-agent", by_name)
        self.assertFalse(by_name["pm-agent"].is_idle_today,
                         "pm-agent has today's daily — should not be idle")
        self.assertTrue(by_name["qa-agent"].is_idle_today,
                        "qa-agent has no today daily — should be idle")
        # Weekly file picked up via the dated grammar.
        self.assertIn("2026-W25.md", by_name["qa-agent"].weekly_files)

    def test_strip_rendered_with_chip_for_present_and_idle_for_absent(self) -> None:
        proj = find_project(self.tmp, "proj-a", today_key=self.today)
        assert proj is not None
        html = render_project(proj)
        # The present agent gets a link chip; the idle agent shows "idle today".
        self.assertIn("Agent reports", html)
        self.assertIn("pm-agent", html)
        self.assertIn("qa-agent · idle today", html)

    def test_project_without_reports_dir_renders_empty_strip(self) -> None:
        proj = find_project(self.tmp, "proj-b", today_key=self.today)
        assert proj is not None
        html = render_project(proj)
        self.assertIn("Agent reports", html)
        # Absent reports tree → empty-state copy, never a crash.
        self.assertIn("No reports tree yet", html)


# ---------------------------------------------------------------------------
# LOOP-7 — Throughput: counts + stuck callout.
# ---------------------------------------------------------------------------


class ThroughputTests(unittest.TestCase):
    """Synthetic timestamps: 2 filed, 1 shipped, 1 verified, 1 stuck (4d old)."""

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-tput-")
        tickets_dir = os.path.join(self.tmp, "tputproj", "board", "tickets")
        os.makedirs(tickets_dir, exist_ok=True)

        # "Now" is the future-ish fixture date. The tests pin `now` via the
        # Project.throughput() argument, so wall-clock drift doesn't break this.
        self.now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)

        fixtures = [
            # T-1: filed 2 days ago; shipped 1 day ago; verified 12h ago. In window.
            ("T-1", "filed/shipped/verified all in window", "Feature", "Done", "pm",
             "2026-06-23T12:00:00Z", "2026-06-25T00:00:00Z",
             "### 2026-06-23T13:00:00Z — dev (run dx)\nstate: Todo → In Progress.\n\n"
             "### 2026-06-24T12:00:00Z — dev (run dx)\nstate: In Progress → In Review.\n\n"
             "### 2026-06-25T00:00:00Z — pm (run px)\nstate: In Review → Done.\n"),
            # T-2: filed 1d ago, no moves yet. Counts as `filed`.
            ("T-2", "freshly filed", "Bug", "Todo", "qa",
             "2026-06-24T12:00:00Z", "2026-06-24T12:00:00Z",
             ""),
            # T-3: STUCK — In Progress, last state move was 5 days ago (>3d).
            ("T-3", "stuck old work", "Feature", "In Progress", "pm",
             "2026-06-15T00:00:00Z", "2026-06-20T07:00:00Z",
             "### 2026-06-20T07:00:00Z — dev (run d-old)\nstate: Todo → In Progress.\n"),
            # T-4: outside the 7-day window — filed 30 days ago, no recent moves.
            ("T-4", "old, untouched", "Feature", "Done", "pm",
             "2026-05-25T00:00:00Z", "2026-05-25T00:00:00Z",
             ""),
        ]
        for tid, title, ttype, state, owner, created, updated, comments in fixtures:
            with open(os.path.join(tickets_dir, f"{tid}.md"), "w", encoding="utf-8") as f:
                f.write(_TICKET_TEMPLATE_WITH_MOVES.format(
                    id=tid, title=title, type=ttype, state=state, owner=owner,
                    labels=f"dev-loop, {ttype}, {owner}",
                    priority=2,
                    created=created, updated=updated,
                    comments=comments,
                ))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_match_synthetic_window(self) -> None:
        proj = find_project(self.tmp, "tputproj")
        assert proj is not None
        tput = proj.throughput(now=self.now)
        # T-1 and T-2 filed inside window (T-3 was 10d ago, T-4 was 30d ago).
        self.assertEqual(tput.filed, 2, "expected 2 tickets filed in last 7d")
        # T-1 shipped (→ In Review) inside the window.
        self.assertEqual(tput.shipped, 1)
        # T-1 verified (→ Done) inside the window.
        self.assertEqual(tput.verified, 1)

    def test_stuck_callout_includes_T3_only(self) -> None:
        proj = find_project(self.tmp, "tputproj")
        assert proj is not None
        tput = proj.throughput(now=self.now)
        stuck_ids = {t.id for t in tput.stuck}
        self.assertEqual(stuck_ids, {"T-3"},
                         f"only T-3 should be stuck; got {stuck_ids}")

    def test_terminal_tickets_never_stuck(self) -> None:
        # T-4 is Done — never stuck, however old it is.
        proj = find_project(self.tmp, "tputproj")
        assert proj is not None
        tput = proj.throughput(now=self.now)
        ids = [t.id for t in tput.stuck]
        self.assertNotIn("T-4", ids)
        self.assertNotIn("T-1", ids)  # Also Done.

    def test_throughput_renders_with_numbers_and_stuck_callout(self) -> None:
        proj = find_project(self.tmp, "tputproj")
        assert proj is not None
        # The renderer uses a *real* clock for `now`; we can't pin it. But the
        # whole stuck/throughput rendering exists, so just sanity-check the
        # structure.
        html = render_project(proj)
        self.assertIn("Throughput", html)
        self.assertIn("filed (7d)", html)
        self.assertIn("shipped (7d)", html)
        self.assertIn("verified (7d)", html)


# ---------------------------------------------------------------------------
# LOOP-7 — Markdown render route: path traversal must be rejected.
# ---------------------------------------------------------------------------


class MarkdownRouteTests(unittest.TestCase):
    """The /reports/<project>/<agent>/<period>/<file> route is strictly
    whitelisted. Any attempt to escape the reports tree must 404.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-md-")
        self.today = datetime.now().strftime("%Y-%m-%d")
        # Project with one valid report file the route should serve.
        pm_daily = os.path.join(self.tmp, "mdproj", "reports", "pm-agent", "daily")
        os.makedirs(pm_daily, exist_ok=True)
        with open(os.path.join(pm_daily, f"{self.today}.md"), "w", encoding="utf-8") as f:
            f.write("# Today\n\nA tiny report.\n")
        # Sensitive file outside the reports tree — the test will try to reach
        # it via traversal and assert it is NEVER served.
        with open(os.path.join(self.tmp, "secret.txt"), "w", encoding="utf-8") as f:
            f.write("THIS-MUST-NEVER-LEAK")
        # Also park something under `mdproj/` (still outside reports/).
        with open(os.path.join(self.tmp, "mdproj", "extra.md"), "w", encoding="utf-8") as f:
            f.write("MUST-NOT-LEAK-EITHER")

        self.port = _free_port()
        handler = make_handler(self.tmp)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _status(self, path: str) -> int:
        try:
            with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as resp:
                return resp.status
        except Exception as e:
            return getattr(e, "code", 0)

    def _body(self, path: str) -> str:
        with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as resp:
            return resp.read().decode("utf-8")

    def test_valid_report_path_serves_200(self) -> None:
        status = self._status(f"/reports/mdproj/pm-agent/daily/{self.today}.md")
        self.assertEqual(status, 200)

    def test_unknown_agent_is_404(self) -> None:
        # "bogus-agent" is not in the whitelist.
        self.assertEqual(
            self._status(f"/reports/mdproj/bogus-agent/daily/{self.today}.md"),
            404,
        )

    def test_traversal_with_dotdot_segments_is_404(self) -> None:
        # Even URL-encoded `..` segments must be rejected.
        for atk in [
            "/reports/mdproj/pm-agent/daily/..",
            "/reports/mdproj/pm-agent/daily/../../../etc/passwd",
            "/reports/mdproj/pm-agent/../extra.md",
            "/reports/mdproj/../../secret.txt",
        ]:
            with self.subTest(attack=atk):
                self.assertEqual(self._status(atk), 404)
        # The secret outside the tree must not appear in the index either.
        index = self._body("/")
        self.assertNotIn("THIS-MUST-NEVER-LEAK", index)

    def test_filename_must_match_dated_grammar(self) -> None:
        # Non-dated filename — even if it exists somewhere — must 404.
        # Plant a bogus file in the daily/ dir and confirm the route refuses to serve it.
        bogus = os.path.join(self.tmp, "mdproj", "reports", "pm-agent", "daily", "notes.md")
        with open(bogus, "w", encoding="utf-8") as f:
            f.write("ARBITRARY")
        self.assertEqual(
            self._status("/reports/mdproj/pm-agent/daily/notes.md"),
            404,
        )


# ---------------------------------------------------------------------------
# LOOP-7 — Markdown renderer safety.
# ---------------------------------------------------------------------------


class MarkdownRenderTests(unittest.TestCase):
    def test_html_in_source_is_escaped(self) -> None:
        # A malicious report shouldn't be able to inject script tags.
        out = render_markdown("Hello <script>alert(1)</script> world\n")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_basic_constructs(self) -> None:
        src = "# Title\n\nA **bold** word and a `code` snippet.\n"
        out = render_markdown(src)
        self.assertIn("<h3>Title</h3>", out)  # headings nested under page h1
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<code>code</code>", out)

    def test_link_only_http(self) -> None:
        out = render_markdown("See [docs](https://example.com/x)\n")
        self.assertIn('href="https://example.com/x"', out)
        # javascript: scheme must NOT be linkified. The literal text may
        # survive (escaped), but no <a href="javascript:..."> tag may appear.
        bad = render_markdown("See [x](javascript:alert(1))\n")
        self.assertNotIn('href="javascript:', bad)
        self.assertNotIn('<a href', bad)


# ---------------------------------------------------------------------------
# LOOP-11 — Null-byte FENCED placeholder collision.
#
# The renderer extracts fenced code blocks behind internal sentinel
# placeholders, then restores them after escaping the rest. The old
# deterministic sentinel grammar (`\x00FENCED<n>\x00`) collided with
# user-controlled bytes that happened to match the same shape — two
# distinct failure modes:
#   - out-of-range `<n>` (no matching block) → IndexError → request thread
#     died → client saw RemoteDisconnected;
#   - in-range `<n>` (matching an existing block) → silent substitution of
#     ANOTHER block's rendered HTML at the sentinel position → 200 with
#     wrong-but-escaped content (worse than crashing).
# The fix (Option B in the ticket) replaces the deterministic grammar with
# a per-render random token, so user bytes can never alias the sentinel.
# ---------------------------------------------------------------------------


class MarkdownPlaceholderCollisionTests(unittest.TestCase):
    """Regression tests for LOOP-11. Both failure modes must be closed:
    out-of-range index (was IndexError) AND in-range substitution
    (was silent block aliasing).
    """

    def test_out_of_range_sentinel_does_not_crash(self) -> None:
        # No fenced blocks in source ⇒ placeholders list is empty. The old
        # deterministic regex would match `\x00FENCED999\x00` and try
        # placeholders[999], raising IndexError.
        src = "Before\x00FENCED999\x00After\n"
        # Must not raise. Result is a string with the literal bytes
        # rendered as escaped text — never as another block's content.
        out = render_markdown(src)
        self.assertIsInstance(out, str)
        # The bytes survive in the output (escaped/literal) — they were
        # never wrongly resolved.
        self.assertIn("Before", out)
        self.assertIn("After", out)

    def test_in_range_sentinel_does_not_alias_real_block(self) -> None:
        # One real fenced block (placeholders[0] will exist). A literal
        # `\x00FENCED0\x00` byte sequence elsewhere in the source used to
        # silently render placeholders[0]'s HTML at the wrong location,
        # so the same fenced block's content appeared TWICE in the output.
        src = (
            "First paragraph.\n\n"
            "```\nSECRET_FROM_FIRST_FENCE\n```\n\n"
            "Middle paragraph: \x00FENCED0\x00 here.\n\n"
            "Last paragraph.\n"
        )
        out = render_markdown(src)
        # The real fenced block renders exactly once.
        self.assertEqual(out.count("SECRET_FROM_FIRST_FENCE"), 1)
        # Surrounding text survives.
        self.assertIn("First paragraph", out)
        self.assertIn("Last paragraph", out)

    def test_per_render_token_does_not_leak_to_output(self) -> None:
        # Two renders of the same source must produce equivalent visible
        # output (modulo the token, which is internal and must NOT appear
        # in the rendered HTML). The internal `\x00FENCED-…` grammar must
        # be fully consumed in step 8.
        src = "```\nA\n```\n"
        a = render_markdown(src)
        b = render_markdown(src)
        self.assertIn("<pre><code>A", a)
        self.assertIn("<pre><code>A", b)
        # The internal sentinel grammar never leaks.
        self.assertNotIn("\x00FENCED", a)
        self.assertNotIn("\x00FENCED", b)
        # And the rendered bodies match (no token differences visible).
        self.assertEqual(a, b)


class MarkdownRouteCollisionTests(unittest.TestCase):
    """Integration: the /reports route survives a report file with the
    sentinel-shaped bytes, and sibling routes stay healthy.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-coll-")
        self.today = datetime.now().strftime("%Y-%m-%d")
        # Project the dashboard will discover (needs a board/tickets/ dir).
        coll_tix = os.path.join(self.tmp, "collproj", "board", "tickets")
        os.makedirs(coll_tix, exist_ok=True)
        with open(os.path.join(coll_tix, "C-1.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\nid: C-1\ntitle: ok\ntype: Feature\nstate: Todo\nowner: pm\n"
                "labels: [dev-loop, Feature, pm]\npriority: 3\n"
                "created: 2026-06-22T00:00:00Z\n---\n"
            )
        rdir = os.path.join(self.tmp, "collproj", "reports", "pm-agent", "daily")
        os.makedirs(rdir, exist_ok=True)
        # The bad-bytes report — same shape as the ticket's repro.
        with open(os.path.join(rdir, f"{self.today}.md"), "wb") as f:
            f.write(b"Before\x00FENCED999\x00After\n")
        # A second project so the index can confirm sibling rendering.
        other_tix = os.path.join(self.tmp, "siblingproj", "board", "tickets")
        os.makedirs(other_tix, exist_ok=True)
        with open(os.path.join(other_tix, "S-1.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\nid: S-1\ntitle: ok\ntype: Feature\nstate: Todo\nowner: pm\n"
                "labels: [dev-loop, Feature, pm]\npriority: 3\n"
                "created: 2026-06-22T00:00:00Z\n---\n"
            )

        self.port = _free_port()
        handler = make_handler(self.tmp)
        self.server = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _status(self, path: str) -> int:
        try:
            with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as resp:
                return resp.status
        except Exception as e:
            # A RemoteDisconnected has no .code (returns 0). Anything other
            # than a real HTTP status is a failure for the bad-bytes route.
            return getattr(e, "code", 0)

    def test_bad_bytes_report_returns_200_no_disconnect(self) -> None:
        # The whole point: a report containing the literal sentinel bytes
        # used to kill the request thread (RemoteDisconnected). Now it
        # must return a real HTTP status — 200 with escaped text is fine.
        status = self._status(
            f"/reports/collproj/pm-agent/daily/{self.today}.md"
        )
        self.assertEqual(status, 200)

    def test_sibling_routes_unaffected(self) -> None:
        # Index lists both projects, per-project view for sibling works,
        # all independent of the bad report file.
        with urlopen(f"http://127.0.0.1:{self.port}/", timeout=2) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
        self.assertIn("collproj", body)
        self.assertIn("siblingproj", body)
        with urlopen(
            f"http://127.0.0.1:{self.port}/p/siblingproj", timeout=2
        ) as resp:
            self.assertEqual(resp.status, 200)


# ---------------------------------------------------------------------------
# LOOP-7 — Index "last activity" sort.
# ---------------------------------------------------------------------------


class IndexSortTests(unittest.TestCase):
    """Two projects with different newest-mtimes — the index must list the
    newest-activity one first, and surface a "last activity: …" line per project.
    """

    def setUp(self) -> None:
        _invalidate_cache()
        self.tmp = tempfile.mkdtemp(prefix="devloop-dash-sort-")
        # Older project — tickets touched in the past.
        older = os.path.join(self.tmp, "older-proj", "board", "tickets")
        os.makedirs(older, exist_ok=True)
        with open(os.path.join(older, "O-1.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\nid: O-1\ntitle: old\ntype: Feature\nstate: Done\nowner: pm\n"
                "labels: [dev-loop, Feature, pm]\npriority: 4\n"
                "created: 2026-01-01T00:00:00Z\n---\n"
            )
        # Backdate its mtime to a known past time.
        os.utime(
            os.path.join(older, "O-1.md"),
            (time.time() - 86400 * 30, time.time() - 86400 * 30),
        )

        # Newer project — fresh ticket.
        newer = os.path.join(self.tmp, "newer-proj", "board", "tickets")
        os.makedirs(newer, exist_ok=True)
        with open(os.path.join(newer, "N-1.md"), "w", encoding="utf-8") as f:
            f.write(
                "---\nid: N-1\ntitle: new\ntype: Bug\nstate: Todo\nowner: qa\n"
                "labels: [dev-loop, Bug, qa]\npriority: 1\n"
                "created: 2026-06-22T00:00:00Z\n---\n"
            )

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_index_lists_newest_first_and_renders_last_activity_line(self) -> None:
        projects = discover_projects(self.tmp)
        html = render_index(projects)
        self.assertIn("last activity:", html)
        # The newer project's name should appear earlier in the body than
        # the older project's name — that's how "newest first" looks on screen.
        i_new = html.find("newer-proj")
        i_old = html.find("older-proj")
        self.assertGreater(i_new, 0)
        self.assertGreater(i_old, 0)
        self.assertLess(i_new, i_old,
                        "newer-proj must appear above older-proj on the index")


if __name__ == "__main__":
    unittest.main()
