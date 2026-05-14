#!/usr/bin/env python3
"""Bootstrap an Everybody Codes 2025 quest.

Usage:
    ./bootstrap.py <quest_number> [--year 2025] [--story <name>] [--force]

Creates `quest<NN>/part{1,2,3}.chatter` stub files, and (if a session cookie
is available) downloads and decrypts the puzzle inputs into
`quest<NN>/part{1,2,3}.txt`.

The session cookie is read from:
  1. The `EC_SESSION` environment variable, or
  2. A `.ec-session` file in the repo root (gitignored), or
  3. `~/.ec-session`

Inputs are decrypted via the `openssl` CLI (no third-party Python deps).
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
API_BASE = "https://api.everybody.codes"
ASSETS_BASE = "https://everybody.codes/assets"
PARTS = (1, 2, 3)


def load_session_cookie() -> str | None:
    env = os.environ.get("EC_SESSION", "").strip()
    if env:
        return env
    for candidate in (REPO_ROOT / ".ec-session", Path.home() / ".ec-session"):
        if candidate.is_file():
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
    return None


def http_get_json(url: str, cookie: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Cookie": f"everybody-codes={cookie}",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://everybody.codes",
            "Referer": "https://everybody.codes/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) "
                "Gecko/20100101 Firefox/130.0"
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_seed(cookie: str) -> str:
    data = http_get_json(f"{API_BASE}/user/me", cookie)
    if data.get("id") is None:
        raise RuntimeError(
            "Not logged in: /user/me returned id=null. Your everybody-codes "
            "cookie is missing, expired, or rotated. Open everybody.codes in "
            "the browser, copy the current cookie value from DevTools → "
            "Storage → Cookies → everybody-codes, and update EC_SESSION or "
            ".ec-session."
        )
    raw = data.get("seed")
    try:
        num = int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        num = 0
    if num <= 0:
        raise RuntimeError(
            "Logged in but got seed=0 from /user/me — unexpected; aborting."
        )
    return str(num)


def get_keys(challenge_type: str, event: str, quest: int, cookie: str) -> dict[int, str]:
    url = f"{API_BASE}/{challenge_type}/{event}/quest/{quest}"
    data = http_get_json(url, cookie)
    keys: dict[int, str] = {}
    for p in PARTS:
        v = data.get(f"key{p}")
        if v:
            keys[p] = str(v)
    return keys


def get_encrypted_inputs(event: str, quest: int, seed: str, cookie: str) -> dict[int, str]:
    url = f"{ASSETS_BASE}/{event}/{quest}/input/{seed}.json"
    data = http_get_json(url, cookie)
    return {p: data[str(p)] for p in PARTS if str(p) in data and data[str(p)]}


def get_encrypted_descriptions(event: str, quest: int, cookie: str) -> dict[int, str]:
    url = f"{ASSETS_BASE}/{event}/{quest}/description.json"
    try:
        data = http_get_json(url, cookie)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    return {p: data[str(p)] for p in PARTS if str(p) in data and data[str(p)]}


_EXAMPLE_RE = re.compile(
    r'<div\s+class="example"[^>]*>(.*?)</div>\s*</div>\s*</div>',
    re.DOTALL | re.IGNORECASE,
)
_FIRST_EXAMPLE_BLOCK_RE = re.compile(
    r'<div\s+class="example"[^>]*>(.*)', re.DOTALL | re.IGNORECASE,
)
_PRE_NOTE_RE = re.compile(
    r'<pre\s+class="note"[^>]*>(.*?)</pre>', re.DOTALL | re.IGNORECASE,
)


_PRE_BOLD_RE = re.compile(
    r"<pre[^>]*>\s*<b[^>]*>\s*([^<]+?)\s*</b>\s*</pre>", re.IGNORECASE
)


def extract_example_answer(description_html: str) -> str | None:
    """Pull the expected example answer out of a decrypted description HTML blob.

    EC consistently highlights the example's final result inside the first
    `<div class="example">` block as `<pre><b>ANSWER</b></pre>`. We take the
    LAST such match within that block (the example may contain several -
    intermediate results are highlighted the same way).
    """
    m = _FIRST_EXAMPLE_BLOCK_RE.search(description_html)
    if not m:
        return None
    block = m.group(1)
    matches = _PRE_BOLD_RE.findall(block)
    if not matches:
        return None
    return html.unescape(matches[-1]).strip()


def extract_example(description_html: str) -> str | None:
    """Pull the example input out of a decrypted description HTML blob.

    The convention is: the first `<div class="example">` contains a
    `<pre class="note">` whose contents are the example input.
    """
    m = _FIRST_EXAMPLE_BLOCK_RE.search(description_html)
    if not m:
        return None
    block = m.group(1)
    pm = _PRE_NOTE_RE.search(block)
    if not pm:
        return None
    text = html.unescape(pm.group(1))
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip("\n") + "\n"


def aes_decrypt_hex(key: str, hex_cipher: str) -> str:
    key_bytes = key.encode("utf-8")
    iv_bytes = key[:16].encode("utf-8")
    n = len(key_bytes)
    algo = {16: "aes-128-cbc", 24: "aes-192-cbc", 32: "aes-256-cbc"}.get(n)
    if algo is None:
        raise RuntimeError(f"Unexpected key length {n}; cannot pick AES variant.")
    try:
        proc = subprocess.run(
            [
                "openssl", "enc", "-d", f"-{algo}",
                "-K", key_bytes.hex(),
                "-iv", iv_bytes.hex(),
            ],
            input=bytes.fromhex(hex_cipher),
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("`openssl` not found on PATH; required for decryption.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"openssl failed: {e.stderr.decode('utf-8', 'replace')}") from e
    return proc.stdout.decode("utf-8")


CHATTER_STUB = """# Quest {n} — Part {part}
#
# Run with:
#     ./run.py {n} {part} --example     # against part{part}.example.txt
#     ./run.py {n} {part}               # against part{part}.txt
#
# Print the final answer using:
#     say "ANSWER:", value
# Anything else printed via `say` is ignored by run.py (treated as debug).

use get_input from "../util/io"
constant input is the result of get_input

# TODO: solve quest {n} part {part}
say "ANSWER:", "TODO"
"""


def scaffold(quest: int, force: bool) -> Path:
    qdir = REPO_ROOT / f"quest{quest:02d}"
    qdir.mkdir(parents=True, exist_ok=True)
    for p in PARTS:
        path = qdir / f"part{p}.chatter"
        if path.exists() and not force:
            print(f"  keep    {path.relative_to(REPO_ROOT)}")
            continue
        path.write_text(CHATTER_STUB.format(n=quest, part=p), encoding="utf-8")
        print(f"  wrote   {path.relative_to(REPO_ROOT)}")
    return qdir


def download_inputs(
    qdir: Path,
    challenge_type: str,
    event: str,
    quest: int,
    cookie: str,
    force: bool,
) -> None:
    seed = get_seed(cookie)
    keys = get_keys(challenge_type, event, quest, cookie)
    if not keys:
        print(f"  warn    no keys returned for {challenge_type} {event} quest {quest} "
              f"(quest may not be unlocked yet)")
        return
    encrypted = get_encrypted_inputs(event, quest, seed, cookie)
    descriptions = get_encrypted_descriptions(event, quest, cookie)
    for p in PARTS:
        key = keys.get(p)
        if not key:
            continue

        # Real input
        out = qdir / f"part{p}.txt"
        hexct = encrypted.get(p)
        if not hexct:
            print(f"  skip    part{p}.txt (not yet available)")
        elif out.exists() and not force:
            print(f"  keep    {out.relative_to(REPO_ROOT)}")
        else:
            plaintext = aes_decrypt_hex(key, hexct)
            out.write_text(plaintext, encoding="utf-8")
            print(f"  fetched {out.relative_to(REPO_ROOT)} ({len(plaintext)} bytes)")

        # Example input + expected answer (both parsed from puzzle description)
        ex_out = qdir / f"part{p}.example.txt"
        exp_out = qdir / f"part{p}.example.expected"
        desc_hex = descriptions.get(p)
        if not desc_hex:
            continue
        ex_needed = not ex_out.exists() or force
        exp_needed = not exp_out.exists() or force
        if not ex_needed and not exp_needed:
            print(f"  keep    {ex_out.relative_to(REPO_ROOT)}")
            print(f"  keep    {exp_out.relative_to(REPO_ROOT)}")
            continue
        try:
            desc_html = aes_decrypt_hex(key, desc_hex)
        except RuntimeError as e:
            print(f"  warn    could not decrypt description part {p}: {e}")
            continue

        if ex_needed:
            example = extract_example(desc_html)
            if example is None:
                print(f"  skip    part{p}.example.txt (no example found in description)")
            else:
                ex_out.write_text(example, encoding="utf-8")
                print(f"  fetched {ex_out.relative_to(REPO_ROOT)} ({len(example)} bytes)")
        else:
            print(f"  keep    {ex_out.relative_to(REPO_ROOT)}")

        if exp_needed:
            answer = extract_example_answer(desc_html)
            if answer is None:
                print(f"  skip    part{p}.example.expected (no answer found in description)")
            else:
                exp_out.write_text(answer.rstrip("\n") + "\n", encoding="utf-8")
                print(f"  fetched {exp_out.relative_to(REPO_ROOT)} ({len(answer)} bytes)")
        else:
            print(f"  keep    {exp_out.relative_to(REPO_ROOT)}")


def ensure_gitignore() -> None:
    gi = REPO_ROOT / ".gitignore"
    required = [
        "# Puzzle inputs and real answers — do not commit",
        "quest*/part[1-3].txt",
        "quest*/part[1-3].expected",
        "",
        "# Local session cookie",
        ".ec-session",
    ]
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    missing = [line for line in required if line and line not in existing]
    if not missing:
        return
    with gi.open("a", encoding="utf-8") as f:
        if existing and existing[-1] != "":
            f.write("\n")
        f.write("\n".join(required) + "\n")
    print(f"  updated .gitignore (+{len(missing)} entries)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bootstrap an Everybody Codes 2025 quest.")
    ap.add_argument("quest", type=int, help="Quest number (1-20)")
    ap.add_argument("--year", default="2025", help="Event year (default: 2025)")
    ap.add_argument("--story", default=None,
                    help="Fetch as a story instead of an event (story name)")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing stubs/inputs")
    ap.add_argument("--no-download", action="store_true",
                    help="Only scaffold; skip input download")
    args = ap.parse_args()

    if not (1 <= args.quest <= 20):
        ap.error("quest must be between 1 and 20")

    print(f"Bootstrapping quest {args.quest:02d}…")
    qdir = scaffold(args.quest, args.force)
    ensure_gitignore()

    if args.no_download:
        return 0

    cookie = load_session_cookie()
    if not cookie:
        print(
            "  warn    no session cookie found — skipping input download.\n"
            "          Set EC_SESSION or write the cookie to .ec-session "
            "(see README)."
        )
        return 0

    challenge_type = "story" if args.story else "event"
    event = args.story if args.story else args.year
    try:
        download_inputs(qdir, challenge_type, event, args.quest, cookie, args.force)
    except urllib.error.HTTPError as e:
        print(f"  error   HTTP {e.code} {e.reason} for {e.url}", file=sys.stderr)
        return 1
    except (RuntimeError, urllib.error.URLError) as e:
        print(f"  error   {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
