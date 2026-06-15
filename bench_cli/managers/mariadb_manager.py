import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from bench_cli.config.mariadb_config import MariaDBConfig
from bench_cli.platform import get_package_manager, is_macos
from bench_cli.utils import run_command

_MACOS_SOCKET_CANDIDATES = ["/tmp/mysql.sock", "/usr/local/var/mysql/mysql.sock"]
_LINUX_SOCKET_CANDIDATES = ["/var/run/mysqld/mysqld.sock", "/run/mysqld/mysqld.sock"]

DEFAULT_VERSION = "11.8"
_REPO_SETUP_URL = "https://r.mariadb.com/downloads/mariadb_repo_setup"


class MariaDBManager:
    def __init__(self, config: MariaDBConfig) -> None:
        self.config = config

    def is_installed(self) -> bool:
        return bool(shutil.which("mysqld") or shutil.which("mariadbd"))

    def install(self) -> None:
        if self.is_installed():
            return
        package_manager = get_package_manager()
        if is_macos():
            package_manager.install(self._brew_package())
            return
        self._setup_apt_repo()
        package_manager.update()
        package_manager.install("mariadb-server", "mariadb-client")

    def start(self) -> None:
        if is_macos():
            run_command(["brew", "services", "start", self._brew_package()])
        else:
            run_command(["sudo", "systemctl", "start", "mariadb"])

    def stop(self) -> None:
        if is_macos():
            run_command(["brew", "services", "stop", self._brew_package()])
        else:
            run_command(["sudo", "systemctl", "stop", "mariadb"])

    def _version(self) -> str:
        return self.config.version or DEFAULT_VERSION

    def _brew_package(self) -> str:
        return self._installed_brew_formula() or f"mariadb@{self._version()}"

    def _installed_brew_formula(self) -> str | None:
        """Return the mariadb formula Homebrew already manages (e.g. 'mariadb@10.6').

        When bench.toml doesn't pin a version, start/stop must target whatever
        brew actually installed — assuming plain 'mariadb' fails when only a
        versioned formula like mariadb@10.6 is present.
        """
        result = subprocess.run(["brew", "list", "--formula"], capture_output=True, text=True)
        if result.returncode != 0:
            return None
        formulae = result.stdout.split()
        if "mariadb" in formulae:
            return "mariadb"
        return next((f for f in formulae if f.startswith("mariadb@")), None)

    def _setup_apt_repo(self) -> None:
        """Add MariaDB's official APT repository pinned to the target version.

        Ubuntu/Debian ship far older MariaDB than the 11.8 LTS series
        """
        script = subprocess.run(
            ["curl", "-LsS", _REPO_SETUP_URL],
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["sudo", "bash", "-s", "--", f"--mariadb-server-version=mariadb-{self._version()}"],
            input=script.stdout,
            check=True,
        )

    def kill_process(self, process_id: int) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("KILL %s", (process_id,))
        finally:
            connection.close()

    @contextmanager
    def snapshot_lock(self):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("FLUSH TABLES WITH READ LOCK")
            yield
        finally:
            with connection.cursor() as cursor:
                cursor.execute("UNLOCK TABLES")
            connection.close()

    def _connect(self):
        import pymysql

        return pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.admin_user,
            password=self.config.root_password,
            unix_socket=self._detect_socket() or None,
        )

    def _detect_socket(self) -> str:
        if self.config.socket_path:
            return self.config.socket_path
        candidates = _MACOS_SOCKET_CANDIDATES if is_macos() else _LINUX_SOCKET_CANDIDATES
        for path in candidates:
            if Path(path).exists():
                return path
        return ""
