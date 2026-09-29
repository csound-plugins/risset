# TODO — deferred review items (risset.py)

## [2] Post-install scripts need a safe design
`install_plugin` runs `binarydef.post_install_script` via `_subproc_call(..., shell=True)`.
Plugins legitimately need post-install tasks (codesign is already handled internally,
but future plugins may need more), and the manifest review process is the current
gate. Do NOT simply re-enable unrestricted shell execution. Future work:
- require an explicit user opt-in flag (e.g. `--allow-scripts`),
- allowlist permitted interpreters/commands, prefer `shell=False` with argv lists,
- confine the script to the plugin's cloned dir, log stdout/stderr,
- record script execution in the install manifest for auditability.

## [4] Download integrity: hashes/signatures
`_download_file` now sanitizes filenames, uses timeouts, `raise_for_status()` and
atomic writes, but there is still no checksum/signature verification and the
session cache is keyed only by URL. Future work:
- add an optional `sha256` (or similar) field to binary/asset definitions in `risset.json`,
- verify the hash after download and before caching/use,
- re-verify cached files on hit; treat mismatch as cache miss + error.

## [6] Manpage pickle cache hardening
The manpage cache under `_MANPAGES_CACHE_DIR` uses `pickle.load` on files in a
writable data dir; a tampered cache file means arbitrary code execution, guarded
only by mtime comparison. It works fine for now, but future work:
- replace pickle with JSON (or another inert serialization),
- or HMAC/hash-verify the cache file before unpickling.

## [14] Import-time side effects (leave for later)
`risset.py` still does work at import time: the `--version`/`sys.exit` prelude and
the global `_session = _Session()` instantiation (which probes platform/arch and,
lazily, csound). Making the module fully import-safe (no `sys.exit`, no eager
`_Session`, lazy singletons) would improve testability and `import risset` use
(as in `test/test_module.py`), but it is a larger refactor touching `main()` and
all `_session` users. Deferred until a dedicated testability pass.

## [16] `_Session` singleton re-init (leave for later)
`_Session.__new__` returns the existing instance but `__init__` re-runs on every
`_Session()` call, resetting `downloaded_files`, `cloned_repos`, `cache`, `debug`,
etc. Callers currently rely on the single global `_session`, so this is latent
rather than active. A proper fix (e.g. `_initialized` guard or module-level
factory + explicit config object) should be done together with [14].

## [20] Narrow overly broad `except Exception` handlers (TODO)
Several command handlers (`cmd_csound_install`, `cmd_makedocs`, `cmd_rm`,
`MainIndex(...)` creation in `main()`) catch `Exception` and return `str(e)`,
losing tracebacks even with `--debug`. Also `IndexItem.read_definition` retries
the git update on any error. Future work: narrow to `OSError/RuntimeError`,
re-raise when `_session.debug` is set, and only retry on missing/stale-file errors.

## [26] Uniform subcommand dispatch (TODO)
`update`, `resetcache`, `dev`, `csound` subparsers don't all use
`set_defaults(func=)` / `required=True`; `main()` dispatches partly via
`if args.command == ...`. Future work: give every subcommand `set_defaults(func=)`,
set `subparsers.required = True`, and dispatch uniformly through `args.func`.
