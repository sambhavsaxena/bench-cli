from __future__ import annotations

import argparse
import json
import sys
import tomllib
from typing import TYPE_CHECKING

from bench_cli.commands.base import Command
from bench_cli.exceptions import BenchError
from bench_cli.utils import host_owner, write_toml

if TYPE_CHECKING:
    from bench_cli.core.bench import Bench


class SetupProductionCommand(Command):
    name = "production"
    help = "Full production setup (process manager + nginx)."
    group = "setup"

    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--skip-nginx",
            action="store_true",
            help="Configure the process manager only; skip nginx and Let's Encrypt.",
        )

    @classmethod
    def from_args(cls, args, bench):
        return cls(bench, skip_nginx=args.skip_nginx)

    def __init__(self, bench: "Bench", skip_nginx: bool = False) -> None:
        self.bench = bench
        self.skip_nginx = skip_nginx

    def run(self) -> None:
        self._require_linux()
        if not self.skip_nginx:
            self._check_admin_domain()
        self.bench.config.validate()
        self._write_dns_multitenancy()
        if self.bench.config.production.process_manager == "systemd":
            self._setup_systemd()
        else:
            self._setup_supervisor()
        if not self.skip_nginx:
            self._enable_nginx()
            self._setup_nginx()
            self._setup_letsencrypt_if_needed()

        self._build_admin_for_production()

        self._print_summary()

    def _require_linux(self) -> None:
        from bench_cli.platform import is_linux

        if not is_linux():
            print(
                "Error: bench setup production only runs on Linux servers.\nOn macOS, use 'bench start' for local development.",
                file=sys.stderr,
            )
            sys.exit(1)

    def _check_admin_domain(self) -> None:
        """Admin is reached only via its domain in production. Use whatever is in
        bench.toml (validate() enforces it is present); just reject a domain that
        another bench already claims."""
        domain = self.bench.config.admin.domain
        if not domain:
            return  # validate() raises the required-in-prod error, naming the bench
        owner = host_owner(self.bench.path, domain)
        if owner:
            raise BenchError(f"Admin domain '{domain}' is already used by bench '{owner}'.")

    def _enable_nginx(self) -> None:
        """Persist production.nginx so later `bench new-site` reloads nginx."""
        if not self.bench.config.production.nginx:
            self.bench.config.production.nginx = True
            self._persist({"production": {"nginx": True}})

    def _persist(self, updates: dict) -> None:
        """Merge ``updates`` into bench.toml in place, preserving all other fields."""
        toml_path = self.bench.path / "bench.toml"
        data = tomllib.loads(toml_path.read_text())
        for section, values in updates.items():
            data.setdefault(section, {}).update(values)
        write_toml(toml_path, data)

    def _write_dns_multitenancy(self) -> None:
        common_config_path = self.bench.sites_path / "common_site_config.json"
        existing_data: dict = {}
        if common_config_path.exists():
            existing_data = json.loads(common_config_path.read_text())
        existing_data["dns_multitenant"] = 1
        common_config_path.write_text(json.dumps(existing_data, indent=2))

    def _setup_supervisor(self) -> None:
        import subprocess
        from bench_cli.platform import get_package_manager

        pkg = get_package_manager()
        if not pkg.is_installed("supervisor"):
            pkg.install("supervisor")
            subprocess.run(["sudo", "systemctl", "disable", "--now", "supervisor"], check=False)
        from bench_cli.managers.supervisor_process_manager import SupervisorProcessManager

        mgr = SupervisorProcessManager(self.bench)
        mgr.generate_config()
        mgr.install_config()
        mgr.reload()

    def _setup_systemd(self) -> None:
        from bench_cli.managers.systemd_process_manager import SystemdProcessManager

        mgr = SystemdProcessManager(self.bench)
        mgr.generate_config()
        mgr.install_config()
        mgr.reload()

    def _setup_nginx(self) -> None:
        from bench_cli.commands.setup.nginx import SetupNginxCommand

        SetupNginxCommand(self.bench).run()

    def _setup_letsencrypt_if_needed(self) -> None:
        from bench_cli.managers.letsencrypt_manager import needs_letsencrypt

        if not needs_letsencrypt(self.bench):
            return
        from bench_cli.commands.setup.letsencrypt import SetupLetsEncryptCommand

        SetupLetsEncryptCommand(self.bench).run()

    def _build_admin_for_production(self) -> None:
        from bench_cli.commands.admin import BuildAdminCommand

        BuildAdminCommand().run()

    def _print_summary(self) -> None:
        from bench_cli.managers.nginx_manager import NginxManager

        nginx_manager = NginxManager(self.bench)
        print("\nProduction setup complete.")
        print("Sites:")
        for site in self.bench.sites():
            if site.config.ssl and nginx_manager.cert_exists(site.config):
                print(f"  https://{site.config.name}")
            else:
                http_port = self.bench.config.nginx.http_port
                port_suffix = "" if http_port == 80 else f":{http_port}"
                print(f"  http://{site.config.name}{port_suffix}")
        if not self.skip_nginx:
            scheme = "https" if nginx_manager.admin_cert_exists() else "http"
            print(f"Admin:\n  {scheme}://{self.bench.config.admin.domain}")
