#!/usr/bin/env python3

from __future__ import annotations

import importlib.metadata
import sys

if (sys.version_info.major, sys.version_info.minor) < (3, 9):
    print("Python 3.9 or higher is needed", file=sys.stderr)
    sys.exit(-1)

if len(sys.argv) >= 2 and (sys.argv[1] == "--version" or sys.argv[1] == "-v"):
    print(importlib.metadata.version("risset"))
    sys.exit(0)

import argparse
import fnmatch
import glob
import inspect as _inspect
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict as _asdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Callable


class PlatformNotSupportedError(Exception):
    """Raised when the current platform is not supported"""


class SchemaError(Exception):
    """An entity (a dict, a json file) does not fulfill the needed schema"""


class ParseError(Exception):
    """Parse error in a manifest file"""


def _subproc_call(args: list[str] | str, shell: bool | None = None):
    if shell is None:
        shell = isinstance(args, str)
    _debug(f"Calling subprocess with shell={shell}: {args}")
    return subprocess.call(args, shell=shell)


def _data_dir_for_platform() -> Path:
    """
    Returns the data directory for the given platform
    """
    platform = sys.platform
    if platform == 'linux':
        return Path("~/.local/share").expanduser()
    elif platform == 'darwin':
        return Path("~/Library/Application Support").expanduser()
    elif platform == 'win32':
        p = R"C:\Users\$USERNAME\AppData\Local"
        return Path(os.path.expandvars(p))
    else:
        raise PlatformNotSupportedError(f"Platform unknown: {platform}")


INDEX_GIT_REPOSITORY = "https://github.com/csound-plugins/risset-data"
RISSET_ROOT = _data_dir_for_platform() / "risset"
RISSET_DATAREPO_LOCALPATH = RISSET_ROOT / "risset-data"
RISSET_GENERATED_DOCS = RISSET_ROOT / "man"
RISSET_CLONES_PATH = RISSET_ROOT / "clones"
RISSET_ASSETS_PATH = RISSET_ROOT / "assets"
RISSET_OPCODESXML = RISSET_ROOT / "opcodes.xml"
_MAININDEX_PICKLE_FILE = RISSET_ROOT / "mainindex.pickle"
MACOS_ENTITLEMENTS_PATH = RISSET_ASSETS_PATH / 'csoundplugins.entitlements'

UNKNOWN_VERSION = "Unknown"


_supported_platforms = {
    'macos-x86_64',
    'linux-x86_64',
    'windows-x86_64',
    'macos-arm64',
    'linux-arm64'
}


_UNSET = object()


_entitlements_str = r"""
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.disable-library-validation</key>
    <true/>
    <key>com.apple.security.device.audio-input</key>
    <true/>
    <key>com.apple.security.device.camera</key>
    <true/>
</dict>
</plist>
"""


def _macos_save_entitlements(session: _Session) -> Path:
    path = MACOS_ENTITLEMENTS_PATH
    _ensure_parent_exists(path)
    if not _session.entitlements_saved:
        with open(path, 'w') as f:
            f.write(_entitlements_str)
        assert os.path.exists(path)
        plutil = shutil.which('plutil')
        if plutil:
            _debug(f"Verifying that the entitlements file '{path}' is a valid plist")
            _subproc_call([plutil, path.as_posix()])
        session.entitlements_saved = True
        _debug(f"Saved entitlements file to {path}")
        _debug(f"Entitlements:\n{open(path).read()}\n------------ end entitlements")

    return path

# SIGNATURE_ID="-"
# codesign --force --sign "${SIGNATURE_ID}" --entitlements csoundplugins.entitlements "/path/to/dylib"


def macos_codesign(dylibpaths: list[str], signature='-') -> None:
    """
    Codesign the given library binaries using entitlements

    Args:
        dylibpaths: a list of paths to codesign
        signature: the signature used. '-' indicates to sign it locally
    """
    if not shutil.which('codesign'):
        raise RuntimeError("Could not find the binary 'codesign' in the path")
    entitlements_path = _macos_save_entitlements(_session)
    assert os.path.exists(entitlements_path)
    for dylibpath in dylibpaths:
        _subproc_call(['codesign', '--force', '--sign', signature, '--entitlements', entitlements_path.as_posix(), dylibpath])
        _debug("Verifying code signing")
        _subproc_call(['codesign', '--display', '--verbose', dylibpath])


def _normalize_platform(s: str) -> str:
    """
    Normalizes platform definition as used in risset.json

    Handles the case where, for compatibility reasons, the
    architecture might be missing, so this function resolves,
    for example, 'windows' to 'windows-x86_64'.

    'linux' and 'windows' resolve to 'linux-x86_64' and 'windows-x86_64',
    'macos' resolves to 'macos-arm64'

    Otherwise the platform definition should consist of a pair <os>-<arch>,
    like "macos-arm64" or "linux-x86_64"

    Returns:
        the normalized platform or an empty string if the given
        value is not a valid platform

    Raises ValueError if the platform is not supported
    """
    if s in ('windows', 'linux'):
        s += '-x86_64'
    elif s == 'macos':
        s += '-arm64'

    return s if s in _supported_platforms else ''


def _platform_architecture() -> str:
    """
    Returns the architecture for this platform

    The architecture is one of 'x86_64' (intel, 64bits),
    'x86' (intel, 32bits), 'arm64' (arm 64bits) or 'arm32' (arm 32bits)
    """
    machine = platform.machine().lower()
    bits, linkage = platform.architecture()
    if machine == 'arm':
        if bits == '64bit':
            return 'arm64'
        elif bits == '32bit':
            return 'arm32'
    elif machine == 'arm64':
        return 'arm64'
    elif machine == 'x86_64' or machine.startswith('amd64') or machine.startswith('intel64'):
        return 'x86_64'
    elif machine == 'i386':
        if bits == '64bit':
            return 'x86_64'
        elif bits == '32bit':
            return 'x86'

    raise RuntimeError(f"** Architecture not supported (machine='{machine}', {bits=}, {linkage=})")


def _csoundlib_version() -> tuple[int, int]:
    """Returns a tuple (major, minor) using the csound api

    This version can differ from the version of the installed csound binary
    """
    import libcsound
    versionid = libcsound.VERSION
    major = versionid // 1000
    minor = (versionid - major*1000) // 10
    return major, minor


def _csound_version(csoundexe='csound') -> tuple[int, int, str]:
    """
    Query the csound version via the executable

    Args:
        csoundexe: the csound executable

    Returns:
        a tuple (major: int, minor: int, rest: str)
    """
    csound_bin = _get_csound_binary(csoundexe)
    if not csound_bin:
        raise OSError("csound binary not found")
    proc = subprocess.Popen([csound_bin, "--version"], stderr=subprocess.PIPE)
    proc.wait()
    assert proc.stderr is not None
    out = proc.stderr.read().decode('ascii')
    for line in out.splitlines():
        if match := re.search(r'--Csound\s+version\s+(\d+)\.(\d+)(.*)', line):
            major = int(match.group(1))
            minor = int(match.group(2))
            rest = match.group(3)
            return major, minor, rest
    raise ValueError("Could not find a version number in the output")


class _Session:
    """
    Simgleton class to hold information about the session

    This class keeps track of downloaded files, cloned repos, etc.
    """
    instance: _Session | None = None

    def __new__(cls, *args, **kwargs):
        if _Session.instance is not None:
            return _Session.instance

        instance = super().__new__(cls, *args, **kwargs)
        _Session.instance = instance
        return instance

    def __init__(self):
        self.downloaded_files: dict[str, Path] = {}
        self.cloned_repos: dict[str, Path] = {}
        self.platform: str = {
            'linux': 'linux',
            'darwin': 'macos',
            'win32': 'windows'
        }[sys.platform]

        self.architecture = _platform_architecture()
        """The current architecture"""

        self.platformid = self._platform_id()
        """The pair <os>-<arch> (linux-x86_64, windows-x86_64, macos-arm64, etc"""

        major, minor = _csoundlib_version()

        self.debug = False
        """True if in debug mode"""

        self.csound_version_tuple = (major, minor)
        """Csound version as (major, minor)"""

        self.csound_version: int = major * 1000 + minor * 10
        """Csound version id as integer, 6190 = 6.19, 7000 = 7.0"""

        self.stop_on_errors = True
        self.entitlements_saved = False
        self.cache = {}

    def _platform_id(self) -> str:
        """
        Returns one of 'linux', 'windows', 'macos' (intel x86_64) or their 'arm64' variant:
        'macos-arm64', 'linux-arm64', etc.
        """
        return f'{self.platform}-{self.architecture}'


_session = _Session()


@dataclass
class _VersionRange:
    minversion: int
    maxversion: int
    includemin: bool = True
    includemax: bool = False

    def __post_init__(self):
        assert isinstance(self.minversion, int) and self.minversion >= 6000, f"Got {self.minversion}"
        assert isinstance(self.maxversion, int) and self.maxversion >= 6000, f"Got {self.maxversion}"

    def contains(self, versionid: int) -> bool:
        """
        Returns True if version is contained within this version range

        Args:
            version: a version id, where version id is ``int(major.minor * 1000)``

        Returns:
            True if *version* is within this range

        Example
        -------

            >>> v = _VersionRange(minversion=6180, maxversion=7000, includemin=True, includemax=False)
            >>> v.contains(6190)
            True
            >>> v.contains(7000)
            False
        """
        if not isinstance(versionid, int) or versionid < 6000:
            raise ValueError(f"Invalid versionid, got {versionid}")
        a = versionid > self.minversion if not self.includemin else versionid >= self.minversion
        maxversion = self.maxversion or 99999
        b = versionid < maxversion if not self.includemax else versionid <= maxversion
        return a and b


def _termsize(width=80, height=25) -> tuple[int, int]:
    if not sys.stdout.isatty():
        return width, height

    try:
        t = os.get_terminal_size()
        return t.columns, t.lines
    except Exception:
        _debug(f"Could not determine terminal size, using default values {width=}, {height=}")
        return width, height


def _version_to_versionid(versionstr: str) -> int:
    if '.' not in versionstr:
        return int(versionstr)
    majors, minors = versionstr.split('.', maxsplit=1)
    patch = 0
    if '.' in minors:
        minors, patchs = minors.split('.', maxsplit=1)
        patch = int(patchs)
        assert 0 <= patch < 10
    versionid = int(majors) * 1000 + int(minors) * 10 + patch
    return versionid


def _parse_version(versionstr: str) -> _VersionRange:
    versionstr = versionstr.replace(' ', '')
    if versionstr.startswith("=="):
        exactversionstr = versionstr[2:]
        versionid = _version_to_versionid(exactversionstr)
        return _VersionRange(minversion=versionid, maxversion=versionid, includemin=True, includemax=True)

    parts = re.split(r"(>=|<=|>|<)", versionstr)
    parts = [p for p in parts if p]
    if len(parts) % 2 != 0:
        raise ParseError(f"Could not parse version range: {versionstr}, parts: {parts}")
    minversion = 6000
    maxversion = 9999
    includemax = False
    includemin = False
    for op, version in zip(parts[::2], parts[1::2]):
        assert op in ('<', '>', '<=', '>=')
        if op[0] == '<':
            maxversion = _version_to_versionid(version)
            if op[-1] == '=':
                includemax = True
        elif op[0] == '>':
            minversion = _version_to_versionid(version)
            if op[-1] == '=':
                includemin = True
        else:
            raise ParseError(f"Could not parse version range: {versionstr}, operator {op} not supported")
    return _VersionRange(minversion=minversion, maxversion=maxversion, includemin=includemin, includemax=includemax)


def _abbrev(s: str, maxlen: int) -> str:
    """Abbreviate string"""
    assert maxlen > 18
    lens = len(s)
    if lens < maxlen:
        return s
    rightlen = min(8, lens // 5)
    return f"{s[:lens - rightlen - 1]}…{s[-rightlen:]}"


def _mainindex_retrieve(days_threshold=10) -> MainIndex | None:
    """
    Try to retrieve a previously pickled mainindex
    """
    picklefile = _MAININDEX_PICKLE_FILE
    if not picklefile.exists():
        return None
    import pickle
    import time
    days_since_last_modification = (picklefile.stat().st_mtime - time.time()) / 86400
    if days_since_last_modification > days_threshold:
        return None
    _debug("Recreating main index from pickled version")
    f = open(picklefile, "rb")
    try:
        return pickle.load(f)
    except Exception as e:
        _errormsg(f"Could not retrieve mainindex from serialized file: {e}")
        _debug(f"Serialized file ({picklefile}) removed")
        os.remove(picklefile)
        return None


def _is_git_repo(path: str | Path) -> bool:
    """
    If `path` a valid git repo?
    """
    # via https://remarkablemark.org/blog/2020/06/05/check-git-repository/
    if isinstance(path, Path):
        path = path.as_posix()
    out = subprocess.check_output(["git", "-C", path, "rev-parse", "--is-inside-work-tree"]).decode("utf-8").strip()
    return out == "true"


def _git_reponame(url: str) -> str:
    """
    Returns the name fo the git repository given as url

    =======================================  =======
    url                                      name
    =======================================  =======
    https://github.com/user/foo.git          foo
    https://gitlab.com/baz/bar.git           bar
    =======================================  =======
    """
    parts = url.split("/")
    if not parts[-1].endswith(".git"):
        raise ValueError(f"A git url should always end in '.git': {url}")
    return parts[-1].rsplit(".", maxsplit=1)[0]


def _is_git_url(url: str) -> bool:
    """
    Is `url` an url to a git repo?
    """
    return _is_url(url) and url.endswith(".git")


def _debug(*msgs, ljust=20) -> None:
    """ Print debug info only if debugging is turned on """
    if _session.debug:
        caller = _abbrev(_inspect.stack()[1][3], ljust)
        print(f"DEBUG:{caller.ljust(ljust)}:", *msgs, file=sys.stderr)


def _errormsg(msg: str) -> None:
    """ Print error message """
    lines = msg.splitlines()
    print("** Error:", lines[0], file=sys.stderr)
    for line in lines[1:]:
        print("         ", line, file=sys.stderr)


def _info(*msgs: str) -> None:
    print(*msgs)


class ErrorMsg(str):
    pass


@dataclass
class Asset:
    """
    An Asset describes any file/files distributed alongside a plugin

    The use case is for data files which are needed by a plugin at runtime

    Attribs:
        source: the source where to get the assets from. It can be a url to a git repository,
            the direct url to a downloadable file/zip file or the path to a local
            folder
        patterns: the paths to extract from the source (if needed). Each item can be either
            a path relative to the root of the git or zip file, or a glob pattern. In the
            case where the url points to a concrete file (not a zip or a git repo), this
            attributes should be empty
        platform: if given, the platform for which this assets are valid (in the case
            of binaries of some kind)
        name: the name of the asset (optional)
    """
    source: str
    """the url where to download the assets from"""

    patterns: list[str]
    """the paths to extract from the url (if needed). It can be a glob pattern"""

    platform: str = 'all'
    """the platform for which this assets are valid"""

    name: str = ''

    def __post_init__(self):
        assert self.source

    def identifier(self) -> str:
        if self.name:
            return self.name
        if self.patterns:
            return f"{self.source}::{','.join(str(patt) for patt in self.patterns)}"
        return self.source

    def local_path(self) -> Path:
        assert self.source
        if _is_url(self.source):
            if _is_git_url(self.source):
                return _git_local_path(self.source)
            else:
                _debug(f"Downloading url {self.source}")
                return _download_file(self.source)
        else:
            # it is a path, check that it exists
            source = Path(self.source)
            assert source.exists(), f"Assert source does not exist: {source}"
            return source

    def retrieve(self) -> list[Path]:
        """
        Download and resolve all files, if needed

        Returns:
            a (possibly empty) list of local paths which belong to this asset.
            In the case of an asset referring to a file within a zip, the
            files are extracted to a temp dir and a path to that temp dir
            is returned
        """
        assert self.source and (_is_url(self.source) or os.path.isabs(self.source)), \
            f"Source should be either a url or an absolute path: {self.source}"
        # self.url is either a git repo or a url pointing to a file
        root = self.local_path()
        if root.is_dir():
            assert _is_git_repo(root)
            _git_update(root)
            collected_assets: list[Path] = []
            for pattern in self.patterns:
                matchedfiles = glob.glob((root/pattern).as_posix())
                collected_assets.extend(Path(m) for m in matchedfiles)
            return collected_assets
        elif root.suffix == '.zip':
            _debug(f"Extracting {self.patterns} from {root}")
            outfiles = _zip_extract(root, self.patterns)
            _debug(f"Extracted {outfiles} from {root}")
            return outfiles
        else:
            # root is a file
            return [root]


@dataclass
class Binary:
    """
    A Binary describes a plugin binary

    Attribs:
        platform: the platform/architecture for which this binary is built. Possible platforms:
            'linux' (x86_64), 'windows' (windows 64 bits), 'macos' (x86_64)
        url: either a http link to a binary/.zip file, or empty if the plugin's location is relative to the
            manifest definition
        build_platform: the platform this binary was built with. Might serve as an orientation for
            users regarding the compatibility of the binary. It can be anything but expected values
            might be something like "macOS 11.xx.
        extractpath: in the case of using a .zip file as url, the extract path should indicate
            a relative path to the binary within the .zip file structure
        post_install_script: a script to run after the binary has been installed
    """
    platform: str
    """The platform for which this binary was compiled.

    A pair <os>-<arch>, where os is one of linux, windows, macos, and
    arch is one of 'x86_64', 'arm64'. See _supported_platforms for an
    up-to-date list"""

    url: str
    """The url of the binary (can be a zip file)"""

    csound_version: str
    """The version range for which this binary is valid (can be of the form >=P.q<X.y)"""

    extractpath: str = ''
    """In the case of the url being an archive, this indicates the relative path of the binary within that archive"""

    build_platform: str = ''
    """If known, the platform under which this binary was built. This can be anything, it is just informative"""

    post_install_script: str = ''
    """A script to run after installation"""

    _csound_version_range: _VersionRange | None = None

    def __post_init__(self):
        platform = _normalize_platform(self.platform)
        if not platform:
            raise ValueError(f"Invalid platform '{self.platform}', expected one of {_supported_platforms}")
        self.platform = platform

    def csound_version_range(self) -> _VersionRange:
        if self._csound_version_range is None:
            self._csound_version_range = _parse_version(self.csound_version)
        return self._csound_version_range

    def matches_versionid(self, versionid: int) -> bool:
        """
        Does this binary apply to the  given versionid?

        Returns:
            True if the versionid is contained within the version range of this binary
        """
        assert isinstance(versionid, int) and versionid >= 6000, f"Got {versionid}"
        return self.csound_version_range().contains(versionid)

    def binary_filename(self) -> str:
        """
        The filename of the binary
        """
        if not self.url.endswith('.zip'):
            return os.path.split(self.url)[1]
        else:
            assert self.extractpath
            return os.path.split(self.extractpath)[1]


@dataclass
class ManPage:
    syntaxes: list[str]
    abstract: str


@dataclass
class IndexItem:
    """
    An  entry in the risset index

    Attribs:
        name: the name of the entity
        url: the url of the git repository
        path: the relative path within the repository to the risset.json file.
    """
    name: str
    url: str
    path: str = ''

    def manifest_path(self) -> Path:
        localpath = _git_local_path(self.url)
        assert localpath.exists()
        manifest_path = localpath / self.path
        if manifest_path.is_file():
            assert manifest_path.suffix == ".json"
        else:
            manifest_path = manifest_path / "risset.json"
        if not manifest_path.exists():
            raise RuntimeError(f"For plugin {self.name} ({self.url}, cloned at {localpath}"
                               f" the manifest was not found at the expected path: {manifest_path}")
        return manifest_path

    def update(self) -> None:
        path = _git_local_path(self.url)
        _git_update(path)

    def read_definition(self: IndexItem) -> Plugin:
        """
        Read the plugin definition pointed by this plugin source

        Returns:
            a Plugin

        Raises: PluginDefinitionError if there is an error
        """
        manifest = self.manifest_path()
        assert manifest.exists() and manifest.suffix == '.json'
        try:
            plugin = _read_plugindef(manifest.as_posix(), url=self.url,
                                     manifest_relative_path=self.path)
        except Exception as e:
            _errormsg(f"Could not read manifest '{manifest.as_posix()}', error: '{e}'. "
                      f"I will update the index and try again")
            self.update()
            plugin = _read_plugindef(manifest.as_posix(), url=self.url,
                                     manifest_relative_path=self.path)
            _info("... ok, that worked")
        plugin.cloned_path = _git_local_path(self.url)
        return plugin


@dataclass
class Plugin:
    """
    Attribs:
        name: name of the plugin
        version: a version for this plugin, for update reasons
        short_description: a short description of the plugin or its opcodes
        binaries: a dict mapping platform to a Binary, like {'windows': Binary(...), 'linux': Binary(...)}
            Possible platforms are: 'linux', 'windows', 'macos', where in each case x86_64 is implied. Other
                platforms, when supported, will be of the form 'linux-arm64' or 'macos-arm64'
        opcodes: a list of opcodes defined in this plugin
        assets: a list of Assets
        author: the author of this plugin
        email: the email of the author
        cloned_path: path to the cloned repository
        doc_folder: the relative path to a folder holding the documentation for each opcode. This folder
            is relative to the manifest. If not provided it defaults to a "doc" folder placed
            besides the manifest
        url: the url of the git repository where this plugin is defined (notice that the binaries can
            be hosted inside this repository or in any other url)
        manifest_relative_path: the subdirectory within the repository where the "risset.json" file is
            placed. If not given, it is assumed that the manifest is placed at the root of the repository
            structure

    {
        "assets": [
            { "url": "...",
              "extractpath": "...",
              "platform": "linux"
            }
        ]
    }
    """
    name: str
    url: str
    version: str
    short_description: str
    binaries: list[Binary]
    opcodes: list[str]
    author: str
    email: str
    cloned_path: Path
    manifest_relative_path: str = ''
    long_description: str = ''
    doc_folder: str = 'doc'
    assets: list[Asset] | None = None

    def __post_init__(self):
        assert isinstance(self.binaries, list) and all(isinstance(b, Binary) for b in self.binaries)
        assert isinstance(self.opcodes, list)
        assert not self.assets or isinstance(self.assets, list)

    def __hash__(self):
        return hash((self.name, self.version))

    @property
    def versiontuple(self) -> tuple[int, int, int]:
        if self.version:
            return _version_tuple(self.version)
        return (0, 0, 0)

    def local_manifest_path(self) -> Path:
        """
        The local path to the manifest file of this plugin
        """
        return self.cloned_path / self.manifest_relative_path / "risset.json"

    def asdict(self) -> dict:
        d = _asdict(self)
        return d

    def manpage(self, opcode: str) -> Path | None:
        """
        Returns the path to the man page for opcode
        """
        markdownfile = opcode + ".md"
        path = self.resolve_doc_folder() / markdownfile
        return path if path.exists() else None

    def resolve_path(self, relpath: Path | str) -> Path:
        """
        Returns the absolute path relative to the manifest path of this plugin
        """
        root = self.local_manifest_path().parent
        return _resolve_path(relpath, root)

    def resolve_doc_folder(self) -> Path:
        """
        Resolve the doc folder for this plugin

        A doc folder can be declared in the manifest as a relative path
        to the manifest itself. If not given, it defaults to a 'doc' folder
        besides the manifest
        """
        root = self.local_manifest_path().parent
        doc_folder = _resolve_path(self.doc_folder or "doc", root)
        if not doc_folder.exists():
            raise OSError(f"No doc folder found (declared as {doc_folder}")
        return doc_folder

    def find_binary(self, platformid='', csound_version: int = 0
                    ) -> Binary | None:
        """
        Find a binary for the platform and csound versions given / current

        Args:
            platformid: the platform id. If intel x86-64, simply the platform ('macos', 'linux', 'windows'),
                otherwise the platform and architecture ('macos-arm64', 'linux-arm64', ...)
            csound_version: the csound version as int (6.18 = 6180, 6.19 = 6190, 7.01 = 7010). This should be
                the version of csound for which the plugin is to be installed. In the plugin definition each
                binary defines a version range for which it is built.

        Returns:
            a Binary which matches the given platform and csound version, or None
            if no match possible
        """

        if not csound_version:
            csound_version = _session.csound_version
        else:
            assert isinstance(csound_version, int) and csound_version >= 6000, f"Got {csound_version}"

        if not platformid:
            platformid = _session.platformid

        possible_binaries = [b for b in self.binaries
                             if b.platform == platformid and b.matches_versionid(csound_version)]
        if not possible_binaries:
            _debug(f"Plugin '{self.name}' does not seem to have a binary for platform '{platformid}'. "
                   f"Found binaries for platforms: {[b.platform for b in self.binaries]}")
            return None
        else:
            if len(possible_binaries) > 1:
                _debug(f"Found multiple binaries for {self.name}. Will select the first one")
            return possible_binaries[0]

    def available_binaries(self) -> list[str]:
        return [f"{binary.platform}/csound{binary.csound_version}"
                for binary in self.binaries]


@dataclass
class Opcode:
    name: str
    plugin: str
    syntaxes: list[str] | None = None
    abstract: str = ''
    installed: bool = True


@dataclass
class InstalledPluginInfo:
    """
    Information about an installed plugin

    Attribs:
        name: (str) name of the plugin
        dllpath: (Path) path of the plugin binary (a .so, .dll or .dylib file)
        installed_in_system_folder: (bool) is this installed in the systems folder?
        installed_manifest_path: (Path) the path to the installation manifest (a .json file)
        versionstr: (str) the installed version, as str (if installed via risset)
    """
    name: str
    dllpath: Path
    versionstr: str | None
    installed_manifest_path: Path | None = None
    installed_in_system_folder: bool = False

    @property
    def versiontuple(self) -> tuple[int, int, int]:
        return _version_tuple(self.versionstr) if self.versionstr and self.versionstr != UNKNOWN_VERSION else (0, 0, 0)


def _main_repository_path() -> Path:
    """
    Get the path of the main data repository

    The main repository is the repository holding risset's main index.
    The main index is a .json file with the name "rissetindex.json" where
    all plugins and other resources are indexed.

    The path returned here determines where this repository should be
    cloned locally
    """
    return RISSET_ROOT / "risset-data"


def user_plugins_path(version: int | tuple[int, int] | None = None) -> Path:
    """
    Return the install path for user plugins

    This returns the default path or the value of $CS_USER_PLUGINDIR. The env
    variable has priority

    Args:
        version: the csound version for which to determine the user plugins path

    Returns:
        the user plugins path, as a Path object
    """
    if version is None:
        version = _session.csound_version_tuple[0]
        major, minor = version, 0
    elif isinstance(version, tuple):
        major, minor = version[0], 0
    elif isinstance(version, int):
        major, minor = version, 0
    else:
        raise TypeError(f"Expected an int major version (6, or 7), a version "
                        f"tuple (6, 0) or None to use the installed version, "
                        f"got {version}")
    cs_user_plugindir = os.getenv("CS_USER_PLUGINDIR")
    if cs_user_plugindir:
        out = Path(cs_user_plugindir)
    else:
        pluginsdir = {
            'linux': f'$HOME/.local/lib/csound/{major}.{minor}/plugins64',
            'win32': f'C:\\Users\\$USERNAME\\AppData\\Local\\csound\\{major}.{minor}\\plugins64',
            'darwin': f'$HOME/Library/csound/{major}.{minor}/plugins64'
        }[sys.platform]
        out = Path(os.path.expandvars(pluginsdir))
    return out


def _is_glob(s: str) -> bool:
    return "*" in s or "?" in s


def _zip_extract_folder(zipfile: Path,
                        folder: str,
                        cleanup=True,
                        destroot: Path | None = None
                        ) -> Path:
    foldername = os.path.split(folder)[1]
    root = Path(tempfile.mktemp())
    root.mkdir(parents=True, exist_ok=True)
    from zipfile import ZipFile
    z = ZipFile(zipfile, 'r')
    pattern = folder + '/*'
    extracted = [z.extract(name, root) for name in z.namelist()
                 if fnmatch.fnmatch(name, pattern)]
    _debug(f"_zip_extract_folder: Extracted files from folder {folder}: {extracted}")
    if destroot is None:
        destroot = Path(tempfile.gettempdir())
    destfolder = destroot / foldername
    if destfolder.exists():
        _debug(f"_zip_extract_folder: Destination folder {destfolder} already exists, removing")
        _rm_dir(destfolder)
    shutil.move(root / folder, destroot)
    assert destfolder.exists() and destfolder.is_dir()
    if cleanup:
        _rm_dir(root)
    return destfolder


def _zip_extract(zipfile: Path, patterns: list[str]) -> list[Path]:
    """
    Extract multiple files from zip

    Args:
        zipfile: the zip file to extract from
        patterns: a list of filenames or glob patterns

    Returns:
        a list of output files extracted. If glob patterns were used there might be
        more output files than number of patterns. Otherwise there is a 1 to 1
        relationship between input and output
    """
    outfolder = Path(tempfile.gettempdir())
    from zipfile import ZipFile
    z = ZipFile(zipfile, 'r')
    out: list[Path] = []
    zipped = z.namelist()
    _debug(f"Inspecting zipfile {zipfile}, contents: {zipped}")
    for pattern in patterns:
        if _is_glob(pattern):
            _debug(f"Matching names against pattern {pattern}")
            for name in zipped:
                if name.endswith("/") and fnmatch.fnmatch(name[:-1], pattern):
                    # a folder
                    out.append(_zip_extract_folder(zipfile, name[:-1]))
                elif fnmatch.fnmatch(name, pattern):
                    _debug(f"   Name {name} matches!")
                    out.append(Path(z.extract(name, path=outfolder.as_posix())))
                else:
                    _debug(f"   Name {name} does not match")
        else:
            out.append(Path(z.extract(pattern, path=outfolder)))
    return out


def _zip_extract_file(zipfile: Path, extractpath: str) -> Path:
    """
    Extracts a file from a zipfile, returns the path to the extracted file

    Args:
        zipfile: the path to a local .zip file
        extractpath: the path to extract inside the .zip file

    Returns:
        the path of the extracted file.

    Raises KeyError if `extractpath` is not in `zipfile`
    """
    return _zip_extract(zipfile, [extractpath])[0]


def _csound_opcodes(method='api') -> set[str]:
    """
    Returns a set of installed opcodes

    Args:
        method: one of 'csound', 'api'
    """
    if method == 'api':
        try:
            import libcsound
        except ImportError:
            method = 'csound'

    if method == 'csound':
        csound_bin = _get_csound_binary("csound")
        if not csound_bin:
            raise RuntimeError("Did not find csound binary")
        proc = subprocess.run([csound_bin, "-z1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        txt = proc.stdout.decode('ascii')
        opcodes = []
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            opcodes.append(parts[0])
        return set(opcodes)
    elif method == 'api':
        import libcsound
        cs = libcsound.Csound()
        return set(opcode.name for opcode in cs.getOpcodes())
    else:
        raise ValueError(f"Method '{method}' unknown, possible methods: 'csound', 'api'")


def _plugin_extension() -> str:
    return {
        'linux': '.so',
        'darwin': '.dylib',
        'win32': '.dll'
    }[sys.platform]


def _get_path_separator() -> str:
    """Returns the path separator for the current platform"""
    if sys.platform == "win32":
        return ";"
    return ":"


def _get_shell() -> str | None:
    """
    Returns one of "bash", "zsh", "fish"

    If not able to get the given information, returns None
    In particular, in windows it returns None
    """
    if sys.platform == "win32":
        return
    shellenv = os.getenv("SHELL")
    if not shellenv:
        return None
    shell = os.path.split(shellenv)[1].strip()
    if shell in ("bash", "zsh", "fish"):
        return shell
    return None


def _get_csound_binary(binary) -> str | None:
    if (out := _session.cache.get('csound-bin', _UNSET)) is _UNSET:
        path = shutil.which(binary)
        _session.cache['csound-bin'] = out = path if path else None
    return out


def _get_git_binary() -> str:
    if (path := _session.cache.get('git-binary')) is None:
        path = shutil.which("git")
        if not path or not os.path.exists(path):
            raise RuntimeError("git binary not found")
        _session.cache['git-binary'] = path
    return path


def _ensure_parent_exists(path: Path) -> None:
    if path.is_dir():
        parent = path
    else:
        parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)


def _git_local_path(repo: str, update=False) -> Path:
    """
    Query the local path of the given repository, clone if needed

    Args:
        repo: the url of the git repository
        update: if not cloned, update the repo
    """
    if repo in _session.cloned_repos:
        return _session.cloned_repos[repo]
    assert repo and _is_git_url(repo), f"Invalid repository name: {repo}"
    _debug(f"Querying local path for repo {repo}")
    reponame = _git_reponame(repo)
    destination = RISSET_CLONES_PATH / reponame
    if destination.exists():
        assert _is_git_repo(destination), f"Expected {destination} to be a git repository"
        _session.cloned_repos[repo] = destination
        if update:
            _git_update(destination)
    else:
        _git_clone_into(repo, destination=destination, depth=1)
        _session.cloned_repos[repo] = destination
    return destination


def _git_clone_into(repo: str, destination: Path, depth=1) -> None:
    """
    Clone the given repository to the destination.

    Args:
        repo: the url to the repository
        destination: local path where the repository will be cloned
        depth: if > 0, the depth of the clone.
    """
    if not isinstance(destination, Path):
        raise TypeError("destination should be a Path")
    if not destination.is_absolute():
        raise ValueError("Destination should be an absolute path")
    if destination.exists():
        raise OSError("Destination path already exists, can't clone git repository")
    gitbin = _get_git_binary()
    _ensure_parent_exists(destination)
    args = [gitbin, "clone"]
    if depth > 0:
        args.extend(["--depth", str(depth)])
    args.extend([repo, str(destination)])
    _subproc_call(args)


def _git_repo_needs_update(repopath: Path) -> bool:
    """
    Check if a repository needs to be updated

    NB: for our use case, where no merges are expected, to update is just
    as fast as to check first and then act.
    """
    cwd = os.path.abspath(os.path.curdir)
    os.chdir(str(repopath))
    git = _get_git_binary()
    _subproc_call([git, "fetch"])
    headhash = subprocess.check_output([git, "rev-parse", "HEAD"]).decode('utf-8')
    upstreamhash = subprocess.check_output([git, "rev-parse", "master@{upstream}"]).decode('utf-8')
    _debug(f"Checking hashes, head: {headhash}, upstream: {upstreamhash}")
    os.chdir(cwd)
    return headhash != upstreamhash


def _git_update(repopath: Path, depth=0, check_if_needed=False) -> None:
    """
    Update the git repo at the given path
    """
    _debug(f"Updating git repository: {repopath}")
    if not repopath.exists():
        raise OSError(f"Can't find path to git repository {repopath}")
    if check_if_needed and not _git_repo_needs_update(repopath):
        _debug(f"Repository {repopath} up to date")
        return
    gitbin = _get_git_binary()
    cwd = os.path.abspath(os.path.curdir)
    os.chdir(str(repopath))
    args = [gitbin, "pull"]
    if depth > 0:
        args.extend(['--depth', str(depth)])
    if _session.debug:
        subprocess.call(args)
    else:
        subprocess.call(args, stdout=subprocess.PIPE)
    os.chdir(cwd)


def _version_tuple(versionstr: str) -> tuple[int, int, int]:
    """ Convert a version string to its integer parts """
    if not versionstr:
        raise ValueError("versionstr is empty")
    parts = versionstr.split(".", maxsplit=3)
    try:
        ints = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"Could not parse version '{versionstr}'")

    if len(ints) == 1:
        ints += [0, 0]
    elif len(ints) == 2:
        ints.append(0)
    elif len(ints) > 3:
        _debug("Too many version parts (max. 3), using the first 3")
        ints = ints[:3]
    i1, i2, i3 = ints
    return i1, i2, i3


def _find_system_plugins_path(possible_paths: list[Path], majorversion) -> Path | None:
    """
    Given a list of possible paths, find the folder where the system plugins are installed
    """
    ext = _plugin_extension()
    _debug("> Searching opcodes dir: ")

    if majorversion == 6:
        if sys.platform == "win32":
            dll = "arrayops.dll"
        else:
            dll = "libarrayops" + ext
    elif majorversion == 7:
        if sys.platform == 'win32':
            dll = "rtpa.dll"
        else:
            dll = "librtpa" + ext
    else:
        raise ValueError(f"Expected 6 or 7, got {majorversion}")

    for d in possible_paths:
        _debug(">> looking at ", d)
        path = d.expanduser().resolve()
        if not path.is_dir() or not path.exists():
            _debug(">>> path does not exist...")
            continue
        plugins = list(path.glob("*" + ext))
        if not plugins:
            _debug(f">>> path {d} exists, but has no plugins, skipping")
        elif any(plugin for plugin in plugins if dll == plugin.name):
            _debug(">>> Found!")
            return path
        else:
            _debug(f">>> Path exists, but it does not seem to be the systems plugin path\n"
                   f">>> ({dll} was not found there)")
            _debug(">>> Plugins found here: ", ', '.join(plugin.name for plugin in plugins))
    return None


def _load_installation_manifest(path: Path) -> dict:
    """
    Load an installation manifest

    An installation manifest is a json file produced during installation,
    with metadata about what was installed (plugin, name, assets, etc).

    Raises json.JSONDecodeError if the manifest's json could not be parsed
    """
    assert path.suffix == '.json'
    try:
        d = json.load(open(path))
        return d
    except json.JSONDecodeError as e:
        _errormsg(f"Could not parse manifest json: {path}")
        raise e


def _is_url(s: str) -> bool:
    """
    Is `s` a valid url?

    Args:
        s: URL address string to validate
    """
    result = urllib.parse.urlparse(str(s))
    return bool(result.scheme and result.netloc)


def _parse_pluginkey(pluginkey: str) -> tuple[str, str]:
    """
    Given a key pluginname@version, return (pluginname, version)

    Handle cases where the pluginkey has no version
    """
    if "@" in pluginkey:
        name, version = pluginkey.split("@")
    else:
        name = pluginkey
        version = "0.0.0"
    return name, version


def _normalize_version(version: str, default="0.0.0") -> str:
    try:
        versiontup = _version_tuple(version)
    except ValueError as e:
        _errormsg(f"Error while parsing version {version}: %s (Exception: {e})")
        return default
    return ".".join(str(i) for i in versiontup)


def _expand_substitutions(s: str, substitutions: dict[str, str]) -> str:
    """
    Expands variables of the form $var or ${var}
    """
    from string import Template
    t = Template(s)
    return t.substitute(substitutions)


def _parse_binarydef(binarydef: dict, substitutions: dict[str, str]) -> Binary:
    """
    Parses a binary definition within a risset.json dict

    A binary definition has the form

    {   "platform": str,
        "url": str,
        "build_platform": str,
        "extractpath": str (optional)
    }

    * platform: one of 'linux', 'windows', 'macos', optionally followed by the architecture,
        separated by a '-' sign. Possible architectures: 'x86_64', 'arm64'. In all linux, windows and macos
        the default architecture is 'x86_64'.
    * url: the url where to download the binary. It can be an url to the binary itself, to a .zip file,
        or to a git repository
    * build_platform: optional information about the platform where the given binary was built. This serves as
        reference for a user. For example, in linux a build platform might be "Ubuntu 20.04". This normally marks
        the lower bound for compatibility.
    * extractpath: if the case where the url does not point to a binary, extractpath should be used
        to indicate the location of the binary within the .zip file or within the git repository
    """
    assert isinstance(binarydef, dict), f"dict: {binarydef}"
    platform = binarydef.get('platform')
    if not platform:
        raise ParseError(f"Plugin binary should have a platform key. Binary definition: {binarydef}")

    normalized_platform = _normalize_platform(platform)
    if not normalized_platform:
        raise ParseError(f"Platform '{platform}' not supported. "
                         f"Possible platforms are {_supported_platforms}. ")

    url = binarydef.get('url')
    if not url:
        raise ParseError(f"Plugin definition for {platform} should have an url")

    csound_version = binarydef.get('csound_version')
    if not csound_version:
        _errormsg(f'No csound version found for binary {binarydef}')
        csound_version = '>=6.18<7.0'

    url = _expand_substitutions(url, substitutions)
    build_platform = binarydef.get('build_platform', 'unknown')
    return Binary(platform=platform, url=url, build_platform=build_platform,
                  extractpath=binarydef.get('extractpath', ''),
                  post_install_script=binarydef.get('post_install', ''),
                  csound_version=csound_version)


def _parse_asset(assetdef: dict, defaultsource: str) -> Asset:
    source = assetdef.get('url', defaultsource)
    extractpath = assetdef.get('extractpath') or assetdef.get('path')
    if not source and not extractpath:
        raise ParseError("Asset definition should have an URL or an extractpath key")
    paths = extractpath.split(";") if extractpath else []
    return Asset(source=source, patterns=paths, platform=assetdef.get('platform', 'all'), name=assetdef.get('name', ''))


def _enforce_key(d: dict, key: str):
    value = d.get(key)
    if value is None:
        raise SchemaError(f"Plugin has no {key} key")
    return value


def _plugin_from_dict(d: dict, pluginurl: str, subpath: str) -> Plugin:
    """
    Args:
        d: the loaded json
        pluginurl: the url of this plugin
        subpath: the path of the manifest's folder, relative to the root of the repository
    """
    clonepath = _git_local_path(pluginurl)
    version = _normalize_version(_enforce_key(d, 'version'))
    pluginname = _enforce_key(d, 'name')
    opcodes = _enforce_key(d, 'opcodes')
    opcodes.sort()
    substitutions = {key: str(value) for key, value in d.items() if isinstance(value, (int, float, str))}

    binaries: list[Binary] = []
    binarydefs = _enforce_key(d, 'binaries')
    if not isinstance(binarydefs, list):
        import pprint
        s = pprint.pformat(binarydefs)
        _errormsg("Expected a list of binary definitions, got: ")
        _errormsg(s)
        raise SchemaError(f"Parsing 'binaries', expected a list of binary definitions, got a {type(binarydefs)}")
    for binarydef in binarydefs:
        if not isinstance(binarydef, dict):

            _errormsg(f"{pluginname}: Parsing 'binaries' key, expected a dict, got")
            raise SchemaError(f"Parsing 'binaries', Expected a dict, got {binarydef}")
        try:
            _debug(f"Parsing binary definition for {pluginname}: {binarydef}")
            binary = _parse_binarydef(binarydef, substitutions=substitutions)
            binaries.append(binary)
        except ParseError as e:
            _errormsg(f"Failed to parse binary definition for plugin {d.get('name', '??')}")
            _errormsg(f"... source data: {binarydef}")
            _errormsg(str(e))

    if not binaries:
        raise SchemaError("No valid binaries defined")

    manifest_local_folder = clonepath / subpath
    if not manifest_local_folder.exists():
        _errormsg(f"The local manifest folder corresponding to plugin {pluginname} was not found "
                  f"({manifest_local_folder})")

    assets: list[Asset] = []
    assetdefs = d.get('assets')
    if assetdefs:
        if not isinstance(assetdefs, list):
            raise SchemaError(f"assets should hold a list of asset definitions, got {assetdefs}")
        for assetdef in assetdefs:
            try:
                assets.append(_parse_asset(assetdef, defaultsource=manifest_local_folder.as_posix()))
            except ParseError as e:
                _errormsg(str(e))

    return Plugin(
        name=_enforce_key(d, 'name'),
        version=version,
        short_description=_enforce_key(d, 'short_description'),
        author=_enforce_key(d, 'author'),
        email=_enforce_key(d, 'email'),
        opcodes=opcodes,
        binaries=binaries,
        doc_folder=d.get('doc', ''),
        long_description=d.get('long_description', ''),
        url=pluginurl,
        manifest_relative_path=subpath,
        assets=assets,
        cloned_path=_git_local_path(pluginurl)
    )


def _resolve_path(path: str | Path,
                  basedir: str | Path | None = None
                  ) -> Path:
    """
    Convert path to absolute, use `basedir` or the cwd as base
    """
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    if basedir is None:
        return (Path.cwd()/p).resolve()
    return (Path(basedir) / p).resolve()


def _rm_dir(path: Path) -> None:

    if not path.exists():
        return

    # On windows rmtree might fail when a file is marked as read-only
    # This is the case inside a git repo.
    # Solution taken from: https://bugs.python.org/issue43657
    def remove_readonly(func, path, exc_info):
        """Clear the readonly bit and reattempt the removal"""
        # ERROR_ACCESS_DENIED = 5
        if func not in (os.unlink, os.rmdir) or exc_info[1].winerror != 5:
            raise exc_info[1]
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(path.as_posix(), onerror=remove_readonly)


def _copy_recursive(src: Path, dest: Path) -> None:
    if not dest.exists():
        raise OSError(f"Destination path ({dest.as_posix()}) does not exist")
    if not dest.is_dir():
        raise OSError(f"Destination path ({dest.as_posix()}) should be a directory")

    if src.is_dir():
        _debug(f"Copying all files under {str(src)} to {str(dest)}")
        for f in src.glob("*"):
            _debug("    ", str(f))
            if f.is_dir():
                shutil.copytree(f.absolute().as_posix(), dest.as_posix())
            else:
                shutil.copy(f.as_posix(), dest.as_posix())
    else:
        _debug(f"Copying file {str(src)} to {str(dest)}")
        shutil.copy(src.as_posix(), dest.as_posix())


def _read_plugindef(filepath: str | Path,
                    url: str = '',
                    manifest_relative_path: str = ''
                    ) -> Plugin:
    """
    Create a Plugin from a plugin definition file (risset.json)

    Args:
        filepath: an absolute path to the plugin definition
        manifest_relative_path: relative path to manifest

    Returns:
        a Plugin

    Raises SchemaError if the definition is invalid (it does not define
    all needed keys) or json.JSONDecodeError if the json itself is not correctly formatted
    """
    # absolute path
    path = Path(filepath).resolve()

    if not path.exists():
        raise SchemaError(f"plugin definition file ({path}) not found")

    assert path.suffix == ".json", "Plugin definition file should be a .json file"

    _debug("Parsing manifest:", path)

    try:
        d = json.load(open(path))
    except json.decoder.JSONDecodeError as e:
        _errormsg(f"Could not parse json file {path}:\n    {e}")
        raise e

    _debug("... manifest json ok")

    try:
        plugin = _plugin_from_dict(d, pluginurl=url, subpath=manifest_relative_path)
    except SchemaError as e:
        _errormsg(f"Error while processing {filepath}")
        raise e
    except Exception as e:
        _errormsg(f"Unknown error while processing {filepath}")
        raise e

    return plugin


def _normalize_path(path: str) -> str:
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    return path


def _make_install_manifest(plugin: Plugin, assetfiles: list[str] | None = None
                           ) -> dict:
    """
    Create an installation manifest dict

    Args:
        plugin: the Plugin corresponding to this installation manifest
        assetfiles: if given, a list of asset filenames installed by this plugin
            (only the filenames, no path: all assets are placed in a flat folder
            under the plugins prefix)
    """
    platform_id = _session.platformid
    binary = plugin.find_binary(platformid=platform_id)
    if not binary:
        raise RuntimeError(f"No binary found for plugin {plugin.name} (platform: {platform_id}")

    out: dict[str, Any] = {}
    out['name'] = plugin.name
    out['author'] = plugin.author
    out['email'] = plugin.email
    out['version'] = plugin.version
    out['opcodes'] = plugin.opcodes
    out['long_description'] = plugin.long_description
    out['short_description'] = plugin.short_description
    out['build_platform'] = binary.build_platform
    out['binary'] = binary.binary_filename()
    out['platform'] = platform_id
    out['assetfiles'] = assetfiles or []
    return out


def _print_with_line_numbers(s: str) -> None:
    for i, line in enumerate(s.splitlines()):
        print(f"{i+1:003d} {line}")


def _filename_from_content_disposition(cd: str) -> str:
    """
    Get filename from content-disposition

    Via: https://www.codementor.io/@aviaryan/downloading-files-from-urls-in-python-77q3bs0un

    Args:
        cd: content disposition

    Returns:
        the filename or an empty string
    """
    if not cd:
        return ''
    fname = re.findall('filename=(.+)', cd)
    if len(fname) == 0:
        return ''
    return fname[0]


def _download_file(url: str, destination_folder='', cache=True) -> Path:
    """
    Download the given url. Raises RuntimeError if failed

    Args:
        url: the url to download from
        destination_folder: if given, the folder to place the downloaded file. Defaults to
            the temporary folder. If given, cache is disabled.
        cache: if False, bypass the cache.
    """
    baseoutfile = os.path.split(url)[1]
    cachedpath = _session.downloaded_files.get(url)
    if cachedpath is not None and cache:
        _debug("Found file in the cache, no need to download")
        if destination_folder:
            destpath = Path(destination_folder) / baseoutfile
            _debug(f"Copying cached downloaded file '{cachedpath}' to '{destpath}'")
            shutil.copy(cachedpath, destpath)
            return destpath
        else:
            return cachedpath
    _debug("Downloading url", url)
    import requests
    try:
        resp = requests.get(url, verify=True, allow_redirects=True)
        contentdisp = resp.headers.get('content-disposition')
        if contentdisp is not None:
            contentdisp_filename = _filename_from_content_disposition(contentdisp)
            if contentdisp_filename:
                baseoutfile = contentdisp_filename

    except requests.ConnectionError as err:
        _errormsg(f"Connection error while trying to download url: '{url}'")
        raise err
    except Exception as err:
        _errormsg(f"Unknown exception while trying to download url: '{url}'")
        raise err

    if not destination_folder:
        destination_folder = tempfile.gettempdir()
    destpath = Path(destination_folder) / baseoutfile
    _debug(f"Writing downloaded content from url '{url}' to file '{destpath}'")
    open(destpath, 'wb').write(resp.content)
    _session.downloaded_files[url] = destpath
    return destpath


def _check_mimetype(path: Path) -> str:
    """
    Checks the mimetype of the given path, returns an error message
    """
    import filetype
    out = filetype.guess(path.as_posix())
    if out is None:
        return "Unknown mimetype"
    ext = path.suffix
    mimes = {
        '.zip': 'application/zip',
        '.so': 'application/x-executable',
        '.dylib': 'application/x-executable',
        '.dll': 'application/x-executable',
    }
    if ext not in mimes:
        return f"Unknown suffix: {ext}"
    if out.mime != mimes[ext]:
        return f"Expected {mimes[ext]}, got {out.mime}"
    return ''


def default_system_plugins_path(major: int | None = None, minor=0) -> list[Path]:
    if major is None:
        major = _session.csound_version_tuple[0]
    platform = _session.platform

    if platform == 'linux':
        possible_dirs = [f"/usr/local/lib/csound/plugins64-{major}.{minor}",
                         f"/usr/lib/csound/plugins64-{major}.{minor}",
                         f"/usr/lib/x86_64-linux-gnu/csound/plugins64-{major}.{minor}",
        ]
        if _session.architecture == 'arm64':
            # This is where debian in raspberry pi installs csound's plugins
            # https://packages.debian.org/bullseye/armhf/libcsound64-6.0/filelist
            possible_dirs.append(f"/usr/lib/arm-linux-gnueabihf/csound/plugins64-{major}.{minor}/")
    elif platform == 'macos':
        # The path based on ~ is used when csound is compiled from source.
        # We give that priority since if a user is doing that, it is probably someone who knows
        # what she is doing
        MAC_CSOUNDLIB = 'CsoundLib64'
        API_VERSION = f'{major}.{minor}'
        HOME = os.getenv("HOME")
        possible_dirs = [
            f"/usr/local/opt/csound/Frameworks/{MAC_CSOUNDLIB}.framework/Versions/{API_VERSION}/Resources/Opcodes64",
            f"{HOME}/Library/Frameworks/{MAC_CSOUNDLIB}.framework/Versions/{API_VERSION}/Resources/Opcodes64",
            f"/Library/Frameworks/{MAC_CSOUNDLIB}.framework/Versions/{API_VERSION}/Resources/Opcodes64",
            f"/usr/local/lib/csound/plugins64-{API_VERSION}",
            f"/usr/lib/csound/plugins64-{API_VERSION}"
        ]
    elif platform == "windows":
        possible_dirs = [f"C:\\Program Files\\Csound{major}_x64\\plugins64"]
        path = os.getenv('PATH')
        if path is None:
            raise RuntimeError("Could not determine the value of the PATH env variable")
        pathfolders = path.split(os.pathsep)
        possible_dirs += pathfolders
    else:
        raise PlatformNotSupportedError(f"Platform {platform} not supported")
    return [Path(p).absolute() for p in possible_dirs]


def system_plugins_path(majorversion: int | None = None) -> Path | None:
    """
    Get the path were system plugins are installed.
    """
    if majorversion is None:
        majorversion = _session.csound_version_tuple[0]
    elif majorversion != _session.csound_version_tuple[0]:
        _debug(f"Queryng system plugin path for csound version {majorversion}, but "
               f"csound's version is {_session.csound_version}")
    if (out := _session.cache.get(f'system_plugins_path_{majorversion}', _UNSET)) is _UNSET:
        _session.cache[f'system_plugins_path_{majorversion}'] = out = _system_plugins_path(majorversion=majorversion)
    return out


def _system_plugins_path(majorversion: int) -> Path | None:
    assert majorversion in (6, 7)
    opcodedir64 = f"OPCODE{majorversion}DIR64"
    opcodedir = os.getenv(opcodedir64)
    if opcodedir:
        _debug(f"Env variable {opcodedir64}, set to {opcodedir}")
        possible_paths = [Path(p) for p in opcodedir.split(_get_path_separator())]
    else:
        possible_paths = default_system_plugins_path(major=majorversion)

    out = _find_system_plugins_path(possible_paths, majorversion=majorversion)
    if not out:
        _info(f"System plugins path not found. Searched paths: {possible_paths}")
        _debug(f"Csound version: {_session.csound_version}, version tuple: {_session.csound_version_tuple}")
        return None
    assert out.exists() and out.is_dir() and out.is_absolute()
    return out


def user_installed_dlls(majorversion: int | None = None) -> list[Path]:
    """
    Return a list of plugins installed at the user plugin path.
    """
    if majorversion is None:
        majorversion = _session.csound_version_tuple[0]
    elif majorversion != _session.csound_version_tuple[0]:
        _debug(f"Querying installed dlls for csound version {majorversion}, "
               f"csound's version is {_session.csound_version_tuple}")
    if (out := _session.cache.get(f'user_installed_dlls_{majorversion}', _UNSET)) is _UNSET:
        path = user_plugins_path(version=majorversion)
        out = list(path.glob("*" + _plugin_extension())) if path and path.exists() else []
        _session.cache[f'user_installed_dlls_{majorversion}'] = out
    return out


def system_installed_dlls(majorversion: int | None = None) -> list[Path]:
    """
    List of plugins installed at the system's path
    """
    if majorversion is None:
        majorversion = _session.csound_version_tuple[0]
    if (out := _session.cache.get(f'system_installed_dlls_{majorversion}')) is None:
        path = system_plugins_path(majorversion=majorversion)
        out = list(path.glob("*" + _plugin_extension())) if path and path.exists() else []
        _session.cache[f'system_installed_dlls_{majorversion}'] = out
    return out


class MainIndex:
    """
    This class holds risset's main index
    """
    def __init__(self,
                 datarepo: Path | None = None,
                 update=False,
                 majorversion: int | None = None):
        """
        Args:
            datarepo: the local path to clone the git main index repository to
            update: if True, update index prior to parsing
        """
        if majorversion is None:
            # major, minor = _csound_version()
            major, minor = _csoundlib_version()
            if not (major == 6 or major == 7):
                raise RuntimeError(f"Csound version {major}.{minor} not supported")
            majorversion = major

        if datarepo is None:
            datarepo = RISSET_ROOT / 'risset-data'
        else:
            assert isinstance(datarepo, Path)
        self.indexfile = datarepo / "rissetindex.json"
        if not datarepo.exists():
            updateindex = False
            _git_clone_into(INDEX_GIT_REPOSITORY, datarepo, depth=1)
        else:
            updateindex = update
        assert datarepo.exists()
        assert _is_git_repo(datarepo)
        assert self.indexfile.exists(), f"Main index file not found, searched: {self.indexfile}"

        self.datarepo: Path = datarepo

        self.majorversion: int = majorversion

        self.pluginsources: dict[str, IndexItem] = {}
        self.plugins: dict[str, Plugin] = {}
        self._cache: dict[str, Any] = {}
        self._parse_index(updateindex=updateindex, updateplugins=update, stop_on_errors=False)
        self.user_plugins_path = user_plugins_path(version=self.majorversion)
        if update:
            self.serialize()

    def _parse_index(self, updateindex=False, updateplugins=False, stop_on_errors=True) -> None:
        """
        Parse the main index and each entity defined within it

        If there are errors for a plugin definition, this plugin is skipped and an
        error message is printed, unless fail_if_error is True, in which case the
        whole operation is cancelled
        """
        self.plugins.clear()
        self.pluginsources.clear()
        self._cache.clear()
        if updateindex:
            _git_update(self.datarepo)

        indexstr = open(self.indexfile).read()
        try:
            d = json.loads(indexstr)
        except json.JSONDecodeError as err:
            _errormsg(f"Error while parsing json index file {self.indexfile}")
            _print_with_line_numbers(indexstr)
            raise RuntimeError(f"Could not parse index file: {err}")

        self.version = d.get('version', '')
        plugins: dict[str, Plugin] = d.get('plugins', {})
        updated: set[Path] = set()

        for name, plugindef in plugins.items():
            assert isinstance(name, str)
            assert isinstance(plugindef, dict)
            url = plugindef.get('url')
            if not url:
                _errormsg(f"Invalid plugin source definition for plugin {name}: {plugindef}")
                raise ValueError(f"Error while parsing the risset index. "
                                 f"Plugin {name} does not define a url")
            assert _is_git_url(url), f"url for plugin {name} is not a git repository: {url}"
            path = plugindef.get('path', '')
            pluginsource = IndexItem(name=name, url=url, path=path)
            pluginpath = _git_local_path(url)
            assert pluginpath.exists()
            if updateplugins and pluginpath not in updated:
                _git_update(pluginpath)
                updated.add(pluginpath)

            self.pluginsources[name] = pluginsource

        if self.pluginsources:
            for name, pluginsource in self.pluginsources.items():
                try:
                    _debug(f"Parsing plugin definition for {name}")
                    plugin = self._parse_plugin(name)
                    self.plugins[name.lower()] = plugin
                except Exception as e:
                    if stop_on_errors:
                        raise e
                    else:
                        _errormsg(f"Error while parsing plugin definition for '{name}': {e}")

    def update(self):
        """
        Update all sources and reread the index
        """
        self._parse_index(updateindex=True, updateplugins=True, stop_on_errors=_session.stop_on_errors)
        self.serialize()

    def build_documentation(self,
                            dest: Path | None = None,
                            buildhtml=True,
                            onlyinstalled=False
                            ) -> Path:
        """
        Build the documentation for the plugins indexed

        Arguments:
            dest: the destination folder. If not given, it is written to RISSET_ROOT/man (see below)
            buildhtml: if True, build the html manual from the given markdown docs
            onlyinstalled: if True, only the documentation for the plugins/opcodes actually installed
                is generated

        Returns:
            the path where the documentation was placed

        ===========   ===========================================
        Platform      Default docs folder
        ===========   ===========================================
        linux         ~/.local/share/risset/man
        macos         ~/Library/risset/man
        windows       C:/Users/$USERNAME/AppData/Local/risset/man
        ===========   ===========================================
        """
        return _generate_documentation(self, dest=dest, buildhtml=buildhtml, onlyinstalled=onlyinstalled)

    def _parse_plugin(self, pluginname: str) -> Plugin:
        pluginsource = self.pluginsources.get(pluginname)
        if pluginsource is None:
            raise KeyError(f"Plugin {pluginname} not known. Known plugins: {self.pluginsources.keys()}")
        manifestpath = pluginsource.manifest_path()
        assert manifestpath.exists()
        manifeststr = open(manifestpath).read()
        try:
            _ = json.loads(manifeststr)
        except json.JSONDecodeError as err:
            _errormsg(f"Error while parsing plugin manifest. name={pluginname}, manifest={manifestpath}")
            _print_with_line_numbers(manifeststr)
            raise err
        return pluginsource.read_definition()

    def installed_dlls(self) -> dict[str, tuple[Path, bool]]:
        """
        Returns a dict mapping dll name to (installed_path: str, user_installed: bool)
        """
        user_dlls = user_installed_dlls()
        system_dlls = system_installed_dlls()
        db = {}
        for dll in user_dlls:
            db[dll.name] = (dll, True)
        for dll in system_dlls:
            db[dll.name] = (dll, False)
        return db

    def installed_path_for_dll(self, binary: str) -> tuple[Path | None, bool]:
        """
        Get the installed path for a given plugin binary

        Returns (path to dll, user_installed). If not installed returns (None, False). A user installed
        dll has priority over system installed

        Args:
            binary: the name of the plugin binary, WITH extension (libfoo.so, libfoo.dll, etc)

        Returns:
            A tuple (path to the actual file or None if not found, True if this is inside the user plugins path)
        """
        dlldb = self.installed_dlls()
        if binary in dlldb:
            path, userinstalled = dlldb[binary]
            return path, userinstalled
        else:
            _debug(f"The binary {binary} could not be found in the installed dlls. Installed dlls:")
            if _session.debug:
                for dll, (path, userinstalled) in dlldb.items():
                    print(f" - {dll.ljust(28)}: {path} ", file=sys.stderr)
            return None, False

    def installed_manifests_path(self) -> Path:
        """
        Returns the path to were installation manifests are saved in this system

        Creates the path if it doesn't exist already
        """
        path = RISSET_ROOT / "installed-manifests"
        if not path.exists():
            path.mkdir(parents=True)
        return path

    def installed_manifests(self) -> list[Path]:
        """
        Return a list of all installed manifests
        """
        path = self.installed_manifests_path()
        manifests = list(path.glob("*.json"))
        return manifests

    def _is_plugin_recognized_by_csound(self, plugin: Plugin, method='api') -> bool:
        """
        Check if a given plugin is installed

        This routine queries the available opcodes in csound and checks
        that the opcodes in plugin are present

        Returns:
            True if the plugin is recognized by csound
        """
        test = plugin.opcodes[0]
        opcodes = _csound_opcodes(method=method)
        return test in opcodes

    def plugin_installed_path(self, plugin: Plugin) -> Path | None:
        """
        Returns the path to the plugin's dll

        If the plugin is not installed or the binary is not found
        returns None
        """
        binary = plugin.find_binary()
        if not binary:
            _debug(f"No binary found for plugin {plugin.name}")
            return None

        binfile = binary.binary_filename()
        dll, user_installed = self.installed_path_for_dll(binfile)
        return dll

    def is_plugin_installed(self, plugin: Plugin, check=True, method='api') -> bool:
        """
        Is the given plugin installed?

        It checks that the binary is in csound's path. If check is True, it
        checks that the opcodes defined in the plugin are actually present

        Arguments:
            plugin: the plugin to query
            check: if True, we check if the opcodes declared in the plugin definition
                are actually available
            method: one of 'csound' (check via the binary), 'api' (check via the API)

        Returns:
            True if the plugin is installed. If check, we also check that the plugin is actually
            loaded by csound
        """
        binary = plugin.find_binary()
        if not binary:
            _debug(f"No matching binary for plugin {plugin.name}")
            return False

        binfile = binary.binary_filename()
        if not binfile:
            return False
        dll, user_installed = self.installed_path_for_dll(binfile)
        if dll is None:
            return False
        return True if not check else self._is_plugin_recognized_by_csound(plugin, method=method)

    def find_manpage(self, opcode: str, markdown=True) -> Path | None:
        """
        Find the man page for the given opcode

        If markdown is True, search for the .md file, otherwise search the
        html documentation

        Args:
            opcode: the name of the opcode
            markdown: if True, return the markdown file of the opcode, otherwise
                returns the path to the .html file generated from it
        """
        if not markdown:
            docfolder = Path(RISSET_GENERATED_DOCS)
            if not docfolder.exists():
                _errormsg("Documentation needs to be generated first (see `risset makedocs`)")
                return None
            htmlpage = docfolder / "site" / "opcodes" / (opcode + ".html")
            if not htmlpage.exists():
                _errormsg(f"No html page found. Path: {htmlpage}")
                return None
            return htmlpage
        else:
            for plugin in self.plugins.values():
                if opcode in plugin.opcodes:
                    return plugin.manpage(opcode)
            _errormsg(f"Opcode {opcode} not found")
            return None

    def installed_plugin_info(self, plugin: Plugin) -> InstalledPluginInfo | None:
        """
        Returns an InstalledPluginInfo if found, None otherwise
        """
        _debug(f"Checking if plugin {plugin.name} is installed")
        binary = plugin.find_binary()
        if not binary:
            _debug(f"Plugin {plugin.name} has no binary for this platform and/or csound version"
                   f". Binaries: {plugin.binaries}")
            return None
        binfile = binary.binary_filename()
        dll, user_installed = self.installed_path_for_dll(binfile)
        if not dll:
            # plugin is not installed
            _debug(f"plugin {plugin.name} is not installed yet")
            return None

        installed_version = UNKNOWN_VERSION
        installed_manifest_path = None

        for manifest in self.installed_manifests():
            pluginkey = manifest.name.split(".")[0]
            name, version = _parse_pluginkey(pluginkey)
            if name == plugin.name:
                try:
                    result = _load_installation_manifest(manifest)
                except Exception as e:
                    _errormsg(f"Could not load installation manifest for plugin {plugin.name}, skipping. "
                              f"Original error: {e}")
                    continue
                installed_version = result['version']
                installed_manifest_path = manifest
                break

        out = InstalledPluginInfo(
            name=plugin.name,
            dllpath=dll,
            versionstr=installed_version,
            installed_in_system_folder=str(dll.parent) == str(system_plugins_path()),
            installed_manifest_path=installed_manifest_path
        )
        return out

    def get_plugin_dll(self,
                       plugin: Plugin,
                       platformid: str = '',
                       csound_version: int = 0,
                       check_mimetype=True
                       ) -> Path:
        """
        Returns the path to the binary as defined in the manifest

        If needed, downloads the file pointed by a url and extracts it if compressed,
        to a temporary location. If the plugin includes the binary within its repository
        then the local path of the cloned repository is returned

        Args:
            plugin: the plugin which defines which binary to get
            platformid: the platform for which to get the binary. If not given, use the
                current platform. This argument is provided to test the downloading and
                extracting methods locally.
            csound_version: the csound version to find a plugin dll for.

        Returns:
            the path of the binary.
        """
        assert isinstance(plugin, Plugin)
        if not platformid:
            platformid = _session.platformid
        if not csound_version:
            csound_version = _session.csound_version
        bindef = plugin.find_binary(platformid=platformid, csound_version=csound_version)
        if not bindef:
            available = ", ".join(plugin.available_binaries())
            raise PlatformNotSupportedError(
                f"No binary defined for platform {platformid} / {csound_version}."
                f" Available platforms for {plugin.name}: {available}")
        # The binary defines a url / path under the "url" key. Both can be a
        # binary (a .so, .dll, .dylib file) or a .zip file. In this latter case,
        # the key "extractpath" needs to be defined, in which case it points to
        # the relative path to the binary inside the compressed file

        # The manifest defines a path. If it is relative, it is relative to the
        # manifest itself.
        if _is_url(bindef.url):
            path = _download_file(bindef.url)
        else:
            # url points to a local file, relative to the manifest
            manifestpath = plugin.local_manifest_path()
            path = _resolve_path(bindef.url,  manifestpath.parent)
        _debug(f"get_plugin_dll: resolved path = {str(path)}")
        if not path.exists():
            raise IOError(f"Binary not found. Given path was: {str(path)}")

        if check_mimetype:
            errormsg = _check_mimetype(path)
            if errormsg:
                # Check if it is a "Not Found" message from github downloads
                with open(path, "r") as f:
                    line = f.readline()
                    if line.strip() == "Not Found":
                        raise RuntimeError(f"The downloaded file {path} is not a zip file. The url ('{bindef.url}') pointed to an invalid file")
                raise RuntimeError(f"The downloaded file {path} has an incorrect mimetype: {errormsg}")

        if path.suffix in ('.so', '.dll', '.dylib'):
            return path
        elif path.suffix == '.zip':
            if not bindef.extractpath:
                raise SchemaError(
                    f"The binary definition for {plugin.name} has a compressed url {bindef.url}"
                    f" but does not define an `extractpath` attribute to locate the "
                    f"binary within the compressed file")
            try:
                return _zip_extract_file(path, bindef.extractpath)
            except Exception as e:
                raise RuntimeError(f"Error while extracting {bindef.extractpath} from zip {str(path)}: {e}")
        else:
            raise SchemaError(f"Suffix {path.suffix} not supported in url: {bindef.url}")

    def opcodes_by_name(self) -> dict[str, Opcode]:
        """
        Returns a dict mapping opcodename to an Opcode definition
        """
        out = self._cache.get('opcodes_by_name')
        if out:
            return out
        out = {opcode.name: opcode
               for opcode in self.defined_opcodes()}
        self._cache['opcodes_by_name'] = out
        return out

    def parse_manpage(self, opcode: str) -> ManPage | None:
        """
        Parse the manual page for a given opcode

        Args:
            opcode: opcode name

        Returns:
            a ManPage, if a manpage was found for the opcode, or None
        """
        manpage = self.find_manpage(opcode, markdown=True)
        return _manpage_parse(manpage, opcode) if manpage else None

    def defined_opcodes(self) -> list[Opcode]:
        """
        Returns a list of opcodes
        """
        cached = self._cache.get('defined_opcodes')
        if cached:
            return cached
        opcodes = []
        for plugin in self.plugins.values():
            pluginstalled = self.is_plugin_installed(plugin, check=False)
            for opcodename in plugin.opcodes:
                manpage = self.parse_manpage(opcodename)
                if not manpage:
                    _errormsg(f"No manpage for opcode {opcodename}!")
                opcodes.append(Opcode(name=opcodename, plugin=plugin.name, installed=pluginstalled,
                                      abstract=manpage.abstract if manpage else '?',
                                      syntaxes=manpage.syntaxes if manpage else []))
        opcodes.sort(key=lambda opc: opc.name.lower())
        self._cache['defined_opcodes'] = opcodes
        return opcodes

    def serialize(self, outfile: str | Path = _MAININDEX_PICKLE_FILE
                  ) -> None:
        import pickle
        # Populate cache
        _ = self.opcodes_by_name()
        _ = self.installed_dlls()
        pickle.dump(self, open(outfile, 'wb'))

    def install_plugin(self, plugin: Plugin, check=False) -> ErrorMsg | None:
        """
        Install the given plugin

        Args:
            plugin: the plugin to install
            check: if True, check that the opcodes defined in plugin are present
                after installation

        Returns:
            None if ok, an ErrorMsg if failed

        Example
        =======

            >>> import risset
            >>> idx = risset.MainIndex(update=True)
            >>> pluginpoly = idx.plugins['poly']
            >>> idx.install_plugin(pluginpoly)
        """
        assert isinstance(plugin, Plugin)
        platformid = _session.platformid
        try:
            # This method will download and extract the plugin if necessary
            plugin_binary_path = self.get_plugin_dll(plugin)
        except PlatformNotSupportedError as e:
            return ErrorMsg(f"Platform '{platformid}' not supported for plugin '{plugin.name}': {e}")
        except RuntimeError as e:
            return ErrorMsg(f"Error while getting plugin dll (plugin: {plugin.name}): {e}")
        except SchemaError as e:
            return ErrorMsg(f"The plugin definition for {plugin.name} has errors: {e}")

        installpath = user_plugins_path()
        installpath.mkdir(parents=True, exist_ok=True)
        _debug("User plugins path: ", installpath.as_posix())
        _debug("Downloaded dll for plugin: ", plugin_binary_path.as_posix())
        try:
            shutil.copy(plugin_binary_path.as_posix(), installpath.as_posix())
        except IOError as e:
            _debug(f"Tried to copy {plugin_binary_path.as_posix()} to {installpath.as_posix()} but failed")
            _debug(str(e))
            return ErrorMsg("Could not copy the binary to the install path")

        installed_path = installpath / plugin_binary_path.name
        if not installed_path.exists():
            return ErrorMsg(f"Installation of plugin {plugin.name} failed, binary was not found in "
                            f"the expected path: {installed_path.as_posix()}")

        _session.cache.clear()

        # installation succeeded, check that it works
        if not self.is_plugin_installed(plugin, check=check):
            if platformid.startswith('macos'):
                # try code signing the binary
                _debug(f"The binary '{installed_path.as_posix()}' was installed but it is not recognized by csound. "
                       f"It might be a security problem. I will try to code sign it")
                macos_codesign([installed_path.as_posix()])
                if self._is_plugin_recognized_by_csound(plugin):
                    _debug("... Ok, that worked. ")
                else:
                    _errormsg(f"The plugin '{plugin.name}' was not recognized. The reason might be that the binary"
                              f" needs to be code-signed. ")

            if not check:
                return ErrorMsg(f"Tried to install plugin {plugin.name}, but the binary"
                                f" is not present.")
            else:
                return ErrorMsg(f"Tried to install plugin {plugin.name}, but opcode "
                                f"{plugin.opcodes[0]}, which is provided by this plugin, "
                                f"is not present")

        # Install assets, if any
        assetfiles = []
        if plugin.assets:
            for asset in plugin.assets:
                if asset.platform == 'all' or asset.platform == platformid:
                    _debug(f"Installing asset {asset.identifier()}")
                    assetfiles.extend(self.install_asset(asset, plugin.name))

        # install manifest
        manifest_path = self.installed_manifests_path() / f"{plugin.name}.json"
        manifest = _make_install_manifest(plugin, assetfiles=assetfiles)
        try:
            manifest_json = json.dumps(manifest, indent=True)
        except Exception as e:
            _errormsg(f"install_plugin: json error while saving manifest: {e}")
            _errormsg(f"   manifest was: \n{manifest}")
            return ErrorMsg("Error when dumping manifest to json")

        binarydef = plugin.find_binary()
        if binarydef and binarydef.post_install_script:
            script = plugin.resolve_path(binarydef.post_install_script)
            _subproc_call(script.as_posix(), shell=True)

        with open(manifest_path.as_posix(), "w") as f:
            f.write(manifest_json)
        _debug(f"Saved manifest for plugin {plugin.name} to {manifest_path}")

        # no errors
        return None

    def list_plugins_as_dict(self, installed=False) -> dict:
        d = {}
        for plugin in self.plugins.values():
            assert isinstance(plugin, Plugin)
            info = self.installed_plugin_info(plugin)
            binary = plugin.find_binary()
            plugininstalled = info is not None
            if installed and not plugininstalled:
                continue
            plugdict: dict[str, Any] = {'version': plugin.version}
            if info:
                plugdict['installed'] = True
                plugdict['installed-version'] = info.versionstr
                plugdict['path'] = info.dllpath.as_posix()
            else:
                plugdict['installed'] = False
                plugdict['available'] = binary is not None

            plugdict['opcodes'] = plugin.opcodes
            plugdict['url'] = plugin.url
            plugdict['short_description'] = plugin.short_description
            plugdict['long_description'] = plugin.long_description
            plugdict['author'] = plugin.author
            d[plugin.name] = plugdict
        return d

    def available_plugins(self, platformid: str = '', csound_version: int = 0, installed_only=False,
                          not_installed_only=False, method='api', check=True
                          ) -> list[Plugin]:
        if not platformid:
            platformid = _session.platformid

        if not csound_version:
            csound_version = _session.csound_version

        plugins = []
        for plugin in self.plugins.values():
            if plugin.find_binary(platformid=platformid, csound_version=csound_version):
                if installed_only and not self.is_plugin_installed(plugin, check=check, method=method):
                    continue
                elif not_installed_only and self.is_plugin_installed(plugin, check=check, method=method):
                    continue
                plugins.append(plugin)
        return plugins

    def list_plugins(self, installed=False, nameonly=False, leftcolwidth=20,
                     oneline=False, upgradeable=False, header=True
                     ) -> bool:
        """
        Print a list of the installed plugins
        """
        width, height = _termsize()
        descr_max_width = width - 36

        if upgradeable:
            installed = True

        platform = _session.platformid
        csoundversion = _session.csound_version

        if header:
            print(f"Csound Version: {csoundversion}")
            print()

        for plugin in self.plugins.values():
            data = []
            info = self.installed_plugin_info(plugin)
            plugininstalled = info is not None

            if not plugininstalled and installed:
                continue

            if upgradeable and (not info or info.versiontuple == (0, 0, 0) or
                                plugin.versiontuple <= info.versiontuple):
                continue

            if nameonly:
                print(plugin.name)
                continue

            extra_lines = []
            if info:
                if info.versionstr == UNKNOWN_VERSION:
                    data.append("manual")
                else:
                    if oneline:
                        data.append(info.versionstr)
                    else:
                        data.append(f"installed: {info.versionstr}")
                if not info.installed_in_system_folder and not oneline:
                    extra_lines.append(f"Path: {info.dllpath}")
            if data:
                status = "[" + ", ".join(data) + "]"
            else:
                status = ""
            leftcol = f"{plugin.name} /{plugin.version}"
            descr = plugin.short_description
            bindef = plugin.find_binary()
            if not bindef:
                available = ', '.join(plugin.available_binaries())
                extra_lines.append(f"-- No binaries for {platform}/{csoundversion}")
                extra_lines.append(f"   Available binaries: {available}")
            if oneline and len(descr) > descr_max_width:
                descr = descr[:descr_max_width] + "…"
            symbol = "*" if plugininstalled else "-"
            print(f"{symbol} {leftcol.ljust(leftcolwidth)} | {descr} {status}")
            if extra_lines:
                for line in extra_lines:
                    print(" " * leftcolwidth + "   |   ", line)
        print()
        return True

    def show_plugin(self, pluginname: str, binary_url=False) -> bool:
        """
        Show info about a plugin

        Returns True on success
        """
        plugdef = self.plugins.get(pluginname.lower())
        if plugdef is None:
            _errormsg(f"Plugin '{pluginname}' unknown\n"
                      f"Known plugins: {', '.join(self.plugins.keys())}")
            return False
        info = self.installed_plugin_info(plugdef)
        print("\n"
              f"Plugin        : {plugdef.name}    \n"
              f"Author        : {plugdef.author} ({plugdef.email}) \n"
              f"URL           : {plugdef.url}     \n"
              f"Version       : {plugdef.version} \n"
              )
        if info:
            manifest = (info.installed_manifest_path.as_posix() if info.installed_manifest_path
                        else 'No manifest (installed manually)')
            print(f"Installed     : {info.versionstr} (path: {info.dllpath.as_posix()}) \n"
                  f"Manifest      : {manifest}")
        print(f"Abstract      : {plugdef.short_description}")
        if plugdef.long_description.strip():
            print("Description:")
            for line in textwrap.wrap(plugdef.long_description, 72):
                print(" " * 3, line)
            # print(textwrap.wrapindent("     ", plugdef.long_description))
        print("Opcodes:")
        opcstrs = textwrap.wrap(", ".join(plugdef.opcodes), 72)
        for s in opcstrs:
            print("   ", s)

        if plugdef.binaries:
            print("Binaries:")
            for binary in plugdef.binaries:
                if not binary_url:
                    print(f"    * {binary.platform}/csound{binary.csound_version}")
                else:
                    url = binary.url
                    if binary.extractpath:
                        url += "/" + binary.extractpath
                    print(f"    * {binary.platform}/csound{binary.csound_version}, {url}")

        if plugdef.assets:
            print("Assets:")
            for asset in plugdef.assets:
                print(f"    * identifier: {_abbrev(asset.identifier(), 70)}\n"
                      f"      source: {asset.source}\n"
                      f"      patterns: {', '.join(asset.patterns)}\n"
                      f"      platform: {asset.platform}")
        print()
        return True

    def uninstall_plugin(self, plugin: Plugin, removeassets=True) -> None:
        """
        Uninstall the given plugin

        This operation also removes the installation manifest, if the
        plugin was installed via risset. Plugins installed in the
        system's directory need to be removed manually.

        Raises RuntimeError if the plugin is not installed or is installed
        in the system's folder.

        Args:
            plugin: the plugin to uninstall
            removeassets: if True, removes the assets installed by this plugin
        """
        info = self.installed_plugin_info(plugin)
        if not info:
            raise RuntimeError(f"Plugin {plugin.name} is not installed")
        if not info.dllpath.exists():
            raise RuntimeError(f"Could not find binary for plugin {plugin.name}. "
                               f"Declared binary: {info.dllpath.as_posix()}")
        if info.installed_in_system_folder:
            raise RuntimeError(f"Plugin is installed in the system folder and needs to"
                               f" be removed manually. Path: {info.dllpath.as_posix()}")
        os.remove(info.dllpath.as_posix())
        assert not info.dllpath.exists(), f"Attempted to remove {info.dllpath.as_posix()}, but failed"
        manifestpath = info.installed_manifest_path
        assetsfolder = RISSET_ASSETS_PATH / plugin.name
        if manifestpath and manifestpath.exists():
            installed_manifest = _load_installation_manifest(manifestpath)
            assetfiles = installed_manifest.get('assetfiles', [])
            if removeassets and assetsfolder.exists():
                _debug(f"Removing assets for plugin {plugin.name}: {assetfiles}")
                for assetfile in assetfiles:
                    assetfullpath = assetsfolder / assetfile
                    if assetfullpath.exists():
                        os.remove(assetfullpath)
                remainingassets = list(assetsfolder.glob("*"))
                if remainingassets:
                    _info(f"There are remaining assets in the folder {assetsfolder}: "
                          f"{', '.join(p.as_posix() for p in remainingassets)}")
                    _info("... They will be removed")
                _rm_dir(assetsfolder)
            os.remove(manifestpath.as_posix())

    def install_asset(self, asset: Asset, prefix: str) -> list[str]:
        """
        Install an Asset under a given prefix

        Args:
            asset: the Asset to install
            prefix: the prefix to install it under.

        Returns:
            a list of installed file names (only the filename, not the
            absolute path, the destination path is RISSET_ASSETS_PATH / prefix)
        """
        destination_folder = RISSET_ASSETS_PATH / prefix
        sources = asset.retrieve()
        destination_folder.mkdir(parents=True, exist_ok=True)
        for source in sources:
            _debug(f"Copying asset {source} to {destination_folder}")
            if source.is_dir():
                shutil.copytree(source, destination_folder/source.name)
            else:
                shutil.copy(source, destination_folder)
        return [f.name for f in sources]

    def generate_opcodes_xml(self) -> str:
        """
        Generates xml following the scheme of the manual's opcodes.xml

        This can be used by frontends to generate help for all csound opcodes

        <?xml version="1.0" encoding="UTF-8"?>
        <opcodes>
          <category name="Orchestra Syntax:Header">
            <opcode>
              <desc>Sets the value of 0 decibels using full scale amplitude.</desc>
              <synopsis>
                <opcodename>0dbfs</opcodename> = iarg
              </synopsis>
            </opcode>
            <opcode>
              <desc>An oscillator which takes tonality and brightness as arguments.</desc>
              <synopsis>ares <opcodename>hsboscil</opcodename> kamp, ktone, kbrite, ibasfreq, iwfn, ioctfn \
               [, ioctcnt] [, iphs]
              </synopsis>
            </opcode>
            ...
          </category>
          ...
        </opcodes>
        """
        lines = []
        indentwidth = 2

        def _(s, indent=0):
            if indent > 0:
                s = (" "*(indent*indentwidth)) + s
            lines.append(s)

        _('<?xml version="1.0" encoding="UTF-8"?>')
        _('<opcodes>')
        # For now, gather all opcodes belonging to one plugin under the same category. Later we can
        # enforce that each plugin defines a category in their manpage
        opcodes = self.opcodes_by_name()
        for plugin in self.plugins.values():
            _(f'<category name="External Plugin:{plugin.name}">', 1)
            for opcodename in plugin.opcodes:
                opcode = opcodes.get(opcodename)
                if not opcode:
                    continue
                manpage = self.parse_manpage(opcodename)
                if not manpage:
                    _errormsg(f"No manpage found for opcode {opcodename}, skipping")
                    continue
                _(f'<opcode name="{opcodename}">', 2)
                _(f"<desc>{manpage.abstract}</desc>", 3)
                if not manpage.syntaxes:
                    _errormsg(f"No syntaxes found for opcode {opcodename}, skipping")
                    continue
                for syntax in manpage.syntaxes:
                    syntax = syntax.replace(opcodename, f"<opcodename>{opcodename}</opcodename>")
                    _(f"<synopsis>{syntax}</synopsis>", 3)
                _("</opcode>", 2)
            _('</category>', 1)
        _('</opcodes>')
        return "\n".join(lines)


###############################################################
#                        Documentation                        #
###############################################################


def _is_package_installed(pkg: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(pkg) is not None


def _call_mkdocs(folder: Path, *args: str) -> None:
    currentdir = os.getcwd()
    os.chdir(folder)
    _debug(f"Rendering docs via mkdocs. Current dir: {os.getcwd()}")
    _subproc_call([sys.executable, "-m", "mkdocs"] + list(args))
    os.chdir(currentdir)


def _is_mkdocs_installed() -> bool:
    return _is_package_installed("mkdocs") or shutil.which("mkdocs") is not None


def _generate_documentation(index: MainIndex,
                            dest: Path | None = None,
                            buildhtml=True,
                            onlyinstalled=False,
                            opcodesxml: Path | None = None
                            ) -> Path:
    """
    Generate documentation for the plugins

    Args:
        index: the main index
        dest: the path where to put the "docs" folder
        buildhtml: if True, call mkdocs to build html documentation
        onlyinstalled: if True, only generate docs for installed plugins
        opcodesxml: if given, generate an opcodes.xml compatible file with the opcodes syntax and
            description and saves it at the given path

    Raises RuntimeExce
    """
    if dest is None:
        dest = RISSET_GENERATED_DOCS
    _compile_docs(index=index, dest=dest / "docs", makeindex=True,
                  onlyinstalled=onlyinstalled)

    if opcodesxml:
        xmlstr = index.generate_opcodes_xml()
        open(opcodesxml, "w").write(xmlstr)

    if buildhtml:
        mkdocsconfig = RISSET_DATAREPO_LOCALPATH / "assets" / "mkdocs.yml"
        if not mkdocsconfig.exists():
            raise IOError(f"Did not find mkdocs configuration file. Searched: {mkdocsconfig}")
        if not _is_mkdocs_installed():
            raise RuntimeError("mkdocs is needed to build the html documentation. Install it via 'pip install mkdocs'")
        shutil.copy(mkdocsconfig, dest)
        _call_mkdocs(dest, "build")

    return dest


def _compile_docs(index: MainIndex, dest: Path, makeindex=True,
                  onlyinstalled=False) -> None:
    """
    Gather all manpages and generate a mkdocs compatible docs folder

    Args:
        index: the main index
        dest: destination path of the documentation
        makeindex: generate an index file
        onlyinstalled: if True, only generate documentation for installed plugins/opcodes

    """
    dest = dest.expanduser().absolute()
    if dest.exists():
        _debug(f"Removing existing doc folder: {str(dest)}")
        shutil.rmtree(dest.as_posix())
    css_folder = dest / "css"
    opcodes_folder = dest / "opcodes"
    opcodes_assets_folder = opcodes_folder / "assets"

    for folder in [dest, css_folder, opcodes_folder, opcodes_assets_folder]:
        folder.mkdir(exist_ok=True, parents=True)

    # copy .css file
    syntaxhighlightingcss = RISSET_DATAREPO_LOCALPATH / "assets" / "syntax-highlighting.css"
    assert syntaxhighlightingcss.exists()
    shutil.copy(syntaxhighlightingcss, css_folder)

    for plugin in index.plugins.values():
        if onlyinstalled and not index.is_plugin_installed(plugin, check=False):
            continue
        doc_folder = plugin.resolve_doc_folder()
        if doc_folder is None:
            _debug(f"No docs found for plugin: {plugin.name}")
            continue

        docs = doc_folder.glob("*.md")
        _debug(f"Copying docs to {opcodes_folder}")
        for doc in docs:
            _debug(" copying", str(doc))
            shutil.copy(doc.as_posix(), opcodes_folder.as_posix())

        # copy assets
        source_assets_folder = doc_folder / "assets"
        if source_assets_folder.exists() and source_assets_folder.is_dir():
            _debug(f"Copying assets for plugin {plugin.name}")
            _copy_recursive(source_assets_folder, opcodes_assets_folder)
        else:
            _debug(f"No assets to copy for plugin {plugin.name}")

    if makeindex:
        _docs_generate_index(index, dest / "index.md")


def _manpage_parse(manpage: Path, opcode: str) -> ManPage | None:
    if not manpage:
        _errormsg(f"Opcode {opcode} has no manpage")
        return None

    text = open(manpage).read()
    lines = text.splitlines()
    it = iter(lines)
    abstract = ''
    syntaxlines = []
    foundsyntaxtag = False
    for line in it:
        if re.search(r"^\s*#+\s+[s|S]yntax\s*$", line):
            foundsyntaxtag = True
            break
    if foundsyntaxtag:
        for line in it:
            if re.search(r"^\s*[#!;/]", line):
                break
            elif opcode in line and (re.search(r"^\s*[akigS\[x]", line) or line.lstrip().startswith(opcode)):
                syntax = line.strip().split(";", maxsplit=1)[0]
                syntaxlines.append(syntax)

    if "# Abstract" in text:
        # the abstract would be all the text between # Abstract and the next #tag
        it = iter(lines)
        for line in it:
            if "# Abstract" in line:
                break
        for line in it:
            line = line.strip()
            if not line:
                continue
            abstract = line if not line.startswith("#") else ""
            break
        else:
            _debug(f"No abstract in manpage file {manpage}")
    else:
        # no Abstract tag, so abstract is the text between the title and the text tag
        _debug(f"get_abstract: manpage for opcode {opcode} has no # Abstract tag")
        it = iter(lines)
        for line in it:
            line = line.strip()
            if line:
                if line.startswith("#") and line.split("")[-1] == opcode:
                    break
                else:
                    raise ParseError(f"Expected title, got {line}")
        for line in it:
            line = line.strip()
            if line:
                abstract = line if not line.startswith("#") else ""
                break

    return ManPage(syntaxes=syntaxlines, abstract=abstract)


def _docs_generate_index(index: MainIndex, outfile: Path) -> None:
    """
    Generate an index for the documentation

    Arguments:
        index: the main index
        outfile: the path to write the index to (normally an index.md file)
    """
    lines: list[str] = []
    _ = lines.append
    _("# Plugins\n")
    plugins = sorted(index.plugins.values(), key=lambda plugin: plugin.name)
    for plugin in plugins:
        _(f"## {plugin.name}\n")
        _(plugin.short_description + '\n')
        opcodes = sorted(plugin.opcodes)
        for opcode in opcodes:
            manpage = plugin.manpage(opcode)
            if not manpage:
                _debug(f"opcode {opcode} has no manpage")
                continue
            parsedmanpage = _manpage_parse(manpage, opcode)
            if not parsedmanpage or not parsedmanpage.abstract:
                _errormsg(f"Could not get abstract for opcode {opcode}")
                continue
            _(f"  * [{opcode}](opcodes/{opcode}.md): {parsedmanpage.abstract}")

        _("")
    with open(outfile, "w") as f:
        f.write("\n".join(lines))


###############################################################
#                        Subcommands                          #
###############################################################


def cmd_list(mainindex: MainIndex, args) -> str:
    """
    Lists all plugins available for download
    """
    if args.json:
        d = mainindex.list_plugins_as_dict(installed=args.installed)
        if args.outfile:
            with open(args.outfile, "w") as f:
                json.dump(d, f, indent=2)
        else:
            print(json.dumps(d, indent=2))
        return ''
    else:
        header = True
        if args.oneline or args.nameonly or args.noheader:
            header = False
        ok = mainindex.list_plugins(installed=args.installed, nameonly=args.nameonly, oneline=args.oneline,
                                    upgradeable=args.upgradeable, header=header)
        return '' if ok else 'Error while listing plugins'


def cmd_show(index: MainIndex, args) -> str:
    """
    Returns True on success
    """
    ok = index.show_plugin(args.plugin, binary_url=args.full)
    return '' if ok else "Errors while showing plugins"


def cmd_rm(index: MainIndex, args) -> str:
    """
    Remove a plugin
    """
    errors = 0
    for pluginname in args.plugin:
        plugdef = index.plugins.get(pluginname)
        if not plugdef:
            _errormsg(f"Plugin {pluginname} not defined. Known plugins: {', '.join(index.plugins.keys())}")
            errors += 1
            continue
        try:
            index.uninstall_plugin(plugdef)
        except Exception as e:
            _errormsg(str(e))
            errors += 1
    return '' if not errors else 'Errors while removing plugins'


def cmd_install(index: MainIndex, args) -> str:
    """
    Install or upgrade a plugin

    If the plugin is installed but with a prior version, it will
    be upgraded. If it is installed but with an unknown version,
    installation is only performed if the --force flag is given

    Returns True if success

    Flags:
        --force  - force installation even if plugin is already installed

    Args:
        plugin   - name of the plugin to install
    """
    allplugins: list[Plugin] = []
    for pattern in args.plugins:
        matched = [plugin for name, plugin in index.plugins.items()
                   if fnmatch.fnmatch(name, pattern)]
        if matched:
            allplugins.extend(matched)
    if not allplugins:
        return "No plugins matched"

    allplugins = list(set(allplugins))  # remove duplicates
    errors = []
    for plugin in allplugins:
        plugininfo = index.installed_plugin_info(plugin)
        if not plugininfo:
            # Not installed
            _debug(f"Plugin {plugin.name} not installed, installing")
        elif not plugininfo.versionstr or plugininfo.versionstr == UNKNOWN_VERSION:
            # plugin is installed but without a corresponding install manifest.
            if not args.force:
                errors.append(f"Plugin {plugin.name} is already installed. Use --force to force reinstall")
        else:
            if plugin.versiontuple <= plugininfo.versiontuple:
                _debug(f"Plugin {plugin.name}, version: {plugin.version}")
                _debug(f"    Installed version: {plugininfo.versionstr}")
                _info(f"Installed version of plugin {plugin.name} is up-to-date")
                continue
            _info(f"Updating plugin {plugin.name}: "
                  f"{plugininfo.versionstr} -> {plugin.version}")
        error = index.install_plugin(plugin)
        if error:
            _debug(f"Errors while installing {plugin.name}")
            errors.append(error)
    return '' if not errors else '; '.join(errors)


def _open_in_default_application(path: str):
    """
    Open path with the app defined to handle it by the user
    at the os level (xdg-open in linux, start in win, open in osx)
    """
    platform = sys.platform
    if platform == 'linux':
        subprocess.call(["xdg-open", path])
    elif platform == "win32":
        os.startfile(path)  # type: ignore
    elif platform == "darwin":
        subprocess.call(["open", path])
    else:
        raise RuntimeError(f"platform {platform} not supported")


def cmd_man(idx: MainIndex, args) -> str:
    """
    Show man page for an installed opcode

    Returns True if success

    Flags:
        --html      - Use .html file instead of .md version
        --path      - Do not open manpage, only print the path
        --external  - Open file in external app. This is only used when opening the markdown page. Without this
                      the markdown is output to the terminal
        opcode      - opcode(s) to get manpage of. Can be a wildcard
    """
    opcodes: list[Opcode] = []
    if args.html and not args.markdown:
        fmt = "html"
    else:
        fmt = "markdown"
    for pattern in args.opcode:
        opcodes.extend(opcode for opcode in idx.defined_opcodes()
                       if fnmatch.fnmatch(opcode.name, pattern))
    if not opcodes:
        # open the index
        htmlidx = RISSET_GENERATED_DOCS / "site" / "index.html"
        if not htmlidx.exists():
            return f"Index file for the documentation not found (path: {htmlidx.as_posix()}"
        _open_in_default_application(htmlidx.as_posix())
    else:
        for opcode in opcodes:
            _debug("man: processing opcode ", opcode.name)
            path = idx.find_manpage(opcode=opcode.name, markdown=fmt == "markdown")
            if not path:
                _errormsg(f"No manpage for opcode {opcode.name}")
                continue
            if args.path:
                # just print the path
                print(f"{opcode.name}:{str(path)}")
            elif args.simplepath:
                print(str(path))
            elif fmt == "markdown":
                if args.external:
                    _open_in_default_application(path.as_posix())
                else:
                    _show_markdown_file(path, style=args.theme)
            else:
                # open it in the default application
                _open_in_default_application(str(path))
    return ''


def cmd_resetcache(args) -> str:
    _rm_dir(RISSET_DATAREPO_LOCALPATH)
    _rm_dir(RISSET_CLONES_PATH)
    if os.path.exists(_MAININDEX_PICKLE_FILE):
        os.remove(_MAININDEX_PICKLE_FILE)
    return ''

def update_self():
    """Upgrade risset itself"""
    _info("Updating risset")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "risset", "--upgrade"])


def cmd_list_installed_opcodes(plugins_index: MainIndex, args) -> str:
    """
    Print a list of installed opcodes

    """
    if args.long:
        for opcode in plugins_index.defined_opcodes():
            print(f"{opcode.name.ljust(20)}{opcode.plugin.ljust(12)}{_abbrev(opcode.abstract, 60)}")
    else:
        for opcode in plugins_index.defined_opcodes():
            print(opcode.name)
    return ''


def cmd_dev(idx: MainIndex, args) -> str:
    if args.cmd == 'opcodesxml':
        outstr = idx.generate_opcodes_xml()
        outfile = args.outfile or RISSET_OPCODESXML
        if outfile == 'stdout':
            print(outstr)
        else:
            open(outfile, "w").write(outstr)
            _debug(f"Generated opcodes.xml at '{outfile}'")
    elif args.cmd == 'codesign':
        if _session.platform != 'macos':
            return f"Code signing is only available for macos, not for '{_session.platform}'"

        plugins = idx.available_plugins(installed_only=True, check=False)
        dylibs = []
        for plugin in plugins:
            info = idx.installed_plugin_info(plugin)
            assert info is not None
            dylibs.append(info.dllpath.as_posix())

        if not dylibs:
            _debug(f"Did not find any binary to sign. Plugins: {plugins}")
        else:
            _debug(f"Code signing the following plugin binaries: {dylibs}")
            macos_codesign(dylibs)

    return ''


def cmd_makedocs(idx: MainIndex, args) -> str:
    """
    Generate the documentation for all opcodes

    Options:
        --onlyinstalled: if True, only generate documentation for installed opcodes
        --outfolder: if given the documentation is placed in this folder. Otherwise, it is
            placed in RISSET_GENERATED_DOCS
    """
    outfolder = args.outfolder or RISSET_GENERATED_DOCS

    try:
        _generate_documentation(idx, dest=Path(outfolder), buildhtml=True, onlyinstalled=args.onlyinstalled,
                                opcodesxml=RISSET_OPCODESXML)
    except Exception as e:
        return str(e)

    _info(f"Documentation generated in {outfolder}")
    _info(f"Saved opcodes.xml to {RISSET_OPCODESXML}")
    return ''


def cmd_info(idx: MainIndex, args) -> str:
    picklefile = _MAININDEX_PICKLE_FILE
    if not picklefile.exists():
        lastupdate = 99999999
    else:
        import time
        lastupdate = int((time.time() - picklefile.stat().st_mtime) / 686400)



    d = {
        'version': importlib.metadata.version("risset"),
        'index-version': idx.version,
        'pluginspath': idx.user_plugins_path.as_posix(),
        'rissetroot': RISSET_ROOT.as_posix(),
        'clonespath': RISSET_CLONES_PATH.as_posix(),
        'assetspath': RISSET_ASSETS_PATH.as_posix(),
        'htmldocs': (RISSET_GENERATED_DOCS/"site").as_posix(),
        'manpages': (RISSET_GENERATED_DOCS/"docs/opcodes").as_posix(),
        'datarepo': RISSET_DATAREPO_LOCALPATH.as_posix(),
        'opcodesxml': (RISSET_ROOT / "opcodes.xml").as_posix(),
        'days-since-update': lastupdate,
        'installed-plugins': [plugin.name for plugin in idx.plugins.values()
                              if idx.is_plugin_installed(plugin, check=False)]
    }
    if args.full:
        d['plugins'] = idx.list_plugins_as_dict()
    jsonstr = json.dumps(d, indent=True)
    if args.outfile:
        open(args.outfile, "w").write(jsonstr)
    else:
        print(jsonstr)
    return ''


def cmd_upgrade(idx: MainIndex, args) -> str:
    """ Upgrades all installed packages if they can be upgraded """
    for plugin in idx.plugins.values():
        if not idx.is_plugin_installed(plugin):
            continue
        info = idx.installed_plugin_info(plugin)
        if not info or info.versiontuple == (0, 0, 0):
            _debug(f"Upgrade: plugin {plugin.name} installed manually, will not upgrade")
        elif plugin.versiontuple <= info.versiontuple:
            _debug(f"Upgrade: plugin {plugin.name} already up to date"
                   f" (installed version: {info.versiontuple}, latest version: {plugin.versiontuple}")
        else:
            _debug(f"Upgrading plugin {plugin.name} from {info.versiontuple} to {plugin.versiontuple}")
            err = idx.install_plugin(plugin)
            if err:
                _errormsg(f"Error while installing {plugin.name}")
                _errormsg("    " + str(err))
    return ''


def cmd_download(idx: MainIndex, args) -> str:
    """Downloads a binary for a given plugin"""
    outfolder = args.path
    if not outfolder:
        outfolder = Path.cwd().as_posix()

    if not os.path.exists(outfolder):
        return f"download: Output folder '{outfolder}' does not exist"

    platformid = args.platform
    if not platformid:
        platformid = _session.platformid

    plugin = idx.plugins.get(args.plugin)
    if plugin is None:
        pluginnames = ', '.join(idx.plugins.keys())
        return f"download: Unknown plugin '{args.plugin}'. Available plugins: {pluginnames}"


    dllpath = idx.get_plugin_dll(plugin=plugin, platformid=platformid)
    if not dllpath.exists():
        return (f"Error while downloading binary for plugin '{plugin.name}'. "
                f"Expected to find the binary at '{dllpath}', but the path does not exist")

    outfile = Path(outfolder) / dllpath.name
    if outfile.exists():
        return f"download: the destination path '{outfile}' already exists."

    shutil.move(dllpath, outfolder)
    _info(f"Downloaded binary for plugin '{plugin.name}' to '{outfile}'")
    return ''


def validate_definition(infile: str) -> str:
    """
    Validate a risset.json definition

    Args:
        infile: the file to validate

    Returns:
        an empty str if ok, a list of errors (separated by ';') otherwise
    """
    if not os.path.exists(infile):
        return f"validate: file {infile} not found"
    try:
        jsonstr = open(infile).read()
        root = json.loads(jsonstr)
    except json.JSONDecodeError as e:
        return f"validate: Error decoding json file '{infile}': {e}"

    def check(d: dict, key: str, valuetype: type | tuple[type] = str, options=None, validator: Callable[[Any], str | None] = None) -> str:
        if key not in d:
            return f"Key '{key}' not found"
        value = d[key]
        if not isinstance(value, valuetype):
            return f"Expected a value of type {valuetype}, got {value}"
        if options and value not in options:
            return f"Expected one of {options}, got {value}"
        if validator:
            errormsg = validator(value)
            if errormsg:
                return errormsg
        return ''

    def validate_version(s):
        parts = s.split(".")
        if not 1 <= len(parts) <= 3:
            return f"Invalid version: {s}"
        if not all(part.isdecimal() for part in parts):
            return f"Version parts must be integers, got {s}"

    def validate_platform(s):
        if _normalize_platform(s) not in _supported_platforms:
            return f"Invalid platform '{s}', expected one of {_supported_platforms}"

    def validate_bins(binaries):
        for binary in binaries:
            if not isinstance(binary, dict):
                return f"Invalid binary definition, expected a dict, got a {binary}"
            if errormsg := check(binary, "platform", validator=validate_platform):
                return f"Invalid binary definition: {errormsg}"
            if errormsg := check(binary, 'url'):
                return f"Invalid binary definition: {errormsg}"
            else:
                url = binary['url']
                assert isinstance(url, str)
                if url.endswith('.zip'):
                    if errormsg := check(binary, 'extractpath'):
                        return f"The binary url is a zip file, an `extractpath` key is needed ({url=})"
            if errormsg := check(binary, "csound_version"):
                return f"Invalid binary definition: {errormsg}"
            else:
                versionrangestr = binary['csound_version']
                try:
                    versionrange = _parse_version(versionrangestr)
                    if versionrange.contains(5):
                        return f"Invalid version range: {versionrangestr}"
                except ParseError as e:
                    return f"Invalid version in 'csound_version': {versionrangestr}, error: {e}"


    errors = []
    errors.append(check(root, "name", valuetype=str))
    errors.append(check(root, "version", valuetype=str, validator=validate_version))
    errors.append(check(root, "opcodes", valuetype=list, validator=lambda opcodes: '' if isinstance(opcodes, list) and all(isinstance(opc, str) for opc in opcodes) else 'Invalid opcode list'))  # noqa: E741
    errors.append(check(root, "short_description"))
    for key in ('short_description', 'author', 'email', 'license', 'repository'):
        errors.append(check(root, key))
    errors.append(check(root, "binaries", valuetype=list, validator=validate_bins))
    allerrors = [f"Error in {infile}: {error}" for error in errors if error]
    return '; '.join(allerrors) if allerrors else ''


def cmd_validate(idx: MainIndex, args) -> str:
    """Validate a definition file"""
    return validate_definition(args.infile)


def _running_from_terminal() -> bool:
    return sys.stdin.isatty()


def _print_file(path: Path) -> None:
    text = open(str(path)).read()
    print(text)


def _show_markdown_file(path: Path, style='dark') -> None:
    if not _running_from_terminal():
        _open_in_default_application(str(path))
        return

    from pygments import highlight
    from pygments.formatters import TerminalTrueColorFormatter
    from pygments.lexers import MarkdownLexer
    from pygments.styles import STYLE_MAP
    # from pygments.formatters import TerminalFormatter
    code = open(path).read()
    if style == 'dark':
        style = 'fruity'
    elif style == 'light':
        style = 'friendly'
    else:
        if style not in STYLE_MAP:
            style = 'default'

    print(highlight(code, MarkdownLexer(), TerminalTrueColorFormatter(style=style)))
    # print(highlight(code, MarkdownLexer(), TerminalFormatter()))


def main():
    # Preliminary checks
    if sys.platform not in ("linux", "darwin", "win32"):
        _errormsg(f"Platform not supported: {sys.platform}")
        sys.exit(-1)

    if _get_git_binary() is None:
        _errormsg("git command not found. Check that git is installed and in the PATH")
        sys.exit(-1)

    def flag(parser, flag, help=""):
        parser.add_argument(flag, action="store_true", help=help)

    # Main parser
    parser = argparse.ArgumentParser()
    flag(parser, "--debug", help="Print debug information")
    flag(parser, "--update", help="Update the plugins data before any action")
    flag(parser, "--stoponerror", help="Stop parsing if an error is detected")
    flag(parser, "--version", help="Print version and exit")
    parser.add_argument("-c", "--csound", default=0, type=int,
                        help="Which csound version to use (one of 0, 6, 7). "
                             "Use 0 to detect the installed version")

    subparsers = parser.add_subparsers(dest='command')

    # List command
    list_cmd = subparsers.add_parser('list', help="List packages")

    flag(list_cmd, "--json", help="Outputs list as json")
    flag(list_cmd, "--nameonly", help="Output just the name of each plugin")
    flag(list_cmd, "--installed", help="List only installed plugins")
    flag(list_cmd, "--upgradeable", help="List only installed packages which can be upgraded")
    flag(list_cmd, "--notinstalled", help="List only plugins which are not installed")
    flag(list_cmd, "--noheader", help="Do not print any extra information")
    list_cmd.add_argument("-o", "--outfile", help="Outputs to a file")
    list_cmd.add_argument("-1", "--oneline", action="store_true", help="List each plugin in one line")
    list_cmd.set_defaults(func=cmd_list)

    # Install command
    install_cmd = subparsers.add_parser("install", help="Install or update a package")
    flag(install_cmd, "--force", help="Force install/reinstall")
    install_cmd.add_argument("plugins", nargs="+",
                             help="Name of the plugin/plugins to install. "
                                  "Glob pattern are supported (enclose them inside quotation marks)")
    install_cmd.set_defaults(func=cmd_install)

    # remove command
    rm_cmd = subparsers.add_parser("remove", help="Remove a package")
    rm_cmd.add_argument("plugin", nargs="+", help="Plugin/s to remove")
    rm_cmd.set_defaults(func=cmd_rm)

    # show command
    show_cmd = subparsers.add_parser("show", help="Show information about a plugin")
    flag(show_cmd, "--full", help="Show additional information about a plugin")
    show_cmd.add_argument("plugin", help="Plugin to gather information about")
    show_cmd.set_defaults(func=cmd_show)

    # build docs
    makedocs_cmd = subparsers.add_parser("makedocs", help="Build the documentation for all defined plugins. "
                                                          "This depends on mkdocs being installed")
    makedocs_cmd.add_argument("--onlyinstalled", action="store_true", help="Build docs only for installed plugins")
    makedocs_cmd.add_argument("-o", "--outfolder", help="Destination folder to place the documentation",
                              default='')
    makedocs_cmd.set_defaults(func=cmd_makedocs)

    # man command
    man_cmd = subparsers.add_parser("man", help="Open manual page for an installed opcode. "
                                                "Multiple opcodes or a glob wildcard are allowed")
    man_cmd.add_argument("-p", "--path", action="store_true",
                         help="Only print the path of the manual page. The format is <opcode>:<path>, allowing to "
                              "query the path for multiple opcodes")
    man_cmd.add_argument("-s", "--simplepath", action="store_true",
                         help="Print just the path of the manual page")
    man_cmd.add_argument("-m", "--markdown", action="store_true",
                         help="Use the .md page instead of the .html version")
    man_cmd.add_argument("-e", "--external", action="store_true",
                         help="Open the man page in the default app. This is only"
                              " used when opening the markdown man page.")
    man_cmd.add_argument("--html", action="store_true",
                         help="Opens the .html version of the manpage in the default browser (or outputs the path"
                              " with the --path option)")
    man_cmd.add_argument("--theme", default="dark",
                         choices=['dark', 'light', 'gruvbox-dark', 'gruvbox-light', 'material', 'fruity', 'native'],
                         help="Style used when displaying markdown files (default=dark)")
    man_cmd.add_argument("opcode", nargs="*",
                         help="Show the manual page of this opcode/opcodes. Multiple opcodes "
                              "can be given and each entry can be also a glob pattern (make sure to "
                              "enclose it in quotation marks)")
    man_cmd.set_defaults(func=cmd_man)

    # update command
    update_cmd = subparsers.add_parser("update", help="Update repository. Updates the metadata about available"
                                                      "packages, their versions, etc.")

    # list-opcodes
    listopcodes_cmd = subparsers.add_parser("listopcodes", help="List installed opcodes")
    listopcodes_cmd.add_argument("-l", "--long", action="store_true", help="Long format")
    listopcodes_cmd.set_defaults(func=cmd_list_installed_opcodes)

    # reset
    reset_cmd = subparsers.add_parser("resetcache", help="Remove local clones of plugin's repositories")

    # info
    info_cmd = subparsers.add_parser("info", help="Outputs information about risset itself in json format")
    info_cmd.add_argument("--outfile", default=None, help="Save output to this path")
    info_cmd.add_argument("--full", action="store_true", help="Include all available information")
    info_cmd.set_defaults(func=cmd_info)

    # upgrade
    upgrade_cmd = subparsers.add_parser("upgrade", help="Upgrade any installed plugin to a new version, if there"
                                                        "is one")
    upgrade_cmd.set_defaults(func=cmd_upgrade)

    # download
    download_cmd = subparsers.add_parser('download', help='Download a plugin')
    download_cmd.add_argument('--path', help='Directory to download the plugin to (default: current directory)')
    download_cmd.add_argument('--platform', help='The platform of the plugin to download (default: current platform)',
                              choices=['linux', 'macos', 'window', 'macos-arm64', 'linux-arm64'])
    download_cmd.add_argument('plugin', help='The name of the plugin to download')
    download_cmd.set_defaults(func=cmd_download)

    # validate
    validate_cmd = subparsers.add_parser("validate", help="Validate a risset.json definition")
    validate_cmd.add_argument('infile', help="File to validate. By default, a risset.json definition")
    validate_cmd.set_defaults(func=cmd_validate)

    # dev: risset dev opcodesxml
    #      risset dev codesign
    dev_cmd = subparsers.add_parser("dev", help="Commands for developer use")

    dev_cmd.add_argument("--outfile", default=None,
                         help="Set the output file for any action generating output")
    dev_cmd.add_argument("cmd", choices=["opcodesxml", "codesign"],
                         help="Subcommand. opcodesxml: generate xml output similar to "
                              "opcodes.xml in the csound's manual; "
                              "codesign: code sign all installed plugins (macos only)")
    dev_cmd.set_defaults(func=cmd_dev)


    args = parser.parse_args()
    _session.debug = args.debug
    _session.stop_on_errors = args.stoponerror

    if args.version:
        from importlib.metadata import version
        print(version("risset"))
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(-1)
    elif args.command == 'resetcache':
        cmd_resetcache(args)
        sys.exit(0)

    update = args.update or args.command == 'update'

    if args.csound == 0:
        csoundversion, minor, rest = _csound_version()
    else:
        csoundversion = args.csound

    try:
        _debug(f"Creating main index - csound major version: {csoundversion}")
        if not update:
            mainindex = _mainindex_retrieve() or MainIndex(update=False, majorversion=csoundversion)
        else:
            # this will serialize the mainindex
            mainindex = MainIndex(update=True, majorversion=csoundversion)
    except Exception as e:
        _errormsg("Failed to create main index")
        if _session.debug:
            raise e
        else:
            _errormsg(str(e))
            sys.exit(-1)

    if args.command == 'update':
        sys.exit(0)
    else:
        errormsg = args.func(mainindex, args)
        if errormsg:
            _errormsg(f"Command {args.command} failed")
            _errormsg(errormsg)
            sys.exit(-1)
        sys.exit(0)


if __name__ == "__main__":
    main()
