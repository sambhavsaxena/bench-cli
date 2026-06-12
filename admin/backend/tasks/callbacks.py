import json
import os
import shutil
import subprocess


def new_site_failure_callback(meta: dict) -> None:
    site_name = meta["args"]["name"]
    site_path = os.path.join(meta["bench_root"], "sites", site_name)
    shutil.rmtree(site_path, ignore_errors=True)
    _remove_from_hosts(site_name)


def _remove_from_hosts(site_name: str) -> None:
    hosts_path = "/etc/hosts"
    entry = f"127.0.0.1 {site_name}"
    try:
        lines = open(hosts_path).read().splitlines()
    except OSError:
        return

    kept = [line for line in lines if entry not in line.split("#", 1)[0].split()]
    if len(kept) == len(lines):
        return

    subprocess.run(
        ["sudo", "tee", hosts_path],
        input=("\n".join(kept) + "\n").encode(),
        capture_output=True,
        check=False,
    )


def ssl_setup_failure_callback(meta: dict) -> None:
    site_name = meta["args"]["site"]
    config_path = os.path.join(meta["bench_root"], "sites", site_name, "site_config.json")
    config = json.loads(open(config_path).read())
    config["ssl"] = False
    open(config_path, "w").write(json.dumps(config, indent=1))
