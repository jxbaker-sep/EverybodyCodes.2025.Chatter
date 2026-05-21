#!/usr/bin/env python3
"""Run an Everybody Codes / Chatter quest part and verify its output.

Usage:
    ./run.py <quest> <part> [--example] [--expected <file>] [--no-verify]

    ./run.py 1 1                  # runs quest01/part1.chatter on part1.txt,
                                  # verifies against quest01/part1.expected
    ./run.py 1 1 --example        # runs against part1.example.txt,
                                  # verifies against part1.example.expected
    ./run.py 1 1 --no-verify      # just run; print everything; don't check

Solution contract:
    The .chatter script must print the final answer on a line of the form

        ANSWER: <value>

    Any other output is treated as debug (printed to stderr-stream for the
    user but ignored for verification). The script reads its input file from
    argv[0] via `use args from "std:cli"`.

Expected files live next to the input:
    quest01/part1.txt           → quest01/part1.expected
    quest01/part1.example.txt   → quest01/part1.example.expected
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
CHATTER_REPO = Path(os.environ.get("CHATTER_HOME", "/Users/jxbaker/dev/chatter"))

ANSWER_RE = re.compile(r"^ANSWER:\s*(.*?)\s*$")


def chatter_command(script: Path, input_path: Path) -> tuple[list[str], Path | None]:
    """Build the command + cwd for invoking the Chatter interpreter."""
    override = os.environ.get("CHATTER_CMD")
    if override:
        return override.split() + [str(script), str(input_path)], None

    # Use the local ts-node from the chatter checkout. Running with cwd set to
    # CHATTER_REPO makes node resolve ts-node from its node_modules without a
    # global lookup (which can hang on a registry round-trip).
    ts_node = CHATTER_REPO / "node_modules" / ".bin" / "ts-node"
    src_cli = CHATTER_REPO / "src" / "index.ts"
    if ts_node.is_file() and src_cli.is_file():
        return [str(ts_node), str(src_cli), str(script), str(input_path)], CHATTER_REPO

    dist_cli = CHATTER_REPO / "dist" / "index.js"
    if dist_cli.is_file():
        return ["node", str(dist_cli), str(script), str(input_path)], None

    raise FileNotFoundError(
        f"Could not find a Chatter entrypoint. Tried {ts_node} and {dist_cli}. "
        f"Set CHATTER_HOME or CHATTER_CMD to override."
    )


def extract_answer(stdout: str) -> tuple[str | None, list[str]]:
    """Return (answer, debug_lines). If no ANSWER: line, answer is None."""
    answer: str | None = None
    debug: list[str] = []
    for line in stdout.splitlines():
        m = ANSWER_RE.match(line)
        if m and answer is None:
            answer = m.group(1)
        else:
            debug.append(line)
    return answer, debug


def normalize(s: str) -> str:
    return s.strip()


def copy_to_clipboard(text: str) -> str | None:
    """Best-effort copy to system clipboard. Returns tool name on success."""
    candidates: list[tuple[str, list[str]]] = []
    if sys.platform == "darwin":
        candidates.append(("pbcopy", ["pbcopy"]))
    elif sys.platform.startswith("linux"):
        candidates.append(("wl-copy", ["wl-copy"]))
        candidates.append(("xclip", ["xclip", "-selection", "clipboard"]))
        candidates.append(("xsel", ["xsel", "--clipboard", "--input"]))
    elif sys.platform.startswith("win"):
        candidates.append(("clip", ["clip"]))
    for name, cmd in candidates:
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True)
            return name
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Run and verify a quest part.")
    ap.add_argument("quest", type=int, help="Quest number (1-20)")
    ap.add_argument("part", type=str,
                    help="Part: 1, 2, or 3 — optionally followed by a single "
                         "lowercase letter (e.g. '2a') to select an "
                         "alternate-implementation script that reuses part 2's "
                         "input and expected files.")
    ap.add_argument("--example", nargs="?", const=0, default=None, type=int,
                    metavar="N",
                    help="Use the example input. Bare --example uses "
                         "part<N>.example.txt; --example 1, --example 2, etc. "
                         "use part<N>.example.<i>.txt for quests with multiple "
                         "worked examples.")
    ap.add_argument("--expected", default=None,
                    help="Override path to the expected-output file.")
    ap.add_argument("--no-verify", action="store_true",
                    help="Run but don't verify against an expected file.")
    ap.add_argument("--save", action="store_true",
                    help="Write the answer to the expected file. "
                         "Errors if the expected file already exists; use "
                         "this only to record a freshly-confirmed answer.")
    ap.add_argument("--force-slow", action="store_true",
                    help="Run even if a part<N>.slow marker exists next to "
                         "the solution. By default such parts are skipped.")
    args = ap.parse_args()

    part_match = re.fullmatch(r"([1-3])([a-z]?)", args.part)
    if not part_match:
        print(f"error: invalid part {args.part!r}; expected 1, 2, 3, or a "
              f"digit followed by one lowercase letter (e.g. 2a)",
              file=sys.stderr)
        return 2
    part_num = int(part_match.group(1))     # used for input/expected paths
    part_id = args.part                     # used for script and .slow marker

    qdir = REPO_ROOT / f"quest{args.quest:02d}"
    script = qdir / f"part{part_id}.chatter"
    slow_marker = qdir / f"part{part_id}.slow"
    if slow_marker.is_file() and not args.force_slow:
        note = slow_marker.read_text(encoding="utf-8").strip()
        print(f"⏭  skipping quest{args.quest:02d}/part{part_id}: marked SLOW",
              file=sys.stderr)
        if note:
            print(f"   ({note})", file=sys.stderr)
        print(f"   pass --force-slow to run anyway.", file=sys.stderr)
        return 0
    if args.example is not None:
        if args.example == 0:
            numbered = sorted(qdir.glob(f"part{part_num}.example.[0-9]*.txt"))
            numbered_re = re.compile(
                rf"^part{part_num}\.example\.(\d+)\.txt$"
            )
            numbered = [p for p in numbered if numbered_re.match(p.name)]
            if numbered:
                indices = sorted(
                    int(numbered_re.match(p.name).group(1)) for p in numbered
                )
                idx_list = ", ".join(f"--example {i}" for i in indices)
                print(
                    f"quest{args.quest:02d}/part{part_num} has "
                    f"{len(indices)} worked examples; re-run with one of: "
                    f"{idx_list}",
                    file=sys.stderr,
                )
                return 2
            input_path = qdir / f"part{part_num}.example.txt"
            expected_path = qdir / f"part{part_num}.example.expected"
        else:
            input_path = qdir / f"part{part_num}.example.{args.example}.txt"
            expected_path = qdir / f"part{part_num}.example.{args.example}.expected"
    else:
        input_path = qdir / f"part{part_num}.txt"
        expected_path = qdir / f"part{part_num}.expected"
    if args.expected:
        expected_path = Path(args.expected)

    for required in (script, input_path):
        if not required.is_file():
            print(f"error: missing {required}", file=sys.stderr)
            return 2

    cmd, cwd = chatter_command(script, input_path)
    print(f"$ {' '.join(cmd)}", file=sys.stderr)

    # Stream stdout line-by-line so debug lines surface immediately on
    # long-running solutions. Stderr is forwarded in a background thread.
    proc = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    def _pump_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()

    stderr_thread = threading.Thread(target=_pump_stderr, daemon=True)
    stderr_thread.start()

    answer: str | None = None
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        m = ANSWER_RE.match(line)
        if m and answer is None:
            answer = m.group(1)
        else:
            print(f"  [debug] {line}", file=sys.stderr)
            sys.stderr.flush()
    returncode = proc.wait()
    stderr_thread.join()

    if returncode != 0:
        print(f"\n✗ chatter exited with code {returncode}", file=sys.stderr)
        return returncode

    if answer is None:
        print("\n✗ no `ANSWER: …` line found in stdout", file=sys.stderr)
        return 1

    print(f"\nANSWER: {answer}")

    if args.save:
        if expected_path.exists():
            print(f"✗ refusing to overwrite existing {expected_path.relative_to(REPO_ROOT) if expected_path.is_relative_to(REPO_ROOT) else expected_path}",
                  file=sys.stderr)
            return 1
        expected_path.write_text(answer.rstrip("\n") + "\n", encoding="utf-8")
        print(f"✓ saved → {expected_path.relative_to(REPO_ROOT) if expected_path.is_relative_to(REPO_ROOT) else expected_path}")
        return 0

    if args.no_verify:
        return 0

    if not expected_path.is_file():
        print(f"\n? no expected file at {expected_path.relative_to(REPO_ROOT) if expected_path.is_relative_to(REPO_ROOT) else expected_path}")
        tool = copy_to_clipboard(answer)
        if tool:
            print(f"  📋 answer copied to clipboard via {tool} — paste into everybody.codes")
        else:
            print(f"  (clipboard tool not found; answer above)")
        print(f"  to record this answer:")
        print(f"    echo '{answer}' > {expected_path}")
        return 0

    expected = normalize(expected_path.read_text(encoding="utf-8"))
    actual = normalize(answer)
    if expected == actual:
        print(f"✓ matches {expected_path.name}")
        return 0
    print(f"✗ expected {expected!r}, got {actual!r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
