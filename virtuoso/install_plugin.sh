#!/usr/bin/env bash
# Register (or remove) VLUT auto-load in the user's ~/.cdsinit so the ADE
# plugin loads on every Virtuoso startup. Idempotent; safe if the plugin
# file is missing (the load is guarded).
#
#   virtuoso/install_plugin.sh              # install auto-load
#   virtuoso/install_plugin.sh --uninstall  # remove it
set -e

HERE=$(cd "$(dirname "$0")" && pwd)
PLUGIN="$HERE/vlut_ade.il"
CDSINIT="${CDSINIT:-$HOME/.cdsinit}"
BEGIN=";; >>> VLUT ADE plugin (managed by install_plugin.sh) >>>"
END=";; <<< VLUT ADE plugin <<<"

# strip any existing managed block
strip_block() {
    [ -f "$CDSINIT" ] || return 0
    awk -v b="$BEGIN" -v e="$END" '
        $0==b {skip=1} !skip {print} $0==e {skip=0}' "$CDSINIT" > "$CDSINIT.vlut.tmp"
    mv "$CDSINIT.vlut.tmp" "$CDSINIT"
}

if [ "$1" = "--uninstall" ]; then
    strip_block
    echo "==> removed VLUT auto-load from $CDSINIT"
    exit 0
fi

if [ ! -f "$PLUGIN" ]; then
    echo "ERROR: plugin not found at $PLUGIN" >&2
    exit 1
fi

touch "$CDSINIT"
strip_block   # remove an old block first so re-running just updates it

cat >> "$CDSINIT" <<EOF
$BEGIN
setShellEnvVar(sprintf(nil "VLUT_ROOT=%s" "$(cd "$HERE/.." && pwd)"))
when(isFile("$PLUGIN") load("$PLUGIN"))
$END
EOF

echo "==> VLUT auto-load added to $CDSINIT"
echo "    (loads $PLUGIN on Virtuoso startup; CIW menu: VLUT)"
echo "    Restart Virtuoso, or load it now in the CIW:"
echo "      load(\"$PLUGIN\")"
