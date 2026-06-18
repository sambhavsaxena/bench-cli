#!/bin/bash
set -e

INSTALL_URL="https://raw.githubusercontent.com/frappe/bench-cli/main/install.sh"
BENCH_CLI_DIR="$HOME/bench-cli"
DEFAULT_USER="frappe"

# ── arguments / environment (non-interactive support) ───────────────────────
# --user <name> | BENCH_USER   non-root user to create/use when run as root
# -y | --yes    | BENCH_YES=1  never prompt; use defaults
BENCH_USER="${BENCH_USER:-}"
NONINTERACTIVE="${BENCH_YES:-0}"
while [ $# -gt 0 ]; do
    case "$1" in
        --user) BENCH_USER="$2"; shift 2 ;;
        --user=*) BENCH_USER="${1#*=}"; shift ;;
        -y|--yes) NONINTERACTIVE=1; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

[ "$(id -u)" -eq 0 ] && SUDO="" || SUDO="sudo"

# ── passwordless sudo ───────────────────────────────────────────────────────
# bench init runs many sudo commands non-interactively (including via the admin
# wizard, which has no TTY), so the user needs NOPASSWD sudo. We keep a managed
# /etc/sudoers.d/<user> file. Writing it as root needs no password, which is
# what makes a fresh VPS (user with no password set) work.
write_sudoers() {
    local user="$1"
    local file="/etc/sudoers.d/$user"
    local tmp
    tmp="$(mktemp)"
    printf '# Frappe bench — managed by install.sh, do not edit\n%s ALL=(ALL) NOPASSWD: ALL\n' "$user" > "$tmp"
    if $SUDO visudo -cf "$tmp" >/dev/null; then
        $SUDO install -m 0440 "$tmp" "$file"
        echo "Configured passwordless sudo at $file"
    else
        echo "Generated sudoers file is invalid — aborting."
        rm -f "$tmp"
        exit 1
    fi
    rm -f "$tmp"
}

ensure_passwordless_sudo() {
    # macOS bench is dev-only (brew, no sudo); nothing to set up.
    [ "$(uname)" = "Darwin" ] && return 0
    command -v sudo >/dev/null 2>&1 || return 0

    # Already passwordless (own file or group membership) — don't clobber it.
    if sudo -n true 2>/dev/null; then
        return 0
    fi

    if [ "$NONINTERACTIVE" = "1" ]; then
        echo "Passwordless sudo is required but not configured, and running non-interactively."
        echo "Re-run as root, or add /etc/sudoers.d/$(id -un) with: $(id -un) ALL=(ALL) NOPASSWD: ALL"
        exit 1
    fi

    echo "Bench needs passwordless sudo to install packages and manage services."
    if ! sudo -v; then
        echo "sudo authentication failed. Re-run this installer as root to set it up."
        exit 1
    fi
    write_sudoers "$(id -un)"
}

# ── root handling: create a non-root user, then continue as that user ───────
setup_user_and_reexec() {
    if [ "$(uname)" = "Darwin" ]; then
        echo "Warning: running as root on macOS — continuing as root (dev only)."
        return 0
    fi

    echo "bench should not run as root. Setting up a non-root user."

    local user="$BENCH_USER"
    if [ -z "$user" ]; then
        if [ "$NONINTERACTIVE" = "1" ]; then
            user="$DEFAULT_USER"
        else
            read -rp "Username to create or use [$DEFAULT_USER]: " user
            user="${user:-$DEFAULT_USER}"
        fi
    fi
    if [ -z "$user" ] || [ "$user" = "root" ]; then
        echo "Refusing to use '$user' — pick a non-root username."
        exit 1
    fi

    if ! id "$user" >/dev/null 2>&1; then
        echo "Creating user '$user'..."
        useradd -m -s /bin/bash "$user"
        usermod -aG sudo "$user" 2>/dev/null || true
    fi

    write_sudoers "$user"

    # Re-run the installer as the new user. Prefer the exact script we were
    # invoked with (so local/dev runs aren't silently replaced by main); fall
    # back to re-fetching only when piped via curl | bash (no real $0).
    local self
    self="$(mktemp)"
    if [ -f "$0" ]; then
        cp "$0" "$self"
    else
        curl -fsSL "$INSTALL_URL" -o "$self"
    fi
    chmod 0755 "$self"

    local passthru=""
    [ "$NONINTERACTIVE" = "1" ] && passthru="-y"

    echo "Continuing installation as '$user'..."
    if command -v runuser >/dev/null 2>&1; then
        exec runuser -l "$user" -c "bash '$self' $passthru"
    else
        exec su - "$user" -c "bash '$self' $passthru"
    fi
}

if [ "$(id -u)" -eq 0 ]; then
    setup_user_and_reexec
fi

ensure_passwordless_sudo

# ── clone or update ─────────────────────────────────────────────────────────
if [ -d "$BENCH_CLI_DIR" ]; then
    echo "Updating bench-cli..."
    git -C "$BENCH_CLI_DIR" pull
else
    echo "Cloning bench-cli..."
    git clone https://github.com/frappe/bench-cli "$BENCH_CLI_DIR"
fi

chmod +x "$BENCH_CLI_DIR/bench"

# Install uv if not present
if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install Node.js (needed by bench start (wizard mode) to install JS deps and build
# assets). Idempotent: skip if node is already present. nodesource needs sudo, which
# is now passwordless.
if ! command -v node >/dev/null 2>&1 && command -v apt-get >/dev/null 2>&1; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# ── add bench to PATH ───────────────────────────────────────────────────────
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

# ── admin venv (Flask backend for the setup wizard and admin UI) ────────────
ADMIN_VENV="$BENCH_CLI_DIR/.admin-venv"
if [ ! -f "$ADMIN_VENV/bin/python" ]; then
    echo "Setting up admin environment..."
    uv venv "$ADMIN_VENV" --quiet
    # Read deps from pyproject.toml if python3 is available, otherwise use known defaults
    if command -v python3 >/dev/null 2>&1; then
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
