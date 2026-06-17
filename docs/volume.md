# Volume Management

bench manages all storage on ZFS. On Linux every bench gets a ZFS pool — volume setup is a mandatory part of `bench init` (macOS is dev-only and skips it). A single ZFS pool is created and separate datasets are carved out for bench data and MariaDB data — each with configurable quotas and reservations.

The pool can be backed three ways, selected by `volume.backing`:

- **`backing = "device"`** — a dedicated block device (`/dev/sdb`). Best performance; use this when a spare disk or attached volume is available.
- **`backing = "image"`** — a preallocated image file on the root filesystem (default `/var/lib/bench-zfs/<pool>.img`), used as a file vdev. For machines **without a spare disk**: everything above the vdev (datasets, quotas, reservations, snapshots) works identically. Slightly lower performance than a dedicated device since ZFS sits on top of the existing filesystem — fine for dev and small setups.
- **`backing = "auto"`** — let `bench init` decide. An unused disk is auto-discovered and used as device backing; if none exists, image backing is used. Quotas and reservations are derived from the backing size. See [Auto backing](#auto-backing-discovery-and-smart-sizing) below.

The image file is always **preallocated** with `fallocate` (never sparse), so the pool can't be corrupted later by the root filesystem filling up — setup fails fast instead if the space isn't there.

---

## Auto backing — discovery and smart sizing

The minimal hands-off config:

```toml
[volume]
pool = "bench-pool"
backing = "auto"
```

During `bench init`, the volume setup step resolves `auto` to a concrete backing and **persists the resolved values back to `bench.toml`**, so the settings UI and re-runs see real values.

**Device discovery** (`lsblk -J -b`): a disk qualifies as *unused* when it is a whole disk (`type = disk`), writable, has **no partitions**, **no filesystem signature** (excludes `zfs_member`, `LVM2_member`, `linux_raid_member`, ext4, ...), **nothing mounted**, and is at least 10G. The largest qualifying disk wins — e.g. a freshly attached EBS volume. The root disk never qualifies (it has mounted partitions).

**Smart sizing** (also used by the setup wizard's prefilled defaults):

| Value | Default |
|---|---|
| Image size (no spare disk) | 75% of rootfs free space, min 10G |
| `benches.quota` | 60% of backing size |
| `mariadb.quota` | 40% of backing size |
| `benches.reservation` | 10% of backing size |
| `mariadb.reservation` | 5% of backing size |

Quotas use a strict 60/40 split (no overcommit) so a full benches dataset can never starve MariaDB. All values are floored to whole gigabytes (min 1G).

> **Auto backing implies auto sizing.** With `backing = "auto"`, quotas and reservations are always recomputed from the resolved backing — set `backing = "device"` or `"image"` explicitly if you want manual control over sizes.

---

## Design constraints

- **Mandatory on Linux.** Every bench runs on ZFS — there is no off switch. Machines without a spare disk use a disk image on the root filesystem (`backing = "image"` or `"auto"`). macOS (dev only) skips volume setup entirely.
- **One pool, two datasets.** A single ZFS pool on one backing (disk or image file) holds two datasets: one for bench directories (`<pool>/benches`) and one for MariaDB data (`<pool>/mariadb`). This keeps data locality simple and snapshotting independent per concern.
- **Quotas and reservations from bench.toml.** Space limits and guarantees are declared in `bench.toml` — no manual `zfs set` commands needed.
- **Snapshot support.** ZFS datasets can be snapshotted on demand via `bench volume snapshot`. This is a building block for backup workflows; scheduling is left to the operator (cron, etc.).
- **Linux only.** ZFS volume management targets Ubuntu/Linux servers. `VolumeSetupCommand` exits with a clear error on macOS.
- **No pool destruction.** bench will never destroy a ZFS pool or rollback a dataset without an explicit user-confirmed command. All destructive operations require `--yes`.
- **Runs once during `bench init`.** Volume setup is not idempotent by design. It runs as part of `bench init` on Linux and is not intended to be re-run.

---

## bench.toml additions

```toml
# ── Volume (ZFS, mandatory on Linux) ────────────────────────────────────────────────
[volume]
pool = "bench-pool"        # ZFS pool name (created if it does not exist)
backing = "device"         # "device" (dedicated disk) | "image" (file on root FS) | "auto" (discover)
device = "/dev/sdb"        # block device to create the pool on (backing = "device")
                           # ignored if the pool already exists

[volume.image]             # only read when backing = "image"
size = "60G"               # preallocated size of the image file (fallocate)
# path = "/var/lib/bench-zfs/bench-pool.img"   # optional, this is the default

[volume.benches]
reservation = "10G"        # guaranteed space for bench directories
quota = "50G"              # hard cap on bench directory space

[volume.mariadb]
reservation = "5G"         # guaranteed space for MariaDB data files
quota = "20G"              # hard cap on MariaDB data space
data_dir = "/var/lib/mysql" # path MariaDB reads/writes its data files
                            # bench remounts the dataset here via zfs set mountpoint
```

> **Per-bench instances.** When a bench has its own MariaDB instance
> (`mariadb.instance` set — the `bench new` default on Linux), its `mariadb`
> dataset mounts at the instance datadir `/var/lib/mysql-<instance>` instead of
> the shared `/var/lib/mysql`. This is what makes snapshots and rollbacks
> bench-independent — see
> [Per-bench MariaDB instances](architecture.md#per-bench-mariadb-instances).
> Shared-server benches (no `instance`) keep using `/var/lib/mysql` as below.

### Validation

On every config load:
- `volume.pool` must be a non-empty string.
- `volume.backing` must be `"device"`, `"image"`, or `"auto"`.
- `backing = "auto"` → no other backing fields required; everything is resolved at `bench init` time.
- `backing = "device"` → `volume.device` is required.
- `backing = "image"` → `volume.image.size` is required (valid ZFS size); `volume.image.path`, if set, must be absolute. Before setup, the root filesystem must have enough free space to preallocate the image.
- All sizes (`reservation`, `quota`, `image.size`) must be positive integers with an optional `K`/`M`/`G`/`T` suffix (e.g. `"10G"`, `"512M"`) — no decimals, negatives, or zero.
- Reservations cannot exceed their dataset's quota, and no quota/reservation may exceed the backing size (device size or image size).
- `volume.mariadb.data_dir` must be an absolute path.
- The image path must **not** live under `benches/` or the MariaDB data dir — the pool mounts over those paths.

---

## Package layout additions

```
bench_cli/
├── config/
│   └── volume_config.py      # VolumeConfig, BenchesDatasetConfig, MariaDBDatasetConfig
│
├── commands/
│   └── volume.py             # VolumeSetupCommand, VolumeStatusCommand,
│                             # VolumeSnapshotCommand, VolumeListSnapshotsCommand,
│                             # VolumeDestroySnapshotCommand
│
└── managers/
    └── volume_manager.py     # VolumeManager, SnapshotInfo
```

---

## Config dataclasses

```python
@dataclass
class BenchesDatasetConfig:
    reservation: str = "10G"
    quota: str = "50G"

@dataclass
class MariaDBDatasetConfig:
    reservation: str = "5G"
    quota: str = "20G"
    data_dir: str = "/var/lib/mysql"

@dataclass
class VolumeConfig:
    pool: str = "bench-pool"
    backing: str = "auto"  # "device" | "image" | "auto"
    device: str = ""
    image: ImageConfig = field(default_factory=ImageConfig)
    benches: BenchesDatasetConfig = field(default_factory=BenchesDatasetConfig)
    mariadb: MariaDBDatasetConfig = field(default_factory=MariaDBDatasetConfig)

    @property
    def benches_dataset(self) -> str:
        return f"{self.pool}/benches"

    @property
    def mariadb_dataset(self) -> str:
        return f"{self.pool}/mariadb"
```

`VolumeConfig` is added to `BenchConfig`:

```python
@dataclass
class BenchConfig:
    ...
    volume: VolumeConfig = field(default_factory=VolumeConfig)
```

---

## `VolumeManager`

All ZFS operations go through `VolumeManager`. It runs `zfs` and `zpool` as subprocesses — no Python ZFS library needed. ZFS is installed automatically via the system package manager if not already present.

```python
class VolumeManager:
    def __init__(self, config: VolumeConfig): ...

    # Pool lifecycle

    def pool_exists(self) -> bool: ...

    def create_pool(self) -> None:
        """zpool create <pool> <vdev> — skipped if pool already exists.

        vdev is the block device (backing = "device") or the preallocated
        image file, created via fallocate if missing (backing = "image").
        """

    # Dataset lifecycle

    def dataset_exists(self, dataset: str) -> bool: ...

    def create_dataset(self, dataset: str) -> None:
        """zfs create <dataset> — skipped if already exists."""

    def set_quota(self, dataset: str, quota: str) -> None:
        """zfs set quota=<quota> <dataset>"""

    def set_reservation(self, dataset: str, reservation: str) -> None:
        """zfs set reservation=<reservation> <dataset>"""

    # Mount helpers

    def get_mountpoint(self, dataset: str) -> Path:
        """Return the current mountpoint via zfs get -H -o value mountpoint <dataset>."""

    def set_mountpoint(self, dataset: str, target: Path) -> None:
        """
        Remount the dataset at target via: zfs set mountpoint=<target> <dataset>
        Creates target directory if it does not exist.
        ZFS persists the mountpoint natively — no /etc/fstab entry needed.
        """

    # Data migration

    def migrate_data(self, source: Path, dataset: str) -> None:
        """
        rsync source → ZFS auto-mount, then remount the dataset at source.
        Used for directories owned by other users that cannot be renamed
        (e.g. /var/lib/mysql owned by the mysql system user).
        The original files remain on the root FS hidden under the ZFS overlay.
        """

    def migrate_dir(self, source: Path, dataset: str) -> None:
        """
        mv source → source.migration (same-FS rename, instant)
        zfs set mountpoint=source
        rsync source.migration → source
        rm -rf source.migration
        Used for directories we own and can freely rename and delete (e.g. benches/).
        Leaves zero leftover files on the root FS.
        """

    # Snapshots

    def snapshot(self, dataset: str, tag: str) -> None:
        """zfs snapshot <dataset>@<tag>"""

    def list_snapshots(self, dataset: str) -> list[SnapshotInfo]:
        """zfs list -t snapshot — returns list of SnapshotInfo sorted oldest-first."""

    def destroy_snapshot(self, dataset: str, tag: str) -> None:
        """zfs destroy <dataset>@<tag> — raises VolumeError if snapshot does not exist."""

    # High-level setup

    def setup(self) -> None:
        """
        Create the pool and both datasets with their quotas and reservations.
        Does not migrate data or set mountpoints — that is handled by VolumeSetupCommand.
        """
```

```python
@dataclass
class SnapshotInfo:
    name: str          # e.g. "bench-pool/benches@20250528-140000"
    dataset: str       # "bench-pool/benches"
    snapshot_tag: str  # "20250528-140000"
    created_at: datetime
    used_bytes: int
```

---

## Data migration strategies

When `bench init` runs on Linux, it must move existing data from the root filesystem into the ZFS datasets before mounting. Two strategies are used depending on who owns the directory:

### MariaDB — rsync + ZFS overlay (`migrate_data`)

`/var/lib/mysql` is owned by the `mysql` system user and is under an AppArmor profile that blocks `rename()` on the directory itself even as root. Instead:

1. `manager.setup()` creates the dataset; ZFS auto-mounts it at `/<pool>/mariadb`.
2. MariaDB is stopped (`systemctl stop mariadb`).
3. `rsync -a /var/lib/mysql/ /<pool>/mariadb/` copies all data file-by-file (root can read any file).
4. `zfs set mountpoint=/var/lib/mysql <pool>/mariadb` remounts the dataset at the original path.
5. MariaDB is started (`systemctl start mariadb`).

The original files under `/var/lib/mysql` remain on the root FS hidden under the ZFS overlay mount. This is an accepted trade-off: data is minimal during `bench init`, and the hidden files waste a negligible amount of root FS space.

We also need to ensure the recordsize during mariadb dataset creation is mariadb friendly for maximum efficiency, will do that in the coming PRs.

### Benches — move + rsync + cleanup (`migrate_dir`)

`bench_cli_root/benches/` is owned by the frappe user, so it can be freely renamed:

1. `mv benches/ benches.migration/` — instant same-filesystem rename.
2. `zfs set mountpoint=benches/ <pool>/benches` — ZFS mounts the dataset at the original path.
3. `rsync -a benches.migration/ benches/` — copies data into ZFS.
4. `rm -rf benches.migration/` — removes the backup, leaving zero leftover files on the root FS.

The ZFS dataset mounts at `bench_cli_root/benches/` — the exact path `find_bench_root()` already scans — so no symlinks or path changes are needed anywhere else in the CLI.

---

## Integration with `bench init`

On Linux, `InitCommand` runs `VolumeSetupCommand` as step 3, immediately after installing system packages (which installs and starts MariaDB so its data directory exists) and before `Bench.create_directories()` (so all subsequent directory creation lands on ZFS).

```
1.  Validate bench.toml
2.  Install system packages          ← MariaDB installed and started here
3.  [Linux] Set up ZFS volumes
      • manager.setup()              — create pool + datasets
      • setup_mariadb()              — migrate_data + restart MariaDB
      • setup_benches()              — migrate_dir
4.  Create bench directory structure  ← runs on ZFS from this point
5.  Create Python virtualenv
...
```

---

## CLI commands

### `bench volume status`

Displays current pool and dataset state.

```bash
bench volume status
```

Output:

```
Pool       bench-pool            ONLINE  size=100G  free=87G
Dataset    bench-pool/benches    quota=50G  reservation=10G  used=3.2G  avail=46G
Dataset    bench-pool/mariadb    quota=20G  reservation=5G   used=1.8G  avail=18G
```

### `bench volume snapshot`

Creates a timestamped snapshot of one or both datasets.

```bash
bench volume snapshot                    # snapshot both datasets
bench volume snapshot --dataset benches  # snapshot bench data only
bench volume snapshot --dataset mariadb  # snapshot MariaDB data only
```

Snapshot tags are generated as `YYYYMMDD-HHMMSS`. Snapshots are always available — no configuration needed.

### `bench volume list-snapshots`

Lists all snapshots for a dataset.

```bash
bench volume list-snapshots
bench volume list-snapshots --dataset benches
```

Output:

```
Dataset: bench-pool/benches
  20250528-140000               created: 2025-05-28 14:00:00  used: 124M
  20250527-020000               created: 2025-05-27 02:00:00  used: 98M
```

### `bench volume destroy-snapshot`

Destroys a named snapshot. Requires `--yes` to confirm.

```bash
bench volume destroy-snapshot 20250527-020000 --dataset benches --yes
```

---

## Live quota and reservation changes

Quotas and reservations can be updated at any time via the **ZFS Volume** tab in the admin Settings modal — no bench restart required. The change is applied in two steps:

1. **Validate** — before writing `bench.toml`, the new quota is compared against the dataset's current used bytes (`zfs get -H -p -o value used <dataset>`). If the new quota would be less than the used size, the request is rejected with an error and nothing is written.

   > Setting a quota below the current used size does not make ZFS refuse the command, but it immediately blocks all further writes to the dataset. MariaDB would receive "Got error 28 from storage engine" and crash. The validation step prevents this.

2. **Apply** — after `bench.toml` is written, `zfs set quota=<value> <dataset>` and `zfs set reservation=<value> <dataset>` are run for any values that changed. If the ZFS commands fail (e.g. device is full, dataset does not exist), the error is returned in the API response alongside `"ok": true` — the TOML has already been saved.

The quota validation is implemented in `VolumeManager.validate_quota(dataset, quota)`:

```python
def validate_quota(self, dataset: str, quota: str) -> str | None:
    if quota.lower() in ("none", "0"):
        return None
    if not self.dataset_exists(dataset):
        return None
    used = self.get_used_bytes(dataset)
    new_quota = self._parse_size_bytes(quota)
    if new_quota < used:
        used_g = round(used / 1024**3, 2)
        name = dataset.split("/")[-1]
        return f"Quota {quota} is less than current used size ({used_g}G) for {name} dataset"
    return None
```

`_parse_size_bytes` handles suffixes `K`, `M`, `G`, `T`, `P` (base-1024) and bare integer strings.

---

## Error handling

`VolumeManager` raises `bench_cli.exceptions.VolumeError` (a subclass of `BenchError`) for all ZFS command failures. The CLI catches this at the top level and prints the error along with the underlying command that failed.

Common errors:

| Situation | Message shown |
|-----------|--------------|
| `zfs` / `zpool` not installed | ZFS is installed automatically; if installation fails, a `VolumeError` is raised |
| Pool does not exist | Raised by `zpool list` inside `pool_exists()` |
| Dataset does not exist | Raised by `zfs list` inside `dataset_exists()` |
| Quota less than reservation | Caught at validation time before any ZFS commands run |
| Snapshot does not exist | "Snapshot '<dataset>@<tag>' does not exist." |

---

## Security notes

- All `zpool create`, `zfs create`, `zfs set`, `rsync`, `mv`, and `rm` operations that require elevated privileges run under `sudo`.
- Mounting is done via `zfs set mountpoint=` — ZFS handles persistence natively with no `/etc/fstab` modifications.
- `bench volume destroy-snapshot` always requires `--yes`. No snapshot is ever destroyed silently.
- Dataset names and snapshot tags are constructed from `bench.toml` values and generated timestamps only. All ZFS calls use `subprocess` with a list argv — never `shell=True`.
