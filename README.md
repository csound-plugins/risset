# risset: a package manager for csound

This is the repository of risset, a package manager for csound external
plugins and user-defined-opcodes

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
```

# Show documentation of a given opcode in the default browser

$ risset doc poly

-----

# For Developers

## Format

## Plugin / UDO

A package can be either a binary plugin or UDO. A binary is a shared library with a number
of opcodes defined in it. A UDO is a .udo file with a number of user-defined-opcodes defined

## Manifest

Each plugin will have an accompanying manifest in the .json format. The name of this file
should be risset.manifest.json

See some example manifests here: XXX

#### Manifest format

##### Example of a manifest for a plugin

```json
{
    "name": "name_of_the_plugin",
    "libname": "name_of_the_shared_library",
    "version": "major.minor.patch",
    "short_description": "a short description",
    "long_description"?: "a long description",
    "csound_version": "minimal_csound_version",
    "binaries": {
        "linux": {
            "url": "url",
            "build_platform": "major.minor.patch",
            "extra_binaries": ["url1", "url2", ...]
        }, 
        "macos": {
            "url": "url",
            "build_platform": ...
        },
        "windows": ... 
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
* `version`: a version string indicating the version of this binaries
* `short_description`: "A series of chaotic oscillators / noise generators"
* `long_description` (optional): "A longer description of what these opcodes do"
* `csound_version`: The minial version of csound needed to run these opcodes. Example "6.14.0" (a string)
* `binaries`: A dictionary with platform as keys. Possible platforms: "linux", "macos", "windows". 
    The value for each entry should is itself a dictionary of the form {"url": str, "version": str}. 
    * `url` is a downloadable url pointing to the shared library itself (.so, .dll, ,dylib)
    * `extra_binaries` is an **optional** field holding an array of other binaries needed
    * `build_platform` is a string identifying the platform used to build the binary
* `manual`: A url to a .zip file holding one .md file for each opcode defined plus any number of 
    example files, resources (soundfiles, images), etc.
* `opcodes`: A list of all opcodes included in this plugin
* `author`: The name of the author / mainteiner
* `email`: email of the author / mainteiner

## Platform support

It is desirable, but not a requirement, that all opcodes support the three major desktop
platforms: linux, macos and windows. Support for a given platform is indicated by the availability of
a binary for the given platform in the manifest.json file. 

# Aggregation / Indexing

All plugins are aggregated in a plugins.json file, with the format

{
    "plugins": {
        "plugin_name@version": "manifest_url",
        ...    
    }
}

* `plugin_name` corresponds to the name in the manifest
* `version` corresponds to the version in the manifest
* `manifest_url`: url to the manifest.json of this plugin (a downloadable file)

# Implementation

## risset.py

A python script implementing installation of plugins
For all operations the url of the plugins.json must be known. A default url should be 
defined

### Commands

#### list

Lists all known plugins

#### show (plugin)

Show information about one plugin   

#### install (plugin)   

Install a given plugin for the current platform. Plugins are installed into
OPCODES6DIR64 if defined. Otherwise they are installed into a proposed folder
and a hint is printed to define that folder as OPCODES6DIR64. Specifically plugins
should NOT be installed in system folders and should be accessible without any
administrator"s rights. 


* linux: $HOME/.local/share/csound6/plugins64
* macos: $HOME/Library/Application Support/csound6/plugins64
* windows: C:\Users\<username>\AppData\Local\csound6\plugins64

Default folder for help (manual) files: $OPCODES6DIR64/help
An installation manifest is placed under <DataDir>/risset/installed_plugins. This installation manifest
is a copy of the plugin manifest renamed to <plugin-name>@<version>.risset.json

NB: DataDir is $HOME/.local/share in linux, $HOME/Library/Application Support in macOS, etc.

#### list-installed

List installed plugins

#### uninstall (plugin)

Uninstall a given plugin



-------------
[1]: 