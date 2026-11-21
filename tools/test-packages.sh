#!/usr/bin/env bash
# Run every package's package-level tests (packages/*/tests/package-tests.sh)
# against a given emit binary. These are the checks that are not execution-path
# checks: export surfaces, provenance, rejected imports, and similar.
set -euo pipefail
cd "$(dirname "$0")/.."
. tools/log.sh
if [ "$#" -ne 1 ]; then echo "usage: tools/test-packages.sh EMIT" >&2; exit 2; fi
EMIT="$1"
case "$EMIT" in /*) ;; *) EMIT="$PWD/$EMIT" ;; esac
[ -x "$EMIT" ] || { echo "emit binary not executable: $EMIT" >&2; exit 2; }
start=$SECONDS
count=0
for script in packages/*/tests/package-tests.sh; do
  [ -e "$script" ] || continue
  package="$(basename "$(dirname "$(dirname "$script")")")"
  say "test package $package -> $script"
  bash "$script" "$EMIT"
  count=$((count + 1))
done
say "verify package tests -> $count packages passed [$((SECONDS - start))s]"
