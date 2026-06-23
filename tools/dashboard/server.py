"""Read-only HTTP server: index + per-project kanban view.

Binds 127.0.0.1 only (LOOP-1 AC #6). No auth, no external network.

LOOP-7: extends the per-project view with three live-activity surfaces
(recent activity, agent reports strip, throughput) and gives the index a
"last activity" sort. Adds a sanitized-markdown render route for the
agent report files. Still strictly read-only. A small mtime-aware cache
keeps per-request work cheap for the 1000-ticket / 90-report budget.
"""

from __future__ import annotations

import html
import os
import re
import secrets
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .board import (
    AgentReport,
    COLUMNS,
    OTHER,
    Project,
    StateMove,
    Throughput,
    Ticket,
    discover_projects,
)


# ---------------------------------------------------------------------------
# Per-data-dir mtime-aware cache.
#
# LOOP-1 AC permits a ≤30s cache. We use a tiny TTL cache keyed on data_dir
# so a flurry of requests (e.g. a browser fetching the index + a click-through
# into a project) doesn't re-walk the same trees four times. Threading-safe
# (the HTTP server is multi-threaded).
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 5.0  # well under the 30s ceiling — fresh enough to feel live
_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, list[Project]]] = {}


def _cached_discover(data_dir: str, today_key: str) -> list[Project]:
    key = (data_dir, today_key)
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < _CACHE_TTL_SECONDS:
            return hit[1]
    projects = discover_projects(data_dir, today_key=today_key)
    with _cache_lock:
        _cache[key] = (now, projects)
    return projects


def _today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _invalidate_cache() -> None:
    """Test hook — drop the cache so a seeded change is visible immediately."""
    with _cache_lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# HTML scaffolding.
# ---------------------------------------------------------------------------

_BASE_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; padding: 1.5rem 2rem; background: #f6f7f9; color: #1a1a1a; }
a { color: #0a66c2; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { margin: 0 0 1rem; font-size: 1.5rem; }
h2 { margin: 1.4rem 0 .6rem; font-size: 1.1rem; }
h3 { margin: 1rem 0 .4rem; font-size: 1rem; }
.crumb { margin-bottom: 1rem; font-size: .9rem; }
.projects { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.project { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
           padding: 1rem; }
.project .meta { color: #687078; font-size: .85rem; margin-top: .3rem; }
.project .lastact { color: #687078; font-size: .8rem; margin-top: .2rem; font-style: italic; }
.empty { color: #888; font-style: italic; }
.board { display: grid; gap: .8rem;
         grid-template-columns: repeat(4, minmax(220px, 1fr)); }
.col { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
       padding: .8rem; min-height: 120px; }
.col h2 { margin: 0 0 .6rem; display: flex; justify-content: space-between; align-items: center; }
.col h2 .count { background: #eef0f3; color: #404040; border-radius: 999px;
                 font-size: .75rem; padding: .1rem .5rem; }
.card { background: #fafbfc; border: 1px solid #e3e6ea; border-radius: 6px;
        padding: .5rem .6rem; margin-bottom: .5rem; font-size: .88rem; }
.card .title { font-weight: 600; line-height: 1.25; }
.card .id { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            color: #687078; font-size: .8rem; }
.card .row { display: flex; gap: .35rem; align-items: center; flex-wrap: wrap;
             margin-top: .35rem; }
.pill { display: inline-block; padding: .05rem .45rem; border-radius: 999px;
        font-size: .72rem; line-height: 1.4; border: 1px solid transparent; }
.pill.type-Feature { background: #e7f3ff; color: #064e9e; }
.pill.type-Bug { background: #ffe8e6; color: #8e2c2c; }
.pill.type-Improvement { background: #efe7ff; color: #4b1e8b; }
.pill.owner-pm { background: #fff3cd; color: #6e560a; }
.pill.owner-qa { background: #d9f0d3; color: #1e6e1a; }
.pill.prio-1 { background: #ffd6d6; color: #8a0a0a; }
.pill.prio-2 { background: #fff0c4; color: #7a5b0d; }
.pill.prio-3 { background: #eef0f3; color: #404040; }
.pill.prio-4 { background: #eef0f3; color: #687078; }
.pill.prio-0 { background: #eef0f3; color: #687078; }
.pill.label { background: #f0f2f5; color: #404040; border-color: #e3e6ea; }
.pill.age { background: transparent; color: #687078; }
.panel { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
         padding: .8rem 1rem; margin-top: 1rem; }
.panel h2 { margin-top: 0; }
.activity { list-style: none; padding: 0; margin: 0; }
.activity li { padding: .35rem 0; border-bottom: 1px solid #f0f1f4;
               font-size: .9rem; display: flex; gap: .6rem; flex-wrap: wrap;
               align-items: baseline; }
.activity li:last-child { border-bottom: none; }
.activity .ts { color: #687078; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                font-size: .8rem; min-width: 11ch; }
.activity .transition { color: #404040; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                        font-size: .8rem; }
.activity .agent { background: #eef0f3; padding: .05rem .4rem; border-radius: 999px;
                   font-size: .72rem; color: #404040; }
.reports-strip { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
.report-chip { background: #fafbfc; border: 1px solid #e3e6ea; border-radius: 999px;
               padding: .3rem .7rem; font-size: .85rem; display: inline-flex;
               align-items: baseline; gap: .4rem; }
.report-chip.idle { background: transparent; color: #888; font-style: italic; }
.report-chip .ago { color: #687078; font-size: .75rem; }
.report-chip .more { color: #0a66c2; font-size: .75rem; }
.throughput { display: grid; gap: .4rem; grid-template-columns: repeat(3, minmax(70px, 1fr)); }
.throughput .stat { background: #fafbfc; border: 1px solid #e3e6ea; border-radius: 6px;
                    padding: .5rem; text-align: center; }
.throughput .stat .n { font-size: 1.4rem; font-weight: 600; line-height: 1; }
.throughput .stat .label { color: #687078; font-size: .8rem; margin-top: .2rem; }
.stuck { margin-top: .6rem; color: #8a5a0a; font-size: .85rem; }
.stuck ul { margin: .3rem 0 0; padding-left: 1.2rem; }
.other { margin-top: 1rem; }
.footer { color: #888; font-size: .8rem; margin-top: 2rem; }
.report-body { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
               padding: 1rem 1.5rem; }
.report-body pre { background: #f6f7f9; padding: .6rem .8rem; border-radius: 6px;
                   overflow-x: auto; font-size: .85rem; }
.report-body code { background: #f0f1f4; padding: 0 .25rem; border-radius: 3px;
                    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                    font-size: .9em; }
.report-body p { line-height: 1.5; }
.review { background: #fafbfc; border: 1px solid #e3e6ea; border-radius: 8px;
          padding: .7rem 1rem; margin-top: 1rem; font-size: .9rem; }
.review h2 { margin: 0 0 .4rem; font-size: .95rem; }
.review .state { display: inline-block; padding: .05rem .5rem; border-radius: 999px;
                 font-size: .72rem; line-height: 1.4; border: 1px solid transparent;
                 margin-left: .35rem; vertical-align: 1px; }
.review .state.none { background: #eef0f3; color: #404040; }
.review .state.awaiting { background: #fff0c4; color: #7a5b0d; }
.review .state.acted { background: #d9f0d3; color: #1e6e1a; }
.review .nudge { color: #404040; margin: .2rem 0 .5rem; }
.review .ack { color: #404040; margin: .2rem 0 .5rem; }
.review .drop-label { color: #687078; font-size: .78rem; margin: .4rem 0 .15rem; }
.review code.drop { display: block; background: #f6f7f9; padding: .4rem .6rem;
                   border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                   font-size: .82rem; word-break: break-all; user-select: all; }
"""


def _layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{_BASE_CSS}</style></head><body>{body}"
        "<div class='footer'>dev-loop dashboard · read-only · "
        "127.0.0.1 only</div></body></html>"
    )


# ---------------------------------------------------------------------------
# Card + activity helpers.
# ---------------------------------------------------------------------------

def _card_html(t: Ticket) -> str:
    type_pill = f"<span class='pill type-{html.escape(t.type)}'>{html.escape(t.type)}</span>" if t.type else ""
    owner_pill = f"<span class='pill owner-{html.escape(t.owner)}'>{html.escape(t.owner)}</span>" if t.owner else ""
    prio_pill = (
        f"<span class='pill prio-{t.priority}'>{html.escape(t.priority_label)}</span>"
    )
    age_pill = f"<span class='pill age'>{t.age_days()}d</span>"
    label_pills = "".join(
        f"<span class='pill label'>{html.escape(l)}</span>"
        for l in t.display_labels()
    )
    return (
        "<div class='card'>"
        f"<div class='id'>{html.escape(t.id)}</div>"
        f"<div class='title'>{html.escape(t.title)}</div>"
        f"<div class='row'>{type_pill}{owner_pill}{prio_pill}{age_pill}{label_pills}</div>"
        "</div>"
    )


def _humanize_ago(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def _activity_html(moves: list[StateMove]) -> str:
    if not moves:
        return "<p class='empty'>No state-move activity recorded yet.</p>"
    items = []
    for m in moves:
        ts_short = m.timestamp[:16].replace("T", " ")  # 2026-06-22 16:01
        items.append(
            "<li>"
            f"<span class='ts'>{html.escape(ts_short)}</span>"
            f"<span class='agent'>{html.escape(m.agent)}</span>"
            f"<span class='id'>{html.escape(m.ticket_id)}</span>"
            f"<span class='transition'>{html.escape(m.from_state)} → {html.escape(m.to_state)}</span>"
            f"<span>{html.escape(m.ticket_title)}</span>"
            "</li>"
        )
    return f"<ul class='activity'>{''.join(items)}</ul>"


def _reports_strip_html(project_key: str, reports: list[AgentReport]) -> str:
    if not reports:
        return "<p class='empty'>No reports tree yet for this project.</p>"
    now = time.time()
    chips = []
    for r in reports:
        if r.is_idle_today:
            chips.append(
                f"<span class='report-chip idle'>{html.escape(r.agent)} · idle today</span>"
            )
        else:
            assert r.today_mtime is not None
            ago = _humanize_ago(max(0.0, now - r.today_mtime))
            today_key = _today_key()
            href = f"/reports/{html.escape(project_key)}/{html.escape(r.agent)}/daily/{today_key}.md"
            chips.append(
                "<span class='report-chip'>"
                f"<a href='{href}'>{html.escape(r.agent)}</a>"
                f"<span class='ago'>{html.escape(ago)}</span>"
                "</span>"
            )
        # Add weekly/monthly links when present (no <select> — pure links, no JS).
        more = []
        for name in r.weekly_files[:1]:
            href = f"/reports/{html.escape(project_key)}/{html.escape(r.agent)}/weekly/{html.escape(name)}"
            more.append(f"<a class='more' href='{href}'>weekly</a>")
        for name in r.monthly_files[:1]:
            href = f"/reports/{html.escape(project_key)}/{html.escape(r.agent)}/monthly/{html.escape(name)}"
            more.append(f"<a class='more' href='{href}'>monthly</a>")
        if more:
            chips[-1] = chips[-1].replace(
                "</span>", " · " + " · ".join(more) + "</span>", 1
            )
    return f"<div class='reports-strip'>{''.join(chips)}</div>"


def _throughput_html(tput: Throughput) -> str:
    body = (
        "<div class='throughput'>"
        f"<div class='stat'><div class='n'>{tput.filed}</div>"
        "<div class='label'>filed (7d)</div></div>"
        f"<div class='stat'><div class='n'>{tput.shipped}</div>"
        "<div class='label'>shipped (7d)</div></div>"
        f"<div class='stat'><div class='n'>{tput.verified}</div>"
        "<div class='label'>verified (7d)</div></div>"
        "</div>"
    )
    if tput.stuck:
        items = "".join(
            f"<li><span class='id'>{html.escape(t.id)}</span> "
            f"{html.escape(t.title)} <em>({html.escape(t.state)})</em></li>"
            for t in tput.stuck
        )
        body += (
            "<div class='stuck'>"
            f"Stuck for ≥3 days: {len(tput.stuck)} ticket{'s' if len(tput.stuck) != 1 else ''}"
            f"<ul>{items}</ul>"
            "</div>"
        )
    else:
        body += "<div class='stuck'>Nothing stuck ≥3 days. ✓</div>"
    return body


# ---------------------------------------------------------------------------
# Pages.
# ---------------------------------------------------------------------------

def render_index(projects: list[Project]) -> str:
    body = ["<h1>dev-loop · projects</h1>"]
    if not projects:
        body.append("<p class='empty'>No projects found under the data dir yet.</p>")
    else:
        # AC #4: sort by newest "last activity" first. Projects with no activity
        # sink to the bottom.
        sorted_projects = sorted(
            projects,
            key=lambda p: (p.last_activity_mtime or 0.0),
            reverse=True,
        )
        now = time.time()
        body.append("<div class='projects'>")
        for p in sorted_projects:
            count = len(p.tickets)
            meta = f"{count} ticket{'s' if count != 1 else ''}" if count else "no tickets yet"
            if p.last_activity_mtime is not None:
                lastact = f"last activity: {_humanize_ago(max(0.0, now - p.last_activity_mtime))}"
            else:
                lastact = "last activity: never"
            blocked_line = ""
            if p.blocked_count > 0:
                blocked_line = (
                    f"<div class='meta blocked'>{p.blocked_count} blocked</div>"
                )
            body.append(
                "<div class='project'>"
                f"<a href='/p/{html.escape(p.key)}'>{html.escape(p.key)}</a>"
                f"<div class='meta'>{meta}</div>"
                f"{blocked_line}"
                f"<div class='lastact'>{html.escape(lastact)}</div>"
                "</div>"
            )
        body.append("</div>")
    return _layout("dev-loop dashboard", "".join(body))


def render_project(project: Project) -> str:
    by_col = project.by_column()
    body = [
        "<div class='crumb'><a href='/'>← all projects</a></div>",
        f"<h1>{html.escape(project.key)}</h1>",
    ]

    # --- Kanban board (LOOP-1) -----------------------------------------------
    body.append("<div class='board'>")
    for col in COLUMNS:
        cards = by_col.get(col, [])
        body.append(
            f"<div class='col' data-column='{html.escape(col)}'>"
            f"<h2>{html.escape(col)} <span class='count'>{len(cards)}</span></h2>"
        )
        for t in cards:
            body.append(_card_html(t))
        body.append("</div>")
    body.append("</div>")
    other = by_col.get(OTHER, [])
    if other:
        body.append(
            "<div class='other'>"
            f"<h2>Other ({len(other)}) · Canceled / Duplicate / Backlog</h2>"
            "<div class='board' style='grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));'>"
        )
        for t in other:
            body.append(_card_html(t))
        body.append("</div></div>")

    # --- LOOP-7 panels -------------------------------------------------------
    body.append("<div class='panel'>")
    body.append("<h2>Recent activity</h2>")
    body.append(_activity_html(project.recent_activity()))
    body.append("</div>")

    body.append("<div class='panel'>")
    body.append("<h2>Agent reports</h2>")
    body.append(_reports_strip_html(project.key, project.agent_reports))
    body.append("</div>")

    body.append("<div class='panel'>")
    body.append("<h2>Throughput</h2>")
    body.append(_throughput_html(project.throughput()))
    body.append("</div>")

    return _layout(f"{project.key} · dev-loop", "".join(body))


def render_not_found(detail: str = "") -> str:
    body = ["<div class='crumb'><a href='/'>← all projects</a></div>",
            "<h1>not found</h1>"]
    if detail:
        body.append(f"<p class='empty'>{html.escape(detail)}</p>")
    return _layout("not found · dev-loop", "".join(body))


# ---------------------------------------------------------------------------
# Markdown render route — strictly read-only, strictly whitelisted.
# ---------------------------------------------------------------------------

# Filenames must match the dated grammar (conventions §22). Anything else 404s.
_DAILY_FN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_WEEKLY_FN = re.compile(r"^\d{4}-W\d{2}\.md$")
_MONTHLY_FN = re.compile(r"^\d{4}-\d{2}\.md$")

_PERIOD_RE = {"daily": _DAILY_FN, "weekly": _WEEKLY_FN, "monthly": _MONTHLY_FN}

# Agent dir names are strict — only the known skill names. This rules out
# arbitrary subdir traversal even if the period dir is omitted.
_KNOWN_AGENTS = {
    "pm-agent", "qa-agent", "dev-agent", "sweep-agent",
    "reflect-agent", "ops-agent", "architect-agent", "signal-agent",
}

# Markdown bits we render. Everything else is escaped to text.
_FENCED_RE = re.compile(r"```([a-zA-Z0-9_+-]*)\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC_RE = re.compile(r"(?<![*_])\*([^*\n]+)\*(?!\*)")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")


def render_markdown(src: str) -> str:
    """Tiny safe markdown renderer. Operator-trusted input, but we still
    escape everything first and only re-introduce the constructs we recognize.
    """
    # 1. Extract fenced code blocks first — their contents are NOT processed
    # further. Use a per-render unique token so user-controlled bytes in `src`
    # cannot alias the placeholder grammar (LOOP-11): a deterministic sentinel
    # like `\x00FENCED<n>\x00` was both crashable (out-of-range index →
    # IndexError) and aliasable (in-range index → silent substitution of
    # another block's content). The random token defeats both vectors.
    placeholders: list[str] = []
    token = secrets.token_hex(16)
    sentinel_prefix = f"\x00FENCED-{token}-"
    sentinel_suffix = "\x00"

    def _stash_fenced(m: re.Match[str]) -> str:
        code = m.group(2)
        rendered = f"<pre><code>{html.escape(code)}</code></pre>"
        placeholders.append(rendered)
        return f"{sentinel_prefix}{len(placeholders) - 1}{sentinel_suffix}"

    work = _FENCED_RE.sub(_stash_fenced, src)

    # 2. Escape everything.
    work = html.escape(work)

    # 3. Headings (after escape, so the # is literal already).
    def _heading(m: re.Match[str]) -> str:
        level = min(6, max(1, len(m.group(1))))
        # Headings inside the rendered report use h3+ to nest below the page H1.
        level = min(6, level + 2)
        return f"<h{level}>{m.group(2).strip()}</h{level}>"

    work = _HEADING_RE.sub(_heading, work)

    # 4. Inline code (do this before bold/italic so `**` inside backticks is preserved).
    work = _INLINE_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", work)

    # 5. Bold + italic.
    work = _BOLD_RE.sub(r"<strong>\1</strong>", work)
    work = _ITALIC_RE.sub(r"<em>\1</em>", work)

    # 6. Links — http(s) only, no scheme injection.
    work = _LINK_RE.sub(r'<a href="\2" rel="noopener noreferrer">\1</a>', work)

    # 7. Paragraphs — split on blank lines, wrap leftovers in <p> unless they
    # already look like a block element (start with <h or <pre or are a placeholder).
    out_blocks = []
    for block in re.split(r"\n\s*\n", work):
        b = block.strip()
        if not b:
            continue
        if b.startswith("<h") or b.startswith("<pre") or sentinel_prefix in b:
            out_blocks.append(b)
        else:
            out_blocks.append(f"<p>{b}</p>")
    rendered = "\n".join(out_blocks)

    # 8. Restore fenced placeholders. Only this render's tokenized sentinels
    # can match; user bytes carrying `\x00FENCED<n>\x00` are now literal text
    # (escaped in step 2). Bounds check stays as defense in depth.
    sentinel_re = re.compile(
        rf"\x00FENCED-{re.escape(token)}-(\d+)\x00"
    )

    def _restore(m: re.Match[str]) -> str:
        idx = int(m.group(1))
        if 0 <= idx < len(placeholders):
            return placeholders[idx]
        return m.group(0)

    return sentinel_re.sub(_restore, rendered)


def _review_state(report_path: str) -> tuple[str, str, float | None]:
    """LOOP-12 — derive the 点评 panel state from sibling file metadata.

    Returns ``(state, drop_path, acted_mtime)`` where ``state`` is one of
    ``"none"`` / ``"awaiting"`` / ``"acted"`` per conventions §22. Purely
    existence + mtime; never reads the sidecar content (sidecars are
    machine-owned).
    """
    drop_path = report_path + ".review.md"
    acted_path = report_path + ".review.acted"
    review_exists = os.path.isfile(drop_path)
    acted_exists = os.path.isfile(acted_path)
    # LOOP-17 — the sibling may vanish between `isfile` and `getmtime`. Treat a
    # failed stat as "gone" and fold the post-race truth back into the
    # three-state machine, rather than letting the FileNotFoundError escape
    # `_review_state → _review_panel_html → _serve_report → _route → do_GET`
    # (none of which wrap this call) and kill the request thread.
    try:
        review_mtime = os.path.getmtime(drop_path) if review_exists else None
    except OSError:
        review_mtime = None
    try:
        acted_mtime = os.path.getmtime(acted_path) if acted_exists else None
    except OSError:
        acted_mtime = None
    review_exists = review_exists and review_mtime is not None
    acted_exists = acted_exists and acted_mtime is not None
    if not review_exists and not acted_exists:
        return "none", drop_path, None
    if review_exists and (
        not acted_exists or (review_mtime or 0.0) > (acted_mtime or 0.0)
    ):
        return "awaiting", drop_path, acted_mtime
    # acted_exists and (no review_md, or acted is at least as new)
    return "acted", drop_path, acted_mtime


def _review_panel_html(report_path: str, agent: str) -> str:
    state, drop_path, acted_mtime = _review_state(report_path)
    header = (
        "<h2>Operator review (点评) "
        f"<span class='state {state}'>{html.escape(state)}</span></h2>"
    )
    if state == "none":
        msg = (
            "<p class='nudge'>Drop a free-form <code>*.review.md</code> sibling "
            "to critique this report; the agent will distill it into a "
            "<code>lessons.md</code> rule on its next fire.</p>"
        )
    elif state == "awaiting":
        msg = (
            "<p class='nudge'>Critique on file — "
            "awaiting next agent fire.</p>"
        )
    else:  # acted
        ts = ""
        if acted_mtime is not None:
            ts = datetime.fromtimestamp(acted_mtime).strftime("%Y-%m-%d %H:%M")
        msg = (
            "<p class='ack'>Acted by "
            f"<code>{html.escape(agent)}</code>"
            + (f" at {html.escape(ts)}" if ts else "")
            + ".</p>"
        )
    drop = (
        "<div class='drop-label'>Drop path:</div>"
        f"<code class='drop'>{html.escape(drop_path)}</code>"
    )
    return f"<div class='review'>{header}{msg}{drop}</div>"


def render_report_page(
    project_key: str,
    agent: str,
    period: str,
    filename: str,
    body_md: str,
    mtime: float | None,
    report_path: str | None = None,
) -> str:
    ago = ""
    if mtime is not None:
        ago = _humanize_ago(max(0.0, time.time() - mtime))
    crumb = (
        "<div class='crumb'>"
        f"<a href='/'>← all projects</a> · "
        f"<a href='/p/{html.escape(project_key)}'>{html.escape(project_key)}</a>"
        "</div>"
    )
    rendered = render_markdown(body_md)
    meta = (
        f"<div class='lastact'>{html.escape(agent)} · {html.escape(period)} · "
        f"{html.escape(filename)}"
        + (f" · {html.escape(ago)}" if ago else "")
        + "</div>"
    )
    review_panel = ""
    if report_path is not None:
        review_panel = _review_panel_html(report_path, agent)
    body = (
        f"{crumb}"
        f"<h1>{html.escape(filename)}</h1>"
        f"{meta}"
        f"<div class='report-body'>{rendered}</div>"
        f"{review_panel}"
    )
    return _layout(f"{filename} · {project_key} · dev-loop", body)


def _resolve_report_path(
    data_dir: str, project_key: str, agent: str, period: str, filename: str,
) -> str | None:
    """Strict path resolution. Returns absolute path inside the reports tree,
    or None if any check fails.
    """
    # 1. Whitelist each segment — no `..`, no slashes, no empty.
    for seg in (project_key, agent, period, filename):
        if not seg or "/" in seg or "\\" in seg or seg in {".", ".."}:
            return None
    if agent not in _KNOWN_AGENTS:
        return None
    pattern = _PERIOD_RE.get(period)
    if pattern is None or not pattern.match(filename):
        return None

    # 2. Build the path. The expected report container.
    project_root = os.path.realpath(os.path.join(data_dir, project_key))
    reports_root = os.path.realpath(os.path.join(project_root, "reports"))
    candidate = os.path.realpath(os.path.join(
        project_root, "reports", agent, period, filename
    ))
    # 3. Ensure the resolved path stays under the reports tree.
    if not candidate.startswith(reports_root + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


def _serve_report(data_dir: str, project_key: str, agent: str, period: str, filename: str) -> tuple[int, str]:
    path = _resolve_report_path(data_dir, project_key, agent, period, filename)
    if path is None:
        return 404, render_not_found("report not found")
    try:
        with open(path, "r", encoding="utf-8") as f:
            body = f.read()
        mtime: float | None = os.path.getmtime(path)
    except (OSError, UnicodeDecodeError):
        return 404, render_not_found("report not readable")
    return 200, render_report_page(
        project_key, agent, period, filename, body, mtime, report_path=path,
    )


# ---------------------------------------------------------------------------
# Router.
# ---------------------------------------------------------------------------

def _route(path: str, data_dir: str) -> tuple[int, str]:
    if path == "/" or path == "":
        projects = _cached_discover(data_dir, _today_key())
        return 200, render_index(projects)
    if path.startswith("/p/"):
        key = path[len("/p/"):].rstrip("/")
        if not key or "/" in key or key in {"..", "."}:
            return 404, render_not_found("invalid project key")
        # Use the cache (it discovers ALL projects, then we find ours).
        for p in _cached_discover(data_dir, _today_key()):
            if p.key == key:
                return 200, render_project(p)
        return 404, render_not_found(f"no project named {key!r}")
    if path.startswith("/reports/"):
        parts = path[len("/reports/"):].split("/")
        if len(parts) != 4:
            return 404, render_not_found("invalid report path")
        project_key, agent, period, filename = parts
        return _serve_report(data_dir, project_key, agent, period, filename)
    return 404, render_not_found(f"unknown path {path!r}")


def make_handler(data_dir: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        # Silence the per-request stderr log so the launch line stays the only
        # noise on stdout. (The base class logs to stderr by default.)
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802 (stdlib API)
            status, body = _route(self.path, data_dir)
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def default_data_dir() -> str:
    return os.environ.get(
        "DEVLOOP_DATA_DIR",
        os.path.expanduser("~/.claude/plugins/data/dev-loop"),
    )


def run(host: str = "127.0.0.1", port: int = 5173, data_dir: str | None = None) -> None:
    """Block-running server entrypoint."""
    data_dir = data_dir or default_data_dir()
    handler = make_handler(data_dir)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"dev-loop dashboard running at http://{host}:{port}  (data dir: {data_dir})",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down", flush=True)
    finally:
        server.server_close()
