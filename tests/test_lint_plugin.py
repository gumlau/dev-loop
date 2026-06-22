"""Negative-test fixtures for scripts/lint-plugin.py (LOOP-4 AC #8).

Each test points the lint at one fixture under tests/fixtures/lint-bad/<rule>/
and asserts that the lint:
  - exits non-zero
  - reports a finding whose rule prefix matches the expected rule

The clean-repo gate (lint exits zero on the current repo) is enforced
separately by tools/test.sh, which runs scripts/lint-plugin.py against the
real repo root as one of its steps. That's the "negative" → "positive" pair.
"""
from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "lint-bad"

# Make the lint script importable as a module so we don't shell out.
sys.path.insert(0, str(REPO / "scripts"))

import importlib  # noqa: E402
lint_plugin = importlib.import_module("lint-plugin")  # type: ignore[assignment]


def _run(fixture: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = lint_plugin.main(["--root", str(FIXTURES / fixture)])
    return rc, out.getvalue(), err.getvalue()


class TestLintPluginNegative(unittest.TestCase):
    """One test per rule — each fixture trips exactly its target rule."""

    def assert_rule_found(self, fixture: str, rule: str) -> None:
        rc, out, _ = _run(fixture)
        self.assertNotEqual(
            rc, 0,
            f"fixture {fixture!r} should fail lint but exit was 0; "
            f"stdout:\n{out}",
        )
        # Every finding line starts with `<rule>: ` — assert the expected one
        # is present.
        prefix = f"{rule}: "
        self.assertTrue(
            any(line.startswith(prefix) for line in out.splitlines()),
            f"fixture {fixture!r} did not trip rule {rule!r}; got:\n{out}",
        )

    def test_json_integrity(self):
        self.assert_rule_found("json", "json-integrity")

    def test_skill_frontmatter(self):
        self.assert_rule_found("skill", "skill-frontmatter")

    def test_section_refs(self):
        self.assert_rule_found("sectref", "section-refs")

    def test_md_links(self):
        self.assert_rule_found("mdlink", "md-links")

    def test_lessons_skeleton(self):
        self.assert_rule_found("lessons", "lessons-skeleton")

    def test_agent_consistency(self):
        self.assert_rule_found("agent", "agent-consistency")

    def test_shell_example_syntax(self):
        # Catches the LOOP-9 class of doc-vs-shell drift: an env-prefix
        # followed by a `--flag` token inside a fenced shell example.
        self.assert_rule_found("shell", "shell-example-syntax")


class TestLintPluginPositive(unittest.TestCase):
    """The lint must exit zero on the real repo (LOOP-4 AC #9)."""

    def test_clean_repo_passes(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = lint_plugin.main(["--root", str(REPO)])
        self.assertEqual(
            rc, 0,
            f"lint should pass on the clean repo but exited {rc}; "
            f"stdout:\n{out.getvalue()}\nstderr:\n{err.getvalue()}",
        )


if __name__ == "__main__":
    unittest.main()
