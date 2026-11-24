# Compatibility with Emit

emit-packages owns keeping its published `main` compatible with the latest stable
released Emit. A merge reaches users on their next `emit pkg install` or
`emit pkg update`. Publishing a package requires no paired Emit pull request,
collection compatibility pin in Emit, or compiler release.

Each package's `(emit (minimum "X.Y.Z"))` remains a constraint on installation.
Raise it when using newer compiler functionality, and wait until that functionality
is released before relying on it on `main`. The minimum is not a claim that every
older Emit release is in the CI matrix. CI tests the latest stable release. Older
users can upgrade Emit or explicitly select an older checkout with
`emit pkg install --from DIR NAME`.

## Selecting the release under test

The workflow resolves Emit's published stable release once and shares that target
between jobs. It does not use package-collection tags or a checked-in Emit version
to select the target.

```sh
python3 tools/emit-release.py resolve --output /tmp/emit-target.json
python3 tools/emit-release.py verify --target /tmp/emit-target.json --emit "$(command -v emit)"
```

Native CI uses Homebrew on macOS and Nix's default Emit package on Linux. The
default Nix package builds its promoted source release; the flake's `candidate`
package instead builds development sources. Both jobs verify `emit --version`
against the resolved target before accepting package results.

If a channel has not promoted that release yet, verification fails with the
expected and actual versions. Retry after promotion. CI never silently tests an
older release or substitutes a development binary. A release published midway
through a run does not change that run's target.

## Local checks

Choose the binary explicitly. A local development Emit is useful for investigating
compiler changes, but only version-verified CI runs establish latest-stable release
compatibility.

```sh
python3 tools/run-checks.py "$(command -v emit)" --report /tmp/package-paths.json
bash tools/test-packages.sh "$(command -v emit)"
python3 tools/install-check.py "$(command -v emit)" --report /tmp/package-lifecycle.json
```

The execution runner uses every declared `checks.scm` check on five native paths:
`emit run`, scripted `emit repl`, a standalone executable, published artifacts,
and package-manager-installed sources. `--package NAME` limits an investigation
to one package; unknown or empty selections fail. Each executed path must exit
successfully and print its declared `expect` as the final nonblank stdout line.

The artifact path publishes all declared libraries and requires proof that every
declared library the check loads was reused from its artifact. Correct output
through source fallback is a failure. The installed path uses a temporary user
root and an unrelated working directory; only private test helper libraries get
an extra root. It cannot obtain package libraries from the collection checkout.

The lifecycle check verifies available/install/list/import/update/remove. It runs
package checks from installed sources, modifies an installed owned library in its
temporary root to prove the change is observed, updates from the unmodified
collection, checks restored files, and repeats package checks using the same cache.
Removal must leave no installed records or owned files.

These drivers isolate HOME, the user library root, and caches, clearing inherited
library, manifest, and package-download overrides. They do not modify the
collection's libraries or the developer's installed packages. JSON reports record
the collection revision and dirty state, actual binary/source identity, selected
packages and checks, executed paths, results, and durations, including failures.
Narration is on stderr and follows `EMIT_VERBOSITY`.

## Independent source-driver verification

Select an Emit source tree explicitly; the runner uses a temporary source workspace
so the supplied checkout is not a build destination:

```sh
python3 tools/run-checks.py --source ../emit --report /tmp/package-source.json
```

This runs the same package checks through that tree's Chez compiler driver and
compares the same expected output. It requires `chez` plus Emit's LLVM/libgc build
prerequisites. Missing prerequisites or compiler failures exit nonzero; an explicit
source request never becomes a successful skip.

For release evidence, reference CI obtains the resolved release's published source
archive and checksums and verifies its `VERSION` before testing:

```sh
source_dir=$(python3 tools/emit-release.py fetch-source --target /tmp/emit-target.json --output-dir /tmp/emit-source)
python3 tools/emit-release.py verify --target /tmp/emit-target.json --source "$source_dir"
python3 tools/run-checks.py --source "$source_dir" --report /tmp/package-source.json
```

## CI ownership and coverage transfer

`.github/workflows/checks.yml` runs native checks on pull requests, pushes to
`main`, weekly schedules, and manual dispatch. The required `Package checks`
status accepts only successful release resolution and both native platform jobs;
failure, cancellation, and unexpected omission fail it. The source-reference job
runs weekly and on manual dispatch. Its ordinary omission on PR/push events is
intentional; a selected reference job's failure remains visible and fails the
workflow. CI retains the target and reports even when validation fails.

| Retiring Emit coverage | Collection-owned command | Trigger |
| --- | --- | --- |
| `malt-core`, `malt-training`, `malt-xor` | `tools/run-checks.py EMIT`, corresponding `checks.scm` entries on all five native paths | PR, main push, weekly, manual |
| `malt-core-source`, `malt-training-source`, `malt-xor-source` | `tools/run-checks.py --source EMIT_SOURCE`, same entries | Weekly/manual source-reference job |
| Malt semantics within `malt-installed` | Installed-source execution and `tools/install-check.py EMIT` | Required native platform jobs |
| Artifact publication and loaded-library reuse | Artifact path of `tools/run-checks.py EMIT` | Required native platform jobs |
| Generic installed-library, provider, and SRFI 27 checks | Remain in Emit with Emit-owned fixtures | Emit's own gates |

The legacy IDs identify the transfer; they do not limit the check list. All current
checks, including comparator checks, run. Package-level export, provenance, and
import-conflict tests remain in `tools/test-packages.sh`.

The companion Emit change is `decouple-package-collection`. Its maintainers can
review this coverage map and passing native/reference run URLs before retiring
their collection gates. Future changes to `checks.scm` and its readers belong to
this repository. An Emit compiler defect found here should get a small independent
reproduction and an issue in `bwbensonjr/emit`.
