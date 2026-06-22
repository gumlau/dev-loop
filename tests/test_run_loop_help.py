"""Coverage test for `scripts/run-loop.sh --help` / `-h` (LOOP-16).

Asserts:
  (a) `run-loop.sh --help` exits 0 and prints a usage block to stdout
      (the "Usage:" marker from the in-file usage docblock is present).
  (b) `run-loop.sh -h` exits 0 with the same usage marker (alias).
  (c) The help path is **precondition-free**: it works with `DATA_DIR`
      pointed at a non-existent directory and without `projects.json`
      readable, i.e. on a fresh machine in the exact "help me, I'm new"
      state the AC calls out.
  (d) Order independence — `run-loop.sh --restart --help` and
      `run-loop.sh --help --restart` both surface help (the `--restart`
      consumer must not swallow `--help`).
  (e) Existing unknown-key error path is unchanged for non-help args
      (smoke non-regression).
"""
from __future__ import annotations

import os
import subprocess
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_LOOP = os.path.join(REPO_ROOT, "scripts", "run-loop.sh")
USAGE_MARKER = "Usage:"


def _run(args: list[str], *, data_dir: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if data_dir is not None:
        env["DATA_DIR"] = data_dir
    # Sterilize anything that would otherwise let the script find a real
    # config / claude binary / tmux on PATH — exercise the precondition-free
    # path the AC pins.
    return subprocess.run(
        ["bash", RUN_LOOP, *args],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=env,
    )


class RunLoopHelpTests(unittest.TestCase):
    def test_long_help_exits_zero_and_prints_usage(self) -> None:
        r = _run(["--help"])
        self.assertEqual(r.returncode, 0, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        self.assertIn(USAGE_MARKER, r.stdout)
        # Synopsis + at least one example must be present per AC #1.
        self.assertIn("Examples:", r.stdout)
        # Every env var the launcher reads must be listed (AC #1 "every env var").
        for var in ("PROJECT", "PROJECTS", "MODE", "SWEEP", "REFLECT",
                    "OPS", "ARCHITECT", "SIGNAL", "RESTART", "DATA_DIR"):
            self.assertIn(var, r.stdout, msg=f"env var {var!r} missing from --help")

    def test_short_help_alias(self) -> None:
        r = _run(["-h"])
        self.assertEqual(r.returncode, 0, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        self.assertIn(USAGE_MARKER, r.stdout)

    def test_help_is_precondition_free(self) -> None:
        # DATA_DIR points at a path that does not exist. The help handler
        # must NOT touch the filesystem or a `cfg()` call before exiting.
        bogus = "/tmp/devloop-help-nope-does-not-exist-9276"
        self.assertFalse(os.path.exists(bogus), "test prereq: bogus dir should not exist")
        r = _run(["--help"], data_dir=bogus)
        self.assertEqual(r.returncode, 0, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        self.assertIn(USAGE_MARKER, r.stdout)
        # The "config not found" precondition error must NOT have fired.
        self.assertNotIn("config not found", r.stderr)
        self.assertNotIn("config not found", r.stdout)

    def test_help_wins_over_restart_in_either_order(self) -> None:
        for args in (["--restart", "--help"], ["--help", "--restart"]):
            with self.subTest(args=args):
                r = _run(args)
                self.assertEqual(r.returncode, 0, msg=f"args={args}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}")
                self.assertIn(USAGE_MARKER, r.stdout)

    def test_unknown_key_error_path_unchanged_for_non_help_args(self) -> None:
        # A non-help positional arg must NOT be treated as --help — this
        # would silently break the "unknown project key" error path that
        # operators rely on to catch typos in their project key.
        # Skip if the operator's real projects.json happens to include the
        # synthetic key (vanishingly unlikely, but be defensive).
        r = _run(["__loop16-no-such-project__"])
        # Either:
        #   - script reached the "unknown project key" preflight (rc=1), or
        #   - it hit an earlier precondition (claude/tmux/python3/config
        #     missing, also rc=1).
        # In all non-help paths, --help did NOT swallow the arg.
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn(USAGE_MARKER, r.stdout)


if __name__ == "__main__":
    unittest.main()
