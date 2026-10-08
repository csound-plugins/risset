# bash completion for risset
# Source this file or place it in your bash-completion directory, e.g.
#   ~/.local/share/bash-completion/completions/risset

_risset_plugins() {
    risset list --nameonly 2>/dev/null
}

_risset_installed_plugins() {
    risset list --installed --nameonly 2>/dev/null
}

_risset_opcodes() {
    risset listopcodes 2>/dev/null
}

_risset_filedir() {
    local IFS=$'\n'
    COMPREPLY=()
    compopt -o filenames 2>/dev/null
    COMPREPLY=( $(compgen -f -- "$1") )
}

_risset() {
    COMPREPLY=()
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local commands="list install remove show makedocs man update listopcodes resetcache info upgrade download validate dev csound"
    local global_opts="-h --help --debug --no-color --update --stop-on-error --user-plugins-path --version"

    local list_opts="--json --all --nameonly --installed --upgradeable --noheader -o --outfile -1 --oneline"
    local install_opts="--force"
    local show_opts="--full"
    local makedocs_opts="--onlyinstalled -o --outfolder"
    local man_opts="-p --path -s --simplepath -m --markdown --html -e --external --theme"
    local listopcodes_opts="--all -l --long"
    local resetcache_opts="--full"
    local info_opts="--outfile --full"
    local download_opts="--path --platform"
    local dev_opts=""
    local opcodesxml_opts="--outfile"
    local completions_opts="--fish --bash --zsh --install"
    local csound_install_opts="--force"
    local help_opts="-h --help"

    # Options taking a value are handled independently of the subcommand
    case "$prev" in
        --theme)
            COMPREPLY=( $(compgen -W "dark light gruvbox-dark gruvbox-light material fruity native" -- "$cur") )
            return
            ;;
        --platform)
            COMPREPLY=( $(compgen -W "linux macos windows macos-arm64 linux-arm64" -- "$cur") )
            return
            ;;
        --user-plugins-path|--outfile|--outfolder|--path|-o)
            _risset_filedir "$cur"
            return
            ;;
    esac

    # Locate the subcommand
    local cmd="" cmd_index=-1 i
    for (( i = 1; i < COMP_CWORD; i++ )); do
        case "${COMP_WORDS[i]}" in
            list|install|remove|show|makedocs|man|update|listopcodes|resetcache|info|upgrade|download|validate|dev|csound)
                cmd="${COMP_WORDS[i]}"
                cmd_index=$i
                break
                ;;
        esac
    done

    # No subcommand yet: complete commands / global options
    if [ -z "$cmd" ]; then
        if [[ "$cur" == -* ]]; then
            COMPREPLY=( $(compgen -W "$global_opts" -- "$cur") )
        else
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        fi
        return
    fi

    # Locate nested subcommand for dev / csound
    local subcmd=""
    if [ "$cmd" = dev ]; then
        for (( i = cmd_index + 1; i < COMP_CWORD; i++ )); do
            case "${COMP_WORDS[i]}" in
                opcodesxml|codesign|completions)
                    subcmd="${COMP_WORDS[i]}"
                    break
                    ;;
            esac
        done
    elif [ "$cmd" = csound ]; then
        for (( i = cmd_index + 1; i < COMP_CWORD; i++ )); do
            case "${COMP_WORDS[i]}" in
                install)
                    subcmd="${COMP_WORDS[i]}"
                    break
                    ;;
            esac
        done
    fi

    local opts="$global_opts"
    case "$cmd" in
        list)        opts="$opts $list_opts" ;;
        install)     opts="$opts $install_opts" ;;
        show)        opts="$opts $show_opts" ;;
        makedocs)    opts="$opts $makedocs_opts" ;;
        man)         opts="$opts $man_opts" ;;
        listopcodes) opts="$opts $listopcodes_opts" ;;
        resetcache)  opts="$opts $resetcache_opts" ;;
        info)        opts="$opts $info_opts" ;;
        download)    opts="$opts $download_opts" ;;
        dev)
            if [ -z "$subcmd" ]; then
                if [[ "$cur" == -* ]]; then
                    COMPREPLY=( $(compgen -W "$global_opts $help_opts" -- "$cur") )
                else
                    COMPREPLY=( $(compgen -W "opcodesxml codesign completions" -- "$cur") )
                fi
                return
            fi
            case "$subcmd" in
                opcodesxml) opts="$opts $opcodesxml_opts" ;;
                codesign)   opts="$opts $help_opts" ;;
                completions) opts="$opts $completions_opts" ;;
            esac
            ;;
        csound)
            if [ -z "$subcmd" ]; then
                if [[ "$cur" == -* ]]; then
                    COMPREPLY=( $(compgen -W "$global_opts $help_opts" -- "$cur") )
                else
                    COMPREPLY=( $(compgen -W "install" -- "$cur") )
                fi
                return
            fi
            case "$subcmd" in
                install) opts="$opts $csound_install_opts" ;;
            esac
            ;;
    esac

    # Complete options
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
        return
    fi

    # Complete positional arguments
    case "$cmd" in
        install)     COMPREPLY=( $(compgen -W "$(_risset_plugins)" -- "$cur") ) ;;
        remove)      COMPREPLY=( $(compgen -W "$(_risset_installed_plugins)" -- "$cur") ) ;;
        show|download) COMPREPLY=( $(compgen -W "$(_risset_plugins)" -- "$cur") ) ;;
        man)         COMPREPLY=( $(compgen -W "$(_risset_opcodes)" -- "$cur") ) ;;
        validate)    _risset_filedir "$cur" ;;
        *)           COMPREPLY=( $(compgen -W "$opts" -- "$cur") ) ;;
    esac
}

complete -F _risset risset
