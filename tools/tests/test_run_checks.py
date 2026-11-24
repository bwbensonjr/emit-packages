"""Regression tests for collection-owned execution proof and isolation."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("collection_checks", Path(__file__).parents[1] / "run-checks.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)

FAKE_EMIT = """#!/usr/bin/env python3
import os
from pathlib import Path
import re
import sys
args = sys.argv[1:]
mode = os.environ.get("TEST_EMIT_MODE", "")
if args == ["--version"]:
    print("emit 0.13.0 (LLVM 22.1.8)")
    sys.exit(0)
action = args[0]
if action == "lib":
    if mode == "publication-fail":
        print("publication failed", file=sys.stderr)
        sys.exit(1)
    source = Path(args[1])
    name = re.search(r"define-library \\(([^)]+)\\)", source.read_text()).group(1)
    stem = Path(args[args.index("-o") + 1]) / name.replace(" ", ".")
    for suffix in (".ll", ".exports", ".artifact"):
        if mode != "missing-artifact" or suffix != ".artifact":
            Path(str(stem) + suffix).write_text("published")
    sys.exit(0)
if action == "pkg":
    assert args[1] == "install"
    if mode != "missing-installed":
        target = Path(os.environ["XDG_DATA_HOME"]) / "emit/lib/fixture/core.sld"
        target.parent.mkdir(parents=True)
        target.write_text("installed")
    sys.exit(0)
if action == "build":
    output = Path(args[args.index("-o") + 1])
    output.write_text("#!/bin/sh\\nprintf '(fixture ok)\\\\n'\\n")
    output.chmod(0o755)
    sys.exit(0)
if action == "run" and "--manifest" in args:
    manifest = Path(args[args.index("--manifest") + 1])
    artifact = manifest.parent / "artifacts/fixture.core.ll"
    print("resolve library (fixture core) -> /source/core.sld  [manifest fixture]", file=sys.stderr)
    if mode == "source-fallback":
        print("cache: no entry for library fixture.core:, compiling it", file=sys.stderr)
    elif mode != "missing-proof":
        print(f"artifact: library fixture.core: reused from {artifact} [explicit full unit]", file=sys.stderr)
elif action == "run":
    assert "EMIT_MANIFEST" not in os.environ
    assert "EMIT_LIBRARY_PATH" not in os.environ
    assert "EMIT_PKG_COMMIT" not in os.environ
    assert "EMIT_PKG_ARCHIVE" not in os.environ
    roots = [args[i + 1] for i, arg in enumerate(args) if arg == "-L"]
    if roots and all(not root.endswith("/lib") for root in roots):
        installed = Path(os.environ["XDG_DATA_HOME"]) / "emit/lib/fixture/core.sld"
        if not installed.is_file():
            print("missing installed library", file=sys.stderr)
            sys.exit(1)
if mode == "wrong-output":
    print("wrong")
else:
    print("(fixture ok)")
"""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.collection = self.root / "collection"
        self.package = self.collection / "packages/fixture"
        (self.package / "tests").mkdir(parents=True)
        (self.collection / "lib/fixture").mkdir(parents=True)
        (self.package / "package.scm").write_text(
            "(package (name fixture) (version \"1.0.0\") (libraries (fixture core)))\n")
        (self.package / "checks.scm").write_text(
            "((check core (program \"tests/check.scm\") (expect \"(fixture ok)\")))\n")
        self.program = self.package / "tests/check.scm"
        self.program.write_text("(import (fixture core))\n(display \"(fixture ok)\")\n")
        (self.collection / "lib/fixture/core.sld").write_text(
            "(define-library (fixture core) (export value) (import (scheme base)) "
            "(begin (define value 1)))\n")
        self.emit = self.root / "emit"
        self.emit.write_text(FAKE_EMIT)
        self.emit.chmod(0o755)
        self.report = self.root / "report.json"

    def main(self, arguments=None, mode=""):
        env = {"TEST_EMIT_MODE": mode, "EMIT_VERBOSITY": "quiet",
               "EMIT_LIBRARY_PATH": "/unwanted/library", "EMIT_MANIFEST": "/unwanted/manifest",
               "EMIT_PKG_ARCHIVE": "https://unwanted", "EMIT_PKG_COMMIT": "a" * 40}
        with patch.object(checks, "ROOT", self.collection), patch.dict(os.environ, env), \
                contextlib.redirect_stderr(io.StringIO()):
            return checks.main(arguments if arguments is not None else [str(self.emit), "--report", str(self.report)])

    def artifact(self, mode=""):
        work = self.root / "artifact-test"
        work.mkdir()
        env = checks.isolated_env(work)
        env["TEST_EMIT_MODE"] = mode
        return checks.run_artifacts(str(self.emit), self.program, self.package,
                                    [("fixture", "core")], self.collection, work, env)

    def test_all_native_paths_have_identity_and_results(self):
        self.assertEqual(self.main(), 0)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["status"], "passed")
        self.assertEqual([r["path"] for r in report["results"]], list(checks.PATHS))
        self.assertTrue(all(r["passed"] and r["exit_status"] == 0 for r in report["results"]))
        self.assertEqual(report["compiler"]["version"], "0.13.0")
        self.assertEqual(len(report["compiler"]["sha256"]), 64)
        self.assertIsNone(report["collection"]["commit"])
        artifact = next(r for r in report["results"] if r["path"] == "artifacts")
        self.assertEqual(artifact["details"]["reused"], 1)

    def test_failed_output_does_not_count_later_paths_as_passed(self):
        self.assertEqual(self.main(mode="wrong-output"), 1)
        report = json.loads(self.report.read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(len(report["results"]), 1)
        self.assertEqual(report["results"][0]["actual"], "wrong")
        self.assertFalse(report["results"][0]["passed"])

    def test_publication_failure_is_rejected(self):
        code, _, err, _ = self.artifact("publication-fail")
        self.assertNotEqual(code, 0)
        self.assertIn("publication failed", err)

    def test_missing_artifact_is_rejected(self):
        code, _, err, _ = self.artifact("missing-artifact")
        self.assertNotEqual(code, 0)
        self.assertIn("missing or empty", err)

    def test_correct_output_with_source_fallback_is_rejected(self):
        code, out, err, _ = self.artifact("source-fallback")
        self.assertEqual(checks.final_line(out), "(fixture ok)")
        self.assertNotEqual(code, 0)
        self.assertIn("compiled from source", err)

    def test_correct_output_without_reuse_proof_is_rejected(self):
        code, out, err, _ = self.artifact("missing-proof")
        self.assertEqual(checks.final_line(out), "(fixture ok)")
        self.assertNotEqual(code, 0)
        self.assertIn("missing artifact reuse proof", err)

    def test_no_declared_library_loaded_is_rejected(self):
        with self.assertRaisesRegex(checks.Failure, "no declared library"):
            checks.artifact_reuse("unrelated diagnostics", [("fixture", "core")], self.root)

    def test_each_loaded_library_needs_its_own_proof(self):
        stderr = (
            "resolve library (fixture core) -> core.sld\n"
            "resolve library (fixture other) -> other.sld\n"
            f"artifact: library fixture.core: reused from {self.root}/fixture.core.ll\n")
        with self.assertRaisesRegex(checks.Failure, "fixture other"):
            checks.artifact_reuse(stderr, [("fixture", "core"), ("fixture", "other")], self.root)

    def test_pkg_path_cannot_resolve_missing_installed_file_from_checkout(self):
        work = self.root / "pkg-test"
        work.mkdir()
        env = checks.isolated_env(work)
        env["TEST_EMIT_MODE"] = "missing-installed"
        code, _, err, _ = checks.run_installed(str(self.emit), self.program, self.package,
                                              self.collection, work, env)
        self.assertNotEqual(code, 0)
        self.assertIn("missing installed library", err)

    def test_isolation_removes_overrides_and_preserves_toolchain(self):
        inherited = {key: "external" for key in checks.REMOVED_ENV}
        inherited.update({"HOME": "/real/home", "XDG_DATA_HOME": "/real/data",
                          "EMIT_CACHE": "/real/cache", "CC": "/toolchain/clang"})
        env = checks.isolated_env(self.root / "isolation", inherited)
        self.assertTrue(all(key not in env for key in checks.REMOVED_ENV))
        self.assertEqual(env["CC"], "/toolchain/clang")
        self.assertNotEqual(env["HOME"], inherited["HOME"])
        self.assertTrue(Path(env["XDG_DATA_HOME"]).is_dir())

    def test_unknown_package_and_empty_selection_fail(self):
        with self.assertRaisesRegex(checks.Failure, "unknown packages"):
            checks.select_packages(self.collection, ["missing"])
        (self.package / "package.scm").unlink()
        with self.assertRaisesRegex(checks.Failure, "no packages"):
            checks.select_packages(self.collection)

    def test_missing_checks_and_empty_checks_fail(self):
        (self.package / "checks.scm").unlink()
        with self.assertRaisesRegex(checks.Failure, "checks.scm"):
            checks.select_packages(self.collection)
        (self.package / "checks.scm").write_text("()")
        with self.assertRaisesRegex(checks.Failure, "no declared checks"):
            checks.select_packages(self.collection)

    def test_invalid_modes_write_failure_report(self):
        self.assertEqual(self.main([str(self.emit), "--source", str(self.root), "--report", str(self.report)]), 1)
        self.assertIn("exactly one", json.loads(self.report.read_text())["error"])
        self.assertEqual(self.main(["--report", str(self.report)]), 1)
        self.assertEqual(json.loads(self.report.read_text())["results"], [])

    def test_missing_source_files_and_chez_fail(self):
        source = self.root / "source"
        source.mkdir()
        with self.assertRaisesRegex(checks.Failure, "missing required file"):
            checks.source_identity(source)
        (source / "src").mkdir()
        (source / "src/compile.ss").write_text("; source driver")
        (source / "VERSION").write_text("0.13.0\n")
        (source / "emit-libs.scm").write_text("()")
        with patch.object(checks.shutil, "which", return_value=None):
            with self.assertRaisesRegex(checks.Failure, "requires Chez"):
                checks.source_identity(source)

    def test_invalid_metadata_and_program_escape_fail(self):
        with self.assertRaisesRegex(checks.Failure, "unbalanced"):
            checks.parse(")")
        with self.assertRaisesRegex(checks.Failure, "unterminated"):
            checks.parse("(\"unfinished)")
        (self.package / "checks.scm").write_text(
            "((check core (program \"../../../outside.scm\") (expect \"ok\")))")
        with self.assertRaisesRegex(checks.Failure, "missing or outside"):
            checks.load_checks(self.package)

    def test_source_snapshot_preserves_original(self):
        source = self.root / "source"
        for name in ("src", "lib", "tools"):
            (source / name).mkdir(parents=True)
        (source / "VERSION").write_text("0.13.0")
        (source / "emit-libs.scm").write_text("()")
        work = self.root / "snapshot"
        work.mkdir()
        snapshot = checks.prepare_source_tree(source, work)
        (snapshot / "build").mkdir()
        self.assertFalse((source / "build").exists())


if __name__ == "__main__":
    unittest.main()
