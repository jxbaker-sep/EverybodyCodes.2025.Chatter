# Everybody Codes 2025 — in Chatter

Solutions to the [Everybody Codes 2025](https://everybody.codes/) puzzles
written by hand in [Chatter](https://github.com/jxbaker/chatter).

## Layout

```
quest01/
  part1.chatter   part2.chatter   part3.chatter
  part1.txt       part2.txt       part3.txt   (gitignored)
```

## Bootstrapping a quest

```bash
./bootstrap.py 1        # scaffolds quest01/ and downloads inputs
./bootstrap.py 1 --force        # overwrite existing files
./bootstrap.py 1 --no-download  # scaffold only
```

### Session cookie

To download inputs, the script needs your `everybody-codes` session cookie.
Get it from your browser devtools (Application → Cookies on
https://everybody.codes after logging in), then either:

```bash
export EC_SESSION='your-cookie-uuid-here'
# — or —
echo 'your-cookie-uuid-here' > .ec-session   # gitignored
```

The script uses the system `openssl` for AES-CBC decryption, so there are no
Python package dependencies.

## Running & verifying a solution

```bash
./run.py 1 1 --example     # run quest01/part1.chatter on part1.example.txt
./run.py 1 1               # run on the real input
./run.py 1 1 --no-verify   # just run; don't check against an expected file
```

The Chatter script receives the input file path as `argv[0]`:

```chatter
use args from "std:cli"
args
constant input_path is item 1 of it
constant input is lines of file input_path
```

The script must print the final answer on its own line:

```chatter
say "ANSWER:", value
```

Any other `say` output is treated as debug — `run.py` reprints it as
`  [debug] …` on stderr but ignores it when checking the answer.

### Expected files

`run.py` verifies against a sibling file alongside the input:

| input                     | expected                       |
| ------------------------- | ------------------------------ |
| `quest01/part1.txt`       | `quest01/part1.expected`       |
| `quest01/part1.example.txt` | `quest01/part1.example.expected` |

If no expected file exists yet, `run.py` prints the answer and shows the
exact shell command to record it.

### Chatter location

`run.py` invokes Chatter from `$CHATTER_HOME` (default
`/Users/jxbaker/dev/chatter`). To override the runner entirely, set
`CHATTER_CMD="node /path/to/cli.js"` (or similar).

## Running a solution

## Manual invocation

```bash
# from /Users/jxbaker/dev/chatter (the language repo)
npx ts-node src/index.ts /path/to/quest01/part1.chatter /path/to/quest01/part1.txt
```

The script reads its input path from CLI args via `use args from "std:cli"`.
Prefer `./run.py` for the full verify workflow.
