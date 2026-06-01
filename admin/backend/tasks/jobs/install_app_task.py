import subprocess
import sys

from .base_task import BaseTask


class InstallAppTask(BaseTask):
    @classmethod
    def _parser(cls):
        p = super()._parser()
        p.add_argument("site")
        p.add_argument("app")
        return p

    def __init__(self, bench, bench_root, args):
        super().__init__(bench, bench_root, args)
        self.site = args.site
        self.app = args.app

    def run(self) -> None:
        sites_dir = self.bench_root / "sites"

        print(f"Installing {self.app} into {self.site}...")
        sys.stdout.flush()
        result = subprocess.run(
            [*self.bench.frappe_call, "frappe", "--site", self.site, "install-app", self.app],
            cwd=str(sites_dir),
        )
        if result.returncode != 0:
            sys.exit(result.returncode)

        app_dir = self.bench_root / "apps" / self.app
        if (app_dir / "package.json").exists():
            print(f"\nInstalling JS dependencies for {self.app}...")
            sys.stdout.flush()
            subprocess.run(["yarn", "install"], cwd=str(app_dir), check=False)

        print("\nBuilding assets...")
        sys.stdout.flush()
        subprocess.run([*self.bench.frappe_call, "frappe", "build", "--force"], cwd=str(sites_dir))


if __name__ == "__main__":
    InstallAppTask.main()
