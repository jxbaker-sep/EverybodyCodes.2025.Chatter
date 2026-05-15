# Copilot Instructions

> **Hands off `.chatter` files.** The author is writing every line of Chatter
> by hand. Do not generate, complete, edit, or suggest Chatter source code.
> Limit AI assistance to `bootstrap.py`, `run.py`, README/docs, shell tasks,
> and project configuration.

Solutions to **Everybody Codes 2025** puzzles, written by hand in
[Chatter](https://github.com/jxbaker/chatter) (a HyperTalk-inspired language
under active development at `/Users/jxbaker/dev/chatter`).

## Bootstrapping a quest

```bash
./bootstrap.py <N>            # scaffold quest<NN>/ and download inputs
./bootstrap.py <N> --force    # overwrite existing files
./bootstrap.py <N> --no-download
```

`bootstrap.py` is a stdlib-only Python script. AES-CBC decryption is done by
shelling out to `openssl`, so there are no Python package dependencies.

The session cookie comes from `$EC_SESSION` or a `.ec-session` file
(repo root or `$HOME`). Both `.ec-session` and `quest*/part*.txt` are
gitignored — never commit either.

## Running & verifying a solution

```bash
./run.py <quest> <part> --example   # run on part<N>.example.txt
./run.py <quest> <part>             # run on the real input
./run.py <quest> <part> --no-verify
```

The Chatter script reads its input path from `argv[0]`:

```chatter
use args from "std:cli"
args
constant input_path is item 1 of it
constant input is lines of file input_path
```

Final answers MUST be printed as `ANSWER: <value>` on their own line. All
other `say` output is treated as debug; `run.py` echoes it back prefixed
with `[debug]` on stderr and ignores it for verification.

Expected files live alongside inputs:

  - `quest01/part1.txt`         → `quest01/part1.expected`
  - `quest01/part1.example.txt` → `quest01/part1.example.expected`

If no expected file exists, `run.py` prints the answer plus the exact
shell command to record it.

### Slow parts (skip in regressions)

If a `quest<NN>/part<N>.slow` file is present, `run.py` **skips** that
part by default and prints the marker's contents as the reason. This is
the mechanism for marking solutions that are correct but take minutes
(or longer) to run, so they don't pollute casual reruns or regression
sweeps.

  - To run anyway: `./run.py <quest> <part> --force-slow`
  - To mark a part slow: create the marker with a short note, e.g.
    `echo "Mariani-Silver; ~3min on example" > quest02/part3.slow`
  - **AI / assistant guidance:** never run a `.slow` part as part of
    a regression, verification sweep, or "just check it still works"
    flow. Only run it when the user explicitly asks for that part.

`run.py` invokes the local Chatter checkout via
`$CHATTER_HOME/node_modules/.bin/ts-node` (default
`CHATTER_HOME=/Users/jxbaker/dev/chatter`). Set `CHATTER_CMD` to override.

## Layout

```
quest<NN>/
  part1.chatter           part2.chatter           part3.chatter
  part1.txt               part2.txt               part3.txt           # real inputs (gitignored)
  part1.example.txt       part2.example.txt       part3.example.txt   # example inputs (gitignored)
  part1.expected          part2.expected          part3.expected      # real answers (committed)
  part1.example.expected  part2.example.expected  part3.example.expected  # example answers (committed)
```

## Conventions

- One directory per quest, zero-padded: `quest01`, `quest02`, ..., `quest20`.
- Solutions are written by hand in `.chatter`. Do not auto-generate solution
  code.
- Chatter currently has no file I/O; inputs are inspected manually and
  relevant data is encoded into the `.chatter` source as constants.
- Run a solution against the local Chatter checkout:
  `npx ts-node /Users/jxbaker/dev/chatter/src/index.ts quest01/part1.chatter`

## Language notes (Chatter)

- Reads like English: `constant foo is 5`, `say "hello"`, `if x is 5 then`.
- `it` is a function-scoped register holding the result of the last
  statement; `say` does **not** update it.
- `constant` bindings are immutable; reassignment is a compile error.
- Strict equality: comparing a number to a string is a runtime error.
- Mixing `and`/`or` at the same precedence level requires parentheses.
- Golden tests live in `/Users/jxbaker/dev/chatter/tests/chatter/` —
  `<name>.chatter` + `<name>.expected`.

## When extending bootstrap.py

The download flow mirrors `MrTimeey/everybodycodes-data`:

1. `GET /api/user/me` (with `Cookie: everybody-codes=<token>`) → `seed`
2. `GET /api/event/<year>/quest/<n>` → `key1`, `key2`, `key3` (UTF-8 strings)
3. `GET https://everybody-codes.b-cdn.net/assets/<year>/<n>/input/<seed>.json`
   → hex ciphertext per part
4. AES-CBC decrypt: key bytes = key string as UTF-8; IV = first 16 bytes of
   the key; variant is picked by key length (16/24/32 → AES-128/192/256-CBC).

For Story content (vs the main event), swap `event` → `story/<story-name>` in
the URLs; `bootstrap.py` exposes this via `--story <name>`.
