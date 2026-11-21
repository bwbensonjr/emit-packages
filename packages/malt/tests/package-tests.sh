#!/usr/bin/env bash
# Malt package-level tests: export surface, provenance and reference fixtures,
# rejected imports, and the explicit-base import conflict. Racket is used only by
# `reference/check.py --upstream`, which this script never passes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../../.." && pwd)"
. "$ROOT/tools/log.sh"
EMIT="${1:?usage: package-tests.sh EMIT}"
TMP="$(mktemp -d)"
cleanup () {
  if [ "${EMIT_TEST_KEEP:-0}" = 1 ]; then say "retain Malt package-test diagnostics -> $TMP"
  else rm -rf "$TMP"; fi
}
trap cleanup EXIT
export EMIT_CACHE="$TMP/cache"
unset EMIT_LIBRARY_PATH EMIT_MANIFEST
ROOTS=(-L "$ROOT/lib" -L "$HERE")

python3 "$HERE/malt-core-exports.py"
python3 "$HERE/reference/check.py"
python3 "$HERE/reference/xor-reference-tests.py"

cd "$TMP"
for name in 'ext1-∇' 'ext2-∇'; do
  printf '(import (only (malt learner) %s))\n' "$name" > "$TMP/unsupported.scm"
  if "$EMIT" run "${ROOTS[@]}" "$TMP/unsupported.scm" > "$TMP/reject.out" 2> "$TMP/reject.err"; then
    say "fail reject $name -> unsupported export accepted"
    exit 1
  fi
  grep -Fq "$name" "$TMP/reject.err" || { cat "$TMP/reject.err" >&2; exit 1; }
  say "reject $name -> unavailable export diagnostic"
done

cat > "$TMP/conflict.scm" <<'SCM'
(import (scheme base))
(import (malt learner))
(gradient (lambda (x) (* x x)) 3.0)
SCM
if "$EMIT" run "${ROOTS[@]}" "$TMP/conflict.scm" > "$TMP/conflict.out" 2> "$TMP/conflict.err"; then
  say "fail conflict.scm -> explicit base and learner imports accepted"
  exit 1
fi
grep -qi 'conflict' "$TMP/conflict.err" || { cat "$TMP/conflict.err" >&2; exit 1; }
say "reject conflict.scm -> explicit base and learner import conflict"
say "verify Malt package tests -> exports, provenance, 2 rejected imports, 1 conflict"
