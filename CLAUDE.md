# Agent Instructions

`AGENTS.md` is a symlink to this file; edit `CLAUDE.md` only.

## What this repository is

The emit-packages collection: R7RS library packages for the
[Emit](https://github.com/bwbensonjr/emit) Scheme compiler, released independently of
Emit and tested against it. Emit ships only the standard libraries and a few SRFIs;
domain libraries such as Malt (`(malt learner)`) live here. Malt lived in the Emit
repository until November 2026 (see `packages/malt/PROVENANCE.md`).

`README.md` is the reference for layout, installation, and the `checks.scm` contract.
The essentials:

- `lib/` is one library root holding every package's libraries. A package's `.sld`
  files go under `lib/`, never under `packages/<name>/`.
- `packages/<name>/` holds `package.scm` (metadata and the declared library list),
  `checks.scm`, `LICENSE`, `PROVENANCE.md`, `tests/`, and `docs/`.
- `tools/` holds the three drivers below and `log.sh`.

Emit itself is usually checked out beside this repository at `../emit`. Its
`docs/PACKAGES.md` (user side of `emit pkg`), `docs/DEVELOPMENT.md` ("The pinned
emit-packages collection"), and `docs/OUTPUT.md` are the authoritative references for
the topics summarized below.

## Testing

Every driver takes the `emit` binary to test as its only argument:

```sh
tools/run-checks.py "$(command -v emit)"       # execution-path checks: run, repl, build
tools/test-packages.sh "$(command -v emit)"    # package-level tests (exports, provenance, conflicts)
tools/install-check.py "$(command -v emit)"    # emit pkg install/list/remove (Emit 0.13.0+)
```

- Pick the binary deliberately. `command -v emit` is usually Homebrew's release; to
  test against unreleased Emit work, pass `../emit/build/emit`. CI uses the latest
  release (Homebrew on macOS, `nix build github:bwbensonjr/emit` on Linux).
- `run-checks.py` is the slow one: every check runs three times, and `emit build`
  links a native executable per check. For a quick loop on one program, run it
  directly with the same roots the driver uses:
  `emit run -L lib -L packages/<name>/tests packages/<name>/tests/<file>.scm`.
- `EMIT_TEST_KEEP=1` keeps package-test temporary directories for diagnosis.
- None of the drivers needs Racket. Malt's `tests/reference/check.py --upstream`
  regenerates fixtures from a pinned upstream checkout with Racket; it is optional
  and never run by CI.
- A new behavior gets an execution-path check in `checks.scm`: a self-checking
  program whose final stdout line is the expected datum. Keep the `checks.scm`
  format exactly as small as the README describes (see "Coordinating with Emit").
- When a package's facade export list changes, update its pinned inventories too.
  For Malt that is `tests/malt-core-exports.py` (internal libraries) and
  `tests/reference/export-map.json` (every facade export with its upstream source or
  "Emit addition").

## Releases

- **`main` is the release.** `emit pkg install` and `emit pkg update` fetch the
  collection's current `main`, so a merge reaches users on their next update.
  Packages are not tagged; the `v*` tags in this repository are Emit release tags
  carried over with Malt's history.
- `main` requires the single `Package checks` status from
  `.github/workflows/checks.yml`, which passes only when every platform job passed.
  Add a platform as a new job under `needs:`; never change the required status name.
  The workflow also runs weekly so a new Emit release that breaks a package shows up.
- **Bump a package's `version` in `package.scm`** under SemVer in the same pull request
  as any change to its shipped libraries: before 1.0, a new feature or an incompatible
  change (including new facade exports that can conflict with an explicit
  `(scheme base)` import) takes a minor bump, a fix a patch bump. Documentation, test,
  CI, and OpenSpec-only changes take no bump. `emit pkg list` shows this version.
- `package.scm`'s `(emit (minimum ...))` must stay true: a package may not use a
  feature newer than the Emit version it declares without raising it.

## Coordinating with Emit

- Emit validates **one pinned commit** of this repository:
  `EMIT_PACKAGES_PIN_COMMIT` in Emit's `tools/emit-packages-pin.sh`, run by
  `tools/emit-packages.py` in its `emit-packages-pinned` (native) and
  `emit-packages-pinned-source` (Chez source driver) suites. A commit here changes
  nothing in Emit until that pin moves; moving it is a separate, reviewed Emit change
  verified with `bash tools/test.sh --suite emit-packages-pinned`.
- To test an unpushed change here against an Emit checkout, from `../emit`:
  `EMIT_PACKAGES_DIR=../emit-packages python3 tools/emit-packages.py`. The run is
  labelled `UNPINNED` and is not evidence for a pin.
- Emit's driver reads `checks.scm` too and adds an execution path that consumes
  published library artifacts. Any change to the `checks.scm` contract must land in
  Emit's driver as well, so treat it as a cross-repository change.
- A bug in Emit found while working here is filed against `bwbensonjr/emit`, with a
  reproduction that does not need this repository where possible.

## Conventions

- **OpenSpec** tracks designs and tasks (`openspec/specs`, `openspec/changes`). An
  OpenSpec change is for work being started.
- **Correctness defects go in GitHub Issues** (`gh issue list`), not in files or inline
  TODOs. Include a reproduction, the cause with file references, and a possible fix;
  reference the issue from the fixing commit (`Fixes #N`). `gh` may have several
  accounts authenticated: check `gh auth status` and use `bwbensonjr`.
- **Tools narrate what they do**, following Emit's `docs/OUTPUT.md`: lines of the form
  `<verb> <input> -> <output>  [<metrics>]`, narration on stderr, data on stdout,
  verbosity from `EMIT_VERBOSITY` (`quiet`, default, `verbose`). Shell tools source
  `tools/log.sh` for `say` and `vsay`; the Python drivers implement the same levels.
- **Terminology** follows Emit: **command** for `emit run`, `emit repl`, `emit build`,
  `emit lib`, or `emit pkg`, and **verb** only for the selector; **execution path** for
  a way compiled code runs. Do not use "door" as a metaphor.
- **Scheme comments** go on their own line before the code they describe, except for
  very brief notes. Emit formats its own sources with pitch; this repository has no
  formatter gate, so match the surrounding layout by hand.
- Preserve upstream provenance: adapted code keeps its attribution header, and
  `PROVENANCE.md` records every intentional departure from upstream, including Emit
  additions.
