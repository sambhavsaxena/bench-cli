from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from bench_cli.config.app_config import AppConfig
from bench_cli.utils import run_command

if TYPE_CHECKING:
    from bench_cli.core.bench import Bench


class App:
    def __init__(self, config: AppConfig, bench: "Bench") -> None:
        self.config = config
        self.bench = bench

    @property
    def path(self) -> Path:
        return self.bench.apps_path / self.config.name

    @property
    def is_cloned(self) -> bool:
        return self.path.exists() and (self.path / ".git").exists()

    def _detect_default_branch(self) -> str:
        import subprocess
        result = subprocess.run(
            ["git", "ls-remote", "--symref", self.config.repo, "HEAD"],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("ref: refs/heads/"):
                return line.split("refs/heads/")[1].split()[0]
        # Probe common Frappe branch names in priority order
        refs = subprocess.run(
            ["git", "ls-remote", "--heads", self.config.repo],
            capture_output=True, text=True,
        ).stdout
        for candidate in ("develop", "master", "version-16", "version-15"):
            if f"refs/heads/{candidate}" in refs:
                return candidate
        return "develop"

    def clone(self) -> None:
        branch = self.config.branch or self._detect_default_branch()
        run_command([
            "git", "clone",
            self.config.repo,
            "--branch", branch,
            "--depth", "1",
            str(self.path),
        ], stream_output=True)

    def update(self) -> None:
        run_command([
            "git", "-c", "pack.threads=1",
            "-C", str(self.path),
            "fetch", "origin", self.config.branch,
            "--depth", "1",
        ])
        run_command([
            "git", "-C", str(self.path),
            "merge", "--ff-only",
            f"origin/{self.config.branch}",
        ])

    def build_assets(self) -> None:
        if not (self.path / "package.json").exists():
            return
        run_command(["yarn", "--cwd", str(self.path), "build"])
