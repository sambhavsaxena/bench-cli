from __future__ import annotations

import json
import re
import shutil
import sys
import subprocess
from pathlib import Path

from bench_cli.config.app_config import AppConfig
from bench_cli.core.app import App
from bench_cli.core.bench import Bench
from bench_cli.managers.python_env_manager import PythonEnvManager

# Matches esbuild content-hash output: name.bundle.XXXXXXXX.js / .css
_BUNDLE_RE = re.compile(r"^(.+)\.bundle\.[A-Z0-9]{8}\.(js|css)$")


class GetAppCommand:
    def __init__(self, bench: Bench, repo: str, branch: str = "") -> None:
        from pathlib import PurePosixPath

        name = PurePosixPath(repo.rstrip("/")).name
        if name.endswith(".git"):
            name = name[:-4]

        self.bench = bench
        self.repo = repo
        self.name = name
        self.app = App(AppConfig(name=name, repo=repo, branch=branch), bench)

    def run(self) -> None:
        self._clone()
        self._install()
        self._register()
        self._build()
        print(f"\n'{self.name}' installed successfully.")

    def _clone(self) -> None:
        if self.app.is_cloned:
            print(f"'{self.name}' already cloned at {self.app.path}, skipping clone.")
        else:
            print(f"Cloning {self.name}...")
        sys.stdout.flush()
        if not self.app.is_cloned:
            self.app.clone()

    def _install(self) -> None:
        print(f"Installing {self.name}...")
        sys.stdout.flush()
        PythonEnvManager(self.bench).install_app(self.app)

    def _register(self) -> None:
        apps_txt = self.bench.sites_path / "apps.txt"
        existing = apps_txt.read_text().splitlines() if apps_txt.exists() else []
        if self.name not in existing:
            apps_txt.write_text("\n".join(existing + [self.name]) + "\n")

    def _build(self) -> None:
        app_dir = self.bench.path / "apps" / self.name
        # Frappe apps follow the convention: apps/{name}/{name}/public/
        app_public_dir = app_dir / self.name / "public"
        dist_dir = app_public_dir / "dist"

        if self._has_prebuilt_assets(dist_dir):
            print(f"\nPre-built assets found for {self.name} — linking without rebuild...")
            sys.stdout.flush()
            self._setup_prebuilt_assets(app_public_dir, dist_dir)
            return

        if (app_dir / "package.json").exists():
            print(f"\nInstalling JS dependencies for {self.name}...")
            sys.stdout.flush()
            subprocess.run(["yarn", "install"], cwd=str(app_dir), check=False)

        print(f"\nBuilding assets...")
        sys.stdout.flush()
        subprocess.run(
            [*self.bench.frappe_call, "frappe", "build", "--force"],
            cwd=str(self.bench.sites_path),
            check=False,
        )

    # ------------------------------------------------------------------
    # Pre-built asset helpers
    # ------------------------------------------------------------------

    def _has_prebuilt_assets(self, dist_dir: Path) -> bool:
        js_dir = dist_dir / "js"
        return js_dir.is_dir() and any(
            f for f in js_dir.iterdir()
            if _BUNDLE_RE.match(f.name)
        )

    def _setup_prebuilt_assets(self, app_public_dir: Path, dist_dir: Path) -> None:
        """Wire up pre-built dist/ into sites/assets/ without running esbuild.

        Creates the symlink sites/assets/{app}/ -> apps/{app}/{app}/public/
        and generates assets.json / assets-rtl.json from the dist file names.
        """
        assets_dir = self.bench.sites_path / "assets"
        assets_dir.mkdir(exist_ok=True)

        # sites/assets/{app}/ -> apps/{app}/{app}/public/
        app_link = assets_dir / self.name
        if app_link.is_symlink():
            app_link.unlink()
        elif app_link.is_dir():
            shutil.rmtree(str(app_link))
        app_link.symlink_to(app_public_dir.resolve())

        self._write_assets_json(dist_dir, assets_dir)

        print(f"  Linked {app_link} -> {app_public_dir.resolve()}")

    def _write_assets_json(self, dist_dir: Path, assets_dir: Path) -> None:
        app_name = self.name
        assets: dict[str, str] = {}
        rtl_assets: dict[str, str] = {}

        # JS bundles
        js_dir = dist_dir / "js"
        if js_dir.is_dir():
            for f in sorted(js_dir.iterdir()):
                m = _BUNDLE_RE.match(f.name)
                if m and m.group(2) == "js":
                    assets[f"{m.group(1)}.bundle.js"] = (
                        f"/assets/{app_name}/dist/js/{f.name}"
                    )

        # LTR CSS bundles
        css_dir = dist_dir / "css"
        if css_dir.is_dir():
            for f in sorted(css_dir.iterdir()):
                m = _BUNDLE_RE.match(f.name)
                if m and m.group(2) == "css":
                    assets[f"{m.group(1)}.bundle.css"] = (
                        f"/assets/{app_name}/dist/css/{f.name}"
                    )

        # RTL CSS bundles (separate JSON file)
        rtl_dir = dist_dir / "css-rtl"
        if rtl_dir.is_dir():
            for f in sorted(rtl_dir.iterdir()):
                m = _BUNDLE_RE.match(f.name)
                if m and m.group(2) == "css":
                    rtl_assets[f"rtl_{m.group(1)}.bundle.css"] = (
                        f"/assets/{app_name}/dist/css-rtl/{f.name}"
                    )

        self._merge_json(assets_dir / "assets.json", assets)
        if rtl_assets:
            self._merge_json(assets_dir / "assets-rtl.json", rtl_assets)

    @staticmethod
    def _merge_json(path: Path, new_entries: dict) -> None:
        existing: dict = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except json.JSONDecodeError:
                pass
        existing.update(new_entries)
        path.write_text(json.dumps(existing, indent="\t", sort_keys=True) + "\n")
