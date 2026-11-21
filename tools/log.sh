#!/usr/bin/env bash
# log.sh -- narration helpers following Emit's tool output convention
# (docs/OUTPUT.md in bwbensonjr/emit): narration on stderr, data on stdout,
# verbosity from EMIT_VERBOSITY (quiet|q|0, default, verbose|v|2).
case "${EMIT_VERBOSITY:-default}" in
  quiet|q|0)   EMIT_LEVEL=0 ;;
  verbose|v|2) EMIT_LEVEL=2 ;;
  *)           EMIT_LEVEL=1 ;;
esac
export EMIT_LEVEL
say()  { [ "${EMIT_LEVEL:-1}" -ge 1 ] && printf '%s\n' "$*" >&2 || true; }
vsay() { [ "${EMIT_LEVEL:-1}" -ge 2 ] && printf '%s\n' "$*" >&2 || true; }
