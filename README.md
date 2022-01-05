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

* else  @ 0.2.0        | Miscellaneous plugins
* poly  @ 0.2.0        | Run multiple copies of an opcode in parallel/series
* klib  @ 0.2.0        | hashtable / pool / string cache plugins [installed 0.2.0]
* jsfx  @ 0.2.0        | Jesusonics effects in csound
* mverb @ 1.3.7        | Artificial reverb based on a 2D waveguide mesh

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

Open man page in default browser

    $ risset man <opcode>

Get the path to the .html man page

    $ risset man --path <opcode>

The same, but get the path to the markdown man page

    $ risset man --path --markdown <opcode>


# Plugin Documentation

Documentation for all plugins can be found here: https://csound-plugins.github.io/risset-docs/

-------

# Upgrading risset

If installed via `pip`, do:

    pip3 install risset -U

If installed via `git`, go to the repository and do:

    git pull
    python3 setup.py install


-----

# Contributing

In order to add/modify a plugin, clone [risset-data](https://github.com/csound-plugins/risset-data)

At the root of the repository there is an index file `plugins.json`, listing all available
plugins. Each entry in the index has the form

```json
{
    "plugins": {
        "myplugin@1.0.0": "plugins/<collection>/<version>/manifests/myplugin.json",
        "..." : "..."
    }
}
```

The path to the manifest is relative to the plugins.json file inside the git repository.

## Manifest

Each plugin has an accompanying manifest in the .json format. The name of this file
should correspond to the name of the plugin: "myplugin.json"

#### Example of a manifest for a plugin

```json
{
    "name": "name_of_the_plugin",
    "libname": "name_of_the_shared_library",
    "version": "major.minor.patch",
    "short_description": "a short description",
    "long_description": "a long description",
    "csound_version": "minimal_csound_version",
    "binaries": {
        "linux": {
            "url": "path_or_url_of_binary",
            "build_platform": "major.minor.patch",
            "extra_binaries": ["url1", "url2", "..."]
        },
        "macos": {
            "url": "...",
            "build_platform": "..."
        },
        "windows": "..."
    },
    "doc": "rel/path/to/docfolder",
    "opcodes": ["foo", "bar", "baz"],
    "author": "Plugin Author",
    "email": "author@email.org",
    "repository": "https://url/to/were/the/source/is/developed"
}
```

#### Explanation of each term

In general, each field holding a url can be either a link or a path relative to
the manifest itself.

* `name`: name of the plugin. For example, "chaoticoscils". This name must be unique
* `libname`: the name of the shared library, without extension (example: `libchaoticoscils`).
    This is used to check if the plugin is installed.
* `version`: a version string indicating the version of these binaries. The version
    should have the form "MAYOR.MINOR.PATCH" or "MAJOR.MINOR", where each term is
    an integer
* `short_description`: "A series of chaotic oscillators / noise generators"
* `long_description` (optional): "A longer description of what these opcodes do"
* `csound_version`: The minimal version of csound needed to run these opcodes.
    Example "6.14.0" (a string)
* `binaries`: A dictionary with platforms as keys. Possible platforms: "linux", "macos", "windows".
    The value for each entry should be itself a dictionary of the form:
    * `url`: the path to the shared binary itself (relative to the manifest), or
    a downloadable url pointing to the shared library. At the moment only path are supported
    * `extra_binaries`: an **optional** field holding an array of other binaries needed
    * `build_platform`: a string identifying the platform used to build the binary
* `doc`: (optional) A relative path to the folder holding the man pages for the opcodes.
    Defaults to a folder named "doc" besides the manifest file
* `opcodes`: A list of all opcodes included in this plugin (for documentation purposes)
* `author`: The name of the author / mainteiner
* `email`: email of the author / mainteiner
* `repository`: the URL were the source code for this plugin is hosted

### Platform support

It is desirable, but not a requirement, that all opcodes support the three major desktop
platforms: linux, macos and windows. Support for a given platform is indicated by the availability of
a binary for the given platform in the manifest.json file.


## TODO

* subcommand `doc`: show documentation about an opcode inside a plugin
