# fish completions for risset

set -l commands list install remove show makedocs man update listopcodes resetcache info upgrade download validate dev csound

# --- helpers -----------------------------------------------------------------

function __risset_plugins_all
    risset list --nameonly 2>/dev/null
end

function __risset_plugins_installed
    risset list --installed --nameonly 2>/dev/null
end

function __risset_opcodes
    risset listopcodes 2>/dev/null
end

function __risset_all_opcodes
    risset listopcodes --all 2>/dev/null
end

# --- global options ----------------------------------------------------------

complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l debug -d 'Print debug information'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l no-color -d 'Disable colored output'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l update -d 'Update the plugins data before any action'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l stop-on-error -d 'Stop parsing if an error is detected'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l user-plugins-path -d 'Override the user plugins path' -r
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -l version -d 'Print version and exit'

# --- subcommands -------------------------------------------------------------

complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a list -d 'List packages'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a install -d 'Install or update a package'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a remove -d 'Remove a package'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a show -d 'Show information about a plugin'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a makedocs -d 'Build the documentation for all defined plugins'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a man -d 'Open manual page for an installed opcode'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a update -d 'Update repository metadata'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a listopcodes -d 'List installed opcodes'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a resetcache -d 'Remove local cache'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a info -d 'Outputs information about risset itself in json format'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a upgrade -d 'Upgrade any installed plugin to a new version'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a download -d 'Download a plugin'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a validate -d 'Validate a risset.json definition'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a dev -d 'Commands for developer use'
complete -f -c risset -n "not __fish_seen_subcommand_from $commands" -a csound -d 'Manage the csound installation'

# --- list --------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from list" -l json -d 'Outputs list as json'
complete -f -c risset -n "__fish_seen_subcommand_from list" -l all -d 'List all plugins, even those without a binary for this platform'
complete -f -c risset -n "__fish_seen_subcommand_from list" -l nameonly -d 'Output just the name of each plugin'
complete -f -c risset -n "__fish_seen_subcommand_from list" -l installed -d 'List only installed plugins'
complete -f -c risset -n "__fish_seen_subcommand_from list" -l upgradeable -d 'List only installed packages which can be upgraded'
complete -f -c risset -n "__fish_seen_subcommand_from list" -l noheader -d 'Do not print any extra information'
complete -f -c risset -n "__fish_seen_subcommand_from list" -o o -l outfile -d 'Outputs to a file' -r
complete -f -c risset -n "__fish_seen_subcommand_from list" -o 1 -l oneline -d 'List each plugin in one line'

# --- install -----------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from install" -l force -d 'Force install/reinstall'
complete -f -c risset -n "__fish_seen_subcommand_from install" -a "(__risset_plugins_all)" -d 'Plugin'

# --- remove ------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from remove" -a "(__risset_plugins_installed)" -d 'Plugin'

# --- show --------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from show" -l full -d 'Show additional information about a plugin'
complete -f -c risset -n "__fish_seen_subcommand_from show" -a "(__risset_plugins_all)" -d 'Plugin'

# --- makedocs ----------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from makedocs" -l onlyinstalled -d 'Build docs only for installed plugins'
complete -f -c risset -n "__fish_seen_subcommand_from makedocs" -o o -l outfolder -d 'Destination folder to place the documentation' -r

# --- man ---------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from man" -o p -l path -d 'Only print the path of the manual page'
complete -f -c risset -n "__fish_seen_subcommand_from man" -o s -l simplepath -d 'Print just the path of the manual page'
complete -f -c risset -n "__fish_seen_subcommand_from man" -o m -l markdown -d 'Use the .md page instead of the .html version'
complete -f -c risset -n "__fish_seen_subcommand_from man" -l html -d 'Open the .html version of the manpage'
complete -f -c risset -n "__fish_seen_subcommand_from man" -o e -l external -d 'Open the man page in the default app'
complete -f -c risset -n "__fish_seen_subcommand_from man" -l theme -d 'Style used when displaying markdown files' -x -a 'dark light gruvbox-dark gruvbox-light material fruity native'
complete -f -c risset -n "__fish_seen_subcommand_from man" -a "(__risset_opcodes)" -d 'Opcode'

# --- listopcodes -------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from listopcodes" -l all -d 'List all opcodes, even those within not installed plugins'
complete -f -c risset -n "__fish_seen_subcommand_from listopcodes" -o l -l long -d 'Long format'

# --- resetcache --------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from resetcache" -l full -d 'Remove the entire cache'

# --- info --------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from info" -l outfile -d 'Save output to this path' -r
complete -f -c risset -n "__fish_seen_subcommand_from info" -l full -d 'Include all available information'

# --- download ----------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from download" -l path -d 'Directory to download the plugin to' -r
complete -f -c risset -n "__fish_seen_subcommand_from download" -l platform -d 'The platform of the plugin to download' -x -a 'linux macos windows macos-arm64 linux-arm64'
complete -f -c risset -n "__fish_seen_subcommand_from download" -a "(__risset_plugins_all)" -d 'Plugin'

# --- validate ----------------------------------------------------------------

complete -c risset -n "__fish_seen_subcommand_from validate" -F

# --- dev ---------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from dev; and not __fish_seen_subcommand_from opcodesxml codesign completions" -a opcodesxml -d 'Generate xml output similar to opcodes.xml'
complete -f -c risset -n "__fish_seen_subcommand_from dev; and not __fish_seen_subcommand_from opcodesxml codesign completions" -a codesign -d 'Code sign all installed plugins (macos only)'
complete -f -c risset -n "__fish_seen_subcommand_from dev; and not __fish_seen_subcommand_from opcodesxml codesign completions" -a completions -d 'Output or install the shell completions'
complete -f -c risset -n "__fish_seen_subcommand_from opcodesxml" -l outfile -d "Set the output file (use 'stdout' to print to stdout)" -r
complete -f -c risset -n "__fish_seen_subcommand_from completions" -l fish -d 'Use the fish shell'
complete -f -c risset -n "__fish_seen_subcommand_from completions" -l bash -d 'Use the bash shell'
complete -f -c risset -n "__fish_seen_subcommand_from completions" -l zsh -d 'Use the zsh shell'
complete -f -c risset -n "__fish_seen_subcommand_from completions" -l install -d 'Install the completions instead of printing them'

# --- csound ------------------------------------------------------------------

complete -f -c risset -n "__fish_seen_subcommand_from csound; and not __fish_seen_subcommand_from install" -a install -d 'Install csound'
complete -f -c risset -n "__fish_seen_subcommand_from csound; and __fish_seen_subcommand_from install" -l force -d 'Reinstall csound even if it is already installed'
