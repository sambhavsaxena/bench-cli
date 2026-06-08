from __future__ import annotations

import subprocess
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from bench_cli.config.bench_config import BenchConfig
from bench_cli.config.toml_writer import bench_config_to_toml
from bench_cli.platform import is_linux

from ..validators import first_error, validate_email, validate_port, validate_worker_count

settings_bp = Blueprint("settings", __name__)

_RESTART_KEYS = {
    ("bench", "python"),
    ("bench", "http_port"),
    ("bench", "socketio_port"),
    ("mariadb", "host"),
    ("mariadb", "port"),
    ("mariadb", "admin_user"),
    ("mariadb", "socket_path"),
    ("redis", "cache_port"),
    ("redis", "queue_port"),
    ("redis", "socketio_port"),
    ("workers", "default"),
    ("workers", "short"),
    ("workers", "long"),
    ("production", "process_manager"),
}


def _needs_restart(old: dict, new: dict) -> bool:
    return any(old.get(s, {}).get(k) != new.get(s, {}).get(k) for s, k in _RESTART_KEYS)


def _non_admin_supervisor_programs(conf: Path, bench_name: str) -> list[str]:
    result = subprocess.run(
        ["supervisorctl", "-c", str(conf), "status", f"{bench_name}:*"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line.split()[0] for line in result.stdout.splitlines() if line.strip() and not line.split()[0].endswith("-admin")]


def _regenerate_configs(bench_root: Path, config: BenchConfig) -> None:
    from bench_cli.core.bench import Bench
    from bench_cli.managers.process_manager import ProcessManagerFactory
    from bench_cli.managers.redis_manager import RedisManager

    bench = Bench(config, bench_root)
    RedisManager(config.redis, bench).generate_configs()
    ProcessManagerFactory.create(bench).generate_config()


def _restart_supervisor(manager, bench_name: str) -> tuple[bool, str | None]:
    if not manager.is_alive():
        return False, None
    subprocess.run([*manager._supervisorctl(), "reread"], capture_output=True, timeout=10)
    subprocess.run([*manager._supervisorctl(), "update"], capture_output=True, timeout=10)
    programs = _non_admin_supervisor_programs(manager.supervisor_conf_path, bench_name)
    if not programs:
        return False, None
    result = subprocess.run([*manager._supervisorctl(), "restart", *programs], capture_output=True, text=True, timeout=30)
    return (result.returncode == 0), (result.stderr or result.stdout if result.returncode != 0 else None)


def _restart_systemd(manager) -> tuple[bool, str | None]:
    if not manager.is_running():
        return False, None
    env = manager._systemctl_env()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, env=env, timeout=10)
    non_admin_units = [manager._unit_name(pd.name) for pd in manager._prod_process_definitions() if pd.name != "admin"]
    if not non_admin_units:
        return False, None
    result = subprocess.run([*manager._systemctl(), "restart", *non_admin_units], capture_output=True, text=True, timeout=60, env=env)
    return (result.returncode == 0), (result.stderr or result.stdout if result.returncode != 0 else None)


def _do_restart(bench_root: Path, config: BenchConfig) -> tuple[bool, str | None]:
    from bench_cli.core.bench import Bench
    from bench_cli.managers.process_manager import ProcessManagerFactory
    from bench_cli.managers.supervisor_process_manager import SupervisorProcessManager
    from bench_cli.managers.systemd_process_manager import SystemdProcessManager

    bench = Bench(config, bench_root)
    manager = ProcessManagerFactory.detect_running(bench)
    if isinstance(manager, SupervisorProcessManager):
        return _restart_supervisor(manager, config.name)
    if isinstance(manager, SystemdProcessManager):
        return _restart_systemd(manager)
    return False, None


def _config_snapshot(config: BenchConfig) -> dict:
    return {
        "bench": {"python": config.python_version, "http_port": config.http_port, "socketio_port": config.socketio_port},
        "mariadb": {"host": config.mariadb.host, "port": config.mariadb.port, "admin_user": config.mariadb.admin_user, "socket_path": config.mariadb.socket_path},
        "redis": {"cache_port": config.redis.cache_port, "queue_port": config.redis.queue_port, "socketio_port": config.redis.socketio_port},
        "workers": {"default": config.workers.default_count, "short": config.workers.short_count, "long": config.workers.long_count},
        "production": {"process_manager": config.production.process_manager},
    }


def _build_settings_response(config: BenchConfig) -> dict:
    m, r, n, le, v = config.mariadb, config.redis, config.nginx, config.letsencrypt, config.volume
    return {
        "is_linux": is_linux(),
        "bench": {"name": config.name, "python": config.python_version, "http_port": config.http_port, "socketio_port": config.socketio_port},
        "mariadb": {"host": m.host, "port": m.port, "admin_user": m.admin_user, "socket_path": m.socket_path, "version": m.version or ""},
        "redis": {"cache_port": r.cache_port, "queue_port": r.queue_port, "socketio_port": r.socketio_port, "version": r.version or ""},
        "workers": {"default": config.workers.default_count, "short": config.workers.short_count, "long": config.workers.long_count},
        "nginx": {"http_port": n.http_port, "https_port": n.https_port, "config_dir": str(n.config_dir), "worker_processes": n.worker_processes, "client_max_body_size": n.client_max_body_size},
        "letsencrypt": {"email": le.email, "webroot_path": str(le.webroot_path)},
        "production": {"process_manager": config.production.process_manager, "nginx": config.production.nginx},
        "volume": {
            "enabled": v.enabled,
            "pool": v.pool,
            "device": v.device,
            "benches_reservation": v.benches.reservation,
            "benches_quota": v.benches.quota,
            "mariadb_reservation": v.mariadb.reservation,
            "mariadb_quota": v.mariadb.quota,
            "mariadb_data_dir": v.mariadb.data_dir,
            "snapshots_enabled": v.snapshots.enabled,
        },
    }


class SettingsApplier:
    def __init__(self, config: BenchConfig, data: dict) -> None:
        self.config = config
        self.data = data

    def apply(self) -> str | None:
        self._apply_bench()
        self._apply_mariadb()
        self._apply_redis()
        self._apply_workers()
        self._apply_nginx()
        self._apply_letsencrypt()
        self._apply_volume()
        return self._apply_production() or self._validate()

    def _apply_bench(self) -> None:
        d = self.data.get("bench", {})
        if "python" in d:
            self.config.python_version = str(d["python"])
        if "http_port" in d:
            self.config.http_port = int(d["http_port"])
        if "socketio_port" in d:
            self.config.socketio_port = int(d["socketio_port"])

    def _apply_mariadb(self) -> None:
        d = self.data.get("mariadb", {})
        if not d:
            return
        m = self.config.mariadb
        m.host = str(d.get("host", m.host))
        m.port = int(d.get("port", m.port))
        m.admin_user = str(d.get("admin_user", m.admin_user))
        m.socket_path = str(d.get("socket_path", m.socket_path))
        m.version = str(d.get("version", "")).strip() or None

    def _apply_redis(self) -> None:
        d = self.data.get("redis", {})
        if not d:
            return
        r = self.config.redis
        r.cache_port = int(d.get("cache_port", r.cache_port))
        r.queue_port = int(d.get("queue_port", r.queue_port))
        r.socketio_port = int(d.get("socketio_port", r.socketio_port))
        r.version = str(d.get("version", "")).strip() or None

    def _apply_workers(self) -> None:
        d = self.data.get("workers", {})
        if not d:
            return
        w = self.config.workers
        w.default_count = int(d.get("default", w.default_count))
        w.short_count = int(d.get("short", w.short_count))
        w.long_count = int(d.get("long", w.long_count))

    def _apply_nginx(self) -> None:
        d = self.data.get("nginx", {})
        if not d:
            return
        n = self.config.nginx
        n.http_port = int(d.get("http_port", n.http_port))
        n.https_port = int(d.get("https_port", n.https_port))
        if "config_dir" in d:
            n.config_dir = Path(str(d["config_dir"]))
        n.worker_processes = str(d.get("worker_processes", n.worker_processes))
        n.client_max_body_size = str(d.get("client_max_body_size", n.client_max_body_size))

    def _apply_letsencrypt(self) -> None:
        d = self.data.get("letsencrypt", {})
        if not d:
            return
        le = self.config.letsencrypt
        le.email = str(d.get("email", le.email))
        if "webroot_path" in d:
            le.webroot_path = Path(str(d["webroot_path"]))

    def _apply_volume(self) -> None:
        d = self.data.get("volume", {})
        if not d:
            return
        vol = self.config.volume
        vol.benches.reservation = str(d.get("benches_reservation", vol.benches.reservation))
        vol.benches.quota = str(d.get("benches_quota", vol.benches.quota))
        vol.mariadb.reservation = str(d.get("mariadb_reservation", vol.mariadb.reservation))
        vol.mariadb.quota = str(d.get("mariadb_quota", vol.mariadb.quota))
        vol.mariadb.data_dir = str(d.get("mariadb_data_dir", vol.mariadb.data_dir))
        vol.snapshots.enabled = bool(d.get("snapshots_enabled", vol.snapshots.enabled))

    def _apply_production(self) -> str | None:
        d = self.data.get("production", {})
        if not d:
            return None
        p = self.config.production
        if "process_manager" in d:
            pm = str(d["process_manager"])
            if pm not in ("none", "supervisor", "systemd"):
                return "process_manager must be none, supervisor, or systemd"
            p.process_manager = pm
        p.nginx = bool(d.get("nginx", p.nginx))
        return None

    def _validate(self) -> str | None:
        c = self.config
        return first_error(
            validate_port(c.http_port, "HTTP Port"),
            validate_port(c.socketio_port, "SocketIO Port"),
            validate_port(c.mariadb.port, "MariaDB Port"),
            validate_port(c.redis.cache_port, "Redis Cache Port"),
            validate_port(c.redis.queue_port, "Redis Queue Port"),
            validate_port(c.redis.socketio_port, "Redis SocketIO Port"),
            validate_port(c.nginx.http_port, "Nginx HTTP Port"),
            validate_port(c.nginx.https_port, "Nginx HTTPS Port"),
            validate_worker_count(c.workers.default_count, "Default workers"),
            validate_worker_count(c.workers.short_count, "Short workers"),
            validate_worker_count(c.workers.long_count, "Long workers"),
            validate_email(c.letsencrypt.email),
        )


@settings_bp.route("/")
def get_settings():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    try:
        config = BenchConfig.from_file(bench_root / "bench.toml")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(_build_settings_response(config))


@settings_bp.route("/", methods=["PATCH"])
def update_settings():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    data = request.get_json(silent=True) or {}
    try:
        config = BenchConfig.from_file(bench_root / "bench.toml")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    old_snapshot = _config_snapshot(config)
    err = SettingsApplier(config, data).apply()
    if err:
        return jsonify({"ok": False, "error": err}), 400

    try:
        config.validate()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    try:
        (bench_root / "bench.toml").write_text(bench_config_to_toml(config))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to write config: {e}"}), 500

    restarted, restart_error = False, None
    if _needs_restart(old_snapshot, _config_snapshot(config)):
        try:
            _regenerate_configs(bench_root, config)
        except Exception as e:
            return jsonify({"ok": False, "error": f"Failed to regenerate configs: {e}"}), 500
        restarted, restart_error = _do_restart(bench_root, config)

    return jsonify({"ok": True, "restarted": restarted, "restart_error": restart_error})
