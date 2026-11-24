"""Lifecycle regression checks, including a real two-revision package update."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "install-check.py"
SPEC = importlib.util.spec_from_file_location("install_check", MODULE_PATH)
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)
EMIT = os.environ.get("EMIT_TEST_BINARY") or shutil.which("emit")


def collection(root, version="1.0.0", value=1, old=False):
    package = root / "packages" / "probe"
    (package / "tests").mkdir(parents=True)
    libraries = root / "lib" / "probe"
    libraries.mkdir(parents=True)
    (libraries / "core.sld").write_text(
        "(define-library (probe core) (export value) (import (scheme base))\n"
        f"  (begin (define value {value})))\n"
    )
    declared = "(probe core)"
    if old:
        (libraries / "old.sld").write_text(
            "(define-library (probe old) (export old) (import (scheme base)) "
            "(begin (define old 1)))\n"
        )
        declared += " (probe old)"
    (package / "package.scm").write_text(
        f"(package (name probe) (version \"{version}\") (libraries {declared}))\n"
    )
    (package / "checks.scm").write_text(
        f"((check value (program \"tests/value.scm\") (expect \"{value}\")))\n"
    )
    (package / "tests" / "value.scm").write_text(
        "(import (scheme base) (scheme write) (probe core))\n(display value)\n"
    )
    return root


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.scratch = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_environment_cannot_select_real_roots_or_downloads(self):
        inherited = {"HOME": "/real/home", "XDG_DATA_HOME": "/real/data", "EMIT_CACHE": "/real/cache",
                     "EMIT_MANIFEST": "/real/manifest", "EMIT_LIBRARY_PATH": "/real/lib",
                     "EMIT_PKG_ARCHIVE": "https://invalid/archive", "EMIT_PKG_COMMIT": "abc",
                     "LLVM_CONFIG": "/tools/llvm-config"}
        env = INSTALL.isolated_env(self.scratch, inherited)
        for variable in ("HOME", "XDG_DATA_HOME", "EMIT_CACHE"):
            self.assertTrue(Path(env[variable]).is_relative_to(self.scratch))
        for variable in ("EMIT_MANIFEST", "EMIT_LIBRARY_PATH", "EMIT_PKG_ARCHIVE", "EMIT_PKG_COMMIT"):
            self.assertNotIn(variable, env)
        self.assertEqual(env["LLVM_CONFIG"], "/tools/llvm-config")
        self.assertEqual(inherited["HOME"], "/real/home")

    def test_empty_collection_and_missing_checks_fail(self):
        with self.assertRaisesRegex(INSTALL.Failure, "no packages"):
            INSTALL.packages(self.scratch)
        root = collection(self.scratch / "source")
        (root / "packages" / "probe" / "checks.scm").unlink()
        with self.assertRaisesRegex(INSTALL.Failure, "missing checks.scm"):
            INSTALL.packages(root)

    def test_owned_files_include_extra_declared_paths(self):
        root = collection(self.scratch / "source")
        manifest = root / "packages" / "probe" / "package.scm"
        manifest.write_text(manifest.read_text().rstrip()[:-1] + " (files \"probe/data.scm\"))\n")
        (root / "lib" / "probe" / "data.scm").write_text("package data\n")
        installed = self.scratch / "installed"
        shutil.copytree(root / "lib", installed)
        wanted = INSTALL.packages(root)
        INSTALL.verify_files(root, wanted, installed)
        (installed / "probe" / "data.scm").write_text("old data\n")
        with self.assertRaisesRegex(INSTALL.Failure, "differs.*data.scm"):
            INSTALL.verify_files(root, wanted, installed)

    def test_old_content_and_stale_owned_files_are_rejected(self):
        first = collection(self.scratch / "first", old=True)
        second = collection(self.scratch / "second", "2.0.0", 2)
        installed = self.scratch / "installed"
        shutil.copytree(first / "lib", installed)
        with self.assertRaisesRegex(INSTALL.Failure, "stale.*old.sld"):
            INSTALL.verify_files(second, INSTALL.packages(second), installed)
        (installed / "probe" / "old.sld").unlink()
        with self.assertRaisesRegex(INSTALL.Failure, "differs.*core.sld"):
            INSTALL.verify_files(second, INSTALL.packages(second), installed)

    def test_list_must_record_new_version_and_source(self):
        root = collection(self.scratch / "source", "2.0.0", 2)
        result = subprocess.CompletedProcess([], 0, f"probe 1.0.0 {root}\n", "")
        with self.assertRaisesRegex(INSTALL.Failure, "list does not record"):
            INSTALL.assert_list(result, INSTALL.packages(root), root)

    def test_failure_report_names_input_and_failed_operation(self):
        report = {"results": []}
        env = INSTALL.isolated_env(self.scratch)
        session = INSTALL.Session("/fake/emit", self.scratch, env, report)
        result = subprocess.CompletedProcess([], 1, "wrong", "failure details")
        with mock.patch.object(INSTALL.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(INSTALL.Failure, "after update.*expected 2"):
                session.run("after update/probe/value", ["run", "probe.scm"], "2")
        self.assertEqual(len(report["results"]), 1)
        self.assertFalse(report["results"][0]["passed"])
        self.assertEqual(report["results"][0]["stderr"], "failure details")
        self.assertEqual(report["results"][0]["exit_status"], 1)

    def test_cli_writes_failed_report_for_missing_binary(self):
        output = self.scratch / "failed.json"
        with contextlib.redirect_stderr(io.StringIO()):
            code = INSTALL.main([str(self.scratch / "missing-emit"), "--report", str(output)])
        data = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(data["status"], "failed")
        self.assertIn("not executable", data["error"])
        self.assertIn("path", data["emit"])
        self.assertIn("commit", data["collection"])
        self.assertGreaterEqual(data["duration_seconds"], 0)

    @unittest.skipUnless(EMIT, "requires an installed Emit for lifecycle integration")
    def test_two_revision_update_replaces_behavior_and_deletes_dropped_files(self):
        first = collection(self.scratch / "first", old=True)
        second = collection(self.scratch / "second", "2.0.0", 2)
        work = self.scratch / "work"
        work.mkdir()
        env = INSTALL.isolated_env(self.scratch)
        report = {"results": []}
        session = INSTALL.Session(str(Path(EMIT).resolve()), work, env, report)
        session.pkg("install first", "install", "--from", str(first), "probe")
        INSTALL.run_checks(session, INSTALL.packages(first), "before update")
        INSTALL.verify_update(session, second, INSTALL.packages(second))
        installed = Path(env["XDG_DATA_HOME"]) / "emit" / "lib"
        self.assertFalse((installed / "probe" / "old.sld").exists())
        self.assertTrue(all(result["passed"] for result in report["results"]))
        self.assertEqual(report["results"][-1]["actual"], "2")
        self.assertEqual((first / "lib" / "probe" / "core.sld").read_text().count("value 1"), 1)

    @unittest.skipUnless(EMIT, "requires an installed Emit for lifecycle integration")
    def test_full_lifecycle_restores_owned_code_and_removes_everything(self):
        source = collection(self.scratch / "source")
        before = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        report = {"results": [], "started": INSTALL.time.monotonic()}
        INSTALL.lifecycle(str(Path(EMIT).resolve()), source, self.scratch, report)
        self.assertEqual(report["status"], "passed")
        operations = {result["operation"] for result in report["results"]}
        self.assertIn("modified import/probe", operations)
        self.assertIn("after update/probe/value", operations)
        after = {str(p.relative_to(source)): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any((self.scratch / "data" / "emit" / "lib").rglob("*.sld")))


if __name__ == "__main__":
    unittest.main()
