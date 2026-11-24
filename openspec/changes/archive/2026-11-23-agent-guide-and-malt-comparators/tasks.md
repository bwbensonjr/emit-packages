# Tasks

## 1. Malt comparators and sign predicates

- [x] 1.1 Add a failing execution-path check first: write `packages/malt/tests/comparators.scm` (implicit base) covering the reported `remainder` program and every scenario in `specs/malt-learner-surface/spec.md` except the explicit-base ones, printing `(malt-comparators N)`; add it to `packages/malt/checks.scm`; verify `tools/run-checks.py "$(command -v emit)"` fails on it with `<: not a number`
- [x] 1.2 Define `zero?-0`, `positive?-0`, `negative?-0` in `lib/malt/learner/operations.sld` (base predicate on `primal`), add them to its export list and to the `operations` inventory in `packages/malt/tests/malt-core-exports.py`; verify `python3 packages/malt/tests/malt-core-exports.py` passes
- [x] 1.3 Export `= < <= > >=` (renames of `m:=-0-0` ... `m:>=-0-0`) and `zero? positive? negative?` from `lib/malt/learner.sld`; verify the new check from 1.1 passes on `emit run`, `emit repl`, and `emit build` via `tools/run-checks.py`
- [x] 1.4 Add the eight names to `packages/malt/tests/reference/export-map.json` (group "Comparisons"; comparators cite `main.rkt` rename-out, predicates marked as Emit additions); verify `python3 packages/malt/tests/reference/check.py` passes
- [x] 1.5 Extend the explicit-base `except` lists in `packages/malt/tests/unprefixed.scm` and `packages/malt/tests/notation.scm` to `+ - * / abs max expt = < <= > >= zero? positive? negative?`; verify `malt-unprefixed` and `malt-notation` checks pass
- [x] 1.6 In `packages/malt/tests/package-tests.sh`, add a rejection case importing `(except (scheme base) + - * / abs max expt)` with `(malt learner)` that must fail with a conflict diagnostic; verify `tools/test-packages.sh "$(command -v emit)"` passes
- [x] 1.7 Update `packages/malt/docs/MALT.md` (new `except` list in the portable example; replace "The facade leaves ordinary `= < > <= >=` unchanged" with the new comparator and predicate behavior) and `packages/malt/PROVENANCE.md` (comparator renames follow upstream `main.rkt`; sign predicates are Emit additions); verify the documented portable example runs with `emit run -L lib`
- [x] 1.8 Bump `packages/malt/package.scm` version to `0.2.0`; verify `python3 tools/install-check.py "$(command -v emit)"` passes and reports `malt 0.2.0`
- [x] 1.9 Reproduce the original report in a REPL: `printf '(import (malt learner))\n(define (remainder x y) (if (< x y) x (remainder (- x y) y)))\n(remainder 13 4)\n' | emit repl -L lib` prints `1` with no trap

## 2. Agent guide (CLAUDE.md / AGENTS.md)

- [x] 2.1 Write `CLAUDE.md` with the sections in design D5: repo purpose and layout pointer; testing commands and which `emit` binary to use; release model (`main` is the release, required `Package checks` status, `package.scm` SemVer bump rule); coordination with Emit (pin file, `EMIT_PACKAGES_DIR=../emit-packages python3 tools/emit-packages.py`, `checks.scm` contract changes need an Emit driver change); conventions (OpenSpec, GitHub issues with `gh` as `bwbensonjr`, `tools/log.sh` narration per Emit `docs/OUTPUT.md`, terminology, comment placement); verify every command and path it names exists in this repo or in Emit at the stated location
- [x] 2.2 Confirm `AGENTS.md` is still a symlink to `CLAUDE.md` (`readlink AGENTS.md` prints `CLAUDE.md`) and remove the stray editor backup `CLAUDE.md~`; verify `git status` shows neither the backup nor a replaced `AGENTS.md`

## 3. Integration

- [x] 3.1 Run all three suites against the installed Emit: `tools/run-checks.py`, `tools/test-packages.sh`, `tools/install-check.py`; verify all pass
- [x] 3.2 From an Emit checkout, run `EMIT_PACKAGES_DIR=../emit-packages python3 tools/emit-packages.py` and verify every check passes in the UNPINNED run
- [x] 3.3 Run `openspec validate agent-guide-and-malt-comparators --strict` and verify it passes

## Workflow follow-up

- Open one pull request; merging it to `main` releases Malt 0.2.0 to `emit pkg update` users.
- Archive the change after merge.
- In Emit, move `tools/emit-packages-pin.sh` to the merged commit and run `bash tools/test.sh --suite emit-packages-pinned`.
