#!/usr/bin/env python3
"""Run each Quest 3 part against the 100 bulk inputs in quest03/all-inputs/.

Expects layout:
    quest03/all-inputs/<part>/<id>      # input file
    quest03/all-inputs/answers.json     # {"p1": {"1": "...", ...}, ...}

This script is purely a verifier — it is gitignored alongside all-inputs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QDIR = REPO_ROOT / "quest03"
BULK = QDIR / "all-inputs"
CHATTER_REPO = Path(os.environ.get("CHATTER_HOME", "/Users/jxbaker/dev/chatter"))
DIST_CLI = CHATTER_REPO / "dist" / "src" / "index.js"
TS_NODE = CHATTER_REPO / "node_modules" / ".bin" / "ts-node"
SRC_CLI = CHATTER_REPO / "src" / "index.ts"

if DIST_CLI.is_file():
    BASE_CMD = ["node", str(DIST_CLI)]
    BASE_CWD: Path | None = None
else:
    BASE_CMD = [str(TS_NODE), str(SRC_CLI)]
    BASE_CWD = CHATTER_REPO

ANSWER_RE = re.compile(r"^ANSWER:\s*(.*?)\s*$", re.MULTILINE)


def run_one(part: int, input_path: Path) -> str | None:
    script = QDIR / f"part{part}.chatter"
    cmd = BASE_CMD + [str(script), str(input_path)]
    proc = subprocess.run(cmd, cwd=BASE_CWD, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"  chatter error on part{part} input {input_path.name}:\n{proc.stderr}\n")
        return None
    m = ANSWER_RE.search(proc.stdout)
    return m.group(1) if m else None


def main() -> int:
    answers = json.loads((BULK / "answers.json").read_text())
    parts = [int(p) for p in sys.argv[1:]] or [1, 2, 3]
    total_fail = 0
    for part in parts:
        key = f"p{part}"
        expected_map = answers[key]
        ids = sorted(expected_map.keys(), key=int)
        print(f"\n=== part {part}: {len(ids)} inputs ===")
        t0 = time.time()
        fails = []
        for i, id_ in enumerate(ids, 1):
            input_path = BULK / str(part) / id_
            if not input_path.is_file():
                print(f"  ✗ {id_}: input missing")
                fails.append(id_)
                continue
            got = run_one(part, input_path)
            exp = expected_map[id_]
            ok = got == exp
            if not ok:
                fails.append(id_)
            marker = "✓" if ok else "✗"
            sys.stdout.write(f"\r  [{i}/{len(ids)}] {marker} {id_}: got={got} exp={exp}{' ' * 10}")
            sys.stdout.flush()
            if not ok:
                sys.stdout.write("\n")
        dt = time.time() - t0
        print(f"\n  done in {dt:.1f}s — {len(ids) - len(fails)}/{len(ids)} ok"
              + (f" — failures: {fails}" if fails else ""))
        total_fail += len(fails)
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
