#!/usr/bin/env python3
"""Run the Chatter interpreter on a single file.

Usage:
    ./check.py <path/to/file.chatter> [extra args...]

Useful for sanity-checking whether a utility/library `.chatter` file parses
and loads, without going through run.py's quest/part conventions or its
ANSWER: contract. Any extra args are forwarded to the script as argv.

Honors the same CHATTER_HOME / CHATTER_CMD environment variables as run.py.
Exits with the interpreter's exit code.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CHATTER_REPO = Path(os.environ.get("CHATTER_HOME", "/Users/jxbaker/dev/chatter"))


def chatter_command(script: Path, extra: list[str]) -> tuple[list[str], Path | None]:
    override = os.environ.get("CHATTER_CMD")
    if override:
        return override.split() + [str(script), *extra], None

    ts_node = CHATTER_REPO / "node_modules" / ".bin" / "ts-node"
    src_cli = CHATTER_REPO / "src" / "index.ts"
    if ts_node.is_file() and src_cli.is_file():
        return [str(ts_node), str(src_cli), str(script), *extra], CHATTER_REPO

    dist_cli = CHATTER_REPO / "dist" / "index.js"
    if dist_cli.is_file():
        return ["node", str(dist_cli), str(script), *extra], None

    raise FileNotFoundError(
        f"Could not find a Chatter entrypoint. Tried {ts_node} and {dist_cli}. "
        f"Set CHATTER_HOME or CHATTER_CMD to override."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Run Chatter on a single file (quick compile/load check).",
    )
    ap.add_argument("file", help="Path to the .chatter file")
    ap.add_argument("args", nargs=argparse.REMAINDER,
                    help="Extra arguments forwarded to the script as argv")
    ns = ap.parse_args()

    script = Path(ns.file).resolve()
    if not script.is_file():
        print(f"✗ no such file: {script}", file=sys.stderr)
        return 2

    cmd, cwd = chatter_command(script, ns.args)
    print(f"$ {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
