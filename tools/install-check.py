#!/usr/bin/env python3
"""Exercise collection package installation, execution, update, and removal.

All package state, user roots, and compilation caches live in a temporary directory.
The supplied Emit must support `emit pkg` (0.13.0 or later). Narration goes to stderr;
--report FILE retains JSON evidence, including failures.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent


class Failure(Exception):
    pass


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


def parse(text):
    """Read the small s-expression subset used by package metadata and checks."""
    tokens = re.findall(r";[^\n]*|\"(?:[^\"\\]|\\.)*\"|[()]|[^\s();\"]+", text)
    stack = [[]]
    for token in tokens:
        if token.startswith(";"):
            continue
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) == 1:
                raise Failure("unexpected closing parenthesis in package metadata")
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(json.loads(token) if token.startswith("\"") else token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise Failure("package metadata must hold exactly one complete form")
    return stack[0][0]


def relative_file(value):
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise Failure(f"unsafe package file path: {value}")
    return path


def packages(root):
    found = []
    for path in sorted((root / "packages").glob("*/package.scm")):
        form = parse(path.read_text())
        if not isinstance(form, list) or not form or form[0] != "package":
            raise Failure(f"{path}: expected (package ...)")
        fields = {item[0]: item[1:] for item in form[1:] if isinstance(item, list) and item}
        name = fields["name"][0]
        libraries = [" ".join(lib) for lib in fields["libraries"]]
        files = [relative_file("/".join(lib) + ".sld") for lib in fields["libraries"]]
        files.extend(relative_file(value) for value in fields.get("files", []))
        if not libraries or not files:
            raise Failure(f"{path}: package has no declared libraries")
        checks_path = path.parent / "checks.scm"
        if not checks_path.is_file():
            raise Failure(f"{name}: missing checks.scm")
        checks = []
        for entry in parse(checks_path.read_text()):
            if not isinstance(entry, list) or len(entry) < 3 or entry[0] != "check":
                raise Failure(f"{checks_path}: expected (check NAME ...)")
            parts = {item[0]: item[1:] for item in entry[2:]}
            if set(parts) != {"program", "expect"}:
                raise Failure(f"{checks_path}: check needs program and expect")
            program = path.parent / relative_file(parts["program"][0])
            if not program.is_file():
                raise Failure(f"{checks_path}: missing check program {program}")
            checks.append((entry[1], program, parts["expect"][0]))
        if not checks:
            raise Failure(f"{name}: checks.scm selects no checks")
        for source in files:
            if not (root / "lib" / source).is_file():
                raise Failure(f"{name}: missing declared file {source}")
        found.append({"name": name, "version": fields["version"][0], "libraries": libraries,
                      "files": files, "checks": checks, "directory": path.parent})
    if not found:
        raise Failure(f"{root}: no packages selected")
    return found


def isolated_env(scratch, inherited=None):
    env = dict(os.environ if inherited is None else inherited)
    for key in ("EMIT_LIBRARY_PATH", "EMIT_MANIFEST", "EMIT_PKG_ARCHIVE", "EMIT_PKG_COMMIT"):
        env.pop(key, None)
    for key, directory in (("HOME", "home"), ("XDG_DATA_HOME", "data"), ("EMIT_CACHE", "cache")):
        path = scratch / directory
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    return env


def collection_identity(root):
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None
    return {"path": str(root), "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain"))}


def final_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


class Session:
    def __init__(self, emit, work, env, report):
        self.emit = emit
        self.work = work
        self.env = env
        self.report = report

    def run(self, operation, arguments, expect=None, failure_expected=False):
        started = time.monotonic()
        result = subprocess.run([self.emit, *arguments], cwd=self.work, env=self.env,
                                capture_output=True, text=True)
        got = final_line(result.stdout)
        passed = result.returncode != 0 if failure_expected else result.returncode == 0
        if expect is not None:
            passed = passed and got == expect
        self.report["results"].append({"operation": operation, "path": "pkg", "command": arguments,
                                       "expected": "nonzero exit" if failure_expected else expect,
                                       "actual": got, "exit_status": result.returncode,
                                       "passed": passed, "duration_seconds": time.monotonic() - started,
                                       "stderr": result.stderr})
        if not passed:
            expected = "nonzero exit" if failure_expected else expect or "success"
            actual = got or "(no output)"
            raise Failure(f"{operation}: expected {expected}, "
                          f"got {actual} [exit {result.returncode}]\n{result.stderr}")
        display = got or "passed"
        say(f"check {operation} -> {display}", detail=True)
        return result

    def verify(self, operation, action):
        started = time.monotonic()
        try:
            action()
        except Failure as error:
            self.report["results"].append({"operation": operation, "path": "pkg",
                                           "expected": "valid installed state", "actual": str(error),
                                           "passed": False,
                                           "duration_seconds": time.monotonic() - started})
            raise
        self.report["results"].append({"operation": operation, "path": "pkg",
                                       "expected": "valid installed state", "actual": "verified",
                                       "passed": True,
                                       "duration_seconds": time.monotonic() - started})

    def pkg(self, operation, *arguments):
        say(f"{operation} packages -> emit pkg " + " ".join(arguments))
        return self.run(operation, ["pkg", *arguments])


def assert_list(result, wanted, root):
    listed = {}
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) == 3:
            listed[fields[0]] = (fields[1], fields[2])
    if set(listed) != {p["name"] for p in wanted}:
        raise Failure(f"installed package names differ: {sorted(listed)}")
    for package in wanted:
        name, expected_version = package["name"], package["version"]
        version, source = listed[name]
        if version != package["version"] or Path(source).resolve() != root.resolve():
            raise Failure(f"list does not record {name} {expected_version} from {root}: "
                          f"got {version} from {source}")


def verify_files(root, wanted, installed):
    """Require exact declared content, detecting stale files as well as old bytes."""
    expected = {file for package in wanted for file in package["files"]}
    actual = {path.relative_to(installed) for path in installed.rglob("*") if path.is_file()}
    if actual != expected:
        raise Failure(f"installed file set differs: missing {sorted(str(p) for p in expected - actual)}, "
                      f"stale {sorted(str(p) for p in actual - expected)}")
    for file in sorted(expected):
        if (installed / file).read_bytes() != (root / "lib" / file).read_bytes():
            raise Failure(f"installed source differs from collection after update: {file}")


def run_checks(session, wanted, phase):
    for package in wanted:
        package_name = package["name"]
        roots = ["-L", str(package["directory"] / "tests")]
        for name, program, expect in package["checks"]:
            session.run(f"{phase}/{package_name}/{name}", ["run", *roots, str(program)], expect)


def verify_update(session, root, wanted):
    names = [package["name"] for package in wanted]
    session.pkg("update", "update", "--from", str(root), *names)
    installed = Path(session.env["XDG_DATA_HOME"]) / "emit" / "lib"
    session.verify("verify updated files", lambda: verify_files(root, wanted, installed))
    listed = session.pkg("list after update", "list")
    session.verify("verify updated records", lambda: assert_list(listed, wanted, root))
    run_checks(session, wanted, "after update")


def lifecycle(emit, root, scratch, report):
    wanted = packages(root)
    names = [package["name"] for package in wanted]
    report["packages"] = names
    report["checks"] = ["{}/{}".format(p["name"], name) for p in wanted for name, _, _ in p["checks"]]
    work = scratch / "work"
    work.mkdir()
    env = isolated_env(scratch)
    session = Session(emit, work, env, report)
    version = session.run("Emit identity", ["--version"]).stdout.strip()
    report["emit"] = {"path": emit, "version": version}
    display_names = ", ".join(names)
    say(f"install check {display_names} -> {emit} pkg --from {root}")
    offered = session.pkg("available", "available", "--from", str(root))
    offered_versions = {line.split()[0]: line.split()[1] for line in offered.stdout.splitlines() if line.strip()}
    for package in wanted:
        if offered_versions.get(package["name"]) != package["version"]:
            raise Failure("available does not offer {} {}".format(package["name"], package["version"]))
    session.pkg("install", "install", "--from", str(root), *names)
    listed = session.pkg("list after install", "list")
    session.verify("verify installed records", lambda: assert_list(listed, wanted, root))
    installed = Path(env["XDG_DATA_HOME"]) / "emit" / "lib"
    session.verify("verify installed files", lambda: verify_files(root, wanted, installed))
    for package in wanted:
        for library in package["libraries"]:
            probe = work / "probe.scm"
            probe.write_text(f"(import ({library}))\n(display \"imported\")\n")
            session.run(f"import ({library})", ["run", str(probe)], "imported")
    run_checks(session, wanted, "installed")
    for package in wanted:
        source = package["files"][0]
        (installed / source).write_text("(define-library (invalid lifecycle probe)\n")
        probe = work / "broken.scm"
        library, package_name = package["libraries"][0], package["name"]
        probe.write_text(f"(import ({library}))\n(display \"unexpected\")\n")
        session.run(f"modified import/{package_name}", ["run", str(probe)], failure_expected=True)
    verify_update(session, root, wanted)
    session.pkg("remove", "remove", *names)
    if session.pkg("list after remove", "list").stdout.strip():
        raise Failure("packages remain listed after remove")
    leftovers = [path for path in installed.rglob("*") if path.is_file()]
    if leftovers:
        display_files = ", ".join(str(p) for p in leftovers)
        raise Failure(f"files remain after remove: {display_files}")
    report["status"] = "passed"
    elapsed = time.monotonic() - report["started"]
    say(f"verify install check -> {len(wanted)} packages installed, checked, updated, removed cleanly "
        f"[{elapsed:.1f}s]")


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("emit", help="path to Emit 0.13.0 or later")
    parser.add_argument("--report", type=Path, help="retain JSON evidence, including failures")
    args = parser.parse_args(argv)
    emit = str(Path(shutil.which(args.emit) or args.emit).resolve())
    report = {"collection": collection_identity(ROOT), "emit": {"path": emit},
              "paths": ["pkg"], "results": [], "started": time.monotonic(), "status": "failed"}
    code = 1
    try:
        if not os.access(emit, os.X_OK):
            raise Failure(f"Emit binary not executable: {emit}")
        with tempfile.TemporaryDirectory(prefix="emit-package-install-") as temporary:
            lifecycle(emit, ROOT, Path(temporary), report)
        code = 0
    except (Failure, OSError, KeyError, TypeError, ValueError) as error:
        report["error"] = str(error)
        print(f"install check failed: {error}", file=sys.stderr)
    finally:
        report["duration_seconds"] = time.monotonic() - report.pop("started")
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            count = len(report["results"])
            say(f"write lifecycle report -> {args.report}  [{count} operations]")
    return code


if __name__ == "__main__":
    sys.exit(main())
