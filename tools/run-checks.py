#!/usr/bin/env python3
"""Run every package's declared execution-path checks against a given emit.

Each entry of packages/<name>/checks.scm is run through `emit run`, `emit repl`,
and a standalone executable built by `emit build`, with exactly two library
roots (the collection's lib/ and the package's tests/) and no project manifest.
A path passes when its final non-blank stdout line equals the check's expect
string. See "The checks.scm contract" in README.md.

Narration goes to stderr and follows Emit's tool output convention; verbosity
comes from EMIT_VERBOSITY.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
PATHS = ("run", "repl", "build")


def level():
    value = os.environ.get("EMIT_VERBOSITY", "default").lower()
    if value in {"quiet", "q", "0"}:
        return 0
    if value in {"verbose", "v", "2"}:
        return 2
    return 1


def say(message, detail=False):
    if level() >= (2 if detail else 1):
        print(message, file=sys.stderr)


def tokens(text):
    """Yield the tokens of the small s-expression subset checks.scm uses."""
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c == ";":
            while i < len(text) and text[i] != "\n":
                i += 1
        elif c in "()":
            yield c
            i += 1
        elif c == '"':
            i += 1
            chars = []
            while text[i] != '"':
                if text[i] == "\\":
                    i += 1
                chars.append(text[i])
                i += 1
            i += 1
            yield ("string", "".join(chars))
        else:
            start = i
            while i < len(text) and not text[i].isspace() and text[i] not in '()";':
                i += 1
            yield ("symbol", text[start:i])


def parse(text):
    stack = [[]]
    for token in tokens(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError("checks.scm must hold exactly one list")
    return stack[0][0]


def load_checks(package):
    """Return [(name, program path, expect)] for one package directory."""
    path = package / "checks.scm"
    checks = []
    for entry in parse(path.read_text()):
        if not (isinstance(entry, list) and entry and entry[0] == ("symbol", "check")):
            raise ValueError(f"{path}: entry is not (check NAME ...): {entry}")
        name = entry[1][1]
        fields = {field[0][1]: field[1][1] for field in entry[2:]}
        if set(fields) != {"program", "expect"}:
            raise ValueError(f"{path}: check {name} needs exactly program and expect")
        checks.append((name, package / fields["program"], fields["expect"]))
    return checks


def final_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run_path(emit, path, program, roots, work, env):
    """Run one program on one execution path; return (returncode, stdout, stderr)."""
    if path == "run":
        command = [emit, "run", *roots, str(program)]
        done = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True)
    elif path == "repl":
        command = [emit, "repl", *roots]
        with open(program) as source:
            done = subprocess.run(command, cwd=work, env=env, stdin=source,
                                  capture_output=True, text=True)
    else:
        executable = work / "check-exe"
        build = subprocess.run([emit, "build", *roots, str(program), "-o", str(executable)],
                               cwd=work, env=env, capture_output=True, text=True)
        if build.returncode != 0:
            return build.returncode, build.stdout, build.stderr
        done = subprocess.run([str(executable)], cwd=work, env=env,
                              capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("emit", help="path to the emit binary under test")
    parser.add_argument("--package", action="append",
                        help="limit to this package (repeatable)")
    args = parser.parse_args()
    emit = shutil.which(args.emit) or args.emit
    emit = str(Path(emit).resolve())
    if not os.access(emit, os.X_OK):
        print(f"emit binary not executable: {emit}", file=sys.stderr)
        return 2
    version = subprocess.run([emit, "--version"], capture_output=True, text=True).stdout.strip()
    packages = sorted(p for p in (ROOT / "packages").iterdir() if (p / "checks.scm").exists())
    if args.package:
        packages = [p for p in packages if p.name in args.package]
    env = {k: v for k, v in os.environ.items() if k not in {"EMIT_LIBRARY_PATH", "EMIT_MANIFEST"}}
    start = time.monotonic()
    failures = []
    total = 0
    for package in packages:
        roots = ["-L", str(ROOT / "lib"), "-L", str(package / "tests")]
        for name, program, expect in load_checks(package):
            total += 1
            check_start = time.monotonic()
            with tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary)
                env["EMIT_CACHE"] = str(work / "cache")
                failed = None
                for path in PATHS:
                    code, out, err = run_path(emit, path, program, roots, work, env)
                    got = final_line(out)
                    say(f"  {package.name}/{name} {path} -> {got}", detail=True)
                    if code != 0 or got != expect:
                        failed = (path, code, got, err)
                        break
            elapsed = time.monotonic() - check_start
            if failed:
                path, code, got, err = failed
                say(f"fail {package.name}/{name} {path} -> expected {expect}, got {got or '(no output)'} [exit {code}]")
                if err.strip():
                    print(err.rstrip(), file=sys.stderr)
                failures.append(f"{package.name}/{name}")
            else:
                say(f"check {package.name}/{name} -> {expect}  [{len(PATHS)} paths, {elapsed:.1f}s]")
    elapsed = time.monotonic() - start
    passed = total - len(failures)
    say(f"verify package checks -> {passed}/{total} checks passed against {version}  "
        f"[{len(packages)} packages, {elapsed:.1f}s]")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
