"""Integration test for the read-only dev-loop dashboard.

Seeds a throwaway data dir with one ticket per canonical column, then:
1. Exercises the renderers directly (cards land in expected columns).
2. Boots the HTTP server on a free loopback port and confirms the index
   and per-project views render with the expected card IDs and column counts.

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
import unittest
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
    discover_projects,
    find_project,
    load_ticket,
    parse_frontmatter,
)
from tools.dashboard.server import (  # noqa: E402
    make_handler,
    render_index,
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


if __name__ == "__main__":
    unittest.main()
