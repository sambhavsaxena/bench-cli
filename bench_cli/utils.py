import io
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from bench_cli.exceptions import BenchError, CommandError

if TYPE_CHECKING:
    from bench_cli.core.bench import BenchConfig


def iter_sibling_benches(bench_path: Path) -> Iterator[tuple[Path, "BenchConfig"]]:
    """Yield ``(bench_dir, parsed bench.toml)`` for every *other* bench that
    shares this bench's parent ``benches/`` directory.

    Parse-only (no validation) so half-configured benches are still seen.
    Skips ``bench_path`` itself and any directory without a readable
    ``bench.toml``. ``bench_path`` need not exist yet (e.g. during ``bench new``).
    """
    import tomllib

    from bench_cli.core.bench import BenchConfig

    parent = bench_path.parent
    if not parent.is_dir():
        return
    me = bench_path.resolve()
    for sibling in parent.iterdir():
        if not sibling.is_dir() or sibling.resolve() == me:
            continue
        toml_path = sibling / "bench.toml"
        if not toml_path.exists():
            continue
        try:
            # Parse-only (no validate) so half-configured siblings are still
            # seen — important for port-offset collision avoidance and
            # cross-bench hostname checks.
            yield sibling, BenchConfig._from_dict(tomllib.loads(toml_path.read_text()))
        except Exception:
            continue


def host_owner(bench_path: Path, host: str) -> Optional[str]:
    """Return the name of *another* bench that already claims ``host`` — either
    as one of its sites (``sites/<host>/``) or as its ``admin.domain`` — or
    ``None`` if the host is free across all sibling benches.

    Used to keep site names and admin domains unique across all benches served
    by the same nginx, so two benches can never fight over the same hostname.
    """
    if not host:
        return None
    for sibling, config in iter_sibling_benches(bench_path):
        if (sibling / "sites" / host / "site_config.json").exists():
            return config.name
        if config.admin.domain and config.admin.domain == host:
            return config.name
    return None


def write_toml(path: Path, data: dict) -> None:
    """Minimal TOML serialiser for the simple structures in bench.toml."""
    out = io.StringIO()

    def _write_value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return f'"{v}"'
        if isinstance(v, list):
            return "[" + ", ".join(_write_value(i) for i in v) + "]"
        return str(v)

    def _write_section(obj: dict, prefix: str = "") -> None:
        scalars = {k: v for k, v in obj.items() if not isinstance(v, (dict, list)) or (isinstance(v, list) and not any(isinstance(i, dict) for i in v))}
        dicts = {k: v for k, v in obj.items() if isinstance(v, dict)}
        array_of_tables = {k: v for k, v in obj.items() if isinstance(v, list) and any(isinstance(i, dict) for i in v)}

        for k, v in scalars.items():
            out.write(f"{k} = {_write_value(v)}\n")

        for k, v in dicts.items():
            out.write(f"\n[{prefix}{k}]\n")
            _write_section(v, prefix=f"{prefix}{k}.")

        for k, entries in array_of_tables.items():
            for entry in entries:
                out.write(f"\n[[{prefix}{k}]]\n")
                for ek, ev in entry.items():
                    out.write(f"{ek} = {_write_value(ev)}\n")

    _write_section(data)
    path.write_text(out.getvalue())


def get_yarn_bin() -> str:
    if yarn := shutil.which("yarn"):
        return yarn
    local_yarn = Path.home() / ".local" / "bin" / "yarn"
    if local_yarn.exists():
        return str(local_yarn)
    raise BenchError("yarn not found — run bench init to install it.")


def run_command(
    argv: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    stream_output: bool = False,
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=not stream_output,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode() if not stream_output and result.stderr else ""
        raise CommandError(
            f"Command {argv[0]!r} failed with exit code {result.returncode}.\n{stderr}".strip(),
            returncode=result.returncode,
        )
    return result
