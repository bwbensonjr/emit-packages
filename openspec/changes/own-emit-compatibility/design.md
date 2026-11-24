# Design

## Context

See `proposal.md` for motivation and the companion Emit change `decouple-package-collection` for the consumer-side removal of its pin. The collection already publishes `main`, declares minimum versions in `package.scm`, and owns macOS/Linux checks plus weekly/manual triggers.

`tools/run-checks.py` runs declared checks through run, REPL, and build. Emit's `tools/emit-packages.py` additionally exercises published artifact reuse, installed package execution, and the Chez source driver. `tools/install-check.py` covers available/install/list/import/remove, but not update. Both collection tools need stronger environment isolation and explicit protection against empty selections when extended.

One correction to the companion's initial investigation: `nix build github:bwbensonjr/emit` evaluates the default-branch flake, but that flake's default package consumes the promoted release archive in `packaging/release.json`; development sources are its separate `candidate` package. Neither Homebrew nor Nix currently verifies its installed version against a shared latest-stable target. The risk is channel lag or different releases, rather than necessarily compiling development Emit on Linux. Use this corrected premise when applying the Emit companion.

## Goals / Non-Goals

**Goals:** Own compatibility evidence entirely in this collection; preserve every transferred check; keep local checks usable with an explicitly chosen binary or source tree; make release-version mismatches visible.

**Non-Goals:** Per-Emit historical package selection, a registry service, new package tags, changes to either manifest format, support for unreleased Emit features on published `main`, compiler changes, and recurring Emit-side coordination.

## Decisions

### 1. Resolve the stable target once and verify installed channels

Add a small collection-owned release helper with resolution and verification operations. Resolution reads Emit's published stable-release metadata, rejects drafts/prereleases or malformed identities, and emits a JSON record with version, tag, source asset URL, and checksum asset URL. All jobs consume that record; none resolves independently. The exact API implementation remains encapsulated in this helper and is tested with local metadata fixtures.

Keep Homebrew on macOS and Nix's promoted default package on Linux. Verify the numeric version from `emit --version` against the selected target before running package checks. The initial policy is to fail visibly on channel lag, naming expected and actual versions and how to retry after promotion; no implicit source-build fallback or older-target fallback is introduced. This makes channel propagation an explicit CI limitation without adding another build system here.

Reference CI downloads the selected release's source archive and published checksums, verifies the archive, then checks `VERSION` against the same target. Provision the matching native compiler dependencies and Chez independently; bootstrap regeneration is unnecessary to exercise `src/compile.ss`.

Alternative: assume the two channels are always current. This cannot prove which release was tested. Alternative: record an Emit version/hash in the collection and update it manually per release. Resolve at run time instead; exact versions and checksums live in evidence, not a maintenance pin.

### 2. Extend existing runners and preserve their default entry points

Keep `tools/run-checks.py EMIT [--package NAME]` for native validation. Its default paths become run, REPL, build, artifacts, and pkg. Add `--source EMIT_SOURCE` as an alternative to the positional binary for source-driver validation, retaining `--package`. Source mode requires Chez and the selected tree's driver; it does not silently fall back to the binary. Add `--report FILE` to both modes and the lifecycle tool.

Reuse the small S-expression readers and declared checks; do not change `checks.scm`. Read declared libraries from `package.scm`, publish them in dependency order, and keep test helper libraries separate. Native artifact checks must use the supplied installed Emit's standard libraries, not a sibling checkout's `lib/`. Transfer the useful logic from Emit's driver while removing its repository-relative compiler paths, fetch/cache logic, and pin concept.

Artifact execution uses an explicit temporary manifest and fresh caches, with verbose diagnostics captured for proof. Require each declared library loaded by the program to be reported as reused; source fallback, missing reuse proof, no declared libraries loaded, publication failure, or missing artifact output fails. Exact diagnostic parsing belongs in one tested helper because it depends on Emit's public narration.

For pkg execution, install the package from this checkout into a temporary user root, run from an unrelated temporary directory, and supply only the package test-helper root. No collection library root or manifest may mask a missing installed file. Source mode invokes the chosen tree's `src/compile.ss`, with its `src` library directory, to build and run the same programs and compare the same expected results.

All modes isolate `HOME`, `XDG_DATA_HOME`, and `EMIT_CACHE`; remove inherited library/manifest and package-download overrides. Preserve required system toolchain configuration. Reject unknown package selections, a package missing its checks, or zero selected checks before reporting success. Reports record paths actually executed, including failures; skipped paths never count as passes.

Alternative: retain the Emit driver as an external test service. This would preserve two owners and the coordination rule the user wants to remove. Alternative: copy a Malt snapshot into Emit. Package semantics belong here.

### 3. Prove update with installed state, without changing package releases

Extend `tools/install-check.py EMIT` by default. After the existing install/list checks, run declared package checks from installed sources, then modify one owned installed `.sld` per package to produce a controlled failure when imported. Confirm the modified import fails, update from this unmodified checkout with `emit pkg update --from ROOT`, compare all owned installed files to the declared collection file set, and run package checks again with the same isolated cache so the next compilation must see restored sources. Retain import probes for every declared library and clean removal assertions.

Only files within the temporary installed root are modified. A runner regression uses a small synthetic two-revision collection to show changed behavior after update; it does not invent or publish a new Malt version. Emit's own companion tests fresh network-tip resolution; collection checks focus on package content and ownership.

Alternative: rewrite a real manifest/library version in the checkout to simulate publishing. It adds unnecessary mutation and version policy concerns to compatibility checks.

### 4. Integrate native and reference gates without a cycle

Add a release-resolution job to `.github/workflows/checks.yml`; macOS and Linux depend on it. Preserve the exact required status name `Package checks`, and make its aggregate reject failed, cancelled, or unexpectedly skipped target/platform jobs. Continue PR, main-push, weekly, and manual triggers.

Add a source-reference job to that workflow on weekly/manual events, using the same resolved target. It has its own visible result and retained evidence; intentional omission on PR/push events does not make the native aggregate fail. Keeping it in the existing dispatchable workflow allows reference evidence for a feature branch before merging. Reference failures remain failures of the reference job and overall workflow. Do not require an Emit repository workflow dispatch or token with write access.

Add JSON evidence for collection commit/dirty state, Emit version and executable/source identity, selected paths and checks, result details, and durations. Upload target and reports even after failure. Local development binaries are allowed, labelled with their actual identity; only CI's version-verified runs claim latest-stable compatibility. Narration remains on stderr following `EMIT_VERBOSITY`; JSON goes to the explicit report file.

Alternative: run source compilation on every native matrix cell. Scheduled/manual reference coverage preserves the intended independent-host check without multiplying its cost.

### 5. Publish an explicit coverage handoff

Add `docs/COMPATIBILITY.md` with commands, target policy, triggers, failures, and the transfer table below. README and `CLAUDE.md` link to it and remove the pin/update coordination rule. Edit `CLAUDE.md`, preserving the `AGENTS.md` symlink.

| Emit coverage being retired | Collection owner after implementation | Trigger |
| --- | --- | --- |
| `malt-core`, `malt-training`, `malt-xor` | Corresponding `checks.scm` entries via `tools/run-checks.py EMIT`, including artifacts and pkg | PR, main push, weekly, manual |
| `malt-core-source`, `malt-training-source`, `malt-xor-source` | Same entries via `tools/run-checks.py --source EMIT_SOURCE` | Weekly and manual reference job |
| Malt semantics within `malt-installed` | Installed-source execution plus `tools/install-check.py EMIT` | Required native platform jobs |
| Generic installed-library and SRFI 27 checks | Remain in Emit, using its own fixtures | Emit's own gates |

Run every current declared check, including newer comparator checks; the table identifies legacy IDs, not a filter. Provide native and reference run URLs and identities in the companion handoff. No Emit-maintained collection hash is required. Emit can remove its old gates only after it verifies this handoff; this collection change does not wait on that removal to work.

## Risks / Trade-offs

- Channel promotion can lag the latest source release. Mitigation: fail with expected/actual identity and retry after the appropriate channel is promoted; do not claim a different release was tested.
- A new Emit release can break current collection `main` before a scheduled run detects it. Mitigation: retain weekly/manual runs and maintain compatibility fixes here; no atomic two-repository release guarantee is introduced.
- Artifact narration can change between Emit releases. Mitigation: isolate parsing, fail on missing proof, and cover rejection with runner fixtures.
- Source checks require LLVM/libgc as well as Chez. Mitigation: provision declared prerequisites, retain diagnostics, and fail explicit requests rather than skip.
- Older Emit versions remain outside the latest-stable CI promise. Mitigation: keep minimum declarations truthful and document explicit older-checkout installation without adding history resolution.

## Migration Plan

1. Implement and locally verify release-target identity, runner paths, lifecycle update checks, reports, and contributor documentation in this repository. No package library or version bump is needed.
2. Prepare an independently reviewable collection PR and obtain passing macOS/Linux native plus manually dispatched reference evidence for the same stable Emit target. Keep evidence links in the review handoff, rather than baking a collection revision into Emit.
3. After collection review/merge, resume Emit's `decouple-package-collection`, using this change's command/coverage map and evidence. Its implementation should also correct the initial Nix interpretation noted above.

Rollback can restore collection testing tools or CI without changing installed packages. Once Emit retires its suites, coverage must remain collection-owned during any repair; rollback is not a reason to leave the transferred paths unowned.
