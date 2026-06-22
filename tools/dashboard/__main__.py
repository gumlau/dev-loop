"""Launch the dev-loop dashboard.

    python3 -m tools.dashboard            # default port 5173, default data dir
    python3 -m tools.dashboard --port 5180
    DEVLOOP_DATA_DIR=/tmp/board python3 -m tools.dashboard
"""

from __future__ import annotations

import argparse
import sys

from .server import default_data_dir, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dev-loop-dashboard",
        description="Read-only local dashboard over the dev-loop data dir.",
    )
    parser.add_argument(
        "--port", type=int, default=5173,
        help="TCP port to listen on (default 5173).",
    )
    parser.add_argument(
        "--data-dir", default=None,
        help="Override DEVLOOP_DATA_DIR (default ~/.claude/plugins/data/dev-loop/).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host to bind to. Loopback only by design — override at your own risk.",
    )
    args = parser.parse_args(argv)
    data_dir = args.data_dir or default_data_dir()
    run(host=args.host, port=args.port, data_dir=data_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
