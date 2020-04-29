# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes. All plugins are kept in a separate 
repository at [risset-data](https://github.com/csound-plugins/risset-data)

# Installation

```bash
pip3 install risset
```

or via git:

```bash
git clone https://github.com/csound-plugins/risset
cd risset
python3 setup.py install
```

# Example Usage

```bash
# list all defined packages
$ risset list

* else  @ 0.2.0        | Miscellaneous plugins 
* poly  @ 0.2.0        | Run multiple copies of an opcode in parallel/series
* klib  @ 0.2.0        | hashtable / pool / string cache plugins [installed 0.2.0]
* jsfx  @ 0.2.0        | Jesusonics effects in csound

# Install some packages

$ risset install else jsfx

# Show information about a specific package

$ risset show poly

Plugin     : poly
Installed  : not installed
Abstract   : Run multiple copies of an opcode in parallel/series
Minimal csound version : 6.14
Author     : Eduardo Moguillansky
Platforms  : 
    * linux: Ubuntu 16.04
    * macos: 10.14.0
    * windows: Windows 10
Opcodes    :
             poly, polyseq, poly0

# Show documentation of a given opcode in the default browser

$ risset doc poly

```

-----

# For Developers

`risset`'s data consists of an index file `plugins.json`, listing all available
plugins. Each entry in the index has the form 

```json
{
    "plugins": {
        "myplugin@1.0.0": "path/to/manifest/myplugin.json",
        "..." : "..."
    }
}
```

The path to the manifest is relative to the plugins.json file, or a url to a downloadable file.

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
            "url": "url",
            "build_platform": "major.minor.patch",
            "extra_binaries": ["url1", "url2", "..."]
        }, 
        "macos": {
            "url": "url",
            "build_platform": "..."
        },
        "windows": "..." 
    },
    "manual": "manual_zip_download_url",
    "opcodes": ["foo", "bar", "baz"],
    "author": "author_of_the_plugin",
    "email": "email_of_the_author",
    "repository": "url_to_were_the_source_is_developed"
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
    * `url`: a downloadable url pointing to the shared library itself (.so, .dll, ,dylib)
    * `extra_binaries`: an **optional** field holding an array of other binaries needed
    * `build_platform`: a string identifying the platform used to build the binary
* `manual`: A path/url to a .zip file holding one .md file for each opcode
* `opcodes`: A list of all opcodes included in this plugin (for documentation purposes)
* `author`: The name of the author / mainteiner
* `email`: email of the author / mainteiner

### Platform support

It is desirable, but not a requirement, that all opcodes support the three major desktop
platforms: linux, macos and windows. Support for a given platform is indicated by the availability of
a binary for the given platform in the manifest.json file. 


# Implementation

## risset.py

A python script implementing installation of plugins

### Commands

#### risset list

Lists all known plugins

#### risset show <plugin>

Show information about a plugin   

#### risset install <plugin> [<plugin2>, ...]   

Install a given plugin for the current platform. Plugins are installed into
the system folder where all other builtin plugins are installed. If the `--user`
flag is given, plugins are installed into the corresponding path for each platform. 

* linux: `$HOME/.local/share/csound6/plugins64`
* macos: `$HOME/Library/Application Support/csound6/plugins64`
* windows: `C:\Users\<username>\AppData\Local\csound6\plugins64`

In order for this option to be available the user should have modified its `OPCODE6DIR64`
environment variable to include this path (but also include the builtin path)

#### risset remove <plugin>

Remove an installed plugin

## TODO

* subcommand `doc`: show documentation about an opcode inside a plugin

-------------
[1]: 