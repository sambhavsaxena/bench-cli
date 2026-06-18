from __future__ import annotations

from typing import TYPE_CHECKING

from bench_cli.commands.base import Command

if TYPE_CHECKING:
    from bench_cli.core.bench import Bench


class StopCommand(Command):
    name = "stop"
    help = "Stop the running bench."

    def __init__(self, bench: "Bench") -> None:
        self.bench = bench

    def run(self) -> None:
        from bench_cli.managers.process_manager import ProcessManagerFactory

        ProcessManagerFactory.detect_running(self.bench).stop()

        if self.bench.config.production.enabled:
            from bench_cli.admin_url import admin_url

            print(f"Stopped bench {self.bench.config.name}.")
            print(f"\nThe admin remains available:\n  {admin_url(self.bench.config)}")
        else:
            print("Bench stopped.")
