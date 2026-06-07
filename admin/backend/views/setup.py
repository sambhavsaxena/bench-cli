from __future__ import annotations

import tomllib
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from admin.backend.tasks.manager.task_reader import TaskReader
from admin.backend.tasks.manager.task_runner import TaskRunner
from bench_cli.config.bench_toml_builder import BenchTomlBuilder

setup_bp = Blueprint("setup", __name__)


@setup_bp.route("/config")
def get_config():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    return jsonify(_read_defaults(bench_root))


@setup_bp.route("/save", methods=["POST"])
def save_config():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    data = request.get_json(silent=True) or {}

    error = _validate(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    settings = {**data, "admin_enabled": True}
    content = BenchTomlBuilder(_current_name(bench_root), settings).render()
    (bench_root / "bench.toml").write_text(content)
    return jsonify({"ok": True})


def _validate(data: dict) -> str | None:
    for field in ("mariadb_password", "admin_password"):
        if not data.get(field):
            return f"{field} is required"
    if data.get("volume_enabled"):
        for field in ("volume_pool", "volume_device"):
            if not data.get(field):
                return f"{field} is required when volume management is enabled"
    return None


@setup_bp.route("/init", methods=["POST"])
def start_init():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    data = request.get_json(silent=True) or {}
    args = {}
    if data.get("sudo_password"):
        args["sudo_password"] = data["sudo_password"]
    try:
        task_id = TaskRunner(bench_root).run("bench-init", args)
        return jsonify({"ok": True, "task_id": task_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@setup_bp.route("/new-site", methods=["POST"])
def start_new_site():
    bench_root = Path(current_app.config["BENCH_ROOT"])
    data = request.get_json(silent=True) or {}
    if not data.get("name"):
        return jsonify({"ok": False, "error": "Site name is required"}), 400

    args = {"name": data["name"]}
    if data.get("admin_password"):
        args["admin_password"] = data["admin_password"]
    try:
        task_id = TaskRunner(bench_root).run("new-site", args)
        return jsonify({"ok": True, "task_id": task_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@setup_bp.route("/stream/<task_id>")
def stream_task(task_id: str):
    bench_root = Path(current_app.config["BENCH_ROOT"])
    reader = TaskReader(bench_root)

    def generate():
        for line in reader.stream_output(task_id):
            if line.startswith("__DONE__:"):
                yield f"event: done\ndata: {line[9:]}\n\n"
            else:
                yield f"data: {line}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


def _default_config(bench_root: Path) -> dict:
    return {
        "bench_name": bench_root.name,
        "python": "3.14",
        "mariadb_password": "root",
        "admin_password": "",
        "app_repo": "https://github.com/frappe/frappe",
        "app_branch": "version-16",
        "http_port": 8000,
        "socketio_port": 9000,
        "redis_port": 13000,
        "workers_default": 2,
        "workers_short": 1,
        "workers_long": 1,
        "volume_enabled": False,
        "volume_pool": "",
        "volume_device": "",
        "volume_benches_reservation": "10G",
        "volume_benches_quota": "50G",
        "volume_mariadb_reservation": "5G",
        "volume_mariadb_quota": "20G",
        "volume_mariadb_data_dir": "/var/lib/mysql",
        "volume_snapshots_enabled": False,
    }


def _read_defaults(bench_root: Path) -> dict:
    defaults = _default_config(bench_root)
    toml_path = bench_root / "bench.toml"
    if not toml_path.exists():
        return defaults
    try:
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        defaults.update(_read_general(data, defaults))
        defaults.update(_read_volume(data.get("volume", {}), defaults))
    except Exception:
        pass
    return defaults


def _read_general(data: dict, defaults: dict) -> dict:
    bench = data.get("bench", {})
    app = (data.get("apps") or [{}])[0]
    return {
        "bench_name": bench.get("name", defaults["bench_name"]),
        "python": bench.get("python", defaults["python"]),
        "http_port": bench.get("http_port", defaults["http_port"]),
        "socketio_port": bench.get("socketio_port", defaults["socketio_port"]),
        "mariadb_password": data.get("mariadb", {}).get("root_password", defaults["mariadb_password"]),
        "admin_password": data.get("admin", {}).get("password", defaults["admin_password"]),
        "app_repo": app.get("repo", defaults["app_repo"]),
        "app_branch": app.get("branch", defaults["app_branch"]),
        "redis_port": data.get("redis", {}).get("port", defaults["redis_port"]),
        "workers_default": data.get("workers", {}).get("default", defaults["workers_default"]),
        "workers_short": data.get("workers", {}).get("short", defaults["workers_short"]),
        "workers_long": data.get("workers", {}).get("long", defaults["workers_long"]),
    }


def _read_volume(volume: dict, defaults: dict) -> dict:
    benches = volume.get("benches", {})
    mariadb = volume.get("mariadb", {})
    snapshots = volume.get("snapshots", {})
    return {
        "volume_enabled": volume.get("enabled", defaults["volume_enabled"]),
        "volume_pool": volume.get("pool", defaults["volume_pool"]),
        "volume_device": volume.get("device", defaults["volume_device"]),
        "volume_benches_reservation": benches.get("reservation", defaults["volume_benches_reservation"]),
        "volume_benches_quota": benches.get("quota", defaults["volume_benches_quota"]),
        "volume_mariadb_reservation": mariadb.get("reservation", defaults["volume_mariadb_reservation"]),
        "volume_mariadb_quota": mariadb.get("quota", defaults["volume_mariadb_quota"]),
        "volume_mariadb_data_dir": mariadb.get("data_dir", defaults["volume_mariadb_data_dir"]),
        "volume_snapshots_enabled": snapshots.get("enabled", defaults["volume_snapshots_enabled"]),
    }


def _current_name(bench_root: Path) -> str:
    toml_path = bench_root / "bench.toml"
    if not toml_path.exists():
        return bench_root.name
    try:
        with open(toml_path, "rb") as f:
            return tomllib.load(f).get("bench", {}).get("name", bench_root.name)
    except Exception:
        return bench_root.name
