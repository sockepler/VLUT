#!/usr/bin/env bash
# VLUT installer: venv + dependencies + `vlut` launcher on PATH.
set -e
cd "$(dirname "$0")"
ROOT=$(pwd)

# ---- pick a python (3.9+) ----
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
    for c in python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$c" >/dev/null 2>&1 &&
           "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
            PY="$c"
            break
        fi
    done
fi
if [ -z "$PY" ]; then
    echo "ERROR: no python >= 3.9 found. Set PYTHON=/path/to/python and retry." >&2
    exit 1
fi
echo "==> using $($PY --version) ($PY)"

# ---- venv + package ----
if [ ! -x venv/bin/python ]; then
    echo "==> creating venv"
    "$PY" -m venv venv
fi
echo "==> installing VLUT and dependencies"
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -e .

# ---- PDK descriptor ----
if ! ls pdks/*.yaml >/dev/null 2>&1; then
    echo "NOTE: no PDK descriptor found."
    echo "      cp pdks/example.yaml.template pdks/<your_pdk>.yaml and edit it."
fi

# ---- launcher on PATH ----
BIN="$HOME/.local/bin"
mkdir -p "$BIN"
cat > "$BIN/vlut" <<EOF
#!/bin/bash
exec "$ROOT/venv/bin/vlut" "\$@"
EOF
chmod +x "$BIN/vlut"
echo "==> installed launcher: $BIN/vlut"

case ":$PATH:" in
    *":$BIN:"*) ;;
    *)
        SHELL_RC="$HOME/.bashrc"
        if ! grep -qs '\.local/bin' "$SHELL_RC"; then
            printf '\n# VLUT launcher\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$SHELL_RC"
            echo "==> added ~/.local/bin to PATH in $SHELL_RC (open a new shell)"
        fi
        ;;
esac

echo
echo "Done. Launch with:  vlut   (or ./start.sh)"
