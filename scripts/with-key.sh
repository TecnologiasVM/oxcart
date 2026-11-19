#!/bin/sh
# Run one command with API keys taken from the machine's secret store, set in that
# command's environment only. The key never lands in a file, the shell or the session.
#
#   with-key.sh VAR=entry [VAR=entry ...] -- command [args...]
#   with-key.sh OPENAI_API_KEY=openai-api-key-public -- python scripts/servers.py start
#
# An entry is expected to hold a key: 20 characters or more. For a stored setting that is
# short by nature (a user name, a database name) add ",short" after the entry name:
#   with-key.sh NEO4J_PASSWORD=some-password NEO4J_USER=some-username,short -- command
#
#   macOS  Keychain, generic password, service <entry>, account $USER.
#   Linux  systemd-creds file <dir>/<entry>.cred, made with --user --name=<entry>.
#          <dir> is KEYS_DIR, default ${XDG_CONFIG_HOME:-$HOME/.config}/api-keys/creds.
#
# Storing a key is the owner's job, in their own terminal (never pasted in a chat):
#   macOS  pbpaste | tr -d '\n' | security add-generic-password -U -a "$USER" -s <entry> -w "$(cat)"   (long keys)
#   Linux  systemd-ask-password -n '<entry>:' | systemd-creds --user encrypt --with-key=host+tpm2 --name=<entry> - <dir>/<entry>.cred
set -eu

die() { echo "with-key: $*" >&2; exit 2; }

dir=${KEYS_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/api-keys/creds}
platform=$(uname -s)

read_entry() {
  case "$platform" in
    Darwin) security find-generic-password -a "$USER" -s "$1" -w 2>/dev/null ;;
    Linux)  [ -f "$dir/$1.cred" ] && systemd-creds --user decrypt --name="$1" "$dir/$1.cred" - 2>/dev/null ;;
    *)      die "no secret store for platform '$platform'" ;;
  esac
}

[ $# -gt 0 ] || die "usage: with-key.sh VAR=entry [VAR=entry ...] -- command [args...]"
seen_sep=0
while [ $# -gt 0 ]; do
  case "$1" in
    --) shift; seen_sep=1; break ;;
    *=*)
      var=${1%%=*}; entry=${1#*=}
      case "$var" in ''|*[!A-Za-z0-9_]*|[0-9]*) die "bad variable name '$var'" ;; esac
      min=20
      case "$entry" in *,short) entry=${entry%,short}; min=1 ;; esac
      [ -n "$entry" ] || die "empty entry name for $var"
      value=$(read_entry "$entry") || die "entry '$entry' not found or not readable"
      # A stored key that is empty or a few characters long means the store step went wrong.
      [ ${#value} -ge "$min" ] || die "entry '$entry' is shorter than $min characters: store it again, or mark it ,short"
      export "$var=$value"
      unset value
      shift ;;
    *) die "expected VAR=entry or --, got '$1'" ;;
  esac
done
[ "$seen_sep" -eq 1 ] && [ $# -gt 0 ] || die "nothing to run: put the command after --"
exec "$@"
