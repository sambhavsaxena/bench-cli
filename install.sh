#!/bin/bash
set -e

BENCH_CLI_DIR="$HOME/bench-cli"

# Clone or update
if [ -d "$BENCH_CLI_DIR" ]; then
    echo "Updating bench-cli..."
    git -C "$BENCH_CLI_DIR" pull
else
    echo "Cloning bench-cli..."
    git clone https://github.com/frappe/bench-cli "$BENCH_CLI_DIR"
fi

chmod +x "$BENCH_CLI_DIR/bench"

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Configure passwordless sudo for bench (Linux only — macOS bench is dev-only and
# uses brew, no sudo). bench init runs many sudo commands non-interactively,
# including via the admin wizard which has no TTY, so this must be set up here
# where a TTY is available to prompt for the password. Idempotent: skip if present.
SUDOERS_FILE="/etc/sudoers.d/$(whoami)"
if [ "$(uname)" != "Darwin" ] && [ ! -f "$SUDOERS_FILE" ] && command -v sudo &>/dev/null; then
    echo "Bench needs passwordless sudo to install packages and manage services."
    # Authenticate using the system's native, secure sudo prompt
    sudo -v || { echo "sudo authentication failed."; exit 1; }
    SUDOERS_TMP="$(mktemp)"
    printf '# Frappe bench — managed by install.sh, do not edit\n%s ALL=(ALL) NOPASSWD: ALL\n' "$(whoami)" > "$SUDOERS_TMP"
    if sudo visudo -cf "$SUDOERS_TMP" >/dev/null; then
        sudo install -m 0440 "$SUDOERS_TMP" "$SUDOERS_FILE"
        echo "Configured passwordless sudo at $SUDOERS_FILE"
    else
        echo "Generated sudoers file is invalid — skipping."
    fi
    rm -f "$SUDOERS_TMP"
fi

# Install Node.js (needed by bench start (wizard mode) to install JS deps and build assets).
# Idempotent: skip if node is already present. nodesource needs a root shell,
# which only works here (TTY + sudo) — not in the no-TTY wizard init context.
if ! command -v node &>/dev/null && command -v apt-get &>/dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# Add to PATH in the appropriate shell rc file
add_to_path() {
    local rc="$1"
    local line="export PATH=\"\$HOME/bench-cli:\$PATH\""
    if ! grep -qF 'bench-cli' "$rc" 2>/dev/null; then
        echo "$line" >> "$rc"
        echo "Added bench to PATH in $rc"
    fi
}

if [[ "$SHELL" == */fish ]]; then
    FISH_CONFIG="$HOME/.config/fish/config.fish"
    mkdir -p "$(dirname "$FISH_CONFIG")"
    if ! grep -qF 'bench-cli' "$FISH_CONFIG" 2>/dev/null; then
        echo "fish_add_path \$HOME/bench-cli" >> "$FISH_CONFIG"
        echo "Added bench to PATH in $FISH_CONFIG"
    fi
elif [[ "$SHELL" == */zsh ]]; then
    add_to_path "$HOME/.zshrc"
else
    add_to_path "$HOME/.bashrc"
fi

export PATH="$BENCH_CLI_DIR:$PATH"

# Set up the admin venv (Flask backend for the setup wizard and admin UI)
ADMIN_VENV="$BENCH_CLI_DIR/.admin-venv"
if [ ! -f "$ADMIN_VENV/bin/python" ]; then
    echo "Setting up admin environment..."
    uv venv "$ADMIN_VENV" --quiet
    # Read deps from pyproject.toml if python3 is available, otherwise use known defaults
    if command -v python3 &>/dev/null; then
        ADMIN_DEPS=$(python3 -c "
import tomllib, sys
with open('$BENCH_CLI_DIR/pyproject.toml', 'rb') as f:
    d = tomllib.load(f)
deps = d.get('project', {}).get('optional-dependencies', {}).get('admin', [])
print(' '.join(deps))
" 2>/dev/null)
    fi
    if [ -z "$ADMIN_DEPS" ]; then
        ADMIN_DEPS="flask>=3.0 psutil>=5.9 pymysql>=1.1"
    fi
    # shellcheck disable=SC2086
    uv pip install --python "$ADMIN_VENV/bin/python" --quiet $ADMIN_DEPS
    echo "Admin environment ready."
fi

echo ""
echo "bench installed to $BENCH_CLI_DIR"
echo ""
echo "Quick start:"
echo "  bench new my-bench"
echo "  bench init"
echo "  bench new-site site1.localhost"
echo "  bench start"
echo ""
echo "If 'bench' is not found, open a new terminal or run: source ~/.zshrc"
