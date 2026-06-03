from __future__ import annotations

from bench_cli.utils import run_command
from bench_cli.commands.admin import download_admin_frontend, _cli_root


class UpgradeCommand:
    def run(self) -> None:
        cli_root = _cli_root()

        print("Pulling latest bench-cli...")
        run_command(["git", "-C", str(cli_root), "pull"], stream_output=True)

        print("Downloading latest admin frontend...")
        if not download_admin_frontend(cli_root):
            print("  Download failed. Run 'bench build-admin' to build from source.")
        else:
            print("bench-cli upgraded successfully.")
