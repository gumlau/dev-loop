"""Parse local dev-loop board files (the §18 file-board format).

Pure stdlib. Reads `<data_dir>/<project>/board/tickets/*.md`, extracts each
ticket's YAML frontmatter, and returns a structured view the renderer can group
by column. Strictly read-only — never writes back.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from glob import glob
from typing import Any


# Labels the renderer should hide on the card chips. These are the marker
# (`dev-loop`), the type labels (already shown as the "type" pill), the owner
# labels (shown separately), and the workflow-signal labels — i.e. every label
# defined by conventions §4 EXCEPT the additive sub-types (`coverage`,
# `edge-case`, `tech-debt`, `signal`, `incident`) and the multi-repo `repo:*`
# target. Those are the "non-routing labels" AC #4 asks the card to show.
_ROUTING_LABELS = {
    "dev-loop",
    "Bug", "Feature", "Improvement",
    "pm", "qa",
    "blocked", "needs-pm", "needs-qa",
}

# The four canonical kanban columns (AC #3).
COLUMNS = ["Todo", "In Progress", "In Review", "Done"]
# Everything else (Canceled / Duplicate / Backlog) lands here.
OTHER = "Other"


@dataclass
class Ticket:
    id: str
    title: str
    type: str            # Feature | Bug | Improvement | (other)
    state: str           # §3 state name
    owner: str           # pm | qa | ""
    priority: int        # 1..4 or 0
    labels: list[str]    # the FULL set; the renderer filters routing labels
    created: str         # ISO timestamp string
    path: str            # absolute file path (for diagnostics)

    def display_labels(self) -> list[str]:
        """Labels worth showing on the card (AC #4)."""
        return [l for l in self.labels if l not in _ROUTING_LABELS]

    def age_days(self, now: datetime | None = None) -> int:
        """Whole days since `created`. Zero if parse fails (rather than crash)."""
        now = now or datetime.now(timezone.utc)
        try:
            # Accept the trailing 'Z' (Python <3.11's fromisoformat won't).
            s = self.created.replace("Z", "+00:00")
            ts = datetime.fromisoformat(s)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = now - ts
            return max(0, delta.days)
        except (ValueError, TypeError):
            return 0

    @property
    def column(self) -> str:
        return self.state if self.state in COLUMNS else OTHER

    @property
    def priority_label(self) -> str:
        return {1: "Urgent", 2: "High", 3: "Medium", 4: "Low", 0: "None"}.get(
            self.priority, "None"
        )


@dataclass
class Project:
    key: str
    board_dir: str
    tickets: list[Ticket] = field(default_factory=list)

    @property
    def has_tickets(self) -> bool:
        return bool(self.tickets)

    def by_column(self) -> dict[str, list[Ticket]]:
        out: dict[str, list[Ticket]] = {c: [] for c in COLUMNS}
        out[OTHER] = []
        for t in self.tickets:
            out[t.column].append(t)
        # Stable sort: highest priority first (lowest numeric, except 0=None last), then ID.
        def keyfn(t: Ticket) -> tuple[int, str]:
            return (99 if t.priority == 0 else t.priority, t.id)
        for col in out:
            out[col].sort(key=keyfn)
        return out


# --- Frontmatter parser ------------------------------------------------------
# Conventions §18 specifies one file per ticket: YAML frontmatter between `---`
# markers, then the body, then a `## Comments` section. We need only a tiny
# subset of YAML (no nested maps, no multi-line strings, no quoted keys), so
# this parser is intentionally small — bringing PyYAML in would break "zero
# external dependencies" (AC: works offline; this product is a Claude Code
# plugin with no Python deps to begin with).

_FM_FENCE = re.compile(r"^---\s*$")


def _parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s == "" or s.lower() == "null":
        return None
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip('"').strip("'") for p in inner.split(",") if p.strip()]
    # Strip surrounding quotes if present.
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # Bare integer?
    if s.lstrip("-").isdigit():
        try:
            return int(s)
        except ValueError:
            pass
    return s


def parse_frontmatter(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    if not lines or not _FM_FENCE.match(lines[0]):
        return {}
    out: dict[str, Any] = {}
    for line in lines[1:]:
        if _FM_FENCE.match(line):
            break
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, rhs = line.partition(":")
        out[key.strip()] = _parse_scalar(rhs)
    return out


def load_ticket(path: str) -> Ticket | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        # A non-UTF-8 file (backup-restored, Windows-edited, anything not written
        # as UTF-8) raises UnicodeDecodeError, NOT OSError. Treat it like an
        # unreadable file — skip the ticket, keep the dashboard alive for the
        # rest of the board. Fail-closing one card is fine; fail-closing every
        # project's dashboard because one card has a bad byte is not (LOOP-6).
        return None
    fm = parse_frontmatter(text)
    if not fm.get("id"):
        return None
    labels = fm.get("labels") or []
    if not isinstance(labels, list):
        labels = [str(labels)]
    raw_priority = fm.get("priority")
    if isinstance(raw_priority, int):
        priority = raw_priority
    else:
        try:
            priority = int(str(raw_priority))
        except (TypeError, ValueError):
            priority = 0
    return Ticket(
        id=str(fm.get("id")),
        title=str(fm.get("title") or ""),
        type=str(fm.get("type") or ""),
        state=str(fm.get("state") or ""),
        owner=str(fm.get("owner") or ""),
        priority=priority,
        labels=[str(l) for l in labels],
        created=str(fm.get("created") or ""),
        path=path,
    )


# --- Project discovery -------------------------------------------------------

def discover_projects(data_dir: str) -> list[Project]:
    """Scan `<data_dir>/*/board/tickets/` for project boards.

    Per AC #2, a project with `board/` but no tickets is listed as "no tickets
    yet" rather than hidden. We treat the presence of a `board/` subdirectory
    as the project signal, not the presence of tickets.
    """
    projects: list[Project] = []
    if not os.path.isdir(data_dir):
        return projects
    for entry in sorted(os.listdir(data_dir)):
        proj_dir = os.path.join(data_dir, entry)
        board_dir = os.path.join(proj_dir, "board")
        if not os.path.isdir(board_dir):
            continue
        tickets_dir = os.path.join(board_dir, "tickets")
        tickets: list[Ticket] = []
        if os.path.isdir(tickets_dir):
            for fp in sorted(glob(os.path.join(tickets_dir, "*.md"))):
                t = load_ticket(fp)
                if t is not None:
                    tickets.append(t)
        projects.append(Project(key=entry, board_dir=board_dir, tickets=tickets))
    return projects


def find_project(data_dir: str, key: str) -> Project | None:
    for p in discover_projects(data_dir):
        if p.key == key:
            return p
    return None
