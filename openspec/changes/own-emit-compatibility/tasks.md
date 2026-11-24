# Tasks

## 1. Resolve and verify the stable Emit target

- [x] 1.1 Add a collection-owned release helper that resolves one published stable Emit release into a JSON target record and verifies a supplied binary/source version against it. Add fixture tests for stable selection, draft/prerelease rejection, malformed or unavailable metadata, malformed version output, source-version mismatch, and channel lag. Verify the tests pass with no live network dependency and errors name expected/actual identities.
- [x] 1.2 Document target resolution, latest-stable compatibility ownership, minimum-version scope, and channel-lag failure policy in `docs/COMPATIBILITY.md`; link it from README. Verify the documented helper commands against its help and fixture tests, and describe Nix's promoted default package accurately.

## 2. Transfer execution-path coverage

- [x] 2.1 Extend `tools/run-checks.py EMIT` to publish every declared library and prove artifact reuse for each loaded declared library, using the supplied installed Emit's standard libraries. Add runner fixtures for publication failure, missing artifact output, source fallback, missing reuse proof, and no declared library loaded. Verify fixtures reject those cases even when stdout matches, and a real artifact run passes with reuse counts in its evidence.
- [x] 2.2 Add installed-source execution for every declared check, using `emit pkg install --from` into an isolated user root, an unrelated working directory, and only the package's private helper root. Isolate HOME, user data, manifests, cache, and package download overrides. Verify a valid package passes and a deliberately omitted installed library fails rather than resolving from the checkout or real user root.
- [x] 2.3 Add `tools/run-checks.py --source EMIT_SOURCE` as an alternative to the native binary argument, invoking that tree's Chez compiler driver. Add negative tests for missing Chez, missing driver files, invalid/mutually conflicting invocation modes, missing package checks, unknown packages, and empty selections. Verify all selected declared checks pass against a matching released source tree and explicit prerequisite failures exit nonzero without a successful skip.
- [x] 2.4 Add `--report FILE` and collection/compiler identity, per-check/path results, expected/actual output, exit status, and timing to the runner. Verify success and failure fixture reports accurately account for executed paths and do not count unexecuted paths as passes. Update README's `checks.scm` and command documentation with all five native paths and explicit source mode; preserve the manifest format.

## 3. Verify installed-package updates

- [x] 3.1 Extend `tools/install-check.py EMIT` to run package checks from installed sources, modify only a temporary installed library, prove the modified import fails, update from the unchanged collection, compare restored declared files, rerun checks with the same isolated cache, and retain complete removal checks. Add a small two-revision fixture regression that fails if update leaves old imported behavior or stale owned files. Verify the real lifecycle run passes and the checkout and developer user root remain untouched.
- [x] 3.2 Add lifecycle JSON reporting and the same environment isolation as the execution runner. Verify failure cases retain useful operation/identity diagnostics and failed results. Update README and `docs/COMPATIBILITY.md` with update coverage and temporary-root guarantees; check documented commands match the runner help.

## 4. Wire collection-owned CI and contributor policy

- [x] 4.1 Add shared target resolution and version verification before both native platform jobs in `.github/workflows/checks.yml`; run extended execution, package-level, and lifecycle checks and upload reports/target identity even on failure. Preserve the exact `Package checks` status and reject failed, cancelled, or unexpected skipped required jobs. Verify workflow structure with actionlint and fixture tests of aggregate success/failure cases; inspect both platform logs for the same resolved version.
- [x] 4.2 Add weekly/manual source-reference execution in the same workflow, obtaining the selected release's source archive and checksums, verifying checksum and VERSION, and provisioning Chez plus compiler dependencies. Verify manual feature-branch dispatch runs all declared source checks and retains its report; a missing prerequisite or mismatched target fails visibly. Confirm the reference job is intentionally omitted on ordinary PR/push runs without masking required native failures.
- [x] 4.3 Add the coverage transfer table from design decision 5 to `docs/COMPATIBILITY.md`, and revise README plus `CLAUDE.md` to remove the two-repository check-contract and pin-maintenance instructions. Preserve the `AGENTS.md` symlink. Verify the table covers all retiring Malt IDs, the installed semantics, artifact paths and reference triggers, and a search finds no live instruction to update an Emit collection pin. Historical archives remain unchanged.

## 5. Verify the complete handoff

- [x] 5.1 Run the full extended native runner, package-level tests, and lifecycle checks against one stable released Emit, plus source mode against the matching source tree. Preserve reports and run the negative runner/release-helper tests. Verify every current `checks.scm` entry is accounted for, including comparators, and `openspec validate own-emit-compatibility --strict` plus whitespace checks pass. Confirm package libraries and versions are unchanged.

## Workflow follow-up

- Prepare an independently reviewable collection PR and obtain passing macOS/Linux native workflow results plus manually dispatched source-reference results for the same stable target. Include report artifacts and run URLs in the review handoff; they are evidence, not a checked-in compatibility pin.
- After review and merge, resume Emit's `decouple-package-collection` with the coverage map and evidence. Correct its initial Nix interpretation during that work; the default flake package is promoted release content, while `candidate` is development source.
- Sync and archive this collection change through its own OpenSpec workflow when implementation is complete. Future package updates require only collection-owned review and compatibility checks.

## Validation evidence

- [Manual compatibility run](https://github.com/bwbensonjr/emit-packages/actions/runs/45393655882), 2026-11-24: release resolution, macOS, Linux, Chez reference, and required aggregate all passed against the same resolved Emit 0.13.0 release.
- Retained hosted reports: each native platform passed 35 execution paths and 37 lifecycle operations; the source-reference job passed all 7 declared checks, including comparators.
- Local verification: 41 tooling tests passed, full native/source/lifecycle and package-level checks passed, actionlint and strict OpenSpec validation passed. No package library or package-version files changed.
