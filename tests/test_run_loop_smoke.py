"""Wraps scripts/smoke-run-loop.sh so the run-loop launcher's multi-project
no-clobber behaviour is exercised end-to-end as part of `bash tools/test.sh`.

The smoke shells out to real tmux + bash; CI environments without tmux skip
cleanly (exit 77, autotools convention)."""
import os
import shutil
import subprocess
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMOKE = os.path.join(REPO_ROOT, "scripts", "smoke-run-loop.sh")


class RunLoopSmokeTests(unittest.TestCase):
    def test_smoke_passes(self) -> None:
        if shutil.which("tmux") is None:
            self.skipTest("tmux not on PATH")
        self.assertTrue(os.access(SMOKE, os.X_OK), f"{SMOKE} not executable")
        result = subprocess.run(
            [SMOKE],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 77:
            self.skipTest(f"smoke self-skipped: {result.stdout.strip()}")
        msg = (
            f"smoke failed (rc={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
        self.assertEqual(result.returncode, 0, msg=msg)
        self.assertIn("scripts/run-loop.sh smoke passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
