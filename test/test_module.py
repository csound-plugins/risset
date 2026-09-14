#!/usr/bin/env python3
"""
Test risset used as a module.

This checks that, within a single interpreter session, we can

1. import risset and build an index
2. detect that a plugin is not installed
3. install that plugin
4. detect that the plugin is now installed, without restarting the interpreter
5. render a csd using an opcode provided by the plugin (via libcsound)

Requires csound 7 to be installed (see ``python -m risset csound install``).
"""

import re
import sys
import tempfile
from pathlib import Path

import risset


def render_lfnoise() -> int:
    """
    Render test/lfnoise.csd through libcsound.

    ``lfnoise`` is an opcode provided by the ``else`` plugin, so a successful
    rendering from within this same process proves that csound can actually
    use the plugin installed above. The realtime output option of the example
    is replaced by a file output so that no audio device is needed.
    """
    import libcsound

    csdpath = Path(__file__).parent / "lfnoise.csd"
    csd = csdpath.read_text()

    with tempfile.TemporaryDirectory() as tmpdir:
        outpath = Path(tmpdir) / "lfnoise.wav"
        csd = re.sub(r"<CsOptions>.*?</CsOptions>",
                     f"<CsOptions>\n-o{outpath.as_posix()}\n-d\n-m0\n</CsOptions>",
                     csd, flags=re.DOTALL)

        cs = libcsound.Csound()
        try:
            err = cs.compileCsdText(csd)
            if err != 0:
                print(f"ERROR: could not compile lfnoise.csd (error code {err})",
                      file=sys.stderr)
                return 1
            while not cs.performKsmps():
                pass
        finally:
            cs.destroy()

        if not outpath.exists() or outpath.stat().st_size == 0:
            print("ERROR: rendering lfnoise.csd produced no output", file=sys.stderr)
            return 1
        print(f"OK: rendered lfnoise.csd ({outpath.stat().st_size} bytes)")

    return 0


def main() -> int:
    idx = risset.MainIndex(update=True)

    plugin = idx.plugins.get('else')
    if plugin is None:
        print("ERROR: plugin 'else' not found in the index", file=sys.stderr)
        return 1

    # 3.2 - 'else' must not be installed at this point
    if idx.is_plugin_installed(plugin):
        print("ERROR: plugin 'else' is already installed before the test", file=sys.stderr)
        return 1
    print("OK: plugin 'else' is not installed")

    # 3.3 - install 'else'
    err = idx.install_plugin(plugin)
    if err is not None:
        print(f"ERROR: could not install plugin 'else': {err}", file=sys.stderr)
        return 1
    print("OK: plugin 'else' installed")

    # 3.4 - the same process must now see it as installed
    if not idx.is_plugin_installed(plugin):
        print("ERROR: plugin 'else' is not recognized after installation in the same process",
              file=sys.stderr)
        return 1
    print("OK: plugin 'else' is recognized in the same process")

    # 3.5 - 'lfnoise' must be provided by 'else' for the render test to be meaningful
    if 'lfnoise' not in plugin.opcodes:
        print("ERROR: plugin 'else' does not provide the 'lfnoise' opcode", file=sys.stderr)
        return 1

    # 3.6 - render a csd which uses 'lfnoise' through libcsound
    if render_lfnoise() != 0:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
