# Proposal

## Why

Two gaps surfaced together. First, `(malt learner)` replaces `+ - * /` with
differentiable versions that return scalar duals, but leaves the base comparators in
place, so ordinary recursive code breaks as soon as it compares a result:

```scheme
(import (malt learner))
(define (remainder x y) (if (< x y) x (remainder (- x y) y)))
(remainder 13 4)   ; <: not a number
```

`(- 13 4)` is a dual and base `<` rejects it; `zero?` fails the same way (`=: not a
number`). Upstream Malt's public module (`main.rkt`) exports `=-0-0 <-0-0 <=-0-0 >-0-0
>=-0-0` renamed to `= < <= > >=` for exactly this reason; the Emit port followed the
narrower `learner.rkt` surface and documented the base comparators as intentionally
unchanged.

Second, this repository's `CLAUDE.md` (and `AGENTS.md`, a link to it) is an empty
heading. The collection was split out of Emit in November 2026, and the conventions
that govern work here (OpenSpec, GitHub issues, tool narration, Emit's pinned
validation of this repo, `main` as the release, CI gating) live only in Emit's
`CLAUDE.md` and `docs/`, or in this README. Agents working here start without them.

## What Changes

- **BREAKING (Malt facade)**: `(malt learner)` exports dual-aware `= < <= > >=`
  (aliases of `=-0-0 <-0-0 <=-0-0 >-0-0 >=-0-0`), matching upstream `main.rkt`.
  Programs that import `(scheme base)` explicitly alongside the facade must now also
  exclude these names; the documented `(except (scheme base) + - * / abs max expt)`
  form becomes `(except (scheme base) + - * / abs max expt = < <= > >=)`.
- As Emit additions, the facade also exports dual-aware `zero?`, `positive?`, and
  `negative?`, which fail on duals today in the same way.
- Malt's package version moves from `0.1.0` to `0.2.0` (incompatible export change).
- Tests: a new execution-path check reproducing the reported program, updated
  explicit-base imports in `unprefixed.scm` and `notation.scm`, export-map entries,
  and the package-level conflict test extended to the new names.
- Docs: `MALT.md` import guidance and comparator paragraph, `PROVENANCE.md`
  adaptation notes.
- `CLAUDE.md` gains the development, testing, release, and coordination guidance
  agents need in this repository, adapted from Emit's `CLAUDE.md`,
  `docs/DEVELOPMENT.md`, `docs/PACKAGES.md`, and `docs/OUTPUT.md`. `AGENTS.md` stays a
  symlink to it.

## Capabilities

### New Capabilities
- `malt-learner-surface`: the public binding surface of the `(malt learner)` facade,
  including which base names it shadows with dual-aware versions and how it composes
  with explicit `(scheme base)` imports.

### Modified Capabilities
(none; `openspec/specs/` is empty in this repository)

The `CLAUDE.md` work is documentation only and has no spec delta.

## Impact

- `lib/malt/learner.sld`, `lib/malt/learner/operations.sld` (new predicate
  definitions and exports).
- `packages/malt/package.scm` (version), `checks.scm` (new check),
  `tests/unprefixed.scm`, `tests/notation.scm`, `tests/package-tests.sh`,
  `tests/malt-core-exports.py`, `tests/reference/export-map.json`, new
  `tests/comparators.scm`.
- `packages/malt/docs/MALT.md`, `packages/malt/PROVENANCE.md`.
- `CLAUDE.md` (and through the link, `AGENTS.md`).
- Users of `emit pkg` receive the change on their next `update`; explicit-base
  programs that exclude only the arithmetic names will get an import conflict.
- Emit: its `emit-packages-pinned` suites see nothing until Emit moves
  `tools/emit-packages-pin.sh`; moving the pin past this change picks up the new
  check and the revised explicit-base tests. Emit 0.10.x's bundled older Malt is
  unaffected.
