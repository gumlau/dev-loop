"""Read-only HTTP server: index + per-project kanban view.

Binds 127.0.0.1 only (AC #6). No auth, no external network. Re-reads board
files on each request (board state changes are rare; AC permits ≤30s cache,
but for simplicity we re-read — the data is tiny). The whole product is one
process the operator runs on demand.
"""

from __future__ import annotations

import html
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .board import COLUMNS, OTHER, Project, Ticket, discover_projects, find_project


# Brief HTML scaffolding (inline so the binary is self-contained).
_BASE_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       margin: 0; padding: 1.5rem 2rem; background: #f6f7f9; color: #1a1a1a; }
a { color: #0a66c2; text-decoration: none; }
a:hover { text-decoration: underline; }
h1 { margin: 0 0 1rem; font-size: 1.5rem; }
h2 { margin: 0 0 .6rem; font-size: 1.1rem; }
.crumb { margin-bottom: 1rem; font-size: .9rem; }
.projects { display: grid; gap: .8rem; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
.project { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
           padding: 1rem; }
.project .meta { color: #687078; font-size: .85rem; margin-top: .3rem; }
.empty { color: #888; font-style: italic; }
.board { display: grid; gap: .8rem;
         grid-template-columns: repeat(4, minmax(220px, 1fr)); }
.col { background: #fff; border: 1px solid #e3e6ea; border-radius: 8px;
       padding: .8rem; min-height: 120px; }
.col h2 { display: flex; justify-content: space-between; align-items: center; }
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
.other { margin-top: 1rem; }
.footer { color: #888; font-size: .8rem; margin-top: 2rem; }
"""


def _layout(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        f"<style>{_BASE_CSS}</style></head><body>{body}"
        "<div class='footer'>dev-loop dashboard · read-only · "
        "127.0.0.1 only</div></body></html>"
    )


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


def render_index(projects: list[Project]) -> str:
    body = ["<h1>dev-loop · projects</h1>"]
    if not projects:
        body.append("<p class='empty'>No projects found under the data dir yet.</p>")
    else:
        body.append("<div class='projects'>")
        for p in projects:
            count = len(p.tickets)
            meta = f"{count} ticket{'s' if count != 1 else ''}" if count else "no tickets yet"
            body.append(
                "<div class='project'>"
                f"<a href='/p/{html.escape(p.key)}'>{html.escape(p.key)}</a>"
                f"<div class='meta'>{meta}</div>"
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
    return _layout(f"{project.key} · dev-loop", "".join(body))


def render_not_found(detail: str = "") -> str:
    body = ["<div class='crumb'><a href='/'>← all projects</a></div>",
            "<h1>not found</h1>"]
    if detail:
        body.append(f"<p class='empty'>{html.escape(detail)}</p>")
    return _layout("not found · dev-loop", "".join(body))


def _route(path: str, data_dir: str) -> tuple[int, str]:
    if path == "/" or path == "":
        projects = discover_projects(data_dir)
        return 200, render_index(projects)
    if path.startswith("/p/"):
        key = path[len("/p/"):].rstrip("/")
        # Disallow path traversal — only flat names with no slashes.
        if not key or "/" in key or key in {"..", "."}:
            return 404, render_not_found("invalid project key")
        project = find_project(data_dir, key)
        if project is None:
            return 404, render_not_found(f"no project named {key!r}")
        return 200, render_project(project)
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
