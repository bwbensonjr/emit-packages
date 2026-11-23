#!/usr/bin/env python3
"""Install every package with `emit pkg install --from` and use it as a user would.

The collection's main branch is what `emit pkg` delivers, so this checks that path
end to end against a given emit (0.13.0 or later):

1. `emit pkg available --from ROOT` lists every package at its declared version.
2. `emit pkg install --from ROOT NAME...` installs them into a fresh user library
   root (a temporary XDG_DATA_HOME), and `emit pkg list` records each one with this
   checkout as its source.
3. From an unrelated directory, with no -L, manifest, or EMIT_LIBRARY_PATH, a
   one-line program importing each declared library runs under `emit run`.
4. `emit pkg remove NAME...` leaves nothing installed.

Narration goes to stderr and follows Emit's tool output convention; verbosity comes
from EMIT_VERBOSITY.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


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


def fail(message, result=None):
    print(f"install check failed: {message}", file=sys.stderr)
    if result is not None:
        for stream in (result.stdout, result.stderr):
            for line in stream.splitlines():
                print(f"  {line}", file=sys.stderr)
    sys.exit(1)


def parse(text):
    """Read one s-expression into nested lists of strings (enough for package.scm)."""
    text = re.sub(r";[^\n]*", "", text)
    tokens = re.findall(r'"(?:[^"\\]|\\.)*"|[()]|[^\s()"]+', text)
    stack = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token.strip('"') if token.startswith('"') else token)
    return stack[0][0]


def packages():
    found = []
    for path in sorted((ROOT / "packages").glob("*/package.scm")):
        form = parse(path.read_text())
        fields = {item[0]: item[1:] for item in form[1:] if isinstance(item, list)}
        found.append(
            {
                "name": fields["name"][0],
                "version": fields["version"][0],
                "libraries": [" ".join(lib) for lib in fields["libraries"]],
            }
        )
    return found


def main():
    if len(sys.argv) != 2:
        print("usage: tools/install-check.py EMIT", file=sys.stderr)
        sys.exit(2)
    emit = str(Path(sys.argv[1]).resolve())
    start = time.monotonic()
    wanted = packages()
    names = [p["name"] for p in wanted]
    say(f"install check {', '.join(names)} -> {emit} pkg --from {ROOT}")

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch)
        data = scratch / "data"
        work = scratch / "work"
        work.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "EMIT_LIBRARY_PATH"}
        env["XDG_DATA_HOME"] = str(data)

        def pkg(*args):
            return subprocess.run(
                [emit, "pkg", *args], cwd=work, env=env, capture_output=True, text=True
            )

        result = pkg("available", "--from", str(ROOT))
        if result.returncode != 0:
            fail("emit pkg available", result)
        offered = {line.split()[0]: line.split()[1] for line in result.stdout.splitlines() if line.strip()}
        for p in wanted:
            if offered.get(p["name"]) != p["version"]:
                fail(f"available does not offer {p['name']} {p['version']}", result)
        say(f"verify available -> {len(wanted)} packages offered", detail=True)

        result = pkg("install", "--from", str(ROOT), *names)
        if result.returncode != 0:
            fail("emit pkg install", result)

        result = pkg("list")
        if result.returncode != 0:
            fail("emit pkg list", result)
        listed = {}
        for line in result.stdout.splitlines():
            fields = line.split(maxsplit=2)
            if len(fields) == 3:
                listed[fields[0]] = (fields[1], fields[2])
        for p in wanted:
            version, source = listed.get(p["name"], (None, None))
            if version != p["version"] or source is None or Path(source).resolve() != ROOT:
                fail(f"list does not record {p['name']} {p['version']} from {ROOT}", result)
        say(f"verify list -> {len(wanted)} packages recorded from this checkout", detail=True)

        count = 0
        for p in wanted:
            for library in p["libraries"]:
                program = work / "probe.scm"
                # Only the library under test, as in the README: (malt learner) exports its
                # own arithmetic, which an explicit (scheme base) import would conflict with.
                program.write_text(f'(import ({library}))\n(display "imported")\n')
                result = subprocess.run(
                    [emit, "run", str(program)], cwd=work, env=env, capture_output=True, text=True
                )
                if result.returncode != 0 or result.stdout.strip() != "imported":
                    fail(f"emit run could not import ({library}) from the user root", result)
                say(f"verify import ({library})", detail=True)
                count += 1

        result = pkg("remove", *names)
        if result.returncode != 0:
            fail("emit pkg remove", result)
        result = pkg("list")
        if result.returncode != 0 or result.stdout.strip():
            fail("packages remain listed after remove", result)
        leftover = [p for p in (data / "emit" / "lib").rglob("*") if p.is_file()] if (data / "emit" / "lib").exists() else []
        if leftover:
            fail(f"files remain after remove: {', '.join(str(p) for p in leftover)}")

    say(
        f"verify install check -> {len(wanted)} packages installed, {count} libraries imported, "
        f"removed cleanly [{time.monotonic() - start:.1f}s]"
    )


if __name__ == "__main__":
    main()
