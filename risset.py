#!/usr/bin/env python3
from __future__ import annotations

__version__ = "1.0.0"

import sys

if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print("Python 3.8 or higher is needed", file=sys.stderr)
    sys.exit(-1)

import os
import argparse
import json
from dataclasses import dataclass, asdict as _asdict
import tempfile
import shutil
import subprocess
import textwrap
import fnmatch
from urllib.parse import urlparse
import urllib.request
from pathlib import Path

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import List, Dict, Tuple, Union, Optional



INDEX_GIT_REPOSITORY = "https://github.com/csound-plugins/risset-data"

SETTINGS = {
    'debug': False,
}

# once we require python >= 3.9 we can use functools.cache
_cache = {
}


def _get_platform() -> str:
    """Returns one of "linux", "macos", "windows" """
    # TODO: add support for arm linux (raspi, etc.)
    if (out := _cache.get('platform')) is None:
        _cache['platform'] = out = {
            'linux': 'linux',
            'darwin': 'macos',
            'win32': 'windows'
        }[sys.platform]
    return out


def _data_dir_for_platform() -> Path:
    """
    Returns the data directory for the given platform
    """
    platform = sys.platform
    if platform == 'linux':
        return Path(os.path.expanduser("~/.local/share"))
    elif platform == 'darwin':
        return Path(os.path.expanduser("~/Libary/Application Support"))
    elif platform == 'win32':
        p = R"C:\Users\$USERNAME\AppData\Local"
        return Path(os.path.expandvars(p))
    else:
        raise PlatformNotSupportedError(f"Platform unknown: {platform}")


RISSET_ROOT = _data_dir_for_platform() / "risset"
RISSET_DATAREPO_LOCALPATH = RISSET_ROOT / "risset-data"
RISSET_GENERATED_DOCS = RISSET_ROOT / "man"
RISSET_CLONES_PATH = RISSET_ROOT / "clones"


def _is_git_repo(path: Union[str, Path]) -> bool:
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


def _debug(*msgs) -> None:
    """ Print debug info only if debugging is turned on """
    if SETTINGS['debug']:
        print("DEBUG: ", *msgs, file=sys.stderr)


def _errormsg(msg: str) -> None:
    """ Print error message """
    for line in msg.splitlines():
        print("** Error: ", line, file=sys.stderr)


def _info(*msgs: str) -> None:
    print(*msgs)


def _banner(lines: List[str]):
    """ Print a banner message """
    margin = 2
    marginstr = " " * margin
    sep = "*" * (margin*2 + max(len(line) for line in lines))
    print("", sep, sep, "", sep="\n", end="")
    for line in lines:
        print(marginstr, line)
    print("", sep, sep, "", sep="\n")


class ErrorMsg(str):
    pass


@dataclass
class Binary:
    """
    A Binary describes a plugin binary

    Attributes:
        platform: the platform/architecture for which this binary is built. Possible platforms:
            'linux' (x86_64), 'windows' (windows 64 bits), 'macos' (x86_64)
        url: either a http link to a binary/.zip file, or a relative path to a binary/.zip file
            In the case of a relative path, the path is relative to the manifest definition
        build_platform: the platform this binary was built with
        extractpath: in the case of using a .zip file as url, the extract path should indicate
            a relative path to the binary within the .zip file structure
    """
    platform: str
    url: str
    build_platform: str
    extractpath: str = ''

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
class PluginSource:
    """
    An plugin entry in the risset index

    Attributes:
        name: the name of the plugin
        url: the url of the git repository
        path: the relative path within the repository to the risset.json file.
    """
    name: str
    url: str
    path: str = ''
    localpath: Path = None

    def __post_init__(self):
        if self.localpath is None:
            reponame = _git_reponame(self.url)
            self.localpath = RISSET_CLONES_PATH / reponame

    def manifest_path(self) -> Path:
        if not self.localpath.exists():
            _git_clone(self.url, self.localpath, depth=1)
        manifest_path = self.localpath / self.path
        if manifest_path.is_file():
            assert manifest_path.suffix == ".json"
        else:
            manifest_path = manifest_path / "risset.json"
        if not manifest_path.exists():
            raise RuntimeError(f"For plugin {self.name} ({self.url}, cloned at {self.localpath}"
                               f" the manifest was not found at the expected path: {manifest_path}")
        return manifest_path

    def update(self) -> None:
        path = self.localpath
        assert path.exists() and _is_git_repo(path)
        _git_update(path)

    def read_definition(self: PluginSource) -> Plugin:
        """
        Read the plugin definition pointed by this plugin source

        Returns:
            a Plugin

        Raises: PluginDefinitionError if there is an error
        """
        manifest = self.manifest_path()
        assert manifest.exists() and manifest.suffix == '.json'
        plugin = _plugin_definition_from_file(manifest.as_posix(), url=self.url,
                                              manifest_relative_path=self.path)
        plugin.cloned_path = self.localpath
        return plugin


@dataclass
class Plugin:
    """
    Attributes:
        name: name of the plugin
        version: a version for this plugin, for update reasons
        short_description: a short description of the plugin or its opcodes
        csound_version: csound version compatible with this plugin. Can be a specific version like '6.17' in
            which case this is understood as >= 6.17. Also possible: '>=6.17', '==6.17', '>=6.17<7.0'.
            The version itself must be of the format X.Y or X.Y.Z where all parts are integers.
        binaries: a dict mapping platform to a Binary, like {'windows': Binary(...), 'linux': Binary(...)}
            Possible platforms are: 'linux', 'windows', 'macos', where in each case x86_64 is implied. Other
                platforms, when supported, will be of the form 'linux-arm64' or 'macos-arm64'
        opcodes: a list of opcodes defined in this plugin
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
    """
    name: str
    url: str
    version: str
    short_description: str
    csound_version: str
    binaries: Dict[str, Binary]
    opcodes: List[str]
    author: str
    email: str
    manifest_relative_path: str = ''
    long_description: str = ''
    doc_folder: str = 'doc'
    cloned_path: Path = None

    def __post_init__(self):
        # manifest_relative_path should be either empty or a subdir of the repository's root. It should
        # not point directly to the manifest, since this is hard-coded as risset.json
        assert not self.manifest_relative_path or not os.path.splitext(self.manifest_relative_path)

        if self.cloned_path is None:
            self.cloned_path = RISSET_CLONES_PATH / self.name

    def __hash__(self):
        return hash((self.name, self.version))

    def binary_filename(self, platform: str = None) -> str:
        """
        The filename of the binary (a .so, .dll or .dylib file)

        Returns the filename of the binary, or None if there is no
        binary for the given/current platform
        """
        if platform is None:
            platform = _get_platform()
        binary = self.binaries.get(platform)
        return binary.binary_filename() if binary else None

    def local_manifest_path(self) -> Path:
        """
        The local path to the manifest file of this plugin
        """
        root = Path(self.cloned_path)
        return root / self.manifest_relative_path / "risset.json"

    def asdict(self) -> dict:
        d = _asdict(self)
        return d

    def manpage(self, opcode: str) -> Optional[Path]:
        """
        Returns the path to the man page for opcode
        """
        markdownfile = opcode + ".md"
        path = self.resolve_doc_folder() / markdownfile
        return path if path.exists() else None

    def resolve_doc_folder(self) -> Optional[Path]:
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


@dataclass
class Opcode:
    name: str
    plugin: str
    syntaxes: Optional[List[str]] = None


@dataclass
class InstalledPluginInfo:
    """
    Information about an installed plugin

    Attributes:
        name: (str) name of the plugin
        dllpath: (Path) path of the plugin binary (a .so, .dll or .dylib file)
        installed_in_system_folder: (bool) is this installed in the systems folder?
        installed_manifest_path: (Path) the path to the installation manifest (a .json file)
        versionstr: (str) the installed version, as str (if installed via risset)
    """
    name: str
    dllpath: Path
    versionstr: Optional[str]
    installed_manifest_path: Optional[Path] = None
    installed_in_system_folder: bool = False


UNKNOWN_VERSION = "Unknown"


class PlatformNotSupportedError(Exception):
    """Raised when the current platform is not supported"""


class PluginDefinitionError(Exception):
    """The plugin definition has an error"""


class ParseError(Exception):
    """Parse error in a manifest file"""


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


def user_plugins_path() -> Optional[Path]:
    """
    Return the install path for user plugins

    This returns the default path or the value of $CS_USER_PLUGINDIR. The env
    variable has priority.
    """
    cs_user_plugindir = os.getenv("CS_USER_PLUGINDIR")
    if cs_user_plugindir:
        return Path(cs_user_plugindir)

    pluginsdir = {
        'linux': '$HOME/.local/lib/csound/6.0/plugins64',
        'win32': 'C:\\Users\\$USERNAME\\AppData\\Local\\csound\\6.0\\plugins64',
        'darwin': '$HOME/Library/csound/6.0/plugins64'
    }[sys.platform]
    return Path(os.path.expandvars(pluginsdir))


def _csound_version() -> Tuple[int, int]:
    csound_bin = _get_binary("csound")
    if not csound_bin:
        raise OSError("csound binary not found")
    proc = subprocess.Popen([csound_bin, "--version"], stderr=subprocess.PIPE)
    proc.wait()
    out = proc.stderr.read().decode('ascii')
    for line in out.splitlines():
        if "--Csound version" not in line:
            continue
        parts = line.split()
        versionstr = parts[2]
        major, minor, *rest = versionstr.split(".")
        return int(major), int(minor)
    raise ValueError("Could not find a version number in the output")


def _extract_from_zip(zipfile: str, extractpath: str, outfolder: str = None) -> str:
    """
    Extracts a file from a zipfile, returns the path to the extracted file

    Args:
        zipfile: the path to a local .zip file
        extractpath: the path to extract inside the .zip file

    Returns:
        the path of the extracted file.

    Raises KeyError if `relpath` is not in `zipfile`
    """
    from zipfile import ZipFile
    if not outfolder:
        outfolder = tempfile.gettempdir()
    with ZipFile(zipfile, 'r') as zipobj:
        outfile = zipobj.extract(extractpath, path=outfolder)
        return outfile


def _csound_opcodes() -> List[str]:
    """
    Returns a list of installed opcodes
    """
    csound_bin = _get_binary("csound")
    proc = subprocess.run([csound_bin, "-z1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    txt = proc.stdout.decode('ascii')
    opcodes = []
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        opcodes.append(parts[0])
    return opcodes


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


def _get_shell() -> Optional[str]:
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


def _get_binary(binary) -> Optional[str]:
    path = shutil.which(binary)
    return path if path else None


def _get_git_binary() -> str:
    path = shutil.which("git")
    if not path or not os.path.exists(path):
        raise RuntimeError("git binary not found")
    return path


def _git_clone(repo: str, destination: Path, depth=1) -> None:
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
    parent = destination.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
    args = [gitbin, "clone"]
    if depth > 0:
        args.extend(["--depth", str(depth)])
    args.extend([repo, str(destination)])
    _debug(f"Calling git clone as: {' '.join(args)}")
    subprocess.call(args)


def _git_update(repopath: Path, depth=0) -> None:
    """
    Update the git repo at the given path
    """
    _debug(f"Updating git repository: {repopath}")
    if not repopath.exists():
        raise OSError(f"Can't find path to git repository {repopath}")
    gitbin = _get_git_binary()
    cwd = os.path.abspath(os.path.curdir)
    os.chdir(str(repopath))
    args = [gitbin, "pull"]
    if depth > 0:
        args.extend(['--depth', str(depth)])
    if SETTINGS['debug']:
        subprocess.call(args)
    else:
        subprocess.call(args, stdout=subprocess.PIPE)
    os.chdir(cwd)


def _version_tuplet(versionstr: str) -> Tuple[int, int, int]:
    """ Convert a version string to its integer parts """
    if not versionstr:
        raise ValueError("versionstr is empty")
    parts = versionstr.split(".")
    try:
        ints = [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"Could not parse version {versionstr}")

    if len(ints) == 1:
        ints += [0, 0]
    elif len(ints) == 2:
        ints.append(0)
    elif len(ints) > 3:
        _debug("Too many version parts (max. 3), using the first 3")
        ints = ints[:3]
    i1, i2, i3 = ints
    return i1, i2, i3


def _find_system_plugins_path(possible_paths: List[Path]) -> Optional[Path]:
    """
    Given a list of possible paths, find the folder where the system plugins are installed
    """
    ext = _plugin_extension()
    _debug("> Searching opcodes dir: ")

    if sys.platform == "win32":
        dll = "arrayops.dll"
    else:
        dll = "libarrayops" + ext

    for d in possible_paths:
        _debug("  >> looking at ", d)
        path = d.expanduser().resolve()
        if not path.is_dir() or not path.exists():
            _debug("  >>> path does not exist...")
            continue
        plugins = list(path.glob("*" + ext))
        if not plugins:
            _debug(f"  >>> path {d} exists, but has no plugins, skipping")
            continue
        if any(plugin for plugin in plugins if dll == plugin.name):
            _debug("  >>> Found!")
            return path
        _debug(f"Found plugins dir {d}, but it does not seem to be the systems plugin path"
              f"  ({dll} was not found there)")
        _debug("Plugins found here: ", str(plugins))
    return None



def _load_manifest(path: str) -> Union[dict, ErrorMsg]:
    assert os.path.splitext(path)[1] == ".json"
    try:
        d = json.load(open(path))
        return d
    except Exception as e:
        _errormsg(f"Could not parse manifest {path}")
        return ErrorMsg(str(e))


def _is_url(s: str) -> bool:
    """
    Is `s` a valid url?

    Args:
        s: URL address string to validate
    """
    result = urlparse(str(s))
    return bool(result.scheme and result.netloc)


def _parse_pluginkey(pluginkey: str) -> Tuple[str, str]:
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
        versiontup = _version_tuplet(version)
    except ValueError as e:
        _debug(f"Error while parsing version {version}: %s", str(e))
        return default
    return ".".join(str(i) for i in versiontup)


def _parse_binary(platform: str, binarydef: dict) -> Union[Binary, ErrorMsg]:
    url = binarydef.get('url')
    if not url:
        return ErrorMsg(f"Plugin definition for {platform} should have an url")
    build_platform = binarydef.get('build_platform')
    if not build_platform:
        return ErrorMsg(f"Plugin definition for {platform} should have a build_platform")
    return Binary(platform=platform, url=url, build_platform=build_platform,
                  extractpath=binarydef.get('extractpath', ''))


def _plugin_from_dict(d: dict, pluginurl: str, subpath: str = '') -> Plugin:
    def get_key(key):
        value = d.get(key)
        if value is None:
            raise PluginDefinitionError(f"Plugin has no {key} key")
        return value

    version = _normalize_version(get_key('version'))
    binariesd = get_key('binaries')
    results = [_parse_binary(platform, binary_definition)
               for platform, binary_definition in binariesd.items()]

    binaries = {}
    for result in results:
        if isinstance(result, ErrorMsg):
            _errormsg(result)
        else:
            binaries[result.platform] = result

    if not binaries:
        raise PluginDefinitionError("No valid binaries defined")

    opcodes = get_key('opcodes')
    opcodes.sort()

    return Plugin(
        name=get_key('name'),
        version=version,
        short_description=get_key('short_description'),
        author=get_key('author'),
        email=get_key('email'),
        csound_version=get_key('csound_version'),
        opcodes=opcodes,
        binaries=binaries,
        doc_folder=d.get('doc', ''),
        long_description=d.get('long_description', ''),
        url=pluginurl,
        manifest_relative_path = subpath
    )


def _resolve_path(path: Union[str, Path], basedir: Union[str, Path, None]=None
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
    shutil.rmtree(path.as_posix())


def _copy_recursive(src: Path, dest: Path) -> None:
    if not dest.exists():
        raise OSError(f"Destination path ({str(dest)}) does not exist")
    if not dest.is_dir():
        raise OSError(f"Destination path (str{dest}) should be a directory")

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



def _plugin_definition_from_file(filepath: Union[str, Path], url: str = '',
                                 manifest_relative_path: str = ''
                                 ) -> Plugin:
    """
    Create a Plugin from a plugin definition file (risset.json)

    Args:
        filepath: an absolute path to the plugin definition
        manifest_relative_path: relative path to manifest

    Returns:
        a Plugin

    Raises PluginDefinitionError if the definition is invalid (it does not define
    all needed keys) or json.JSONDecodeError if the json itself is not correctly formatted
    """
    # absolute path
    path = Path(filepath).resolve()

    if not path.exists():
        raise PluginDefinitionError(f"plugin definition file ({path}) not found")

    assert path.suffix == ".json", "Plugin definition file should be a .json file"

    _debug("Parsing manifest:", path)

    try:
        d = json.load(open(path))
    except json.decoder.JSONDecodeError as e:
        _errormsg(f"Could not parse json file {path}:\n    {e}")
        raise e

    try:
        plugin = _plugin_from_dict(d, pluginurl='')
        plugin.manifest_relative_path = manifest_relative_path
        plugin.url = url

    except PluginDefinitionError as e:
        raise e
    return plugin


def _normalize_path(path: str) -> str:
    path = os.path.expandvars(path)
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    return path


def _make_installation_manifest(plugin: Plugin, platform: str) -> dict:
    out = {}
    out['name'] = plugin.name
    out['author'] = plugin.author
    out['email'] = plugin.email
    out['version'] = plugin.version
    out['opcodes'] = plugin.opcodes
    out['long_description'] = plugin.long_description
    out['short_description'] = plugin.short_description
    out['build_platform'] = plugin.binaries[platform].build_platform
    out['binary'] = plugin.binaries[platform].binary_filename()
    out['platform'] = platform
    return out


def _print_with_line_numbers(s: str) -> None:
    for i, line in enumerate(s.splitlines()):
        print(f"{i+1:003d} {line}")


def default_system_plugins_path() -> List[Path]:
    platform = _get_platform()
    if platform == 'linux':
        possible_dirs = ["/usr/local/lib/csound/plugins64-6.0", "/usr/lib/csound/plugins64-6.0"]
    elif platform == 'macos':
        # The path based on ~ is used when csound is compiled from source.
        # We give that priority since if a user is doing that, it is probably someone who knows
        # what she is doing
        MAC_CSOUNDLIB = 'CsoundLib64'
        API_VERSION = '6.0'
        possible_dirs = [
            f"~/Library/Frameworks/{MAC_CSOUNDLIB}.framework/Versions/{API_VERSION}/Resources/Opcodes64",
            f"/Library/Frameworks/{MAC_CSOUNDLIB}.framework/Versions/{API_VERSION}/Resources/Opcodes64",
        ]
    elif platform == "windows":
        possible_dirs = ["C:\\Program Files\\Csound6_x64\\plugins64"]
    else:
        raise PlatformNotSupportedError(f"Platform {platform} not supported")
    return [Path(p).absolute() for p in possible_dirs]


def system_plugins_path() -> Optional[Path]:
    """
    Get the path were system plugins are installed.
    """
    # first check if the user has set OPCODE6DIR64
    if (path := _cache.get('system-plugins-path')) is not None:
        return path
    opcode6dir64 = os.getenv("OPCODE6DIR64")
    if opcode6dir64:
        possible_paths = [Path(p) for p in opcode6dir64.split(_get_path_separator())]
    else:
        possible_paths = default_system_plugins_path()

    out = _find_system_plugins_path(possible_paths)
    if not out:
        _errormsg(f"System plugins path not found! Searched paths: {possible_paths}")
        return None
    assert isinstance(out, Path)
    assert out.exists() and out.is_dir() and out.is_absolute()
    _cache['system-plugins-path'] = out
    return out


def user_installed_dlls() -> List[Path]:
    """
    Return a list of plugins installed at the user plugin path.
    """
    path = user_plugins_path()
    if not path or not path.exists():
        return []
    ext = _plugin_extension()
    return list(path.glob("*"+ext))


def system_installed_dlls() -> List[Path]:
    path = system_plugins_path()
    if not path or not path.exists():
        return []
    ext = _plugin_extension()
    return list(path.glob("*" + ext))


def _datarepo_localpath():
    return RISSET_ROOT / 'risset-data'


class MainIndex:
    def __init__(self, datarepo: Path = None, update=False):
        """
        Args:
            datarepo: the local path to clone the git main index repository to
            update: if True, update index prior to parsing
        """
        if datarepo is None:
            datarepo = RISSET_ROOT / 'risset-data'
        else:
            assert isinstance(datarepo, Path)
        self.indexfile = datarepo / "rissetindex.json"
        if not datarepo.exists():
            updateindex = False
            _git_clone(INDEX_GIT_REPOSITORY, datarepo, depth=1)
        else:
            updateindex = update
        assert datarepo.exists()
        assert _is_git_repo(datarepo)
        assert self.indexfile.exists(), f"Main index file not found, searched: {self.indexfile}"

        self.datarepo = datarepo
        self.version = ''
        self.pluginsources: Dict[str, PluginSource] = {}
        self.plugins: Dict[str, Plugin] = {}
        self._parseindex(updateindex=updateindex, updateplugins=update)

    def _parseindex(self, updateindex=False, updateplugins=False) -> None:
        self.plugins.clear()
        self.pluginsources.clear()
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
        plugins = d.get('plugins', {})
        repoindex = {}
        updated = set()

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
            pluginsource = PluginSource(name=name, url=url, path=path)
            pluginpath = pluginsource.localpath
            if pluginsource.url in repoindex and pluginsource.localpath != repoindex[pluginsource.url]:
                _info(f"Repository {pluginsource.url} already in cloned in path {pluginsource.localpath},"
                     f" but {pluginsource.name} will clone it under a different path: "
                     f"{repoindex[pluginsource.url]}")
            repoindex[pluginsource.url] = pluginsource.localpath
            if not pluginpath.exists():
                _git_clone(pluginsource.url, pluginpath, depth=1)
            elif updateplugins and pluginpath not in updated:
                _git_update(pluginpath)
                updated.add(pluginpath)

            self.pluginsources[name] = pluginsource

        if self.pluginsources:
            for name, pluginsource in self.pluginsources.items():
                plugin = self._parse_plugin(name)
                self.plugins[name] = plugin

    def update(self):
        self._parseindex(updateindex=True, updateplugins=True)

    def build_documentation(self, dest: Path = None, buildhtml=True,  onlyinstalled=False) -> Path:
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

    def _parse_plugin(self, pluginname) -> Optional[Plugin]:
        pluginsource = self.pluginsources.get(pluginname)
        if pluginsource is None:
            raise KeyError(f"Plugin {pluginname} not known. Known plugins: {self.pluginsources.keys()}")
        # todo
        manifestpath = pluginsource.manifest_path()
        assert manifestpath.exists()
        manifeststr = open(manifestpath).read()
        try:
            m = json.loads(manifeststr)
        except json.JSONDecodeError as err:
            _errormsg(f"Error while parsing plugin manifest. name={pluginname}, manifest={manifestpath}")
            _print_with_line_numbers(manifeststr)
            raise err
        return pluginsource.read_definition()

    def installed_path_for_dll(self, binary: str) -> Tuple[Optional[Path], bool]:
        """
        Get the installed path for a given plugin binary

        Returns (path to dll, user_installed). If not installed returns (None, False). A user installed
        dll has priority over system installed

        Args:
            binary: the name of the plugin binary, WITH extension (libfoo.so, libfoo.dll, etc)

        Returns:
            A tuple (path to the actual file or None if not found, True if this is inside the user plugins path)
        """
        user_dlls = user_installed_dlls()
        for user_dll in user_dlls:
            if user_dll.name == binary:
                return user_dll, True
        system_dlls = system_installed_dlls()
        for system_dll in system_dlls:
            if system_dll.name == binary:
                return system_dll, False
        return None, False

    def get_installed_manifests_path(self) -> Path:
        """
        Returns the path to were installation manifests are saved in this system
        """
        path = RISSET_ROOT / "installed-manifests"
        if not path.exists():
            path.mkdir(parents=True)
        return path

    def installed_manifests(self) -> List[Path]:
        """
        Return a list of all installed manifests
        """
        path = self.get_installed_manifests_path()
        manifests = list(path.glob("*.json"))
        return manifests

    def _check_plugin_installed(self, plugin: Plugin) -> bool:
        """
        Check if a given plugin is installed

        This routine queries the available opcodes in csound and checks
        that the opcodes in plugin are present
        """
        test = plugin.opcodes[0]
        opcodes = _csound_opcodes()
        return test in opcodes

    def is_plugin_installed(self, plugin: Plugin, check=True) -> bool:
        """
        Is the given plugin installed?

        It checks that the binary is in csound's path. If check is True, it
        checks that the opcodes defined in the plugin are actually present

        Arguments:
            plugin: the plugin to query
            check: if True, we check if the opcodes declared in the plugin definition
                are actually available
        """
        dll, user_installed = self.installed_path_for_dll(plugin.binary_filename())
        return dll is not None and (not check or self._check_plugin_installed(plugin))

    def find_manpage(self,
                     opcode: str,
                     markdown=True) -> Optional[Path]:
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
            opcodedef: Opcode = self.opcodes.get(opcode)
            if not opcodedef:
                raise ValueError(f"Opcode {opcode} not found")
            plugin = self.plugins.get(opcodedef.plugin)
            if not plugin:
                raise RuntimeError(f"The opcode {opcode} is defined in plugin {opcodedef.plugin}"
                                   f", but the plugin was not found")
            return plugin.manpage(opcode)

    def installed_plugin_info(self, plugin: Plugin) -> Optional[InstalledPluginInfo]:
        """
        Returns an InstalledPluginInfo if found, None otherwise
        """
        _debug(f"Checking if plugin {plugin.name} is installed")
        dll, user_installed = self.installed_path_for_dll(plugin.binary_filename())
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
                result = _load_manifest(manifest.as_posix())
                if isinstance(result, ErrorMsg):
                    _errormsg(str(result))
                    continue
                installed_version = result['version']
                installed_manifest_path = manifest
                break

        out = InstalledPluginInfo(
            name = plugin.name,
            dllpath = dll,
            versionstr = installed_version,
            installed_in_system_folder = str(dll.parent) == str(system_plugins_path()),
            installed_manifest_path = installed_manifest_path
        )
        return out

    def get_plugin_dll(self, plugin: Plugin) -> Path:
        """
        Returns the path to the binary as defined in the manifest

        If needed, downloads the file pointed by a url and extracts it if compressed,
        to a temporary location. If the plugin includes the binary within its repository
        then the local path of the cloned repository is returned

        Args:
            plugin: the plugin which defines which binary to get

        Returns:
            the path of the binary.
        """
        assert isinstance(plugin, Plugin)
        platform = _get_platform()
        bindef = plugin.binaries.get(platform)
        if not bindef:
            defined_platforms = ", ".join(plugin.binaries.keys())
            raise PlatformNotSupportedError(
                f"No binary defined for platform {platform}."
                f" Available platforms for {plugin.name}: {defined_platforms}")
        # The binary defines a url / path under the "url" key. Both can be a
        # binary (a .so, .dll, .dylib file) or a .zip file. In this latter case,
        # the key "extractpath" needs to be defined, in which case it points to
        # the relative path to the binary inside the compressed file

        # The manifest defines a path. If it is relative, it is relative to the
        # manifest itself.
        if _is_url(bindef.url):
            baseoutfile = os.path.split(bindef.url)[1]
            tmpfile, httpmsg = urllib.request.urlretrieve(bindef.url)
            if not os.path.exists(tmpfile):
                raise RuntimeError(f"Error downloading file {bindef.url}")
            path = Path(tmpfile).parent / baseoutfile
            shutil.move(tmpfile, path.as_posix())
        else:
            # url points to a local file, relative to the manifest
            manifestpath = plugin.local_manifest_path()
            path = _resolve_path(bindef.url,  manifestpath.parent)
        _debug(f"get_plugin_dll: resolved path = {str(path)}")
        if not path.exists():
            raise IOError(f"Binary not found. Given path was: {str(path)}")

        if path.suffix in ('.so', '.dll', '.dylib'):
            return path
        elif path.suffix == '.zip':
            if not bindef.extractpath:
                raise PluginDefinitionError(
                    f"The binary definition for {plugin.name} has a compressed url {bindef.url}"
                    f" but does not define an `extractpath` attribute to locate the "
                    f"binary within the compressed file")
            try:
                dll = _extract_from_zip(path.as_posix(), bindef.extractpath)
                return Path(dll)
            except Exception as e:
                raise RuntimeError(f"Error while extracting {bindef.extractpath} from zip {str(path)}: {e}")
        else:
            raise PluginDefinitionError(f"Suffix {path.suffix} not supported in url: {bindef.url}")

    def plugin_installed_version(self, plugin: Plugin) -> Optional[str]:
        """
        Check if the plugin is installed, return its version as string

        A valid version has the form <major>.<minor>[.<patch>] (patch is optional)

        Returns None if the dll is not installed, UNKNOWN_VERSION if the
        dll is installed but there is no corresponding installation
        manifest (it was not installed via risset)
        """
        info = self.installed_plugin_info(plugin)
        if not info:
            _debug(f"Plugin {plugin.name} is not installed")
            return None
        return info.versionstr

    @property
    def opcodes(self) -> Dict[str, Opcode]:
        opcodes = self.defined_opcodes()
        return {opcode.name: opcode
                for opcode in opcodes}

    def defined_opcodes(self, installed=False) -> List[Opcode]:
        """
        Returns a list of opcodes

        Args:
            installed: only opcodes which are installed are returned
        """
        opcodes = []
        for plugin in self.plugins.values():
            if installed and not self.is_plugin_installed(plugin):
                continue
            for opcodename in plugin.opcodes:
                opcodes.append(Opcode(name=opcodename, plugin=plugin.name))
        return opcodes

    def match_opcodes(self, globpattern: str, installed=False) -> List[Opcode]:
        """
        Given a glob pattern, match it against known opcodes.

        Returns a list of matched opcodes (the list might be empty)

        Args:
            globpattern: a glob pattern
            installed: If True, only opcodes belonging to installed plugins
                will be collected
        """
        opcodes = self.defined_opcodes(installed=installed)
        return [opcode for opcode in opcodes
                if fnmatch.fnmatch(opcode.name, globpattern)]

    def install_plugin(self, plugin: Plugin, check=False) -> Optional[ErrorMsg]:
        """
        Install the given plugin

        Args:
            plugin: the plugin to install
            check: if True, check that the opcodes defined in plugin are present
                after installation

        Returns:
            None if ok, an ErrorMsg if failed
        """
        assert isinstance(plugin, Plugin)
        platform = _get_platform()
        try:
            pluginpath = self.get_plugin_dll(plugin)
        except PlatformNotSupportedError as e:
            return ErrorMsg(f"Platform not supported (plugin: {plugin.name}): {e}")
        except RuntimeError as e:
            return ErrorMsg(f"Error while getting (plugin: {plugin.name}): {e}")
        except PluginDefinitionError as e:
            return ErrorMsg(f"The plugin definition for {plugin.name} has errors: {e}")

        installpath = user_plugins_path()
        try:
            shutil.copy(pluginpath.as_posix(), installpath.as_posix())
        except IOError as e:
            _debug(str(e))
            return ErrorMsg("Could not copy the binary to the install path")

        if not (installpath / pluginpath).exists():
            return ErrorMsg(f"Installation of plugin {plugin.name} failed")

        # installation succeeded, check that it works
        if not self.is_plugin_installed(plugin, check=check):
            if not check:
                return ErrorMsg(f"Tried to install plugin {plugin.name}, but the binary"
                                f"is not present")
            else:
                return ErrorMsg(f"Tried to install plugin {plugin.name}, but opcode "
                                f"{plugin.opcodes[0]}, which is provided by this plugin, "
                                f"is not present")

        # install manifest
        manifests_path = self.get_installed_manifests_path()
        if not manifests_path.exists():
            manifests_path.mkdir(parents=True)
        manifest = _make_installation_manifest(plugin, platform=platform)
        manifest_path = manifests_path / f"{plugin.name}.json"
        try:
            manifest_json = json.dumps(manifest, indent=True)
        except Exception as e:
            _errormsg("install_plugin: json error while saving manifest: " + str(e))
            return ErrorMsg("Error when dumping manifest to json")

        with open(manifest_path.as_posix(), "w") as f:
            f.write(manifest_json)
        _debug(f"Saved manifest for plugin {plugin.name} to {manifest_path}")
        _debug(manifest_json)
        # no errors
        return None

    def _list_plugins_as_dict(self, installed=False, allplatforms=False) -> dict:
        d = {}
        platform = _get_platform()
        for plugin in self.plugins.values():
            if platform not in plugin.binaries.keys():
                if not allplatforms:
                    _debug(f"Plugin {plugin.name} has no binary for platform {platform}")
                    _debug("    To include it in the list, use allplatforms")
                    continue
            info = self.installed_plugin_info(plugin)
            plugininstalled = info is not None
            if installed and not plugininstalled:
                continue
            plugdict = {}
            plugdict['version'] = plugin.version
            if info:
                plugdict['installed'] = True
                plugdict['installed-version'] = info.versionstr
                plugdict['path'] = info.dllpath.as_posix()
            else:
                plugdict['installed'] = False
            plugdict['opcodes'] = plugin.opcodes
            plugdict['url'] = plugin.url
            plugdict['short_description'] = plugin.short_description
            plugdict['long_description'] = plugin.long_description
            plugdict['author'] = plugin.author
            d[plugin.name] = plugdict
        return d

    def list_plugins(self, installed=False, nameonly=False, allplatforms=False,
                     leftcolwidth=20, oneline=False):
        platform = _get_platform()
        descr_max_width = 60
        for plugin in self.plugins.values():
            data = []
            if platform not in plugin.binaries.keys():
                if not allplatforms:
                    _debug(f"Plugin {plugin.name} has no binary for platform {platform}")
                    _debug("    To include it in the list, use the --all flag")
                    continue
                data.append("platform not supported")
            info = self.installed_plugin_info(plugin)
            plugininstalled = info is not None
            if installed and not plugininstalled:
                continue
            if nameonly:
                print(plugin.name)
                continue
            extra_lines = []
            if info:
                if info.versionstr == UNKNOWN_VERSION:
                    data.append("installed (manually)")
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
            leftcol = f"{plugin.name}  @ {plugin.version}"
            descr = plugin.short_description
            if oneline and len(descr) > descr_max_width:
                descr = descr[:descr_max_width] + "…"
            symbol = "*" if plugininstalled else "-"
            print(f"{symbol} {leftcol.ljust(leftcolwidth)} | {descr} {status}")
            if extra_lines:
                for line in extra_lines:
                    print(" " * leftcolwidth + f"   |   ", line)
        print()

    def show_plugin(self, pluginname: str) -> bool:
        """
        Show info about a plugin

        Returns True on success
        """
        plugdef = self.plugins.get(pluginname)
        if plugdef is None:
            _errormsg(f"Plugin {pluginname} unknown")
            return False
        info = self.installed_plugin_info(plugdef)
        print()
        print(f"Plugin     : {plugdef.name}")
        print(f"Author     : {plugdef.author}")
        print(f"URL        : {plugdef.url}")
        print(f"Version    : {plugdef.version}")
        if info:
            print(f"Installed  : {info.versionstr} (path: {info.dllpath.as_posix()})")
            print(f"Manifest   : {info.installed_manifest_path.as_posix()}")
        print(f"Abstract   : {plugdef.short_description}")
        if plugdef.long_description.strip():
            print("Description:")
            for line in textwrap.wrap(plugdef.long_description, 72):
                print(" " * 3, line)
            # print(textwrap.wrapindent("     ", plugdef.long_description))
        print("Platforms: ")
        for platform, platform_info in plugdef.binaries.items():
            print(f"    * {platform}: {platform_info.build_platform}")
        print(f"Opcodes:")
        opcstrs = textwrap.wrap(", ".join(plugdef.opcodes), 72)
        for s in opcstrs:
            print(" " * 3, s)

        print(f"Minimal csound version : {plugdef.csound_version}")
        print()
        return True

    def uninstall_plugin(self, plugin: Plugin) -> None:
        """
        Uninstall the given plugin

        This operation also removed the installation manifest, if the
        plugin was installed via risset. Plugins installed in the
        system's directory need to be removed manually.

        Raises RuntimeError if the plugin is not installed or is installed
        in the system's folder.
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
        if info.dllpath.exists():
            raise RuntimeError(f"Attempted to remove {info.dllpath.as_posix()}, but it"
                               f" still exists")
        manifestpath = info.installed_manifest_path
        if manifestpath and manifestpath.exists():
            os.remove(manifestpath.as_posix())


###############################################################
#                        Documentation                        #
###############################################################


def _call_mkdocs(folder: Path, *args: str):
    currentdir = os.getcwd()
    os.chdir(folder)
    subprocess.call(["python", "-m", "mkdocs"] + list(args))
    os.chdir(currentdir)


def _is_mkdocs_installed() -> bool:
    if sys.platform == "linux" or sys.platform == "darwin":
        return shutil.which("mkdocs") is not None
    else:
        try:
            import mkdocs
            return True
        except ImportError as e:
            return False


def _generate_documentation(index: MainIndex, dest: Path = None, 
                            buildhtml=True, onlyinstalled=False
                            ) -> Path:
    if dest is None:
        # ~/.local/share/risset/man
        dest = RISSET_GENERATED_DOCS
    _compile_docs(index=index, dest=dest / "docs", makeindex=True,
                  onlyinstalled=onlyinstalled)
    mkdocsconfig = RISSET_DATAREPO_LOCALPATH / "assets" / "mkdocs.yml"
    if mkdocsconfig.exists():
        shutil.copy(mkdocsconfig, dest)
        if buildhtml:
            if _is_mkdocs_installed():
                _call_mkdocs(dest, "build")
            else:
                _info("mkdocs is needed to build the html documentation")
    return dest


def _compile_docs(index: MainIndex, dest: Path, makeindex=True,
                  onlyinstalled=False) -> None:
    """
    Gathers all manpages and generates a mkdocs compatible docs folder
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
        if onlyinstalled and not index.is_plugin_installed(plugin):
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


def _manpage_get_abstract(manpage: Path, opcode: str) -> str:
    """
    Args:
        manpage: the path to the manpage for the given opcode
            (a markdown file)
        opcode: the name of the opcode

    Returns:
        the abstract. Can be an empty string if the opcode has no abstract

    Raises:
        ParseError if the manpage can't be parsed
    """
    text = open(manpage).read()
    if "# Abstract" in text:
        # the abstract would be all the text between # Abstract and the next #tag
        it = iter(text.splitlines())
        for line in it:
            if not "# Abstract" in line:
                continue
            for line in it:
                line = line.strip()
                if not line:
                    continue
                return line if not line.startswith("#") else ""
        _debug(f"No abstract in manpage file {manpage}")
        return ""
    # no Abstract tag, so abstract is the text between the title and the text tag
    _debug(f"get_abstract: manpage for opcode {opcode} has no # Abstract tag")
    it = iter(text.splitlines())
    for line in it:
        line = line.strip()
        if not line:
            continue
        if not line.startswith("#"):
            raise ParseError(f"Expected title, got {line}")
        parts = line.split()
        if len(parts) != 2:
            raise ParseError("Could not parse title, expected line of the form '# opcode'")
        if parts[1].lower() != opcode.lower():
            raise ParseError(f"Expected title ({parts[1]} to be the same as opcode name ({opcode})")
        for line in it:
            line = line.strip()
            if line:
                return line if not line.startswith("#") else ""
        _debug(f"No abstract in manpage file {manpage}")
        return ""


def _docs_generate_index(index: MainIndex,
                         outfile: Path = None) -> None:
    """
    Generate an index for the documentation

    Arguments:
        index: the main index
        outfile: the path to write the index to (normally an index.md file)
    """
    lines = []
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
            try:
                abstract = _manpage_get_abstract(manpage, opcode)
            except ParseError as err:
                _errormsg(f"Could not get abstract for opcode {opcode}: {err}")
                continue
            _(f"  * [{opcode}](opcodes/{opcode}.md): {abstract}")

        _("")
    with open(outfile, "w") as f:
        f.write("\n".join(lines))


###############################################################
#                        Subcommands                          #
###############################################################


def cmd_list(mainindex: MainIndex, args) -> None:
    """
    Lists all plugins available for download
    """
    # TODO: implement flags: --json, --output
    if args.json:
        d = mainindex._list_plugins_as_dict(installed=args.installed, allplatforms=args.all)
        if args.outfile:
            with open(args.outfile, "w") as f:
                json.dump(d, f, indent=2)
        else:
            print(json.dumps(d, indent=2))
    else:
        mainindex.list_plugins(installed=args.installed, nameonly=args.nameonly,
                               allplatforms=args.all, oneline=args.oneline)


def cmd_show(index: MainIndex, args) -> bool:
    """
    Returns True on success
    """
    return index.show_plugin(args.plugin)


def cmd_rm(index: MainIndex, args) -> bool:
    """
    Remove a plugin
    """
    errors = []
    platform = _get_platform()
    noerrors = True
    for pluginname in args.plugin:
        plugdef = index.plugins.get(pluginname)
        try:
            index.uninstall_plugin(plugdef)
        except Exception as e:
            _errormsg(str(e))
            noerrors = False
    return noerrors


def cmd_install(index: MainIndex, args) -> bool:
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
    allplugins: List[Plugin] = []
    for pattern in args.plugins:
        matched = [plugin for name, plugin in index.plugins.items()
                   if fnmatch.fnmatch(name, pattern)]
        if matched:
            allplugins.extend(matched)
    if not allplugins:
        _errormsg("No plugins matched")
        return False
    allplugins = list(set(allplugins))  # remove duplicates
    errors_found = False
    for plugin in allplugins:
        current_version = index.plugin_installed_version(plugin)
        if current_version == UNKNOWN_VERSION:
            # plugin is installed but without a corresponding install manifest.
            if not args.force:
                _errormsg(f"Plugin {plugin} is already installed. Use --force to force reinstall")
                errors_found = True
                continue
        elif current_version is None:
            # plugin is not installed
            _debug(f"Plugin {plugin} not installed, installing")
        else:
            if _version_tuplet(plugin.version) <= _version_tuplet(current_version):
                _debug(f"Plugin {plugin.name}, version: {plugin.version}")
                _debug(f"    Installed version: {current_version}")
                _info(f"Installed version of plugin {plugin.name} is up-to-date")
                errors_found = True
                continue
            _info(f"Updating plugin {plugin.name}: "
                 f"{current_version} -> {plugin.version}")
        error = index.install_plugin(plugin)
        if error:
            _errormsg(error)
    return False if errors_found else True


def _open_in_default_application(path: str):
    """
    Open path with the app defined to handle it by the user
    at the os level (xdg-open in linux, start in win, open in osx)
    """
    platform = sys.platform
    if platform == 'linux':
        subprocess.call(["xdg-open", path])
    elif platform == "win32":
        os.startfile(path)
    elif platform == "darwin":
        subprocess.call(["open", path])
    else:
        raise RuntimeError(f"platform {platform} not supported")


def cmd_man(idx: MainIndex, args) -> bool:
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
    opcodes = []
    if args.html and not args.markdown:
        fmt = "html"
    else:
        fmt = "markdown"
    for pattern in args.opcode:
        matched = idx.match_opcodes(pattern)
        if matched:
            opcodes.extend(matched)
    if not opcodes:
        # open the index
        htmlidx = RISSET_GENERATED_DOCS / "site" / "index.html"
        if not htmlidx.exists():
            _errormsg(f"Index file for the documentation not found (path: {htmlidx.as_posix()}")
            return False
        _open_in_default_application(htmlidx.as_posix())
    else:
        for opcode in opcodes:
            _debug("man: processing opcode ", opcode.name)
            path = idx.find_manpage(opcode=opcode.name, markdown=fmt=="markdown")
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
                    _show_markdown_file(path)
            else:
                # open it in the default application
                _open_in_default_application(str(path))
    return True


def cmd_update(idx: MainIndex, args) -> bool:
    idx.update()
    return True


def cmd_resetcache(args) -> None:
    _rm_dir(RISSET_DATAREPO_LOCALPATH)
    _rm_dir(RISSET_CLONES_PATH)


def update_self():
    """ upgrade risset itself """
    python = sys.executable
    _info("Updating risset")
    subprocess.check_call([python, "-m", "pip", "install", "risset", "--upgrade"])


def cmd_list_installed_opcodes(plugins_index: MainIndex, args) -> bool:
    """
    Print a list of installed opcodes
    """
    opcodes = plugins_index.defined_opcodes(installed=True)
    opcodes.sort(key=lambda opcode: opcode.name.lower())
    for opcode in opcodes:
        print(opcode.name)
    return True


def cmd_makedocs(idx: MainIndex, args) -> bool:
    """
    Generate the documentation for all opcodes

    Options:
        --onlyinstalled: if True, only generate documentation for installed opcodes
        --outfolder: if given the documentation is placed in this folder. Otherwise it is
            placed in RISSET_GENERATED_DOCS
    """
    outfolder = args.outfolder or RISSET_GENERATED_DOCS
    _generate_documentation(idx, dest=Path(outfolder), buildhtml=True, onlyinstalled=args.onlyinstalled)
    _info(f"Documentation generated in {outfolder}")
    return True


def _running_from_terminal():
    return sys.stdin.isatty()


def _print_file(path: Path) -> None:
    text = open(str(path)).read()
    print(text)


def _has(cmd: str) -> bool:
    """ Returns True if cmd is in the path """
    path = shutil.which(cmd)
    return path is not None


def _show_markdown_file(path: Path) -> None:
    if not _running_from_terminal():
        _open_in_default_application(str(path))
        return

    if sys.platform == 'linux' or sys.platform == 'darwin':
        if _has("bat"):
            subprocess.call(["bat", "--style", "header", str(path)])
        elif _has("pygmentize"):
            subprocess.call(["pygmentize", str(path)])
        elif _has("highlight"):
            #  highlight --force --out-format="${highlight_format}" --style="${HIGHLIGHT_STYLE}"
            subprocess.call(["highlight", "--force", "--out-format=ANSI", str(path)])
        else:
            print("Considere installing 'pygmentize', 'highlight' or 'bat' for better syntax highlighting")
            print()
            _print_file(path)
    else:
        if _has("bat"):
            subprocess.call(["bat", "--style", "header", str(path)], shell=True)
        elif _has("pygmentize"):
            subprocess.call(["pygmentize", str(path)])
        elif _has("highlight"):
            #  highlight --force --out-format="${highlight_format}" --style="${HIGHLIGHT_STYLE}"
            subprocess.call(["highlight", "--force", "--out-format=ANSI", str(path)])
        else:
            print("Considere installing 'highlight', 'bat' or 'pygmentize' for better syntax highlighting")
            print()
            _print_file(path)


def add_flag(parser, flag, help=""):
    parser.add_argument(flag, action="store_true", help=help)


def main():
    # Preliminary checks
    if sys.platform not in ("linux", "darwin", "win32"):
        _errormsg(f"Platform not supported: {sys.platform}")
        sys.exit(-1)

    if _get_binary("git") is None:
        _errormsg("git command not found. Check that git is installed and in the PATH")
        sys.exit(-1)

    # csound_version = _csound_version()
    # debug(f"Csound version: {csound_version}")

    # Main parser
    parser = argparse.ArgumentParser()
    add_flag(parser, "--debug", help="Print debug information")
    add_flag(parser, "--update", help="Update the plugins data before any action")
    add_flag(parser, "--version")
    subparsers = parser.add_subparsers(dest='command')

    # List command
    list_group = subparsers.add_parser('list', help="List packages")
    add_flag(list_group, "--json", help="Outputs list as json")
    add_flag(list_group, "--all", "List all plugins, even those without a binary for the current platform")
    add_flag(list_group, "--nameonly", help="Output just the name of each plugin")
    add_flag(list_group, "--installed", help="List only installed plugins")
    add_flag(list_group, "--notinstalled", help="List only plugins which are not installed")
    list_group.add_argument("-o", "--outfile", help="Outputs to a file")
    list_group.add_argument("-1", "--oneline", action="store_true", help="List each plugin in one line")
    list_group.set_defaults(func=cmd_list)

    # Install command
    install_group = subparsers.add_parser("install", help="Install a package")
    add_flag(install_group, "--force", help="Force install/reinstall")
    install_group.add_argument("plugins", nargs="+",
                               help="Name of the plugin/plugins to install. "
                                    "Glob pattern are supported (enclose them inside quotation marks)")
    install_group.set_defaults(func=cmd_install)

    # remove command
    rm_group = subparsers.add_parser("remove", help="Remove a package")
    rm_group.add_argument("plugin", nargs="+", help="Plugin/s to remove")
    rm_group.set_defaults(func=cmd_rm)

    # show command
    show_group = subparsers.add_parser("show", help="Show information about a plugin")
    show_group.add_argument("plugin", help="Plugin to gather information about")
    show_group.set_defaults(func=cmd_show)

    # build docs
    makedocs_group = subparsers.add_parser("makedocs", help="Build the documentation for all defined plugins. "
                                                            "This depends on mkdocs being installed")
    makedocs_group.add_argument("--onlyinstalled", action="store_true", help="Build docs only for installed plugins")
    makedocs_group.add_argument("-o", "--outfolder", help="Destination folder to place the documentation",
                                default='')
    makedocs_group.set_defaults(func=cmd_makedocs)

    # man command
    man_group = subparsers.add_parser("man", help="Open manual page for an installed opcode. "
                                                  "Multiple opcodes or a glob wildcard are allowed")
    man_group.add_argument("-p", "--path", action="store_true",
                           help="Only print the path of the manual page. The format is <opcode>:<path>")
    man_group.add_argument("-s", "--simplepath", action="store_true",
                           help="Print just the path of the manual page")
    man_group.add_argument("-m", "--markdown", action="store_true",
                           help="Use the .md page instead of the .html version")
    man_group.add_argument("-e", "--external", action="store_true",
                           help="Open the man page in the default app. This is only"
                                " used when opening the markdown man page.")
    man_group.add_argument("--html", action="store_true",
                           help="Use the .html page (opens it in the default browser")
    man_group.add_argument("opcode", nargs="*", help="Show the manual page of this opcode/opcodes")
    man_group.set_defaults(func=cmd_man)

    # update command
    update_group = subparsers.add_parser("update", help="Update repository")
    update_group.set_defaults(func=cmd_update)

    # list-opcodes
    listopcodes = subparsers.add_parser("listopcodes", help="List installed opcodes")
    listopcodes.set_defaults(func=cmd_list_installed_opcodes)
    
    # reset
    resetgroup = subparsers.add_parser("resetcache", help="Remove local clones of plugin's repositories")

    args = parser.parse_args()
    if args.debug:
        SETTINGS['debug'] = True

    if args.version:
        print(__version__)
        sys.exit(0)

    if not args.command:
        parser.print_help()
        sys.exit(-1)

    try:
        mainindex = MainIndex(update=args.update or args.command == 'update')
    except Exception as e:
        _errormsg(str(e))
        sys.exit(-1)

    if args.command == 'update':
        sys.exit(0)
    elif args.command == 'resetcache':
        cmd_resetcache(args)
        sys.exit(0)
    else:
        ok = args.func(mainindex, args)
        sys.exit(0 if ok else -1)
    

if __name__ == "__main__":
    main()
