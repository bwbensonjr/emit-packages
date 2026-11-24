#!/usr/bin/env python3
"""Resolve, verify, and fetch a stable Emit release for collection checks."""
import argparse
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO = "bwbensonjr/emit"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def say(message):
    if os.environ.get("EMIT_VERBOSITY", "default").lower() not in {"quiet", "q", "0"}:
        print(message, file=sys.stderr)


def fail(message):
    raise ValueError(message)


def valid_version(value):
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        fail(f"invalid stable Emit version: {value!r}")
    return value


def checked_asset_url(url, tag, name):
    expected = f"https://github.com/{REPO}/releases/download/{tag}/{name}"
    if url != expected:
        fail(f"unexpected release asset URL for {name}: {url!r}; expected {expected}")
    return url


def target_from_release(release):
    if not isinstance(release, dict):
        fail("release metadata is not an object")
    tag = release.get("tag_name")
    if not isinstance(tag, str):
        fail(f"invalid release tag: {tag!r}")
    if not tag.startswith("v"):
        fail(f"invalid release tag: {tag!r}; expected v<version>")
    version = valid_version(tag[1:])
    if tag != f"v{version}":
        fail(f"release tag {tag!r} does not match stable version {version}")
    if release.get("draft") is not False:
        fail(f"release {tag} metadata does not confirm draft=false")
    if release.get("prerelease") is not False:
        fail(f"release {tag} metadata does not confirm prerelease=false")
    published_at = release.get("published_at")
    if not isinstance(published_at, str) or not published_at.strip():
        fail(f"release {tag} metadata has no published_at identity")
    assets = release.get("assets")
    if not isinstance(assets, list):
        fail("release metadata has no assets list")
    by_name = {a.get("name"): a for a in assets if isinstance(a, dict)}
    archive_name = f"emit-{version}.tar.gz"
    if archive_name not in by_name or "SHA256SUMS" not in by_name:
        fail(f"release {tag} is missing {archive_name} or SHA256SUMS")
    archive_url = checked_asset_url(by_name[archive_name].get("browser_download_url"), tag, archive_name)
    checksums_url = checked_asset_url(by_name["SHA256SUMS"].get("browser_download_url"), tag, "SHA256SUMS")
    release_url = f"https://github.com/{REPO}/releases/tag/{tag}"
    if release.get("html_url") != release_url:
        fail(f"unexpected release page URL for {tag}: {release.get('html_url')!r}")
    return {"version": version, "tag": tag, "archive_url": archive_url,
            "checksums_url": checksums_url, "release_url": release_url}


def resolve(metadata_path=None):
    if metadata_path:
        try:
            data = json.loads(Path(metadata_path).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"cannot read release metadata {metadata_path}: {exc}")
        if isinstance(data, list):
            stable = [item for item in data if isinstance(item, dict)
                      and item.get("draft") is False and item.get("prerelease") is False
                      and isinstance(item.get("published_at"), str) and item["published_at"].strip()]
            stable.sort(key=lambda item: item["published_at"], reverse=True)
            if not stable:
                fail("release metadata contains no published stable release")
            data = stable[0]
    else:
        try:
            request = Request(API, headers={"Accept": "application/vnd.github+json",
                                            "User-Agent": "emit-packages-release-check"})
            token = os.environ.get("GH_TOKEN")
            if token:
                request.add_header("Authorization", f"Bearer {token}")
            with urlopen(request, timeout=30) as response:
                data = json.load(response)
        except (OSError, URLError, json.JSONDecodeError) as exc:
            fail(f"cannot resolve latest stable Emit release: {exc}")
    return target_from_release(data)


def read_target(path):
    try:
        target = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read target {path}: {exc}")
    if not isinstance(target, dict):
        fail(f"target {path} is not a JSON object")
    canonical = target_from_release({
        "tag_name": target.get("tag"), "draft": False, "prerelease": False,
        "published_at": "target identity",
        "html_url": target.get("release_url"), "assets": [
            {"name": f"emit-{target.get('version')}.tar.gz", "browser_download_url": target.get("archive_url")},
            {"name": "SHA256SUMS", "browser_download_url": target.get("checksums_url")},
        ]})
    if target != canonical:
        fail(f"target {path} has unexpected or missing fields")
    return canonical


def emit_version(binary):
    import subprocess
    try:
        done = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f"cannot run Emit binary {binary}: {exc}")
    match = re.fullmatch(r"emit ([^\s]+)(?: \(LLVM [^\r\n]+\))?\s*", done.stdout)
    if done.returncode or not match or not VERSION_RE.fullmatch(match.group(1)):
        fail(f"malformed Emit version output from {binary}: {done.stdout.strip()!r} (exit {done.returncode})")
    return match.group(1)


def verify(target_file, emit=None, source=None):
    started = time.monotonic()
    target = read_target(target_file)
    if (emit is None) == (source is None):
        fail("verify requires exactly one of --emit or --source")
    if emit is not None:
        actual = emit_version(emit)
        identity = str(emit)
    else:
        version_file = Path(source) / "VERSION"
        try:
            actual = version_file.read_text().strip()
        except OSError as exc:
            fail(f"cannot read source VERSION at {version_file}: {exc}")
        if not VERSION_RE.fullmatch(actual):
            fail(f"malformed source VERSION at {version_file}: {actual!r}")
        identity = str(Path(source).resolve())
    if actual != target["version"]:
        expected = target["version"]
        fail(f"Emit version mismatch: expected {expected}, actual {actual} ({identity})")
    tag = target["tag"]
    say(f"verify {identity} -> {actual}  [target {tag}, {time.monotonic() - started:.1f}s]")


def download(url, destination):
    req = Request(url, headers={"User-Agent": "emit-packages-release-check"})
    with urlopen(req, timeout=60) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def fetch_source(target_file, output_dir):
    started = time.monotonic()
    target = read_target(target_file)
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    version = target["version"]
    tag = target["tag"]
    archive_name = f"emit-{version}.tar.gz"
    destination = root / f"emit-{version}"
    if destination.exists() or destination.is_symlink():
        fail(f"source output already exists: {destination}; choose a new output directory")
    with tempfile.TemporaryDirectory(prefix="emit-source-") as temporary:
        work = Path(temporary)
        archive, checksums = work / archive_name, work / "SHA256SUMS"
        say(f"fetch Emit source {tag} -> {root}  [archive and checksums]")
        download(target["archive_url"], archive)
        download(target["checksums_url"], checksums)
        matches = []
        for line in checksums.read_text().splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == archive_name and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
                matches.append(parts[0].lower())
        if len(matches) != 1:
            fail(f"checksums file has {len(matches)} valid entries for {archive_name}")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive_size = archive.stat().st_size
        if digest != matches[0]:
            fail(f"source archive SHA-256 mismatch for {archive_name}: expected {matches[0]}, actual {digest}")
        stage = Path(tempfile.mkdtemp(prefix=".emit-source-stage-", dir=root))
        try:
            with tarfile.open(archive, "r:gz") as tar:
                members = tar.getmembers()
                prefix = f"emit-{version}/"
                for member in members:
                    name = member.name[2:] if member.name.startswith("./") else member.name
                    in_root = name == prefix.rstrip("/") or name.startswith(prefix)
                    safe_type = member.isdir() or member.isfile() or member.issym()
                    safe_link = True
                    if member.issym():
                        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), member.linkname))
                        safe_link = not member.linkname.startswith("/") and (resolved == prefix.rstrip("/") or resolved.startswith(prefix))
                    if (not in_root or Path(name).is_absolute() or ".." in Path(name).parts
                            or not safe_type or not safe_link or member.islnk()):
                        fail(f"unsafe source archive member: {member.name}")
                tar.extractall(stage, members=members, filter="data")
            staged_source = stage / f"emit-{version}"
            version_path = staged_source / "VERSION"
            if not version_path.is_file():
                fail(f"source archive is missing VERSION: {version_path}")
            actual = version_path.read_text().strip()
            if actual != version:
                fail(f"source archive VERSION mismatch: expected {version}, actual {actual}")
            staged_source.rename(destination)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
    absolute = str(destination.resolve())
    elapsed = time.monotonic() - started
    say(f"extract {archive_name} -> {absolute}  [{archive_size} bytes, sha256 {digest}, {elapsed:.1f}s]")
    print(absolute)


def aggregate(results):
    if not results:
        fail("aggregate requires at least one RESULT")
    bad = [result for result in results if result != "success"]
    if bad:
        fail(f"aggregate failed: {len(bad)}/{len(results)} results were not success: {', '.join(bad)}")
    say(f"aggregate {len(results)} results -> success")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("resolve", help="resolve the latest stable release to JSON")
    p.add_argument("--output", required=True)
    p.add_argument("--metadata", help="offline release metadata JSON fixture")
    p = commands.add_parser("verify", help="verify a binary or source VERSION against a target")
    p.add_argument("--target", required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--emit")
    group.add_argument("--source")
    p = commands.add_parser("fetch-source", help="download, verify, and extract release sources")
    p.add_argument("--target", required=True)
    p.add_argument("--output-dir", required=True)
    p = commands.add_parser("aggregate", help="fail unless every supplied result is success")
    p.add_argument("results", nargs="*")
    args = parser.parse_args()
    try:
        if args.command == "resolve":
            started = time.monotonic()
            target = resolve(args.metadata)
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            content = json.dumps(target, indent=2) + "\n"
            path.write_text(content)
            tag = target["tag"]
            say(f"resolve latest stable Emit -> {path}  [{len(content.encode())} bytes, {time.monotonic() - started:.1f}s, {tag}]")
        elif args.command == "verify":
            verify(args.target, emit=args.emit, source=args.source)
        elif args.command == "fetch-source":
            fetch_source(args.target, args.output_dir)
        else:
            aggregate(args.results)
    except (ValueError, OSError, tarfile.TarError, URLError) as exc:
        print(f"emit-release: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
