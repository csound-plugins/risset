![risset](assets/risset-title.png)

# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes. The index aggregating all available packages is kept 
at [risset-data](https://github.com/csound-plugins/risset-data).

# Installation

``risset` depends only on `git` and `python3` (>= 3.9) being installed.


```bash
pip install risset
```

This will install the script "risset" into your path


### Linux

In certain linux distributions it is not allowed to install packages to the
system python. In that case the recommended way is to install risset within
its own virtual environment via `pipx`:

```bash
sudo apt install pipx
pipx install risset
```

# Quick start

```bash

# list all defined packages

$ risset list

* else /1.10.0         | Miscellaneous plugins [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libelse.so
* pathtools /1.10.0    | Cross-platform path handling and string opcodes [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libpathtools.so
* klib /1.10.0         | A hashtable for csound [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libklib.so
* beosc /1.10.0        | Band-enhanced oscillators implementing the sine+noise synthesis model [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libbeosc.so
* jsfx /1.10.0         | jsfx support for csound [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libjsfx.so
* poly /1.10.0         | Multiple (parallel or sequential) instances of an opcode [installed: 1.10.0]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libpoly.so
- sndmeta /1.10.0      | opcodes using libsndfile
* risset /1.10.0       | Cross-platform path handling and string opcodes [manual]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/librisset.so
* vst3 /0.3.0          | Host vst3 plugins in csound [manual]
                       |    Path: /home/xx/.local/lib/csound/6.0/plugins64/libvst3_plugins.so


# Install some packages

$ risset install else jsfx


# Show information about a specific package

$ risset show poly

Plugin        : poly
Author        : Eduardo Moguillansky (eduardo.moguillansky@gmail.com)
URL           : https://github.com/csound-plugins/csound-plugins.git
Version       : 1.10.0
Csound version: >= 6.14
Installed     : 1.10.0 (path: /home/xx/.local/lib/csound/6.0/plugins64/libpoly.so)
Manifest      : /home/xx/.local/share/risset/installed-manifests/poly.json
Abstract      : Multiple (parallel or sequential) instances of an opcode
Description:
    Multiple (parallel or sequential) instances of an opcode
Opcodes:
    defer, poly, poly0, polyseq

    
# Remove a plugin

$ risset remove poly


# See manual page for an opcode (installed or not)

$ risset man poly


```

---------------


# Risset commands

### update

Update the local index to the latest state.

    $ risset update


### list

List all available plugins for your platform

    $ risset list [options]

##### Options

* `--nameonly`: Output just the name of each plugin
* `--installed`: List only installed plugins
* `--upgradeable`: List only installed packages which can be upgraded
* `--notinstalled`: List only plugins which are not installed
* `-1, --oneline`: List each plugin in one line


### show

Show information about a plugin

    $ risset show <plugin>


### install

Install one or multiple plugins

    $ risset install [--force] <plugin> [<plugin2>, ...]

Install a given plugin for the current platform. Plugins are installed into
the user folder (no administrator requirements are needed). Look at the `info`
command to query information about the system.

##### Options

* `--force`: Installs a plugin even if the plugin with the same version is already installed

the system folder where all other builtin plugins are installed (this requires administrator rights in some platforms). Admin rights are needed for this.


### remove

Remove an installed plugin

    $ risset remove <plugin>


    #### documentation

Open man page as markdown in the command line


    $ risset man [options] <opcode>


##### Options

* `-s, --simplepath`: Print just the path of the manual page
* `-m, --markdown`: Use the .md page instead of the .html version
* `-e, --external`: Open the man page in the default app. This is only used when opening the markdown man page.
* `--html`: Opens the .html version of the manpage in the default browser (or outputs the path with the --path option)
* `--theme {dark,light,gruvbox-dark,gruvbox-light,material,fruity,native}`: Style used when displaying markdown files (default=dark)

Open the html man page in the default browser:

    $ risset man --html <opcode>

Generate/update documentation:

    $ risset makedocs

Build the documentation for all defined plugins. This depends on **mkdocs** being installed


### upgrade

    $ risset upgrade

Upgrade any installed plugin to the latest version


### listopcodes

    $ risset listopcodes

List installed opcodes


##### Options

* `-l, --long`: Long format

```
$ risset listopcodes -l

accum               else        Simple accumulator of scalar values
atstop              else        Schedule an instrument at the end of the current instrument
beadsynt            beosc       Band-Enhanced Oscillator-Bank
beosc               beosc       Band-Enhanced Oscillator
bisect              else        Returns the fractional index of a value within a sorted ar…ay / tab
chuap               chua        Simulates Chua's oscillator
crackle             else        generates noise based on a chaotic equation
defer               poly        Run an opcode at the end of current event
deref               else        Dereference a previously created reference to a variable
detectsilence       else        Detect when input falls below an amplitude threshold
dict_del            klib        Remove a key:value pair from a hashtable
dict_dump           klib        Dumps the contents of this dict as a string
dict_exists         klib        Returns 1 if the dict exists, 0 otherwise
dict_free           klib        Free a hashtable
...

```

### download

    $ risset download <plugin>

Download a plugin

##### Options

* `--path PATH`: Directory to download the plugin to (default: current directory)
* `--platform`: The platform of the plugin to download (default: current platform). One of *linux*, *macos*, *window*, *macos-arm64*, *linux-arm64*


### info

    $ risset info [options]

Outputs information about the environment as json in order to be integrated by other systems.
For example, **CsoundQT** uses this command to read the installed plugins and their opcodes
and documentation

##### Options

* `--outfile OUTFILE`: Save output to this path
* `--full`: Include all available information

-------

# Plugin Documentation

Documentation for all plugins can be found here: https://csound-plugins.github.io/risset-docs/

-------

# Upgrading risset

If installed via `pip`, do:

    pip install risset -U

If installed via `git`, go to the repository and do:

    git pull
    python setup.py install


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
more information about the manifest
