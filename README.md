# emit-packages

Packages of R7RS libraries for the [Emit](https://github.com/bwbensonjr/emit) Scheme
compiler. Emit itself ships only the standard libraries and a few selected SRFIs;
domain libraries live here, released on their own schedule and tested against Emit.

| Package | Libraries | Summary |
|---|---|---|
| [malt](packages/malt/docs/MALT.md) | `(malt learner)` | Tensors, reverse-mode automatic differentiation, and training utilities from *The Little Learner* |

## Install

With Emit 0.13.0 or later, `emit pkg` installs packages into Emit's user library root:

```sh
emit pkg install malt
```

Then, from any directory:

```sh
$ printf '(import (malt learner))\n(display (gradient (lambda (x) (* x x)) 3.0))\n' > sq.scm
$ emit run sq.scm
6.0
```

`emit pkg available` lists what the collection offers, `emit pkg list` shows what is
installed and at which commit, `emit pkg update` moves every installed package to the
collection's current `main`, and `emit pkg remove malt` deletes exactly Malt's files.
This repository's `main` branch is the release: every change to it reaches users on
their next `install` or `update`, which is why `main` requires the `Package checks`
status. The collection owns compatibility with the latest stable Emit; see
[Compatibility](docs/COMPATIBILITY.md) for release verification and coverage.
See Emit's [PACKAGES.md](https://github.com/bwbensonjr/emit/blob/main/docs/PACKAGES.md)
for where files go, the safety rules, and recovery.

The user library root is `$XDG_DATA_HOME/emit/lib` when `XDG_DATA_HOME` is set to an
absolute path, and `~/.local/share/emit/lib` otherwise, on macOS and Linux alike. Every
`emit` process finds it with no environment setup, and `emit doctor` lists it as a
`user` provider. A project's own `lib/`, its manifest, `-L` roots, and
`EMIT_LIBRARY_PATH` all take precedence over it, so a project can vendor or patch its
own copy. Emit's verbose resolution narration (`EMIT_VERBOSITY=verbose`) names the root
each library came from.

### From a checkout

To install from a branch, an older commit, or local edits, point `emit pkg` at a
checkout:

```sh
git clone https://github.com/bwbensonjr/emit-packages ~/src/emit-packages
emit pkg install --from ~/src/emit-packages malt
```

**Emit 0.12.x** has no `emit pkg`. Link the checkout's `lib/` at the user library root
instead, and update with `git -C ~/src/emit-packages pull`:

```sh
mkdir -p ~/.local/share/emit
ln -s ~/src/emit-packages/lib ~/.local/share/emit/lib
```

`emit pkg` refuses to write through that link, so to switch to it later, remove the
link and run `emit pkg install`.

**Emit 0.11.x and earlier** have no user library root. Point `EMIT_LIBRARY_PATH` at
the checkout instead, which also works on later versions as an override:

```sh
export EMIT_LIBRARY_PATH="$HOME/src/emit-packages/lib"
```

Emit 0.10.x also ships an older copy of Malt in its installed library root;
`EMIT_LIBRARY_PATH` is searched before that root, so the collection's copy wins.

## Layout

```
lib/                      one library root: the union of every package's libraries
  malt/learner.sld
  malt/learner/*.sld
packages/
  <name>/
    package.scm           metadata: name, version, license, minimum Emit, libraries
    checks.scm            execution-path checks (contract below)
    LICENSE, PROVENANCE.md
    tests/                check programs and package-level tests
    docs/
tools/
  run-checks.py           runs every package's checks against a given emit
  test-packages.sh        runs every package's tests/package-tests.sh
  install-check.py        installs every package with emit pkg and imports its libraries
```

A package's libraries go under `lib/`, never under `packages/<name>/`, so the whole
collection stays one root.

## The `checks.scm` contract

Each package declares its execution-path checks in `packages/<name>/checks.scm`,
a file holding one list:

```scheme
((check NAME (program "tests/file.scm") (expect "(final-datum ...)"))
 ...)
```

- `program` is relative to the package directory. It is an ordinary Scheme
  program that checks its own results and prints a completion datum as its final
  non-blank stdout line.
- A driver runs each program with exactly two library roots, the collection's
  `lib/` and the package's `tests/` directory (for private helper libraries), and
  no project manifest.
- A check passes on an execution path when that path's final non-blank stdout
  line equals `expect` exactly. A nonzero exit or any other final line fails.

The collection owns the format and its readers. `tools/run-checks.py EMIT` runs
all declared checks through `emit run`, scripted `emit repl`, a standalone executable,
published artifacts, and package-manager-installed sources. Artifact validation
requires reuse of each declared library the program loads; source fallback fails.
`tools/run-checks.py --source EMIT_SOURCE` runs the same checks through that source
tree's Chez compiler driver. Neither format changes nor collection updates need a
paired Emit change.

## Testing

```sh
python3 tools/run-checks.py "$(command -v emit)" --report /tmp/package-paths.json
bash tools/test-packages.sh "$(command -v emit)"
python3 tools/install-check.py "$(command -v emit)" --report /tmp/package-lifecycle.json
python3 tools/run-checks.py --source ../emit --report /tmp/package-source.json
```

`install-check.py` verifies available/install/list/import/update/remove with local
collection sources. It proves update restores modified package-owned installed
files and the next compilation observes the restored behavior. The drivers use
isolated temporary user roots and caches, leaving your installed packages alone.
All current declared checks run, including comparator checks. Unknown packages,
empty selections, and explicitly requested source checks without Chez fail.

CI resolves one latest stable Emit release and verifies that Homebrew on macOS and
Nix's promoted default package on Linux both report that version. A lagging channel
fails visibly. Native checks run on PRs, main pushes, weekly schedules and manual
dispatch. Source-reference checks run weekly and manually. Reports retain tested
identities and results on success and failure. None needs Racket or an upstream
checkout. See [Compatibility](docs/COMPATIBILITY.md) for commands, prerequisites,
CI ownership, and the coverage handoff from Emit.

## License

Each package carries its own license and provenance under `packages/<name>/`.
Malt is MIT-licensed; see [packages/malt/LICENSE](packages/malt/LICENSE).
