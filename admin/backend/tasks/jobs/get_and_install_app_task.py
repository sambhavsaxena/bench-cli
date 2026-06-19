import subprocess
import sys

from bench_cli.commands.get_app import GetAppCommand
from .base_task import BaseTask


class GetAndInstallAppTask(BaseTask):
    @classmethod
    def _parser(cls):
        p = super()._parser()
        p.add_argument("site")
        p.add_argument("app")
        p.add_argument("repo")
        p.add_argument("--branch", default="")
        return p

    def __init__(self, bench, bench_root, args):
        super().__init__(bench, bench_root, args)
        self.site = args.site
        self.app = args.app
        self.repo = args.repo
        self.branch = args.branch

    def run(self) -> None:
        print(f"Fetching {self.app} from {self.repo}...")
        sys.stdout.flush()
        GetAppCommand(self.bench, self.repo, self.branch).run()

        sites_dir = self.bench_root / "sites"
        print(f"\nInstalling {self.app} into {self.site}...")
        sys.stdout.flush()
        result = subprocess.run(
            [*self.bench.frappe_call, "frappe", "--site", self.site, "install-app", self.app],
            cwd=str(sites_dir),
        )
        if result.returncode != 0:
            sys.exit(result.returncode)

        app = next((a for a in self.bench.apps() if a.config.name == self.app), None)
        if app:
            print(f"\nBuilding assets for {self.app}...")
            sys.stdout.flush()
            from bench_cli.managers.python_env_manager import PythonEnvManager
            PythonEnvManager(self.bench).build_assets_for_app(app)


if __name__ == "__main__":
    GetAndInstallAppTask.main()
