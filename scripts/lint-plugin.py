#!/usr/bin/env python3
"""Plugin self-lint — the typecheck gate for the dev-loop plugin (LOOP-4).

Wired from `build.typecheck` for the dev-loop project. Pure stdlib (Python 3),
no external deps. Exits 0 if clean, non-zero on any finding.

Output: one finding per line — `<rule>: <path>:<line> <message>` — so a future
CI/CD can grep it. A trailing summary line is written to stderr.

Rules (one per AC in LOOP-4):

  json-integrity      every .json under .claude-plugin/ + config/ + scripts/ +
                      tools/ parses cleanly
  skill-frontmatter   every skills/*/SKILL.md has a YAML frontmatter block with
                      a non-empty `name:` (matching the dir name) and a
                      non-empty `description:`
  section-refs        every `§<N>` in references/conventions.md and
                      skills/*/SKILL.md resolves to a `## <N>.` heading in
                      references/conventions.md
  md-links            every relative `[text](path)` link in README.md,
                      CHANGELOG.md, docs/*.md, references/conventions.md, and
                      skills/*/SKILL.md points at an existing file/dir
  lessons-skeleton    the canonical lessons.md skeleton (in
                      skills/init/SKILL.md) carries every section listed in
                      the `## 14. Lessons file` Layout block of conventions.md
  agent-consistency   every agent named in conventions §1's Topology table is
                      mentioned in README.md AND CHANGELOG.md
  shell-example-syntax  fenced shell examples in docs do not put a `--flag`
                      immediately after a `VAR=value` env prefix (bash treats
                      the flag as the command and exits 127 — LOOP-9)
  tmux-session-name-consistency  docs do not reference a bare
                      `tmux ... -t dev-loop` session — the launcher only
                      creates `dev-loop-<project>` sessions, so a bare name
                      is stale post-LOOP-2 doc drift (LOOP-13)

§17 boundary: this script is a READ-ONLY detector. It NEVER edits
references/conventions.md or any skills/*/SKILL.md — findings about those
files are reported and surfaced as proposals for the operator.

Run on the real repo:
  python3 scripts/lint-plugin.py

Run against a fixture (used by tests/test_lint_plugin.py):
  python3 scripts/lint-plugin.py --root tests/fixtures/lint-bad/<scenario>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Callable

Finding = str


# ---------- helpers ----------

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return p.read_text(encoding="utf-8", errors="replace")


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


# ---------- rules ----------

def check_json_integrity(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for sub in (".claude-plugin", "config", "scripts", "tools"):
        d = root / sub
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.json")):
            try:
                json.loads(_read_text(f))
            except json.JSONDecodeError as e:
                findings.append(
                    f"json-integrity: {_rel(f, root)}:{e.lineno} {e.msg}"
                )
            except OSError as e:
                findings.append(f"json-integrity: {_rel(f, root)}:0 {e}")
    return findings


_SKILL_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\s*\n", re.DOTALL)
_FM_NAME = re.compile(r"^name:\s*(\S[^\n]*?)\s*$", re.MULTILINE)
# Match description: either inline (`description: foo`) OR block scalar
# (`description: >-\n  foo\n  bar`) — accept either as long as it's non-empty.
_FM_DESC_INLINE = re.compile(r"^description:\s*(\S[^\n]*?)\s*$", re.MULTILINE)
_FM_DESC_BLOCK = re.compile(
    r"^description:\s*[>|][+-]?\s*\n((?:[ \t]+\S[^\n]*\n?)+)", re.MULTILINE
)


def check_skill_frontmatter(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    skills_dir = root / "skills"
    if not skills_dir.exists():
        return findings
    for sk_dir in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        sk_file = sk_dir / "SKILL.md"
        if not sk_file.exists():
            findings.append(
                f"skill-frontmatter: {_rel(sk_dir, root)}:0 missing SKILL.md"
            )
            continue
        text = _read_text(sk_file)
        m = _SKILL_FRONTMATTER.match(text)
        if not m:
            findings.append(
                f"skill-frontmatter: {_rel(sk_file, root)}:1 "
                "missing YAML frontmatter block"
            )
            continue
        fm = m.group(1)
        name_m = _FM_NAME.search(fm)
        if not name_m or not name_m.group(1).strip():
            findings.append(
                f"skill-frontmatter: {_rel(sk_file, root)}:1 "
                "missing or empty `name:` field"
            )
        elif name_m.group(1).strip() != sk_dir.name:
            findings.append(
                f"skill-frontmatter: {_rel(sk_file, root)}:1 "
                f"name '{name_m.group(1).strip()}' != dir '{sk_dir.name}'"
            )
        desc_inline = _FM_DESC_INLINE.search(fm)
        desc_block = _FM_DESC_BLOCK.search(fm)
        desc_value = ""
        if desc_inline:
            desc_value = desc_inline.group(1).strip()
        elif desc_block:
            desc_value = " ".join(
                line.strip() for line in desc_block.group(1).splitlines()
            ).strip()
        if not desc_value:
            findings.append(
                f"skill-frontmatter: {_rel(sk_file, root)}:1 "
                "missing or empty `description:` field"
            )
    return findings


_SECTION_HEADING = re.compile(r"^##\s+(\d+[a-z]?)\.\s", re.MULTILINE)
_SECTION_REF = re.compile(r"§(\d+[a-z]?)")


def check_section_refs(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    conv = root / "references" / "conventions.md"
    if not conv.exists():
        return findings  # nothing to validate against; another rule will note
    conv_text = _read_text(conv)
    valid = set(_SECTION_HEADING.findall(conv_text))
    if not valid:
        return findings  # file is empty/malformed; let other rules speak
    targets: list[Path] = [conv]
    skills_dir = root / "skills"
    if skills_dir.exists():
        targets += sorted(skills_dir.glob("*/SKILL.md"))
    for t in targets:
        text = _read_text(t)
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in _SECTION_REF.finditer(line):
                n = m.group(1)
                if n not in valid:
                    findings.append(
                        f"section-refs: {_rel(t, root)}:{lineno} "
                        f"dead §{n} reference (no matching `## {n}.` heading)"
                    )
    return findings


_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\n]+)\)")
_CODE_SPAN = re.compile(r"`[^`\n]*`")


def _strip_code_spans(line: str) -> str:
    """Blank out inline `code spans` so docs explaining `[text](path)` syntax
    don't trip the link check. Length-preserving so column offsets stay sane.
    """
    return _CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def check_md_links(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    targets: list[Path] = []
    for name in ("README.md", "CHANGELOG.md"):
        f = root / name
        if f.exists():
            targets.append(f)
    for sub in ("docs", "references"):
        d = root / sub
        if d.exists():
            targets += sorted(d.glob("*.md"))
    skills_dir = root / "skills"
    if skills_dir.exists():
        targets += sorted(skills_dir.glob("*/SKILL.md"))
    for t in targets:
        text = _read_text(t)
        in_fence = False
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            # Skip fenced code blocks entirely — they document syntax, not links.
            if raw_line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            line = _strip_code_spans(raw_line)
            for m in _MD_LINK.finditer(line):
                target = m.group(2).strip()
                path_part = target.split("#", 1)[0]
                if not path_part:
                    continue  # pure in-page anchor
                if path_part.startswith(("http://", "https://", "mailto:")):
                    continue
                # Resolve relative to the linking file's directory.
                resolved = (t.parent / path_part).resolve()
                if not resolved.exists():
                    findings.append(
                        f"md-links: {_rel(t, root)}:{lineno} "
                        f"broken link → {target}"
                    )
    return findings


# Match the §14 Layout fenced block; the block is markdown source so we look
# for the `Layout` keyword inside §14 followed by a fenced code block.
_LESSONS_LAYOUT = re.compile(
    r"^## 14\.[^\n]*\n.*?Layout[^\n]*\n+```[^\n]*\n(.*?)\n```",
    re.DOTALL | re.MULTILINE,
)
_LESSONS_SECTION = re.compile(r"^##\s+(\S+)\s*$", re.MULTILINE)


def check_lessons_skeleton(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    conv = root / "references" / "conventions.md"
    init_sk = root / "skills" / "init" / "SKILL.md"
    if not conv.exists() or not init_sk.exists():
        return findings  # nothing to check; another rule will flag if needed
    conv_text = _read_text(conv)
    init_text = _read_text(init_sk)
    m = _LESSONS_LAYOUT.search(conv_text)
    if not m:
        findings.append(
            "lessons-skeleton: references/conventions.md:0 "
            "could not locate §14 Layout fenced block"
        )
        return findings
    required = _LESSONS_SECTION.findall(m.group(1))
    if not required:
        findings.append(
            "lessons-skeleton: references/conventions.md:0 "
            "§14 Layout block has no `## <name>` sections"
        )
        return findings
    # The init SKILL.md contains the canonical skeleton inside a fenced block;
    # check that every required section appears as a `## <name>` line (it does
    # since the skeleton is markdown inside an indented code block).
    init_sections = set(_LESSONS_SECTION.findall(init_text))
    # The lines inside init's fenced block are indented by 2 spaces; the regex
    # above is anchored at `^##` so it picks up the unindented headings of the
    # SKILL itself too. Filter the canonical-skeleton presence using a
    # whitespace-tolerant scan instead.
    init_skeleton_sections = set(
        re.findall(r"^\s*##\s+(\S+)\s*$", init_text, re.MULTILINE)
    )
    present = init_sections | init_skeleton_sections
    for section in required:
        if section not in present:
            findings.append(
                f"lessons-skeleton: skills/init/SKILL.md:0 "
                f"canonical skeleton missing required section "
                f"`## {section}` (per conventions §14)"
            )
    return findings


# Topology table rows look like: `| **PM** | ... | ... | ... |`.
_TOPOLOGY_AGENT = re.compile(
    r"^\|\s*\*\*([A-Z][A-Za-z]+)\*\*\s*\|", re.MULTILINE
)


def check_agent_consistency(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    conv = root / "references" / "conventions.md"
    readme = root / "README.md"
    chlog = root / "CHANGELOG.md"
    if not conv.exists() or not readme.exists() or not chlog.exists():
        return findings
    conv_text = _read_text(conv)
    agents = []
    seen = set()
    for m in _TOPOLOGY_AGENT.finditer(conv_text):
        name = m.group(1)
        if name == "Agent":  # header row
            continue
        if name not in seen:
            seen.add(name)
            agents.append(name)
    if not agents:
        return findings
    readme_text = _read_text(readme)
    chlog_text = _read_text(chlog)
    for agent in agents:
        if agent not in readme_text:
            findings.append(
                f"agent-consistency: README.md:0 "
                f"agent '{agent}' (from conventions §1 topology) "
                f"not mentioned in README"
            )
        if agent not in chlog_text:
            findings.append(
                f"agent-consistency: CHANGELOG.md:0 "
                f"agent '{agent}' (from conventions §1 topology) "
                f"not mentioned in CHANGELOG"
            )
    return findings


# Match a malformed shell invocation: one or more `VAR=value` env-prefix
# assignments at the start of the line, followed by a `--flag` token. Bash
# applies the env prefix to the next command word, so the `--flag` becomes
# the command and bash exits 127 with "command not found". This catches
# the LOOP-9 class of doc-vs-shell drift in fenced shell examples.
_SHELL_ENV_PREFIX_FLAG = re.compile(
    r"^\s*[A-Z_][A-Z0-9_]*=\S+(?:\s+[A-Z_][A-Z0-9_]*=\S+)*\s+--\S+"
)


def check_shell_example_syntax(root: Path) -> list[Finding]:
    """Scan fenced code blocks in docs/, README, CHANGELOG, references/,
    and skills/*/SKILL.md for the env-prefix-then-flag landmine. Only
    looks inside fenced blocks (where the lines are actual shell), so
    prose examples of `--flag` syntax don't trip the rule.
    """
    findings: list[Finding] = []
    targets: list[Path] = []
    for name in ("README.md", "CHANGELOG.md"):
        f = root / name
        if f.exists():
            targets.append(f)
    for sub in ("docs", "references"):
        d = root / sub
        if d.exists():
            targets += sorted(d.glob("*.md"))
    skills_dir = root / "skills"
    if skills_dir.exists():
        targets += sorted(skills_dir.glob("*/SKILL.md"))
    for t in targets:
        text = _read_text(t)
        in_fence = False
        for lineno, raw_line in enumerate(text.splitlines(), 1):
            if raw_line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            if _SHELL_ENV_PREFIX_FLAG.match(raw_line):
                findings.append(
                    f"shell-example-syntax: {_rel(t, root)}:{lineno} "
                    f"env-var prefix followed by `--flag` — bash will exec "
                    f"`--flag` as the command (exit 127); the flag must "
                    f"come AFTER the script"
                )
    return findings


# Match a bare `dev-loop` tmux session name in any docs target: `tmux <verb>
# -t dev-loop` where `dev-loop` is NOT followed by `-` (the negative
# lookahead is the AC's `\b` non-`-` boundary, so `dev-loop-<project>` is
# correctly excluded). Post-LOOP-2 the launcher only creates per-project
# sessions — a bare reference is stale doc drift: `tmux attach -t dev-loop`
# fails with "no session found", and `tmux kill-session -t dev-loop`
# silently leaves the real `dev-loop-<project>` loops running (LOOP-13).
_TMUX_BARE_DEVLOOP = re.compile(r"tmux\s+\S+\s+-t\s+dev-loop(?!-)")

# Paragraph-local allow-list. A match wrapped in an explicit anti-pattern
# callout is the operator describing the bug, not committing it. Two
# allow-list signals (case-insensitive on keywords):
#   1. Any of these keywords appears in the same paragraph (the run of
#      non-blank lines around the match): "bare", "don't", "never",
#      "fails", "silently", "no session found", "anti-pattern".
#   2. The line immediately above the match contains the explicit marker
#      `<!-- lint:tmux-allow -->`.
_TMUX_ALLOW_KEYWORDS = (
    "bare",
    "don't",
    "never",
    "fails",
    "silently",
    "no session found",
    "anti-pattern",
)
_TMUX_ALLOW_MARKER = "<!-- lint:tmux-allow -->"


def check_tmux_session_name_consistency(root: Path) -> list[Finding]:
    """Scan README.md, CHANGELOG.md, docs/*.md, references/*.md for the
    LOOP-13 class of doc-vs-script drift: a bare `tmux ... -t dev-loop`
    (without the per-project `-<project>` suffix). The launcher
    (`scripts/run-loop.sh`) only creates `dev-loop-<project>` sessions —
    a bare name is stale post-LOOP-2 doc drift. Allow-listed when wrapped
    in an explicit anti-pattern callout (see allow-list above the regex).
    """
    findings: list[Finding] = []
    targets: list[Path] = []
    for name in ("README.md", "CHANGELOG.md"):
        f = root / name
        if f.exists():
            targets.append(f)
    for sub in ("docs", "references"):
        d = root / sub
        if d.exists():
            targets += sorted(d.glob("*.md"))
    for t in targets:
        text = _read_text(t)
        lines = text.splitlines()
        for lineno, raw_line in enumerate(lines, 1):
            if not _TMUX_BARE_DEVLOOP.search(raw_line):
                continue
            # Allow-list 1: explicit marker on the line above.
            if lineno >= 2 and _TMUX_ALLOW_MARKER in lines[lineno - 2]:
                continue
            # Allow-list 2: paragraph-local keyword. A "paragraph" here is
            # the contiguous run of non-blank lines containing the match.
            start = lineno - 1
            while start > 0 and lines[start - 1].strip() != "":
                start -= 1
            end = lineno
            while end < len(lines) and lines[end].strip() != "":
                end += 1
            paragraph = "\n".join(lines[start:end]).lower()
            if any(kw in paragraph for kw in _TMUX_ALLOW_KEYWORDS):
                continue
            findings.append(
                f"tmux-session-name-consistency: {_rel(t, root)}:{lineno} "
                f"bare `tmux ... -t dev-loop` — the launcher only creates "
                f"`dev-loop-<project>` sessions (LOOP-13). Use the per-project "
                f"form `dev-loop-<project>`."
            )
    return findings


RULES: list[Callable[[Path], list[Finding]]] = [
    check_json_integrity,
    check_skill_frontmatter,
    check_section_refs,
    check_md_links,
    check_lessons_skeleton,
    check_agent_consistency,
    check_shell_example_syntax,
    check_tmux_session_name_consistency,
]


# ---------- entrypoint ----------

def lint(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(root))
    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Plugin self-lint for the dev-loop plugin (LOOP-4)."
    )
    ap.add_argument(
        "--root",
        default=".",
        help="Repo root to lint (default: current working directory)",
    )
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"lint-plugin: --root '{root}' is not a directory", file=sys.stderr)
        return 2
    findings = lint(root)
    for f in findings:
        print(f)
    if findings:
        print(f"FAIL  lint-plugin: {len(findings)} finding(s)", file=sys.stderr)
        return 1
    print("ok  lint-plugin: all rules pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
