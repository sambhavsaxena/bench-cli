from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_TS_RE = re.compile(r"^(\d{8}_\d{6})")


@dataclass
class BackupFile:
    filename: str
    path: str
    size_bytes: int
    created_at: datetime
    kind: str  # 'database' | 'public-file' | 'private-file' | 'site_config'
    timestamp: str


@dataclass
class BackupSet:
    timestamp: str
    created_at: datetime
    files: list[BackupFile]


class BackupReader:
    def __init__(self, bench_root: Path, site_name: str) -> None:
        self._backups_dir = bench_root / "sites" / site_name / "private" / "backups"

    def read_all(self) -> list[BackupSet]:
        if not self._backups_dir.is_dir():
            return []

        by_ts: dict[str, list[BackupFile]] = {}
        for f in self._backups_dir.iterdir():
            if not f.is_file():
                continue
            bf = self._parse_file(f)
            by_ts.setdefault(bf.timestamp, []).append(bf)

        result = []
        for ts in sorted(by_ts, reverse=True):
            files = sorted(by_ts[ts], key=lambda f: f.kind)
            result.append(BackupSet(timestamp=ts, created_at=files[0].created_at, files=files))
        return result

    def _parse_file(self, path: Path) -> BackupFile:
        name = path.name
        m = _TS_RE.match(name)
        ts = m.group(1) if m else "unknown"

        try:
            created_at = datetime.strptime(ts, "%Y%m%d_%H%M%S")
        except ValueError:
            created_at = datetime.fromtimestamp(path.stat().st_mtime)

        if "private-files" in name:
            kind = "private-file"
        elif "files" in name:
            kind = "public-file"
        elif "database" in name:
            kind = "database"
        else:
            kind = "site_config"

        return BackupFile(filename=name, path=str(path), size_bytes=path.stat().st_size, created_at=created_at, kind=kind, timestamp=ts)
