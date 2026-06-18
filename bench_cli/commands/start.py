from __future__ import annotations

import os
import subprocess
import tomllib
from typing import TYPE_CHECKING

from bench_cli.commands.base import Command

if TYPE_CHECKING:
    from bench_cli.core.bench import Bench


class RunCommand(Command):
    name = "start"
    help = "Start all bench processes."

    def __init__(self, bench: "Bench") -> None:
        self.bench = bench

    def run(self) -> None:
        from bench_cli.managers.process_manager import ProcessManager

        initialized = (self.bench.path / "env" / "bin" / "python").exists()
        process_manager = self.bench.config.production.process_manager

        # Dev bench (no process manager): run in the foreground, or the
        # standalone setup wizard if it isn't initialized yet.
        if not process_manager:
            if not initialized:
                self._start_wizard()
                return
            ProcessManager(self.bench).start()
            return

        # Production bench (systemd/supervisor): the admin always runs under the
        # process manager. Pick by the configured manager rather than via the
        # factory, which gates on production.enabled.
        from bench_cli.managers.supervisor_process_manager import SupervisorProcessManager
        from bench_cli.managers.systemd_process_manager import SystemdProcessManager

        manager = (SystemdProcessManager if process_manager == "systemd"
                   else SupervisorProcessManager)(self.bench)

        if not initialized:
            # No workload yet — bring up just the admin (socket-activated) so the
            # setup wizard is served at the bench's domain. The workload starts
            # once the bench is initialized and `setup production` is run.
            from bench_cli.admin_url import admin_url

            manager.setup_admin()
            print(f"Admin running at {admin_url(self.bench.config)}")
            print("Finish setup there; the bench starts serving once it's initialized.")
            return

        if not manager.is_configured():
            from bench_cli.commands.restart import _incomplete_message

            print(_incomplete_message(self.bench))
            return
        manager.start()

    def _start_wizard(self) -> None:
        from bench_cli.commands.admin import download_admin_frontend, _cli_root
        from bench_cli.managers.admin_env_manager import AdminEnvManager

        cli_root = _cli_root()
        admin_mgr = AdminEnvManager(cli_root)
        admin_mgr.ensure()

        assets = cli_root / "admin" / "backend" / "static" / "dist" / "assets"
        if not assets.exists():
            print("Downloading admin frontend...")
            download_admin_frontend(cli_root)

        port = self._admin_port()
        print("\nBench not initialized. Starting setup wizard...")
        print(f"  Open http://localhost:{port} in your browser\n")

        env = {**os.environ, "PYTHONPATH": str(cli_root)}
        subprocess.run(
            [
                str(admin_mgr.python),
                "-m",
                "admin.backend.server",
                "--bench-root",
                str(self.bench.path),
                "--port",
                str(port),
                "--timeout",
                "7200",
                "--wizard",
            ],
            env=env,
        )

        if (self.bench.path / "env" / "bin" / "python").exists():
            print("\nSetup complete. Run 'bench start' to start your bench.\n", flush=True)

    def _admin_port(self) -> int:
        try:
            with open(self.bench.path / "bench.toml", "rb") as f:
                return tomllib.load(f).get("admin", {}).get("port", 7000)
        except Exception:
            return 7000
