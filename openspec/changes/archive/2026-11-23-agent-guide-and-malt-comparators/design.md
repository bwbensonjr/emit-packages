# Design

## Context

See proposal.md for motivation. Relevant current state:

- `lib/malt/learner/operations.sld` already defines and exports the base-rank
  comparators `=-0-0 <-0-0 <=-0-0 >-0-0 >=-0-0` (via `comparator`, which compares
  `primal` values). The facade `lib/malt/learner.sld` re-exports them under those
  names only.
- `(- 13 4)` under the facade returns a scalar dual, confirmed with Emit 0.13.0:
  `(dual? (- 13 4))` is `#t`, and base `zero?` on it fails with `=: not a number`.
- Upstream `main.rkt` (revision `92a3e63`) renames the five `-0-0` comparators to
  `= < <= > >=`. Upstream does not override `zero?`, `positive?`, or `negative?`.
- `packages/malt/docs/MALT.md` states "The facade leaves ordinary `= < > <= >=`
  unchanged"; that sentence is reversed by this change.
- Explicit-base programs exist in `tests/unprefixed.scm`, `tests/notation.scm`, and
  the `MALT.md` example, all excluding `+ - * / abs max expt`.
- `tests/malt-core-exports.py` pins the `operations` export list exactly, and
  `tests/reference/check.py` requires the facade's exports to equal the keys of
  `tests/reference/export-map.json`.
- Emit validates a pinned commit of this repo (`tools/emit-packages-pin.sh`,
  `tools/emit-packages.py`), running each package's `checks.scm`. Adding a check is
  within the existing `checks.scm` contract, so no Emit driver change is needed.

## Goals / Non-Goals

**Goals:**
- Plain recursive numeric code keeps working after `(import (malt learner))`.
- Upstream parity for the comparator names.
- One `CLAUDE.md` that tells an agent how to develop, test, release, and coordinate
  with Emit from inside this repository, without duplicating Emit internals that do
  not apply here.

**Non-Goals:**
- Shadowing `number?`, `real?`, `min`, `exact`, `inexact`, `floor`, or other base
  procedures. `max` already means Malt's tensor max, per upstream.
- Making comparators differentiable or changing the tensorized `-1` comparators.
- Changing the `checks.scm` contract or Emit's pinned-collection driver.
- Moving Emit's pin; that is an Emit-side change after this merges.

## Decisions

**D1. Re-export by rename in the facade; define predicates in `operations`.** The
five comparators are added to `learner.sld` as `(rename m:<-0-0 <)` and so on, so
they share binding identity with the `-0-0` names (as upstream's `rename-out` does).
`zero?`, `positive?`, and `negative?` are new definitions in `operations.sld`,
exported from it as `zero?-0`, `positive?-0`, `negative?-0` and renamed in the facade,
built the same way as `comparator`: apply the base predicate to `(primal x)`.
Alternative considered: define everything in the facade. Rejected because the facade
is a pure export list today and `malt-core-exports.py` treats `operations` as the
home of numeric surface.

Naming note: `operations.sld` may not export `zero?` unprefixed internally without
shadowing its own `(scheme base)` import; the `-0` suffix follows the existing
`exp-0`/`abs-0` convention for base-rank scalar operations.

**D2. Include the sign predicates as an Emit addition.** Upstream has the same
failure for `zero?` on duals, but the reported class of bug ("numeric operators
not shadowed") covers it and the Little Learner style counts down with `zero?`.
Recorded in `PROVENANCE.md` and the export map as an Emit adaptation, not upstream.
Alternative: parity only. Rejected as leaving the same trap one name away.

**D3. Treat it as a breaking package change: `0.1.0` to `0.2.0`.** Explicit-base
programs that exclude only arithmetic names will now conflict. There is no way to
add exports to a facade without that, and the conflict is a compile-time diagnostic
rather than silent behavior change. Implicit-base programs and the REPL (the
documented primary path) only gain behavior.

**D4. Reproduce the report as an execution-path check.** New
`tests/comparators.scm` runs the reported `remainder` program verbatim (implicit
base, like `direct.scm`) plus the spec scenarios, and is added to `checks.scm`, so it
runs under `emit run`, `emit repl`, and `emit build`, here and in Emit's pinned
suite. The REPL path matters because the report came from `emit repl`.

**D5. `CLAUDE.md` content is curated, not copied.** It carries what applies to this
repo and links to Emit for the rest:
- What the repo is and its layout pointer (README holds the detail).
- Testing: the three `tools/` commands, which emit to point them at (Homebrew,
  Nix-built, or a local `~/src/.../emit/build/emit`), `EMIT_TEST_KEEP`, and that
  Racket is only needed for `reference/check.py --upstream`.
- Release model: `main` is the release (`emit pkg update` delivers it), the
  required `Package checks` status, and bumping `package.scm` `version` per
  SemVer for any change to a package's shipped libraries (adapted from Emit's
  versioning rule; docs/tests/CI-only changes take no bump).
- Coordination with Emit: the pin (`tools/emit-packages-pin.sh`), testing an
  unpushed collection change from an Emit checkout with
  `EMIT_PACKAGES_DIR=../emit-packages python3 tools/emit-packages.py`, and that a
  `checks.scm` contract change must land in Emit's driver too.
- Conventions: OpenSpec for changes; correctness defects as GitHub issues (`gh`,
  account `bwbensonjr`); tool narration via `tools/log.sh` per Emit's
  `docs/OUTPUT.md`; Emit's terminology (command/verb, execution path); comment
  placement; Python style per the user's global instructions is not repeated.
- Emit-only material is omitted: `make regen`, bootstrap IR, LLVM, the formatter pin
  (pitch is not wired up here; noted as optional, not a gate).
Alternative: a symlink or include of Emit's `CLAUDE.md`. Rejected: most of it is
compiler-build guidance that would mislead work here.

## Risks / Trade-offs

- [Existing explicit-base user programs break on `emit pkg update`] -> Compile-time
  conflict naming the binding; `MALT.md` shows the new exclusion list; version bump
  and README note.
- [Emit's pinned suite moves to a commit whose `unprefixed.scm` and `notation.scm`
  changed] -> They are self-contained programs under the unchanged contract; Emit's
  pin bump runs `--suite emit-packages-pinned` before landing.
- [Emit 0.10.x REPL prefers its bundled older Malt unless `EMIT_LIBRARY_PATH` is set]
  -> Out of scope; the README already documents the override.
- [`CLAUDE.md` drifts from Emit's docs] -> Link to Emit's documents for detail and
  keep only collection-specific facts inline.

## Migration Plan

Merge to `main` (this is the release). Users run `emit pkg update`. Programs with
explicit `(scheme base)` imports add `= < <= > >= zero? positive? negative?` to their
`except` list. Rollback is a revert on `main` followed by `emit pkg update`. Emit
moves its pin separately.
