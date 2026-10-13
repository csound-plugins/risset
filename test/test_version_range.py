#!/usr/bin/env python3
"""
Regression tests for csound version-range parsing and binary selection.

These are pure-python tests: no csound installation is required.

risset only supports csound 7 and later. Csound 6 version ranges (for example
``>=6.17<7.0``) are no longer usable: a binary declaring such a range is
skipped when parsing a manifest, and querying a csound 6 version is an error.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import risset


def check(condition: bool, message: str) -> int:
    if not condition:
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    return 0


def test_version_range() -> int:
    errors = 0
    cases = [
        # (version range, versionid, expected)
        ("==7.0", 7000, True),
        ("==7.0", 7010, False),
        # a csound7 range
        (">=7.0", 7000, True),
        (">=7.0", 8000, True),
        (">=7.0<8.0", 7010, True),
        (">=7.0<8.0", 8000, False),
        # strict lower bound
        (">7.0", 7010, True),
        (">7.0", 7000, False),
        # upper bound only
        ("<8.0", 7010, True),
        ("<8.0", 8000, False),
        ("<=8.0", 8000, True),
    ]
    for rangestr, versionid, expected in cases:
        got = risset._parse_version(rangestr).contains(versionid)
        errors += check(got == expected,
                        f"_parse_version({rangestr!r}).contains({versionid}) = {got}, expected {expected}")

    # a csound 6 version is not a valid version id anymore
    try:
        risset._parse_version(">=7.0").contains(6180)
        errors += check(False, "contains(6180) should raise ValueError")
    except ValueError:
        pass
    return errors


def test_csound6_ranges() -> int:
    """Csound 6 ranges are recognized and rejected"""
    errors = 0
    csound6_only = [">=6.17<7.0", "==6.18", "<7.0", "<=6.18"]
    for rangestr in csound6_only:
        vrange = risset._parse_version(rangestr)
        errors += check(not vrange.supports_csound7(),
                        f"_parse_version({rangestr!r}) should not support csound 7")
        # and it must never match 7.0
        errors += check(not vrange.contains(7000),
                        f"_parse_version({rangestr!r}).contains(7000) should be False")

    csound7_ranges = [">=7.0", "==7.0", ">=6.17", "<=7.0", ">=7.0<8.0"]
    for rangestr in csound7_ranges:
        errors += check(risset._parse_version(rangestr).supports_csound7(),
                        f"_parse_version({rangestr!r}) should support csound 7")

    # a csound6 binary definition is rejected when parsing a manifest
    binarydef = {"platform": "linux", "url": "https://example.com/x.so",
                 "csound_version": ">=6.17<7.0"}
    try:
        risset._parse_binarydef(binarydef, substitutions={})
        errors += check(False, "_parse_binarydef should reject a csound 6 binary")
    except risset.Csound6BinaryError:
        pass
    return errors


def _make_binary(platform: str, url: str, csound_version: str) -> risset.Binary:
    return risset.Binary(platform=platform, url=url, csound_version=csound_version)


def _manifest(binaries: list[dict]) -> dict:
    return {
        "name": "legacy",
        "version": "1.0.0",
        "short_description": "test plugin",
        "author": "a",
        "email": "a@b.c",
        "opcodes": ["foo"],
        "binaries": binaries,
    }


def test_plugin_without_csound7_binaries() -> int:
    """
    A plugin whose binaries are all for csound 6 must be skipped (return None)
    instead of raising; the reason is logged at debug level only.
    """
    original = risset._git_local_path
    # avoid cloning a repository while parsing the manifest
    risset._git_local_path = lambda url, update=False: Path(tempfile.gettempdir())
    try:
        csound6only = _manifest([
            {"platform": "linux", "url": "https://example.com/old.so",
             "csound_version": ">=6.17<7.0"},
            {"platform": "macos", "url": "https://example.com/old.dylib",
             "csound_version": "==6.18"},
        ])
        plugin = risset._plugin_from_dict(csound6only, pluginurl="https://example.com/r.git", subpath="")
        errors = check(plugin is None, "a csound-6-only plugin should be skipped (None)")

        mixed = _manifest([
            {"platform": "linux", "url": "https://example.com/old.so",
             "csound_version": ">=6.17<7.0"},
            {"platform": "linux", "url": "https://example.com/new.so",
             "csound_version": ">=7.0"},
        ])
        plugin = risset._plugin_from_dict(mixed, pluginurl="https://example.com/r.git", subpath="")
        errors += check(plugin is not None, "a plugin with a csound 7 binary should be kept")
        if plugin is not None:
            errors += check([b.csound_version for b in plugin.binaries] == [">=7.0"],
                            "the csound 6 binary should have been dropped")
    finally:
        risset._git_local_path = original
    return errors


def test_find_binary() -> int:
    csound7 = _make_binary("linux-x86_64",
                           "https://example.com/plugins-csound7-linux-x86_64.zip",
                           ">=7.0")
    plugin = risset.Plugin(
        name="else",
        url="https://example.com/else.git",
        version="2.4.4",
        short_description="",
        binaries=[csound7],
        opcodes=["lfnoise"],
        author="",
        email="",
        cloned_path=Path("/tmp/nonexistent"),
    )

    errors = 0
    selected = plugin.find_binary(platformid="linux-x86_64", csound_version=7000)
    errors += check(selected is csound7, "csound 7.0 must select the csound7 binary")

    # querying a csound 6 version is an error
    try:
        plugin.find_binary(platformid="linux-x86_64", csound_version=6180)
        errors += check(False, "find_binary with csound 6 version should raise ValueError")
    except ValueError:
        pass
    return errors


def main() -> int:
    errors = (test_version_range() + test_csound6_ranges()
              + test_plugin_without_csound7_binaries() + test_find_binary())
    if errors:
        print(f"{errors} test(s) failed", file=sys.stderr)
        return 1
    print("OK: version range and binary selection tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
