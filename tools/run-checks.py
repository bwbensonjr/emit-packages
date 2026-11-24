#!/usr/bin/env python3
"""Run declared package checks against a chosen Emit binary or Chez source tree.

Native checks cover run, REPL, standalone build, published artifacts, and installed
package sources. --source runs the same checks using the selected tree's Chez
driver. Narration goes to stderr; --report writes JSON evidence, including failures.
"""
import argparse
import hashlib
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
PATHS = ("run", "repl", "build", "artifacts", "pkg")
REMOVED_ENV = {
    "EMIT_LIBRARY_PATH", "EMIT_MANIFEST", "EMIT_PKG_ARCHIVE", "EMIT_PKG_COMMIT",
    "EMIT_SHARED_CACHE", "EMIT_NO_SHARED_CACHE",
}


class Failure(Exception):
    """A failed validation prerequisite or proof."""


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
    """Yield the small S-expression subset used by package metadata and sources."""
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
        elif c == "\"":
            i += 1
            chars = []
            while i < len(text) and text[i] != "\"":
                if text[i] == "\\":
                    i += 1
                    if i == len(text):
                        raise Failure("unterminated string escape")
                    chars.append({"n": "\n", "r": "\r", "t": "\t"}.get(text[i], text[i]))
                else:
                    chars.append(text[i])
                i += 1
            if i == len(text):
                raise Failure("unterminated string")
            i += 1
            yield ("string", "".join(chars))
        else:
            start = i
            while i < len(text) and not text[i].isspace() and text[i] not in "()\";":
                i += 1
            yield ("symbol", text[start:i])


def parse(text):
    stack = [[]]
    for token in tokens(text):
        if token == "(":
            stack.append([])
        elif token == ")":
            if len(stack) == 1:
                raise Failure("unbalanced closing parenthesis")
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    if len(stack) != 1 or len(stack[0]) != 1 or not isinstance(stack[0][0], list):
        raise Failure("expected exactly one balanced list")
    return stack[0][0]


def atom(node, kind="symbol"):
    if not isinstance(node, tuple) or len(node) != 2 or node[0] != kind:
        raise Failure(f"expected {kind}, got {node!r}")
    return node[1]


def fields(form, tag):
    if not form or atom(form[0]) != tag:
        raise Failure(f"expected ({tag} ...)")
    found = {}
    for field in form[1:]:
        if not isinstance(field, list) or not field:
            raise Failure(f"malformed {tag} field: {field!r}")
        name = atom(field[0])
        if name in found:
            raise Failure(f"duplicate {tag} field: {name}")
        found[name] = field[1:]
    return found


def load_checks(package):
    """Return [(name, absolute program path, expect)] for a package directory."""
    path = package / "checks.scm"
    try:
        entries = parse(path.read_text())
        checks = []
        seen = set()
        for entry in entries:
            if not isinstance(entry, list) or len(entry) < 2 or atom(entry[0]) != "check":
                raise Failure("entry is not (check NAME ...)")
            name = atom(entry[1])
            if name in seen:
                raise Failure(f"duplicate check {name}")
            seen.add(name)
            values = fields([entry[0], *entry[2:]], "check")
            if set(values) != {"program", "expect"} or any(len(v) != 1 for v in values.values()):
                raise Failure(f"check {name} needs exactly one program and expect")
            program = (package / atom(values["program"][0], "string")).resolve()
            if not program.is_relative_to(package.resolve()) or not program.is_file():
                raise Failure(f"check {name} program is missing or outside package: {program}")
            checks.append((name, program, atom(values["expect"][0], "string")))
        if not checks:
            raise Failure("no declared checks")
        return checks
    except (OSError, Failure) as error:
        raise Failure(f"{path}: {error}") from error


def package_libraries(package, collection=None):
    collection = ROOT if collection is None else Path(collection)
    path = package / "package.scm"
    try:
        values = fields(parse(path.read_text()), "package")
        libraries = []
        for name in values.get("libraries", []):
            if not isinstance(name, list) or not name:
                raise Failure("library name must be a nonempty list")
            parts = tuple(atom(part) for part in name)
            if any(part in {"", ".", ".."} or "/" in part or "\\" in part or "\0" in part for part in parts):
                raise Failure(f"invalid library name {parts}")
            if parts in libraries:
                raise Failure(f"duplicate library {parts}")
            source = library_source(collection, parts)
            if not source.is_file():
                raise Failure(f"declared library source is missing: {source}")
            libraries.append(parts)
        if not libraries:
            raise Failure("no declared libraries")
        return libraries
    except (OSError, Failure) as error:
        raise Failure(f"{path}: {error}") from error


def library_source(collection, name):
    return Path(collection) / "lib" / Path(*name[:-1], name[-1] + ".sld")


def dependency_order(collection, libraries):
    """Publish dependencies before users, reading only import declarations."""
    known = set(libraries)
    dependencies = {}

    def imports(node):
        if not isinstance(node, list) or not node:
            return set()
        if node[0] == ("symbol", "import"):
            found = set()
            for item in node[1:]:
                while (isinstance(item, list) and item and item[0] in {
                    ("symbol", "only"), ("symbol", "except"),
                    ("symbol", "prefix"), ("symbol", "rename"),
                }):
                    if len(item) < 2:
                        raise Failure("malformed import set")
                    item = item[1]
                if isinstance(item, list) and all(isinstance(p, tuple) for p in item):
                    name = tuple(atom(p) for p in item)
                    if name in known:
                        found.add(name)
            return found
        found = set()
        for child in node:
            found.update(imports(child))
        return found

    for name in libraries:
        dependencies[name] = imports(parse(library_source(collection, name).read_text())) - {name}
    ordered, active, seen = [], set(), set()

    def visit(name):
        if name in active:
            raise Failure("library dependency cycle through ({})".format(" ".join(name)))
        if name in seen:
            return
        active.add(name)
        for other in sorted(dependencies[name]):
            visit(other)
        active.remove(name)
        seen.add(name)
        ordered.append(name)

    for name in libraries:
        visit(name)
    return ordered


def select_packages(collection, selected=None):
    base = Path(collection) / "packages"
    packages = sorted(path for path in base.iterdir() if path.is_dir() and (path / "package.scm").is_file())
    if selected:
        unknown = set(selected) - {path.name for path in packages}
        if unknown:
            raise Failure("unknown packages: " + ", ".join(sorted(unknown)))
        packages = [path for path in packages if path.name in selected]
    if not packages:
        raise Failure("no packages selected")
    return [(package, load_checks(package), package_libraries(package, collection)) for package in packages]


def isolated_env(work, inherited=None):
    env = dict(os.environ if inherited is None else inherited)
    for key in REMOVED_ENV:
        env.pop(key, None)
    for key, directory in (("HOME", "home"), ("XDG_DATA_HOME", "data"), ("EMIT_CACHE", "cache")):
        path = Path(work) / directory
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    return env


def final_line(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def run(command, cwd, env, stdin=None):
    with open(stdin if stdin is not None else os.devnull) as source:
        return subprocess.run(command, cwd=cwd, env=env, stdin=source,
                              capture_output=True, text=True)


def result_tuple(done):
    return done.returncode, done.stdout, done.stderr


def quote_scheme(text):
    return "\"" + str(text).replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def artifact_reuse(stderr, libraries, artifacts):
    """Require a reuse proof for every declared library the resolver loaded."""
    loaded, reused = set(), set()
    for name in libraries:
        unit = ".".join(name)
        label = "(" + " ".join(name) + ")"
        if re.search(r"^resolve library " + re.escape(label) + r" -> ", stderr, re.M):
            loaded.add(name)
        expected = f"artifact: library {unit}: reused from {artifacts}/{unit}.ll"
        if expected in stderr:
            reused.add(name)
        if re.search(r"(?:artifact|cache): (?:no (?:shared )?entry for )?library " +
                     re.escape(unit) + r":(?: rejected |, compiling|[^\n]*recompiling)", stderr):
            raise Failure(f"declared library {label} compiled from source or its artifact was rejected")
    missing = loaded - reused
    if missing:
        names = ", ".join("(" + " ".join(name) + ")" for name in sorted(missing))
        raise Failure(f"missing artifact reuse proof for loaded libraries: {names}")
    if not reused:
        raise Failure("no declared library artifact was reused")
    # A success message without resolver identity is not sufficient evidence.
    if not loaded:
        raise Failure("no declared library load was reported")
    return {"loaded": len(loaded), "reused": len(reused), "declared": len(libraries)}


def run_artifacts(emit, program, package, libraries, collection, work, env):
    artifacts = work / "artifacts"
    artifacts.mkdir()
    manifest = work / "artifacts.scm"
    entries = "".join(
        " (library ({}) (source {}) ".format(" ".join(name), quote_scheme(library_source(collection, name))) +
        f"(artifacts {quote_scheme(artifacts)}))\n" for name in libraries)
    manifest.write_text("(\n" + entries + ")\n")
    # The installed manifest remains chained for the chosen executable's standard
    # libraries. Only package entries are supplied by this temporary manifest.
    common = ["--manifest", str(manifest), "-L", str(package / "tests")]
    for name in dependency_order(collection, libraries):
        done = run([emit, "lib", str(library_source(collection, name)), *common,
                    "-o", str(artifacts)], work, env)
        if done.returncode != 0:
            return (*result_tuple(done), {})
        for suffix in (".ll", ".exports", ".artifact"):
            output = artifacts / (".".join(name) + suffix)
            if not output.is_file() or output.stat().st_size == 0:
                return 1, done.stdout, "emit lib ({}) produced missing or empty {}".format(" ".join(name), output), {}
    verbose = dict(env, EMIT_VERBOSITY="verbose")
    # Publication can fill the private cache. Execution uses a different cache so
    # only the explicit published artifacts can satisfy the proof.
    cache = work / "artifact-run-cache"
    cache.mkdir()
    verbose["EMIT_CACHE"] = str(cache)
    done = run([emit, "run", *common, str(program)], work, verbose)
    if done.returncode != 0:
        return (*result_tuple(done), {})
    try:
        counts = artifact_reuse(done.stderr, libraries, artifacts)
    except Failure as error:
        return 1, done.stdout, f"{error}\n{done.stderr}", {}
    say("    artifacts -> {}/{} declared libraries reused".format(counts["reused"], counts["declared"]), detail=True)
    return (*result_tuple(done), counts)


def run_installed(emit, program, package, collection, work, env):
    installed_env = dict(env)
    data = work / "installed-data"
    data.mkdir()
    installed_env["XDG_DATA_HOME"] = str(data)
    cache = work / "installed-cache"
    cache.mkdir()
    installed_env["EMIT_CACHE"] = str(cache)
    done = run([emit, "pkg", "install", "--from", str(collection), package.name], work, installed_env)
    if done.returncode != 0:
        return (*result_tuple(done), {})
    # Deliberately omit the collection lib/ root. Private test helpers are not
    # installed package content, so they retain their own explicit root.
    done = run([emit, "run", "-L", str(package / "tests"), str(program)], work, installed_env)
    return (*result_tuple(done), {})


def run_path(emit, path, program, roots, work, env, package=None, libraries=None,
             collection=None, source_tree=None):
    """Run one check; return exit code, stdout, stderr, and path proof details."""
    collection = ROOT if collection is None else Path(collection)
    if path == "run":
        done = run([emit, "run", *roots, str(program)], work, env)
    elif path == "repl":
        done = run([emit, "repl", *roots], work, env, stdin=program)
    elif path == "build":
        executable = work / "check-exe"
        done = run([emit, "build", *roots, str(program), "-o", str(executable)], work, env)
        if done.returncode == 0:
            done = run([str(executable)], work, env)
    elif path == "artifacts":
        return run_artifacts(emit, program, package, libraries, collection, work, env)
    elif path == "pkg":
        return run_installed(emit, program, package, collection, work, env)
    elif path == "source":
        executable = work / "check-source"
        done = run([shutil.which("chez"), "--libdirs", str(source_tree / "src"),
                    "--script", str(source_tree / "src" / "compile.ss"),
                    "-q", str(program), *roots, "-o", str(executable)], source_tree, env)
        if done.returncode == 0:
            done = run([str(executable)], work, env)
    else:
        raise Failure(f"unknown execution path: {path}")
    return (*result_tuple(done), {})


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def collection_identity(root):
    result = {"path": str(Path(root).resolve()), "commit": None, "dirty": None}
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True)
        if head.returncode == 0:
            result["commit"] = head.stdout.strip()
            status = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                    capture_output=True, text=True)
            result["dirty"] = bool(status.stdout.strip()) if status.returncode == 0 else None
    except OSError:
        pass
    return result


def source_identity(source):
    for required in ("VERSION", "src/compile.ss", "emit-libs.scm"):
        if not (source / required).is_file():
            raise Failure(f"source tree missing required file: {source / required}")
    version = (source / "VERSION").read_text().strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise Failure(f"source tree has malformed VERSION: {version!r}")
    if shutil.which("chez") is None:
        raise Failure("--source requires Chez (`chez`) on PATH")
    digest = hashlib.sha256()
    inputs = [source / "VERSION", source / "emit-libs.scm"]
    for directory in ("src", "lib", "tools"):
        inputs.extend(path for path in (source / directory).rglob("*")
                      if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc")
    for path in sorted(inputs):
        digest.update(str(path.relative_to(source)).encode() + b"\0")
        digest.update(digest_file(path).encode() + b"\n")
    return {"kind": "source", **collection_identity(source), "version": version,
            "source_sha256": digest.hexdigest(),
            "driver_sha256": digest_file(source / "src" / "compile.ss"),
            "chez": str(Path(shutil.which("chez")).resolve())}


def prepare_source_tree(source, work):
    # Chez's driver uses relative paths and writes build/lib. Work in a private
    # copy, so running it never changes the explicitly selected source checkout.
    snapshot = work / "emit-source"
    snapshot.mkdir()
    for name in ("src", "lib", "tools"):
        if not (source / name).is_dir():
            raise Failure(f"source tree missing required directory: {source / name}")
        shutil.copytree(source / name, snapshot / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("VERSION", "emit-libs.scm"):
        shutil.copy2(source / name, snapshot / name)
    return snapshot


def binary_identity(emit):
    resolved = Path(shutil.which(emit) or emit).resolve()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise Failure(f"emit binary not executable: {resolved}")
    done = subprocess.run([str(resolved), "--version"], capture_output=True, text=True)
    match = re.fullmatch(r"emit (\d+\.\d+\.\d+)(?: \([^\n]*\))?", done.stdout.strip())
    if done.returncode != 0 or not match:
        raise Failure(f"emit --version failed or malformed: {done.stdout.strip()!r} [exit {done.returncode}]")
    return {"kind": "native", "path": str(resolved), "version": match.group(1),
            "version_output": done.stdout.strip(), "sha256": digest_file(resolved)}


def write_report(path, data):
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("emit", nargs="?", help="path to the native Emit binary under test")
    parser.add_argument("--source", type=Path, metavar="EMIT_SOURCE",
                        help="instead test this tree's Chez source driver")
    parser.add_argument("--package", action="append", help="limit to this package (repeatable)")
    parser.add_argument("--report", type=Path, help="write JSON evidence, including failed checks")
    args = parser.parse_args(argv)
    start = time.monotonic()
    report = {"collection": collection_identity(ROOT), "compiler": None, "packages": [],
              "selected_paths": ["source"] if args.source else list(PATHS),
              "results": [], "status": "failed"}
    code = 1
    try:
        if bool(args.emit) == bool(args.source):
            raise Failure("supply exactly one native Emit binary or --source EMIT_SOURCE")
        packages = select_packages(ROOT, args.package)
        report["packages"] = [package.name for package, _, _ in packages]
        compiler = source_identity(args.source.resolve()) if args.source else binary_identity(args.emit)
        report["compiler"] = compiler
        emit = compiler["path"] if args.emit else None
        paths = report["selected_paths"]
        failures = 0
        with tempfile.TemporaryDirectory(prefix="emit-package-checks-") as temporary:
            workspace = Path(temporary)
            source_tree = prepare_source_tree(args.source.resolve(), workspace) if args.source else None
            for package, checks, libraries in packages:
                roots = ["-L", str(ROOT / "lib"), "-L", str(package / "tests")]
                for name, program, expect in checks:
                    check_start = time.monotonic()
                    check_failed = False
                    for path in paths:
                        work = workspace / package.name / name / path
                        work.mkdir(parents=True)
                        env = isolated_env(work)
                        path_start = time.monotonic()
                        try:
                            result, out, err, details = run_path(
                                emit, path, program, roots, work, env, package, libraries,
                                ROOT, source_tree)
                        except (OSError, Failure) as error:
                            result, out, err, details = 1, "", str(error), {}
                        got = final_line(out)
                        passed = result == 0 and got == expect
                        entry = {"package": package.name, "check": name, "program": str(program),
                                 "path": path, "expected": expect, "actual": got, "exit_status": result,
                                 "passed": passed, "seconds": time.monotonic() - path_start,
                                 "details": details}
                        if not passed:
                            entry["stderr"] = err
                        report["results"].append(entry)
                        say(f"  {package.name}/{name} {path} -> {got}", detail=True)
                        if not passed:
                            actual = got or "(no output)"
                            print(f"fail {package.name}/{name} {path} -> expected {expect}, "
                                  f"got {actual} [exit {result}]", file=sys.stderr)
                            if err.strip():
                                print(err.rstrip(), file=sys.stderr)
                            check_failed = True
                            # Later paths remain absent from the report, not passed.
                            break
                    failures += int(check_failed)
                    if not check_failed:
                        say(f"check {package.name}/{name} -> {expect}  "
                            f"[{len(paths)} paths, {time.monotonic() - check_start:.1f}s]")
        report["status"] = "failed" if failures else "passed"
        report["checks"] = sum(len(checks) for _, checks, _ in packages)
        report["failed_checks"] = failures
        code = int(bool(failures))
    except (OSError, Failure, ValueError) as error:
        report["error"] = str(error)
        print(f"package checks: {error}", file=sys.stderr)
    finally:
        report["seconds"] = time.monotonic() - start
        write_report(args.report, report)
    passed = sum(bool(item["passed"]) for item in report["results"])
    say("verify package checks -> {}  [{}/{} executed paths, {:.1f}s]".format(
        report["status"], passed, len(report["results"]), report["seconds"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
