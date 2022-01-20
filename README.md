![risset](assets/risset-title.png)

# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes. Plugin binaries and documentation is kept in a separate
repository at [risset-data](https://github.com/csound-plugins/risset-data)

# Installation

`risset` depends only on `git` and `python3` (>= 3.7) being installed. For linux this is
already the case, for macos and windows both need to be installed.

```
pip3 install risset
```

or via git:

```bash
git clone https://github.com/csound-plugins/risset
cd risset
python3 setup.py install
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
Platforms:
    * linux: Ubuntu 18.04
    * macos: 10.14.0
    * windows: Windows 10
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
should correspond to the name of the plugin: "myplugin.json"

#### Example of a manifest for a plugin

```json
{
  "name": "else",
  "version": "1.10.0",  
  "opcodes": [
    "accum",
    "atstop",
    "bisect",
    "crackle",
	...
  ],
  "short_description": "Miscellaneous plugins",
  "long_description": "Collection of miscellaneous plugins",
  "csound_version": "6.16",
  "author": "Eduardo Moguillansky",
  "email": "eduardo.moguillansky@gmail.com",
  "license": "LGPL",
  "repository": "https://github.com/csound-plugins/csound-plugins",
  "binaries": {
    "linux": {
      "url": "https://github.com/csound-plugins/csound-plugins/releases/download/v1.10.0/csound-plugins--linux.zip",
      "extractpath": "libelse.so",
      "build_platform": "Ubuntu 18.04"
    },
    "macos": {
      "url": "https://github.com/csound-plugins/csound-plugins/releases/download/v1.10.0/csound-plugins--macos.zip",
	  "extractpath": "libelse.dylib",
      "build_platform": "10.14.0"
    },
    "windows": {
      "url": "https://github.com/csound-plugins/csound-plugins/releases/download/v1.10.0/csound-plugins--win64.zip",
	  "extractpath": "libelse.dll",
      "build_platform": "Windows 10"
    }
  }
}

```

#### Explanation of each term

* `name`: name of the plugin. This name must be unique
* `version`: a version string indicating the version of these binaries. The version
    should have the form "MAYOR.MINOR.PATCH" or "MAJOR.MINOR", where each term is
    an integer
* `short_description`: "A series of chaotic oscillators / noise generators"
* `long_description` (optional): "A longer description of what these opcodes do"
* `csound_version`: The minimal version of csound needed to run these opcodes.
    Example "6.14.0" (a string)
* `binaries`: A dictionary with platforms as keys. Possible platforms: "linux", "macos", "windows".
    The value for each entry should be itself a dictionary of the form:
    * `url`: the url where to download the plugin. Can point to a zip file.
    * `extractpath`: for the case when the url points to a compressed file, this field indicates
    	whcat should be extracted from the compressed file
    * `build_platform`: a string identifying the platform used to build the binary
* `opcodes`: A list of all opcodes included in this plugin (for documentation purposes)
* `author`: The name of the author / mainteiner
* `email`: email of the author / mainteiner
* `repository`: the URL were the source code for this plugin is hosted, for reference

### Platform support

It is desirable, but not a requirement, that all opcodes support the three major desktop
platforms: linux, macos and windows. Support for a given platform is indicated by the availability of
a binary for the given platform in the manifest.json file.
