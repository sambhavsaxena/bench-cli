from __future__ import annotations

from bench_cli.core.bench import Bench
from bench_cli.exceptions import BenchError
from bench_cli.managers.process_manager import ProcessManagerFactory


class RunCommand:
    def __init__(self, bench: Bench) -> None:
        self.bench = bench

    def run(self) -> None:
        process_manager = ProcessManagerFactory.create(self.bench)
        if self.bench.config.nginx.enabled:
            from bench_cli.managers.supervisor_process_manager import SupervisorProcessManager
            assert isinstance(process_manager, SupervisorProcessManager)
            if not process_manager.supervisor_conf_path.exists():
                raise BenchError(
                    "Supervisor config not found. "
                    "Run 'bench setup production' first."
                )
            process_manager.generate_config()
            process_manager.reload()
        else:
            if not process_manager.procfile_path.exists():
                raise BenchError(
                    f"Procfile not found at {process_manager.procfile_path}. "
                    "Run 'bench init' first to initialise the bench."
                )
        process_manager.start()
