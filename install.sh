#!/bin/bash
set -e

# Install uv if not already present
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Clone or update bench-cli
if [ -d "$HOME/bench-cli" ]; then
    echo "Updating bench-cli..."
    git -C "$HOME/bench-cli" pull
else
    echo "Cloning bench-cli..."
    git clone https://github.com/frappe/bench-cli "$HOME/bench-cli"
fi

# Install bench as a uv tool
echo "Installing bench..."
uv tool install "$HOME/bench-cli"

# Add ~/.local/bin to PATH permanently if not already there
SHELL_RC="$HOME/.bashrc"
if [[ "$SHELL" == */zsh ]]; then
    SHELL_RC="$HOME/.zshrc"
fi

if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$SHELL_RC" 2>/dev/null; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
fi

export PATH="$HOME/.local/bin:$PATH"

echo ""
echo "bench installed successfully. Run: bench --help"
echo "If bench is not found, run: source $SHELL_RC"
