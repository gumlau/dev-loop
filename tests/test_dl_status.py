"""Unit tests for tools/dl-status.py (LOOP-3).

Seeds a sandboxed data dir with a fixture board (one ticket per canonical state
+ extras for the staleness / blocked / oldest-Todo signals) and verifies the
summarizer's counts, the human + JSON output shapes, the >24h stall signal,
and the always-zero exit code.

Pure stdlib (unittest), like the rest of the test suite."""
from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone


_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The status CLI is a hyphenated filename (`dl-status.py`) so it can't be a
# normal `import tools.dl_status` — load it through the package machinery
# explicitly. This matches how the dashboard's `__main__` resolves modules.
_spec = importlib.util.spec_from_file_location(
    "dl_status", os.path.join(_REPO_ROOT, "tools", "dl-status.py")
)
assert _spec is not None and _spec.loader is not None
dl_status = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dl_status)

from tools.dashboard.board import discover_projects  # noqa: E402


_TICKET = """---
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
fixture for dl-status tests.

---
## Comments
"""


def _write_ticket(
    tickets_dir: str,
    tid: str,
    *,
    state: str,
    title: str = "fixture",
    ttype: str = "Feature",
    owner: str = "pm",
    labels: str = "dev-loop, Feature, pm",
    priority: int = 3,
    created: str = "2026-06-20T10:00:00Z",
    updated: str = "2026-06-20T10:00:00Z",
) -> None:
    body = _TICKET.format(
        id=tid, title=title, type=ttype, state=state, owner=owner,
        labels=labels, priority=priority, created=created, updated=updated,
    )
    with open(os.path.join(tickets_dir, f"{tid}.md"), "w", encoding="utf-8") as f:
        _ = f.write(body)


def _seed_board(data_dir: str, key: str, tickets: list[dict[str, object]]) -> str:
    tickets_dir = os.path.join(data_dir, key, "board", "tickets")
    os.makedirs(tickets_dir, exist_ok=True)
    for t in tickets:
        _write_ticket(tickets_dir, **t)
    return tickets_dir


class SummarizeProjectTests(unittest.TestCase):
    NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dl-status-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_counts_per_state_with_other_bucket(self) -> None:
        _seed_board(self.tmp, "proj", [
            {"tid": "T-1", "state": "Todo"},
            {"tid": "T-2", "state": "In Progress"},
            {"tid": "T-3", "state": "In Review"},
            {"tid": "T-4", "state": "Done"},
            {"tid": "T-5", "state": "Canceled"},   # → Other
            {"tid": "T-6", "state": "Duplicate"},  # → Other
        ])
        projects = discover_projects(self.tmp)
        self.assertEqual(len(projects), 1)
        s = dl_status.summarize_project(projects[0], now=self.NOW)
        self.assertEqual(s["counts"], {
            "todo": 1, "in_progress": 1, "in_review": 1, "done": 1, "other": 2,
        })

    def test_no_tickets_yet_when_board_is_empty(self) -> None:
        os.makedirs(os.path.join(self.tmp, "empty", "board", "tickets"))
        projects = discover_projects(self.tmp)
        # find by key — `discover_projects` lists alphabetically.
        empty = [p for p in projects if p.key == "empty"][0]
        s = dl_status.summarize_project(empty, now=self.NOW)
        self.assertFalse(s["has_tickets"])
        self.assertEqual(s["counts"], {
            "todo": 0, "in_progress": 0, "in_review": 0, "done": 0, "other": 0,
        })

    def test_oldest_todo_age_picks_the_largest(self) -> None:
        # NOW = 2026-06-22; one Todo from 5 days ago, one from 1 day ago.
        _seed_board(self.tmp, "proj", [
            {"tid": "T-1", "state": "Todo", "created": "2026-06-17T10:00:00Z"},
            {"tid": "T-2", "state": "Todo", "created": "2026-06-21T10:00:00Z"},
            {"tid": "T-3", "state": "Done", "created": "2026-06-10T10:00:00Z"},
        ])
        s = dl_status.summarize_project(discover_projects(self.tmp)[0], now=self.NOW)
        self.assertEqual(s["oldest_todo_age_days"], 5)

    def test_blocked_count_uses_label(self) -> None:
        _seed_board(self.tmp, "proj", [
            {"tid": "T-1", "state": "Todo", "labels": "dev-loop, Feature, pm, blocked"},
            {"tid": "T-2", "state": "Todo"},
            {"tid": "T-3", "state": "In Progress", "labels": "dev-loop, Bug, qa, blocked, needs-qa"},
        ])
        s = dl_status.summarize_project(discover_projects(self.tmp)[0], now=self.NOW)
        self.assertEqual(s["blocked"], 2)

    def test_stale_in_review_uses_24h_updated_threshold(self) -> None:
        # NOW = 2026-06-22T12; stale ticket updated 30h ago, fresh ticket 1h ago.
        stale_ts = (self.NOW - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        fresh_ts = (self.NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _seed_board(self.tmp, "proj", [
            {"tid": "T-1", "state": "In Review", "updated": stale_ts},
            {"tid": "T-2", "state": "In Review", "updated": fresh_ts},
            {"tid": "T-3", "state": "Todo",      "updated": stale_ts},
        ])
        s = dl_status.summarize_project(discover_projects(self.tmp)[0], now=self.NOW)
        self.assertEqual(s["stale_in_review_24h"], 1)


class CliOutputTests(unittest.TestCase):
    NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="dl-status-cli-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        _seed_board(self.tmp, "alpha", [
            {"tid": "A-1", "state": "Todo"},
            {"tid": "A-2", "state": "In Review"},
        ])
        _seed_board(self.tmp, "beta", [
            {"tid": "B-1", "state": "Done"},
        ])

    def _run(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dl_status.main(["--data-dir", self.tmp, *args])
        return rc, buf.getvalue()

    def test_exit_code_always_zero(self) -> None:
        rc, _ = self._run()
        self.assertEqual(rc, 0)
        empty_tmp = tempfile.mkdtemp(prefix="dl-status-empty-")
        self.addCleanup(lambda: __import__("shutil").rmtree(empty_tmp, ignore_errors=True))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = dl_status.main(["--data-dir", empty_tmp])
        self.assertEqual(rc, 0)
        self.assertIn("(no project boards found)", buf.getvalue())

    def test_human_output_lists_every_project(self) -> None:
        _rc, out = self._run()
        self.assertIn("alpha", out)
        self.assertIn("beta", out)
        # Header is present + the per-project rows.
        self.assertIn("oldestTodo", out)
        self.assertIn("staleIR>24h", out)

    def test_json_round_trip_schema(self) -> None:
        _rc, out = self._run("--json")
        parsed = json.loads(out)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)
        keys = {"project", "has_tickets", "counts", "blocked",
                "oldest_todo_age_days", "stale_in_review_24h"}
        for record in parsed:
            self.assertEqual(set(record.keys()), keys,
                msg=f"unexpected JSON schema: {sorted(record.keys())}")
            self.assertEqual(set(record["counts"].keys()),
                {"todo", "in_progress", "in_review", "done", "other"})
        # Per-project values check (alpha: 1 Todo + 1 In Review; beta: 1 Done)
        by = {r["project"]: r for r in parsed}
        self.assertEqual(by["alpha"]["counts"]["todo"], 1)
        self.assertEqual(by["alpha"]["counts"]["in_review"], 1)
        self.assertEqual(by["beta"]["counts"]["done"], 1)


class DataDirResolutionTests(unittest.TestCase):
    def test_cli_arg_beats_env(self) -> None:
        os.environ["CLAUDE_PLUGIN_DATA"] = "/env/path"
        self.addCleanup(lambda: os.environ.pop("CLAUDE_PLUGIN_DATA", None))
        self.assertEqual(dl_status.resolve_data_dir("/cli/arg"), "/cli/arg")

    def test_env_beats_default(self) -> None:
        os.environ["CLAUDE_PLUGIN_DATA"] = "/env/path"
        self.addCleanup(lambda: os.environ.pop("CLAUDE_PLUGIN_DATA", None))
        self.assertEqual(dl_status.resolve_data_dir(None), "/env/path")

    def test_default_when_nothing_set(self) -> None:
        os.environ.pop("CLAUDE_PLUGIN_DATA", None)
        self.assertEqual(dl_status.resolve_data_dir(None), dl_status.DEFAULT_DATA_DIR)


if __name__ == "__main__":
    unittest.main()
