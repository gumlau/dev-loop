"""dev-loop status — cross-project board-health summary CLI (LOOP-3).

A terminal-friendly companion to the LOOP-1 dashboard: auto-discovers every
project board under `${CLAUDE_PLUGIN_DATA:-~/.claude/plugins/data/dev-loop}/<project>/board/`
and prints a compact per-project summary. `--json` emits the same data as JSON
(one object per project) for `jq` and downstream tools. Read-only; exits 0
always (status is signal, never an alarm — `--alert` would be a separate
ticket, not this one).

Pure stdlib. Re-uses the LOOP-1 reader at `tools.dashboard.board` rather than
forking it — same parse semantics across the dashboard and the CLI.

Usage:
    python3 tools/dl-status.py            # human-readable table
    python3 tools/dl-status.py --json     # JSON (one object per project)
    python3 tools/dl-status.py --data-dir <path>  # override the data root
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Make repo root importable so `from tools.dashboard.board import ...` works
# whether the script is run from the repo root or from anywhere via
# `python3 /abs/path/to/tools/dl-status.py`.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from tools.dashboard.board import (  # noqa: E402
    COLUMNS,
    OTHER,
    Project,
    Ticket,
    discover_projects,
    parse_frontmatter,
)


DEFAULT_DATA_DIR = os.path.expanduser("~/.claude/plugins/data/dev-loop")
STALE_IN_REVIEW_HOURS = 24


def _read_updated(ticket: Ticket) -> str:
    """Return the ticket's `updated:` frontmatter field, or `created` if absent.

    The `Ticket` dataclass owned by `tools.dashboard.board` doesn't carry
    `updated` (LOOP-1 only needed `created`). Re-parsing one field via the
    same `parse_frontmatter` keeps this CLI a pure consumer of the shared
    reader — no edits to the dashboard package.
    """
    try:
        with open(ticket.path, "r", encoding="utf-8") as f:
            fm = parse_frontmatter(f.read())
    except (OSError, UnicodeDecodeError):
        return ticket.created
    return str(fm.get("updated") or ticket.created)


def _hours_since(iso: str, now: datetime) -> float:
    if not iso:
        return 0.0
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds() / 3600.0)
    except (ValueError, TypeError):
        return 0.0


def summarize_project(p: Project, now: datetime | None = None) -> dict[str, object]:
    """Build the per-project summary record (AC #3).

    Counts every ticket by state into the four canonical columns + "Other"
    (Canceled/Duplicate/Backlog land there per `tools.dashboard.board.OTHER`).
    Also computes the oldest Todo age, the blocked count, and the stall
    signal (In Review tickets older than 24 h by `updated`).
    """
    now = now or datetime.now(timezone.utc)
    by = p.by_column()
    counts: dict[str, int] = {c: len(by[c]) for c in COLUMNS}
    counts[OTHER] = len(by[OTHER])

    todos = [t for t in p.tickets if t.state == "Todo"]
    oldest_todo_age = max((t.age_days(now=now) for t in todos), default=0)

    blocked = sum(1 for t in p.tickets if "blocked" in t.labels)

    in_review = [t for t in p.tickets if t.state == "In Review"]
    stale_in_review = sum(
        1 for t in in_review if _hours_since(_read_updated(t), now) > STALE_IN_REVIEW_HOURS
    )

    return {
        "project": p.key,
        "has_tickets": p.has_tickets,
        "counts": {
            "todo": counts["Todo"],
            "in_progress": counts["In Progress"],
            "in_review": counts["In Review"],
            "done": counts["Done"],
            "other": counts[OTHER],
        },
        "oldest_todo_age_days": oldest_todo_age,
        "blocked": blocked,
        "stale_in_review_24h": stale_in_review,
    }


def format_human(summaries: list[dict[str, object]]) -> str:
    """Compact one-line-per-project table for stdout."""
    if not summaries:
        return "(no project boards found)"
    name_w = max(len("project"), max(len(str(s["project"])) for s in summaries))
    header_fmt = (
        f"{'project':<{name_w}}  "
        f"{'Todo':>4} {'IP':>3} {'IR':>3} {'Done':>4} {'Other':>5}  "
        f"{'oldestTodo':>10}  {'blocked':>7}  {'staleIR>24h':>11}"
    )
    sep = "─" * len(header_fmt)
    lines = [header_fmt, sep]
    for s in summaries:
        proj = str(s["project"])
        if not s["has_tickets"]:
            lines.append(f"{proj:<{name_w}}  (no tickets yet)")
            continue
        c = s["counts"]
        assert isinstance(c, dict)
        age_cell = f"{s['oldest_todo_age_days']}d"
        row = (
            f"{proj:<{name_w}}  {c['todo']:>4} {c['in_progress']:>3} "
            + f"{c['in_review']:>3} {c['done']:>4} {c['other']:>5}  "
            + f"{age_cell:>10}  {s['blocked']:>7}  {s['stale_in_review_24h']:>11}"
        )
        lines.append(row)
    return "\n".join(lines)


def resolve_data_dir(cli_arg: str | None) -> str:
    """`--data-dir` > `$CLAUDE_PLUGIN_DATA` > the canonical default."""
    if cli_arg:
        return cli_arg
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return env
    return DEFAULT_DATA_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dl-status",
        description="Cross-project dev-loop board-health summary (read-only).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON (one object per project)")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override the data dir root (default: $CLAUDE_PLUGIN_DATA or ~/.claude/plugins/data/dev-loop)",
    )
    args = parser.parse_args(argv)

    data_dir = resolve_data_dir(args.data_dir)
    projects = discover_projects(data_dir)
    summaries = [summarize_project(p) for p in projects]

    if args.json:
        print(json.dumps(summaries, indent=2, sort_keys=True))
    else:
        print(format_human(summaries))
    return 0  # status is signal, never an alarm — AC #6


if __name__ == "__main__":
    sys.exit(main())
