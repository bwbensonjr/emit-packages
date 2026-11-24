import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "emit-release.py"
SPEC = importlib.util.spec_from_file_location("emit_release", SCRIPT)
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def metadata(version="0.13.0", draft=False, prerelease=False):
    tag = f"v{version}"
    base = f"https://github.com/bwbensonjr/emit/releases/download/{tag}"
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "published_at": "2026-11-01T00:00:00Z",
            "html_url": f"https://github.com/bwbensonjr/emit/releases/tag/{tag}",
            "assets": [
                {"name": f"emit-{version}.tar.gz", "browser_download_url": f"{base}/emit-{version}.tar.gz"},
                {"name": "SHA256SUMS", "browser_download_url": f"{base}/SHA256SUMS"},
            ]}


class EmitReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_target(self, version="0.13.0"):
        path = self.root / "target.json"
        path.write_text(json.dumps(release.target_from_release(metadata(version))))
        return path

    def test_resolution_selects_latest_stable_and_ignores_draft_prerelease(self):
        releases = [metadata("0.14.0", prerelease=True), metadata("0.13.0"),
                    metadata("0.15.0", draft=True)]
        for item, date in zip(releases, ("2026-03", "2026-02", "2026-04")):
            item["published_at"] = date
        fixture = self.root / "releases.json"
        fixture.write_text(json.dumps(releases))
        self.assertEqual(release.resolve(fixture)["version"], "0.13.0")

    def test_rejects_draft_and_prerelease_when_given_as_target_release(self):
        for item in (metadata(draft=True), metadata(prerelease=True)):
            with self.subTest(item=item["draft"], prerelease=item["prerelease"]):
                with self.assertRaisesRegex(ValueError, "draft|prerelease"):
                    release.target_from_release(item)

    def test_rejects_malformed_or_unavailable_metadata(self):
        fixture = self.root / "bad.json"
        fixture.write_text("{")
        with self.assertRaisesRegex(ValueError, "cannot read release metadata"):
            release.resolve(fixture)
        fixture.write_text(json.dumps({"tag_name": "latest", "assets": []}))
        with self.assertRaisesRegex(ValueError, "invalid release tag|invalid stable Emit version"):
            release.resolve(fixture)
        with mock.patch.object(release, "urlopen", side_effect=OSError("offline")):
            with self.assertRaisesRegex(ValueError, "cannot resolve latest stable"):
                release.resolve()

    def test_malformed_tag_and_target_json_fail_with_value_error(self):
        for tag in (None, 123, "latest"):
            item = metadata()
            item["tag_name"] = tag
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                release.target_from_release(item)
        target = self.root / "target.json"
        target.write_text("[]")
        with self.assertRaisesRegex(ValueError, "not a JSON object"):
            release.read_target(target)

    def test_release_metadata_must_confirm_publication_and_stability(self):
        for field, value in (("draft", None), ("prerelease", None), ("published_at", None)):
            item = metadata()
            item.pop(field, None)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "metadata"):
                release.target_from_release(item)

    def test_rejects_untrusted_or_malformed_asset_identity(self):
        item = metadata()
        item["assets"][0]["browser_download_url"] = "https://attacker.invalid/archive"
        with self.assertRaisesRegex(ValueError, "unexpected release asset URL"):
            release.target_from_release(item)

    def test_emit_version_output_must_be_well_formed(self):
        binary = self.root / "emit"
        binary.write_text("#!/bin/sh\nprintf 'Emit version: 0.13.0\\n'\n")
        binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "malformed Emit version output"):
            release.emit_version(binary)

    def test_source_version_mismatch_reports_expected_and_actual(self):
        target = self.write_target("0.13.0")
        source = self.root / "source"
        source.mkdir()
        (source / "VERSION").write_text("0.12.0\n")
        with self.assertRaisesRegex(ValueError, "expected 0.13.0, actual 0.12.0"):
            release.verify(target, source=source)

    def test_emit_version_mismatch_reports_channel_lag(self):
        target = self.write_target("0.13.0")
        binary = self.root / "emit"
        binary.write_text("#!/bin/sh\nprintf 'emit 0.12.0 (LLVM 23.1.4)\\n'\n")
        binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "expected 0.13.0, actual 0.12.0"):
            release.verify(target, emit=binary)

    def test_rejects_wrong_source_version_format(self):
        target = self.write_target()
        source = self.root / "source"
        source.mkdir()
        (source / "VERSION").write_text("0.13.0-dev\n")
        with self.assertRaisesRegex(ValueError, "malformed source VERSION"):
            release.verify(target, source=source)

    def test_fetch_source_rejects_checksum_mismatch(self):
        target = self.write_target()
        out = self.root / "out"
        def fake_download(url, destination):
            if url.endswith("SHA256SUMS"):
                destination.write_text("0" * 64 + "  emit-0.13.0.tar.gz\n")
            else:
                destination.write_bytes(b"not the archived source")
        with mock.patch.object(release, "download", side_effect=fake_download):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                release.fetch_source(target, out)

    def test_fetch_source_rejects_archive_missing_version(self):
        target = self.write_target()
        out = self.root / "out"
        archive = self.root / "fixture.tar.gz"
        with tempfile.TemporaryDirectory(dir=self.root) as tree:
            root = Path(tree) / "emit-0.13.0"
            root.mkdir()
            (root / "README.md").write_text("release fixture")
            with tarfile_open(archive, "w:gz") as tar:
                tar.add(root, arcname="emit-0.13.0")
        digest = release.hashlib.sha256(archive.read_bytes()).hexdigest()
        def fake_download(url, destination):
            if url.endswith("SHA256SUMS"):
                destination.write_text(f"{digest}  emit-0.13.0.tar.gz\n")
            else:
                destination.write_bytes(archive.read_bytes())
        with mock.patch.object(release, "download", side_effect=fake_download):
            with self.assertRaisesRegex(ValueError, "missing VERSION"):
                release.fetch_source(target, out)

    def test_fetch_source_allows_safe_symlink_and_rejects_escape(self):
        target = self.write_target()
        for link_name, link_target, should_pass in (("AGENTS.md", "CLAUDE.md", True),
                                                      ("escape", "../../outside", False)):
            with self.subTest(link=link_name):
                out = self.root / f"out-{link_name}"
                archive = self.root / f"{link_name}.tar.gz"
                with tempfile.TemporaryDirectory(dir=self.root) as tree:
                    root = Path(tree) / "emit-0.13.0"
                    root.mkdir()
                    (root / "VERSION").write_text("0.13.0\n")
                    (root / "CLAUDE.md").write_text("instructions\n")
                    (root / link_name).symlink_to(link_target)
                    with tarfile_open(archive, "w:gz") as tar:
                        tar.add(root, arcname="emit-0.13.0")
                digest = release.hashlib.sha256(archive.read_bytes()).hexdigest()
                def fake_download(url, destination):
                    if url.endswith("SHA256SUMS"):
                        destination.write_text(f"{digest}  emit-0.13.0.tar.gz\n")
                    else:
                        destination.write_bytes(archive.read_bytes())
                with mock.patch.object(release, "download", side_effect=fake_download):
                    if should_pass:
                        with contextlib.redirect_stdout(io.StringIO()):
                            release.fetch_source(target, out)
                        self.assertTrue((out / "emit-0.13.0" / link_name).is_symlink())
                    else:
                        with self.assertRaisesRegex(ValueError, "unsafe source archive member"):
                            release.fetch_source(target, out)

    def test_fetch_source_refuses_existing_destination_without_deleting_it(self):
        target = self.write_target()
        out = self.root / "out"
        destination = out / "emit-0.13.0"
        destination.mkdir(parents=True)
        sentinel = destination / "keep.txt"
        sentinel.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "already exists"):
            release.fetch_source(target, out)
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_fetch_source_checks_version_and_prints_absolute_path(self):
        target = self.write_target()
        out = self.root / "out"
        archive = self.root / "fixture.tar.gz"
        with tempfile.TemporaryDirectory(dir=self.root) as tree:
            root = Path(tree) / "emit-0.13.0"
            root.mkdir()
            (root / "VERSION").write_text("0.13.0\n")
            with tarfile_open(archive, "w:gz") as tar:
                tar.add(root, arcname="emit-0.13.0")
        digest = release.hashlib.sha256(archive.read_bytes()).hexdigest()
        def fake_download(url, destination):
            if url.endswith("SHA256SUMS"):
                destination.write_text(f"{digest}  emit-0.13.0.tar.gz\n")
            else:
                destination.write_bytes(archive.read_bytes())
        stdout = io.StringIO()
        with mock.patch.object(release, "download", side_effect=fake_download), contextlib.redirect_stdout(stdout):
            release.fetch_source(target, out)
        self.assertEqual(stdout.getvalue().strip(), str((out / "emit-0.13.0").resolve()))

    def test_aggregate_requires_nonempty_all_success(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            release.aggregate([])
        with self.assertRaisesRegex(ValueError, "1/2"):
            release.aggregate(["success", "skipped"])
        release.aggregate(["success", "success"])


def tarfile_open(*args, **kwargs):
    import tarfile
    return tarfile.open(*args, **kwargs)


if __name__ == "__main__":
    unittest.main()
