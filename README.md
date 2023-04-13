![risset](assets/risset-title.png)

# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes. The index aggregating all available packages is kept 
at [risset-data](https://github.com/csound-plugins/risset-data).

# Installation

`risset` depends only on `git` and `python3` (>= 3.9) being installed. 


```
pip install risset
```

or via git:

```bash
git clone https://github.com/csound-plugins/risset
cd risset
python setup.py install
```

These commands will install the script "risset" into your path.

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

## Risset commands

#### update

Update the local index to the latest state.

    $ risset update

#### list

List all available plugins for your platform

    $ risset list

#### show

Show information about a plugin

    $ risset show <plugin>


#### install

Install one or multiple plugins

    $ risset install <plugin> [<plugin2>, ...]

Install a given plugin for the current platform. Plugins are installed into
the system folder where all other builtin plugins are installed (this requires administrator rights in some platforms). Admin rights are needed for this.

#### remove

Remove an installed plugin

    $ risset remove <plugin>

#### documentation

Open man page as markdown in the command line

    $ risset man <opcode>

Open the html man page in the default browser:

    $ risset man --html <opcode>

Generate/update documentation:

    $ risset makedocs


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

At the root of the repository there is an index file `rissetindex.json`, listing all available
plugins. Each entry in the index has the form

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

The url + optional path points to a risset.json manifest file

## Manifest

Each plugin has an accompanying manifest in the .json format. The name of this file
is always `risset.json`
See one of the examples in https://github.com/csound-plugins/csound-plugins/tree/master/src for
more information about the manifest
