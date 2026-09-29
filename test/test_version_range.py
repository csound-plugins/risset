#!/usr/bin/env python3
"""
Regression tests for csound version-range parsing and binary selection.

These are pure-python tests: no csound installation is required.

The bug guarded against here: a range like ``>=6.17<7.0`` (the csound 6
binary of e.g. the ``else`` plugin) used to be treated as *inclusive* of 7.0,
so a csound 7.0 system matched both the csound6 and the csound7 binaries and
risset selected the first one (csound6).
"""

import sys
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
        # a csound6 range must not include 7.0
        (">=6.17<7.0", 6170, True),
        (">=6.17<7.0", 6180, True),
        (">=6.17<7.0", 6190, True),
        (">=6.17<7.0", 7000, False),
        (">=6.17<7.0", 6160, False),
        # inclusive upper bound
        (">=6.17<=7.0", 7000, True),
        # a csound7 range
        (">=7.0", 7000, True),
        (">=7.0", 8000, True),
        (">=7.0", 6180, False),
        # strict lower bound
        (">6.17", 6180, True),
        (">6.17", 6170, False),
        # strict/inclusive upper bound only
        ("<7.0", 6190, True),
        ("<7.0", 7000, False),
        ("<=7.0", 7000, True),
        (">=7.0<8.0", 7010, True),
        (">=7.0<8.0", 8000, False),
    ]
    for rangestr, versionid, expected in cases:
        got = risset._parse_version(rangestr).contains(versionid)
        errors += check(got == expected,
                        f"_parse_version({rangestr!r}).contains({versionid}) = {got}, expected {expected}")
    return errors


def _make_binary(platform: str, url: str, csound_version: str) -> risset.Binary:
    return risset.Binary(platform=platform, url=url, csound_version=csound_version)


def test_find_binary() -> int:
    # Mirrors the relevant entries of the `else` plugin manifest
    csound6 = _make_binary("linux-x86_64",
                           "https://example.com/plugins-csound6-linux.zip",
                           ">=6.17<7.0")
    csound7 = _make_binary("linux-x86_64",
                           "https://example.com/plugins-csound7-linux-x86_64.zip",
                           ">=7.0")
    plugin = risset.Plugin(
        name="else",
        url="https://example.com/else.git",
        version="2.4.4",
        short_description="",
        binaries=[csound6, csound7],
        opcodes=["lfnoise"],
        author="",
        email="",
        cloned_path=Path("/tmp/nonexistent"),
    )

    errors = 0
    selected = plugin.find_binary(platformid="linux-x86_64", csound_version=7000)
    errors += check(selected is csound7, "csound 7.0 must select the csound7 binary")
    selected = plugin.find_binary(platformid="linux-x86_64", csound_version=6180)
    errors += check(selected is csound6, "csound 6.18 must select the csound6 binary")
    return errors


def main() -> int:
    errors = test_version_range() + test_find_binary()
    if errors:
        print(f"{errors} test(s) failed", file=sys.stderr)
        return 1
    print("OK: version range and binary selection tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
