# collection-compatibility Specification

## Purpose

Defines how emit-packages maintains its published tip against released Emit, owns package execution-path coverage, and provides evidence independently of Emit's validation gates.

## Requirements

### Requirement: The collection owns published-tip compatibility

emit-packages SHALL maintain `main` as the package source compatible with the latest stable released Emit. Publishing collection changes SHALL require collection-owned checks without a paired Emit pull request, collection pin update, or Emit release. Packages SHALL declare a minimum Emit when they require version-specific functionality.

#### Scenario: A package update publishes independently

- **WHEN** a collection change passes its required compatibility checks and merges to `main`
- **THEN** an unchanged supported Emit installation can obtain it through `emit pkg install` or `emit pkg update` without changing Emit's source or release

#### Scenario: A package needs a new compiler feature

- **WHEN** a package starts using functionality introduced in a newer Emit version
- **THEN** the package declares a sufficient minimum version and its publication checks run against a stable release containing that functionality
- **AND** documentation distinguishes the declared minimum from the latest stable version actually tested

### Requirement: Native CI validates one resolved stable release

Each native compatibility workflow run SHALL resolve one stable, published Emit release and use that target on both macOS and Linux. Before package checks, each platform SHALL verify its installed Emit reports the target version. Failed resolution, unavailable targets, and version mismatches SHALL fail visibly without substituting a development build or another release.

#### Scenario: Channel promotion lags publication

- **WHEN** the installed Homebrew or Nix Emit reports a version different from the resolved stable release
- **THEN** the platform fails with the expected and actual versions and does not report successful release compatibility

#### Scenario: A release appears between platform jobs

- **WHEN** a newer stable Emit is published after the workflow resolves its target
- **THEN** both platform jobs still validate the original resolved target, or fail if they cannot obtain it

### Requirement: Compatibility gates remain collection-owned

The required `Package checks` status SHALL succeed only when the target-resolution and required native platform jobs succeed. Collection checks SHALL run on pull requests, pushes to `main`, a weekly schedule, and manual dispatch. Scheduled/manual reference checks SHALL exercise the Chez source driver against the stable release resolved for that run.

#### Scenario: A required platform fails or is skipped

- **WHEN** a required native job fails, is cancelled, or is unexpectedly skipped
- **THEN** `Package checks` does not pass

#### Scenario: Emit releases without a collection commit

- **WHEN** the next scheduled collection check runs after a new stable Emit release
- **THEN** it resolves that release and tests the collection against it without requiring an Emit-side dispatch or collection pin update

### Requirement: Native package checks cover every retained execution path

Every declared package check SHALL pass through `emit run`, scripted `emit repl`, a standalone `emit build` executable, published library artifacts, and installed package sources. A path SHALL pass only with exit status zero and an exact final nonblank stdout line matching `expect`. Empty or unknown package/check selections SHALL fail rather than pass vacuously.

#### Scenario: One execution path changes a result

- **WHEN** one path exits nonzero or its final result differs from `expect`
- **THEN** validation fails and identifies the package, check, path, expected result, actual result, and exit status

#### Scenario: Installed execution uses package-manager placement

- **WHEN** a package check runs on the installed-source path
- **THEN** its package is installed into a temporary user root with `emit pkg install --from`, and its libraries resolve from that root without access to the collection's `lib/` as an import root
- **AND** private test helper libraries remain available from a separate test root

### Requirement: Artifact checks prove reuse of published libraries

Artifact checks SHALL publish every library a package declares and run against those artifacts. Each declared library loaded by the check SHALL be reported as reused from its published artifact, at least one declared library SHALL be reused, and any loaded declared library compiled from source instead SHALL fail the check.

#### Scenario: A result is correct only through source fallback

- **WHEN** a check prints its expected result but a loaded declared library was compiled from source
- **THEN** artifact validation fails naming that library

#### Scenario: A published library cannot be produced

- **WHEN** publication of any declared library fails or produces no usable artifact
- **THEN** the artifact path fails before accepting execution output as evidence

### Requirement: Source-driver checks require explicit prerequisites

A developer SHALL be able to select source-driver validation using an explicit Emit source tree. Every selected package check SHALL run through its Chez compiler driver and match the same declared `expect`. Missing Chez, missing driver files, empty selections, or compiler failures SHALL fail explicitly. Scheduled/manual release reference runs SHALL verify the source tree's version matches the resolved target.

#### Scenario: Chez is unavailable

- **WHEN** source-driver validation is explicitly selected and Chez is unavailable
- **THEN** the command exits nonzero naming the missing prerequisite, without reporting a successful skip

#### Scenario: The supplied release sources are stale

- **WHEN** reference CI obtains a source tree reporting a version different from its resolved stable target
- **THEN** the run fails naming both versions before treating its package results as release evidence

### Requirement: Package lifecycle validation includes update behavior

Collection lifecycle checks SHALL verify `available`, install, list, update, imported behavior after update, and removal using temporary user roots and local sources. Update validation SHALL prove package-owned installed sources were replaced and the next compilation observes the restored collection behavior. Checks SHALL leave the developer's checkout, user root, and caches unchanged.

#### Scenario: Update restores modified installed code

- **WHEN** a lifecycle check modifies a package-owned installed library and runs `emit pkg update --from` the collection
- **THEN** owned files again match the collection and the next compilation of a package check produces its expected result

#### Scenario: Removal cleans up the updated package

- **WHEN** lifecycle validation removes packages after their successful update
- **THEN** they are absent from the installed list and no package-owned library files remain

### Requirement: Compatibility evidence identifies its inputs and coverage

Compatibility reports SHALL identify the collection revision and dirty state, tested Emit version, native binary or source-tree identity, selected packages/checks/paths, results, and durations. CI SHALL retain reports and release-target identity on failure as well as success. Documentation SHALL map transferred Emit coverage IDs to collection-owned commands and triggers.

#### Scenario: Maintainers review the handoff

- **WHEN** maintainers inspect the implementation's native and reference evidence
- **THEN** it names the tested collection revision and stable Emit target and accounts for Malt core, training, XOR, source-driver, artifact-reuse, and installed-package coverage
- **AND** the reports do not imply that a local development Emit build proves stable-release compatibility
