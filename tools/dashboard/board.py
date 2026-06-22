"""Parse local dev-loop board files (the §18 file-board format).

Pure stdlib. Reads `<data_dir>/<project>/board/tickets/*.md`, extracts each
ticket's YAML frontmatter, and returns a structured view the renderer can group
by column. Strictly read-only — never writes back.

LOOP-7: also parses each ticket's `## Comments` section for state-move events,
walks `<project>/reports/<agent>/{daily,weekly,monthly}/` to surface agent
reports, derives 7-day throughput counts, and exposes a per-project "last
activity" mtime for the index sort.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

# §3 state names — used to anchor the state-move regex.
_STATE_NAMES = ["Backlog", "Todo", "In Progress", "In Review", "Done", "Canceled", "Duplicate"]
_STATE_ALT = "|".join(re.escape(s) for s in _STATE_NAMES)

# A comment header in the §18 ticket layout:
#   ### 2026-06-18T11:02:00Z — dev (run a1b2)
# The em-dash is U+2014. Agent is whatever sits between the em-dash and the
# next whitespace / `(` — typically `dev` / `pm` / `qa` / `sweep` / `reflect`.
_COMMENT_HEADER = re.compile(
    r"^###\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s+—\s+(?P<agent>[^\s(]+)",
    re.MULTILINE,
)
# State-move line in a comment body — uses the canonical → arrow (U+2192).
_STATE_MOVE = re.compile(
    rf"state:\s*(?P<from>{_STATE_ALT})\s*→\s*(?P<to>{_STATE_ALT})",
)

# Dated-report grammar (conventions §22 — anchored, never a bare `*.md` glob,
# so `*.review.md` siblings stay excluded from the newest-marker scans).
_DAILY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_WEEKLY_RE = re.compile(r"^\d{4}-W\d{2}\.md$")
_MONTHLY_RE = re.compile(r"^\d{4}-\d{2}\.md$")


@dataclass
class StateMove:
    """One state transition extracted from a ticket's `## Comments` section."""
    timestamp: str       # ISO Z timestamp from the comment header
    ticket_id: str
    ticket_title: str
    from_state: str
    to_state: str
    agent: str           # e.g. "dev", "pm", "qa"


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
    updated: str         # ISO timestamp string (frontmatter `updated:`)
    path: str            # absolute file path (for diagnostics)
    state_moves: list[StateMove] = field(default_factory=list)

    def display_labels(self) -> list[str]:
        """Labels worth showing on the card (AC #4)."""
        return [l for l in self.labels if l not in _ROUTING_LABELS]

    def age_days(self, now: datetime | None = None) -> int:
        """Whole days since `created`. Zero if parse fails (rather than crash)."""
        return _days_since(self.created, now)

    def last_move_timestamp(self) -> str:
        """The most recent state-move comment timestamp, or `created:` as a fallback."""
        if self.state_moves:
            return max(m.timestamp for m in self.state_moves)
        return self.created

    @property
    def column(self) -> str:
        return self.state if self.state in COLUMNS else OTHER

    @property
    def priority_label(self) -> str:
        return {1: "Urgent", 2: "High", 3: "Medium", 4: "Low", 0: "None"}.get(
            self.priority, "None"
        )


@dataclass
class AgentReport:
    """One agent's reports tree under <project>/reports/<agent>/."""
    agent: str                         # e.g. "pm-agent"
    today_mtime: float | None          # mtime of daily/<today>.md, else None
    weekly_files: list[str]            # validated dated filenames (basename)
    monthly_files: list[str]           # validated dated filenames (basename)

    @property
    def is_idle_today(self) -> bool:
        return self.today_mtime is None


@dataclass
class Throughput:
    """7-day throughput slice for a project (AC #3)."""
    filed: int          # tickets with `created:` inside the window
    shipped: int        # state-moves into `In Review` inside the window
    verified: int       # state-moves into `Done` inside the window
    stuck: list[Ticket] # non-terminal tickets with no state move in `stuck_threshold` days


@dataclass
class Project:
    key: str
    board_dir: str
    project_root: str    # parent of board_dir — where `reports/` lives
    tickets: list[Ticket] = field(default_factory=list)
    agent_reports: list[AgentReport] = field(default_factory=list)
    last_activity_mtime: float | None = None

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

    def recent_activity(self, limit: int = 20) -> list[StateMove]:
        """All state moves across all tickets, newest first, capped at `limit`."""
        events: list[StateMove] = []
        for t in self.tickets:
            events.extend(t.state_moves)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def throughput(
        self,
        window_days: int = 7,
        stuck_threshold: int = 3,
        now: datetime | None = None,
    ) -> Throughput:
        now = now or datetime.now(timezone.utc)
        win_start = now - timedelta(days=window_days)
        filed = 0
        shipped = 0
        verified = 0
        for t in self.tickets:
            ts = _parse_iso(t.created)
            if ts is not None and ts >= win_start:
                filed += 1
            for move in t.state_moves:
                mts = _parse_iso(move.timestamp)
                if mts is None or mts < win_start:
                    continue
                if move.to_state == "In Review":
                    shipped += 1
                elif move.to_state == "Done":
                    verified += 1
        stuck = self._stuck_tickets(stuck_threshold, now)
        return Throughput(filed=filed, shipped=shipped, verified=verified, stuck=stuck)

    def _stuck_tickets(self, threshold_days: int, now: datetime) -> list[Ticket]:
        """Non-terminal tickets whose last state move is ≥ `threshold_days` ago.

        Terminal states (Done/Canceled/Duplicate) are NOT stuck — they finished.
        """
        cutoff = now - timedelta(days=threshold_days)
        terminal = {"Done", "Canceled", "Duplicate"}
        out = []
        for t in self.tickets:
            if t.state in terminal:
                continue
            last = _parse_iso(t.last_move_timestamp())
            if last is not None and last < cutoff:
                out.append(t)
        # Newest-first by ID for stable rendering.
        out.sort(key=lambda t: t.id)
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


def parse_state_moves(text: str, ticket_id: str, ticket_title: str) -> list[StateMove]:
    """Extract state-move events from a ticket's `## Comments` section.

    Each `### <ts> — <agent>` comment block is scanned for a `state: X → Y` line.
    If found, one StateMove is emitted. Comments without a state line are
    activity but not transitions, so they're ignored here.
    """
    # Tolerate `## Comments` at the very start (no leading newline) too —
    # callers pass either whole-file text (where the header is after a \n) or
    # a slice that starts at the section.
    idx = text.find("\n## Comments")
    if idx < 0:
        if text.startswith("## Comments"):
            idx = 0
        else:
            return []
    section = text[idx:]
    headers = list(_COMMENT_HEADER.finditer(section))
    moves: list[StateMove] = []
    for i, h in enumerate(headers):
        body_start = h.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(section)
        body = section[body_start:body_end]
        sm = _STATE_MOVE.search(body)
        if sm:
            moves.append(StateMove(
                timestamp=h.group("ts"),
                ticket_id=ticket_id,
                ticket_title=ticket_title,
                from_state=sm.group("from"),
                to_state=sm.group("to"),
                agent=h.group("agent"),
            ))
    return moves


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
    ticket_id = str(fm.get("id"))
    ticket_title = str(fm.get("title") or "")
    moves = parse_state_moves(text, ticket_id, ticket_title)
    return Ticket(
        id=ticket_id,
        title=ticket_title,
        type=str(fm.get("type") or ""),
        state=str(fm.get("state") or ""),
        owner=str(fm.get("owner") or ""),
        priority=priority,
        labels=[str(l) for l in labels],
        created=str(fm.get("created") or ""),
        updated=str(fm.get("updated") or ""),
        path=path,
        state_moves=moves,
    )


# --- Reports walker ----------------------------------------------------------

def list_agent_reports(project_root: str, today_key: str) -> list[AgentReport]:
    """Scan `<project_root>/reports/<agent>/{daily,weekly,monthly}/` per agent.

    `today_key` is the operator's local-date key (e.g. `2026-06-22`) — used to
    decide whether each agent has a daily report for today.
    """
    reports_dir = os.path.join(project_root, "reports")
    if not os.path.isdir(reports_dir):
        return []
    out: list[AgentReport] = []
    for agent in sorted(os.listdir(reports_dir)):
        agent_dir = os.path.join(reports_dir, agent)
        if not os.path.isdir(agent_dir):
            continue
        today_path = os.path.join(agent_dir, "daily", f"{today_key}.md")
        if os.path.isfile(today_path):
            try:
                today_mtime: float | None = os.path.getmtime(today_path)
            except OSError:
                today_mtime = None
        else:
            today_mtime = None
        weekly = _list_dated(os.path.join(agent_dir, "weekly"), _WEEKLY_RE)
        monthly = _list_dated(os.path.join(agent_dir, "monthly"), _MONTHLY_RE)
        out.append(AgentReport(
            agent=agent,
            today_mtime=today_mtime,
            weekly_files=weekly,
            monthly_files=monthly,
        ))
    return out


def _list_dated(dirpath: str, pattern: re.Pattern[str]) -> list[str]:
    """Return basenames matching the dated grammar, newest-key first."""
    if not os.path.isdir(dirpath):
        return []
    try:
        names = [n for n in os.listdir(dirpath) if pattern.match(n)]
    except OSError:
        return []
    names.sort(reverse=True)
    return names


def _project_last_activity(project_root: str) -> float | None:
    """Max mtime across this project's tickets/*.md + reports/**/*.md.

    Walked once per project (~O(N files)). For the worst-case AC budget (1000
    tickets + 90 daily reports per agent across 4 agents) this is well under
    500ms — `os.scandir` recursive walk is ~50µs/file on disk.
    """
    latest: float | None = None
    # tickets/
    tickets_dir = os.path.join(project_root, "board", "tickets")
    if os.path.isdir(tickets_dir):
        try:
            with os.scandir(tickets_dir) as it:
                for de in it:
                    if de.is_file() and de.name.endswith(".md"):
                        try:
                            m = de.stat().st_mtime
                        except OSError:
                            continue
                        if latest is None or m > latest:
                            latest = m
        except OSError:
            pass
    # reports/<agent>/<period>/<file>.md
    reports_dir = os.path.join(project_root, "reports")
    if os.path.isdir(reports_dir):
        for root, _dirs, files in os.walk(reports_dir):
            for name in files:
                if not name.endswith(".md"):
                    continue
                try:
                    m = os.path.getmtime(os.path.join(root, name))
                except OSError:
                    continue
                if latest is None or m > latest:
                    latest = m
    return latest


# --- Project discovery -------------------------------------------------------

def discover_projects(data_dir: str, today_key: str | None = None) -> list[Project]:
    """Scan `<data_dir>/*/board/tickets/` for project boards.

    Per AC #2 (LOOP-1), a project with `board/` but no tickets is listed as
    "no tickets yet" rather than hidden. LOOP-7 extends this to also surface
    reports + activity + last-activity mtime.

    `today_key` is the local `YYYY-MM-DD` key for "today" (used by the reports
    strip). Defaults to the system's local date — overridable for tests.
    """
    if today_key is None:
        today_key = datetime.now().strftime("%Y-%m-%d")
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
        agent_reports = list_agent_reports(proj_dir, today_key)
        last_activity = _project_last_activity(proj_dir)
        projects.append(Project(
            key=entry,
            board_dir=board_dir,
            project_root=proj_dir,
            tickets=tickets,
            agent_reports=agent_reports,
            last_activity_mtime=last_activity,
        ))
    return projects


def find_project(data_dir: str, key: str, today_key: str | None = None) -> Project | None:
    for p in discover_projects(data_dir, today_key=today_key):
        if p.key == key:
            return p
    return None


# --- Date helpers ------------------------------------------------------------

def _parse_iso(s: str) -> datetime | None:
    """Tolerant ISO-8601 parse. Returns aware UTC datetime, or None."""
    if not s:
        return None
    try:
        ts = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _days_since(iso_ts: str, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    ts = _parse_iso(iso_ts)
    if ts is None:
        return 0
    return max(0, (now - ts).days)
