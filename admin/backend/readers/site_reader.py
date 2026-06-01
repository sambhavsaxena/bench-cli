from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SiteInfo:
    name: str
    exists: bool
    db_name: str
    db_host: str
    installed_apps: list[str]
    site_config: dict


class SiteReader:
    def __init__(self, bench_root: Path) -> None:
        self._bench_root = bench_root

    def read_all(self) -> list[SiteInfo]:
        sites_path = self._bench_root / "sites"
        if not sites_path.is_dir():
            return []
        return [self._read_site(d.name) for d in sorted(sites_path.iterdir()) if d.is_dir() and (d / "site_config.json").exists()]

    def read_one(self, site_name: str) -> SiteInfo:
        return self._read_site(site_name)

    def _read_site(self, site_name: str) -> SiteInfo:
        site_config_path = self._bench_root / "sites" / site_name / "site_config.json"
        exists = site_config_path.exists()
        site_config: dict = {}

        if exists:
            try:
                site_config = json.loads(site_config_path.read_text())
            except (json.JSONDecodeError, OSError):
                site_config = {}

        db_name = site_config.get("db_name", "")
        db_host = site_config.get("db_host", "localhost")
        installed_apps = self._list_apps(site_name) if exists else []

        return SiteInfo(
            name=site_name,
            exists=exists,
            db_name=db_name,
            db_host=db_host,
            installed_apps=installed_apps,
            site_config=site_config,
        )

    def _list_apps(self, site_name: str) -> list[str]:
        python = str(self._bench_root / "env" / "bin" / "python")
        sites_dir = str(self._bench_root / "sites")
        try:
            result = subprocess.run(
                [python, "-m", "frappe.utils.bench_helper", "frappe", "--site", site_name, "list-apps"],
                cwd=sites_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                return []
            apps = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if line:
                    app_name = line.split()[0]
                    if app_name:
                        apps.append(app_name)
            return apps
        except Exception as e:
            return []
