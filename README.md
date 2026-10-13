![risset](assets/risset-title.png)

# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes. The index aggregating all available packages is kept
at [risset-data](https://github.com/csound-plugins/risset-data).

# Installation

*risset* requires **csound 7** or later; csound 6 is no longer supported.

Outside of **csound**, *risset* depends only on **git** and **python** (>= 3.9) 
being installed.
*risset* itself is a python program and can be installed as a any
other python package. In general, The most convenient way to install risset is
via [uv]( https://astral.sh/uv).


## MacOS / linux

```bash

# Install uv itself
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install risset
uv tool install risset

# To upgrade risset itself:
uv tool upgrade risset
```

## Windows

```powershell

powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

uv tool install risset

# To upgrade risset itself:
uv tool upgrade risset

```


----------------------------------------------------

# Quick start

### List all defined packages

```bash

$ risset list

- else /2.0.0          | Miscellaneous plugins
- pathtools /2.0.0     | Cross-platform path handling and string opcodes
- klib /2.0.0          | A hashtable for csound
- beosc /2.0.0         | Band-enhanced oscillators implementing the sine+noise synthesis model
- jsfx /2.0.0          | jsfx support for csound
- poly /2.0.0          | Multiple (parallel or sequential) instances of an opcode
- sndmeta /2.0.0       | opcodes using libsndfile
- risset /2.0.0        | Opcodes to access risset package metadata
- poodle /2.0.0        | Faust plugins ported to csound

```

### Install some packages

```bash

$ risset install else poly

```

### Show information about a specific package

```bash

$ risset show poly

Plugin        : poly
Author        : Eduardo Moguillansky (eduardo.moguillansky@gmail.com)
URL           : https://github.com/csound-plugins/csound-plugins.git
Version       : 1.18.2

Installed     : Unknown (path: /home/xx/.local/lib/csound/7.0/plugins64/libpoly.so)
Manifest      : No manifest (installed manually)
Abstract      : Multiple (parallel or sequential) instances of an opcode
Description:
    Multiple (parallel or sequential) instances of an opcode
Opcodes:
    defer, poly, poly0, polyseq
Binaries:
    * linux/csound>=7.0
    * macos/csound>=7.0
    * macos-arm64/csound>=7.0
    * windows/csound>=7.0

```

### Remove a plugin

```bash

$ risset remove poly

```

### Show manual page for an opcode (installed or not)

```bash
$ risset man poly

```

```markdown

# mtro

## Abstract

an accurate version of metro


## Description

`mtro` is a drop-in replacement of `metro` without the
drifting over time. `metro` is implemented by adding a phase
each cycle, which results in drifting over time due to rounding errors.
`mtro` avoids this problem by keeping a counter and doing multiplication
so that the error is limited.

Following metro's implementation by default `mtro` is triggered at time=0. This
is because `i_initphase` is set to 1 by default. It is possible to make `mtro` skip the
0 trigger by setting `i_initphase` to 0.

## Syntax


    kout mtro kfreq, i_initphase=1


## Arguments

* **kfreq**: the frequency of the trigger
* **i_initphase**: the initial phase (a value between 0 and 1). If set to 0, there is no trigger at time 0.
        If set to 1, `mtro` triggers at time=0, similar to `metro`

## Output

* **kout**: 1 if the mtro has triggered, 0 otherwise

## Execution Time

* Performance

```

---------------


# Commands and options

Run `risset --help` or `risset <command> --help` for command-line help. Global
options go before the command name:

```text
risset [global-options] <command> [command-options] [arguments]
```

## Global options

* `--debug`: Print debug information.
* `--no-color`: Disable colored output.
* `--update`: Update the plugin data before running the command.
* `--stop-on-error`: Stop parsing plugin data when an error is detected.
* `--user-plugins-path PATH`: Use `PATH` as the user plugin directory (same as
  setting `CS_USER_PLUGINDIR`).
* `--version`: Print the risset version and exit.

Risset also reads these environment variables:

* `LIBCSOUNDPATH`: Path to the libcsound library used to query opcodes.
* `CS_USER_PLUGINDIR`: Override the user plugin directory.
* `OPCODE7DIR64`: Path to Csound's system opcodes.

## Package commands

### `update`

Update the local plugin index and metadata:

```bash
risset update
```

### `list`

List plugins available for the current platform and Csound version. By default,
plugins without a matching binary are omitted.

```text
risset list [options]
```

Options:

* `--all`: Include plugins without a binary for the current platform or Csound version.
* `--json`: Output the plugin list as JSON.
* `-o, --outfile FILE`: Write output to a file (only applies with `--json`).
* `--nameonly`: Print only plugin names.
* `--installed`: List only installed plugins.
* `--upgradeable`: List only installed plugins that can be upgraded.
* `--noheader`: Omit extra information in the list output.
* `-1, --oneline`: Print each plugin on one line.

### `show`

Show information about a plugin. `--full` includes additional information,
including the binary URL.

```text
risset show [--full] <plugin>
```

### `install`

Install or update one or more plugins into the user plugin directory; no
administrator privileges are normally needed. Plugin names may be glob
patterns; quote patterns so the shell does not expand them first.

```text
risset install [--force] <plugin> [<plugin> ...]
```

`--force` forces a reinstall, including when the installed version is unknown.

### `remove`

Remove one or more installed plugins:

```text
risset remove <plugin> [<plugin> ...]
```

### `upgrade`

Upgrade all installed plugins for which a newer indexed version is available:

```bash
risset upgrade
```

### `download`

Move a plugin's binary to a directory without installing it. The destination
directory must already exist.

```text
risset download [--path DIRECTORY] [--platform PLATFORM] <plugin>
```

* `--path DIRECTORY`: Destination directory (default: current directory).
* `--platform PLATFORM`: Select `linux`, `linux-arm64`, `macos`, `macos-arm64`,
  or `windows` (default: current platform).

### `resetcache`

Clear the cached manual pages. `--full` also removes the local plugin index and
cloned plugin repositories.

```text
risset resetcache [--full]
```

## Opcode and documentation commands

### `listopcodes`

List installed opcodes. `--all` includes opcodes from plugins that are not
installed; `-l, --long` also prints each opcode's plugin and description.

```text
risset listopcodes [--all] [-l | --long]
```

### `man`

Display an opcode's manual page. Multiple opcode names and quoted glob patterns
are accepted. With no opcode argument, risset opens the generated documentation
index.

```text
risset man [options] [<opcode> ...]
```

* `-p, --path`: Print `<opcode>:<path>` for each manual page.
* `-s, --simplepath`: Print only each manual-page path.
* `-m, --markdown`: Use the Markdown page (the default format).
* `--html`: Open the HTML page in the default browser. `--html` and `--markdown`
  are mutually exclusive.
* `-e, --external`: Open the Markdown page in the default application instead
  of displaying it in the terminal.
* `--theme THEME`: Markdown display style: `dark` (default), `light`,
  `gruvbox-dark`, `gruvbox-light`, `material`, `fruity`, or `native`.

### `makedocs`

Build documentation for plugin opcodes (requires **mkdocs**):

```text
risset makedocs [--onlyinstalled] [-o DIRECTORY]
```

* `--onlyinstalled`: Build documentation only for installed plugins.
* `-o, --outfolder DIRECTORY`: Write documentation to this directory.

### `info`

Print environment and installation information as JSON. The output can be used
by other applications, including CsoundQt.

```text
risset info [--full] [--outfile FILE]
```

* `--full`: Include information about all available plugins.
* `--outfile FILE`: Save the JSON output to a file instead of stdout.

### `validate`

Validate a `risset.json` plugin definition and the manual pages for its opcodes:

```text
risset validate <infile>
```

## Csound and developer commands

### `csound install`

Install Csound using libcsound's installer. On Windows, run from an
Administrator session. Use `--force` to reinstall an existing Csound installation.

```text
risset csound install [--force]
```

### `dev`

Developer utilities are grouped under `risset dev`:

* `risset dev opcodesxml [--outfile FILE]`: Generate `opcodes.xml`; use
  `--outfile stdout` to print it to stdout.
* `risset dev codesign`: Code-sign installed plugin binaries (macOS only).
* `risset dev completions [--fish | --bash | --zsh] [--install]`: Print shell
  completions, or install them with `--install`. The shell is detected when
  possible; specify a shell option if detection fails. Supported on Linux and
  macOS.


-------

# Plugin Documentation

Documentation for all plugins can be found here: https://csound-plugins.github.io/risset-docs/


-----

# Contributing

In order to add/modify a plugin, clone [risset-data](https://github.com/csound-plugins/risset-data)

At the root of the repository there is an index file `rissetindex.json`, with the form:

```json
{
    "version": "1.0.0",
    "plugins": {
        "else": {
            "url": "https://github.com/csound-plugins/csound-plugins.git",
            "path": "src/else"
        },
        "pathtools": {
            "url": "https://github.com/csound-plugins/csound-plugins.git",
            "path": "src/pathtools"
        },
        "klib": {
            "url": "https://github.com/csound-plugins/csound-plugins.git",
            "path": "src/klib"
        },
        "beosc": {
            "url": "https://github.com/csound-plugins/csound-plugins.git",
            "path": "src/beosc"
        },
        "vst3": {
            "url": "https://github.com/csound-plugins/vst3-risset.git"
        }
    }
}
```

To add a plugin to the index, just extend the *plugins* dict. The url should point to a valid git repository,
the path attribute can be used to indicate where risset.json manifest is within this repository. This allows to
define multiple plugins within one repository.

## Manifest

Each plugin has an accompanying manifest in the .json format. The name of this file
is always `risset.json`
See one of the examples in https://github.com/csound-plugins/csound-plugins/tree/master/src for
more information 
