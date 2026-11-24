# Proposal

## Why

emit-packages publishes `main` for `emit pkg install` and `update`, but still relies on an Emit-owned pinned collection suite for part of its compatibility coverage. Owning that coverage here lets packages advance without a paired Emit pull request, collection hash update, or compiler release.

## What Changes

- Make the collection responsible for keeping published `main` compatible with the latest stable released Emit. Retain per-package minimum-version declarations and document the tested release target separately from the minimum.
- Resolve the stable Emit release once per CI run and verify both macOS and Linux test that version. Preserve the required `Package checks` status, weekly runs, and manual runs; report channel lag explicitly instead of accepting a different version.
- Extend collection-owned checks to cover published library artifact reuse and installed package execution, preserving the checks currently hosted in Emit.
- Add an explicit Chez source-driver mode with a supplied Emit source tree, exercised in scheduled/manual reference CI against the resolved stable release. Explicit reference requests fail on missing prerequisites.
- Exercise `emit pkg update --from` and verify the next import sees restored package sources, alongside existing available/install/list/remove checks.
- Replace pin-oriented contributor instructions and the two-repository `checks.scm` maintenance rule with collection-owned testing instructions and an auditable coverage handoff.

## Capabilities

### New Capabilities

- `collection-compatibility`: published-tip compatibility ownership, release-target validation, native/reference execution checks, package installation/update checks, and evidence reporting.

### Modified Capabilities

None. The existing `malt-learner-surface` behavior is unchanged.

## Impact

- `.github/workflows/checks.yml`, a collection-owned reference workflow, `tools/run-checks.py`, `tools/install-check.py`, supporting test tooling, `README.md`, and `CLAUDE.md` (`AGENTS.md` is its symlink).
- Companion to Emit's `decouple-package-collection` change at `../emit/openspec/changes/decouple-package-collection/`. This change supplies its compatibility handoff; Emit removes its own pin and replaces its own integration checks separately.
- No package library, `package.scm` format, `checks.scm` format, installed package state, or Emit command syntax changes. CI, tests, documentation, and planning require no package version bump.
- This is a planning change only. Its implementation produces independently reviewable collection changes and passing native/reference evidence before Emit retires its collection suites.
