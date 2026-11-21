# emit-packages

Packages of R7RS libraries for the [Emit](https://github.com/bwbensonjr/emit) Scheme
compiler. Emit itself ships only the standard libraries and a few selected SRFIs;
domain libraries live here, released on their own schedule and tested against Emit.

| Package | Libraries | Summary |
|---|---|---|
| [malt](packages/malt/docs/MALT.md) | `(malt learner)` | Tensors, reverse-mode automatic differentiation, and training utilities from *The Little Learner* |

## Install

The collection's `lib/` directory is a single Emit library root containing every
package's libraries. Installing is cloning it and telling Emit where it is:

```sh
git clone https://github.com/bwbensonjr/emit-packages ~/src/emit-packages
export EMIT_LIBRARY_PATH="$HOME/src/emit-packages/lib"
```

Then, from any directory:

```sh
$ printf '(import (malt learner))\n(display (gradient (lambda (x) (* x x)) 3.0))\n' > sq.scm
$ emit run sq.scm
6.0
```

`emit run`, `emit repl`, and `emit build` all honour `EMIT_LIBRARY_PATH`. Emit's
`resolve libraries ->` narration lists the roots it searched. A project's own
manifest or `-L` roots still take precedence. Emit 0.10.x also ships an older
copy of Malt in its installed library root; `EMIT_LIBRARY_PATH` is searched
before that root, so the collection's copy wins.

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

Two drivers read this file:

- `tools/run-checks.py EMIT` here, which runs every check through `emit run`,
  `emit repl`, and a standalone `emit build` executable.
- Emit's pinned-collection suite, which runs the same checks against its freshly
  built compiler, adds a path that consumes published artifacts of every library
  in `package.scm`, and adds its Chez source driver in the reference profile.

Keep the format this small. Emit validates a pinned commit of this repository, so
any change to the contract has to land in Emit's driver as well.

## Testing

```sh
tools/run-checks.py "$(command -v emit)"       # execution-path checks
tools/test-packages.sh "$(command -v emit)"    # package-level tests
```

CI runs both against the latest Emit release. Neither needs Racket or an
upstream checkout.

## License

Each package carries its own license and provenance under `packages/<name>/`.
Malt is MIT-licensed; see [packages/malt/LICENSE](packages/malt/LICENSE).
