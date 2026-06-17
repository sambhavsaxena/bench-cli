# bench.toml — Configuration Specification

`bench.toml` is the single source of truth for a bench's infrastructure configuration. It lives at `benches/<name>/bench.toml`.

Apps and sites are **not** tracked in `bench.toml` after `bench init` — they are discovered from the filesystem (`apps/` and `sites/` directories). The `[[apps]]` section exists only to declare the framework app to clone on first init.

---

## Full schema

```toml
# ── Bench identity ────────────────────────────────────────────────────────────
[bench]
name = "my-bench"       # used in process names and log prefixes
python = "3.14"         # Python version to use for the virtualenv

# ── Framework app (cloned during bench init) ──────────────────────────────────
[[apps]]
name = "frappe"
repo = "https://github.com/frappe/frappe"
branch = "version-16"

# ── MariaDB ───────────────────────────────────────────────────────────────────
[mariadb]
host = "localhost"
port = 3306
root_password = "root"  # used only during bench init to create databases/users
# version = "11.8"      # optional — defaults to MariaDB 11.8 LTS (vendor repo on Linux)

# ── Redis ─────────────────────────────────────────────────────────────────────
[redis]
port = 13000            # single Redis instance for all services (simplest)
# version = "7"         # optional — pin to a specific Redis major version
# or use separate instances:
# cache_port = 13000
# queue_port = 11000
# socketio_port = 12000

# ── Workers ───────────────────────────────────────────────────────────────────
# Each [[workers]] group spawns `count` workers listening to `queues`.
[[workers]]
queues = ["default", "short", "long"]   # one worker handling all three queues
count = 1

# ── Nginx (production only) ───────────────────────────────────────────────────
[nginx]
enabled = false         # set to true to enable production nginx setup
http_port = 80
https_port = 443
config_dir = "/etc/nginx/conf.d"
worker_processes = "auto"
client_max_body_size = "50m"

# ── Gunicorn (production only) ───────────────────────────────────────────────
[gunicorn]
workers = 4             # number of Gunicorn worker processes
threads = 4             # threads per worker (used by gthread worker class)
timeout = 120
worker_class = "sync"
malloc_arena_max = 2    # cap glibc malloc arenas to reduce RSS; 0 = leave unset
max_requests = 0        # recycle the web worker after N requests to release heap; 0 = disabled
max_requests_jitter = 0 # random +/- spread on max_requests

# ── Let's Encrypt (production only) ──────────────────────────────────────────
[letsencrypt]
email = "admin@example.com"  # required if any site has ssl = true
webroot_path = "/var/www/letsencrypt"

# ── Admin UI ──────────────────────────────────────────────────────────────────
[admin]
port = 8002             # port the admin UI listens on
password = "secret"     # required — admin refuses to start without this
domain = ""             # optional — serve admin over HTTPS via nginx (production)

# ── ZFS Volume (Linux only, optional) ────────────────────────────────────────
[volume]
enabled = false         # set to true to activate ZFS volume management
pool = "bench-pool"     # ZFS pool name (created during bench init if absent)
device = "/dev/sdb"     # block device for the pool (ignored if pool already exists)

[volume.benches]
reservation = "10G"     # guaranteed space for bench directories
quota = "50G"           # hard cap on bench directory space

[volume.mariadb]
reservation = "5G"      # guaranteed space for MariaDB data files
quota = "20G"           # hard cap on MariaDB data
data_dir = "/var/lib/mysql"  # remounted onto the ZFS dataset during bench init

[volume.snapshots]
enabled = false         # set to true to allow bench volume snapshot
```

---

## Field reference

### `[bench]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Human-readable bench name. Used in process labels and log file names. Must match `^[a-zA-Z][a-zA-Z0-9_-]*$`. |
| `python` | string | yes | — | Python version string (e.g. `"3.14"`). Must be available on the system or installable via `deadsnakes/ppa`. |

### `[[apps]]`

Declares the framework app (frappe) to clone during `bench init`. After init, additional apps are added via `bench get-app` and are tracked on the filesystem, not in this file.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Directory name under `apps/` and the Python package name used for `uv pip install -e`. |
| `repo` | string | yes | Git remote URL (HTTPS or SSH). |
| `branch` | string | yes | The git branch to checkout. |

**Constraints:**
- `name` values must be unique.
- The first (and typically only) app listed is treated as the **framework app** (frappe). It must expose a `bench` CLI entry point for site management commands.

### `[mariadb]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `host` | string | no | `localhost` | MariaDB server host. |
| `port` | int | no | `3306` | MariaDB server port. |
| `root_password` | string | yes | — | Root password used to create site databases and users during `bench init`. |
| `version` | string | no | `11.8` | MariaDB version to install (e.g. `"11.8"`, `"11.4"`). On Linux, bench adds MariaDB's official APT repository pinned to this version and installs `mariadb-server` from it; on macOS it selects the `mariadb@<version>` Homebrew formula. Omit to install the default **11.8 LTS** series. |

### `[redis]`

**Single-instance mode** (recommended for most benches): specify one `port` and a single Redis server handles all three services using separate database numbers (`/0` cache, `/1` queue, `/2` socketio).

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `port` | int | no | — | Run a single Redis instance on this port for all services. When set, `cache_port`/`queue_port`/`socketio_port` are ignored. |
| `cache_port` | int | no | `13000` | Port for the Redis cache instance (multi-instance mode). |
| `queue_port` | int | no | `11000` | Port for the Redis queue instance (multi-instance mode). |
| `socketio_port` | int | no | `12000` | Port for the Redis socketio instance (multi-instance mode). |
| `version` | string | no | — | Redis version to install (e.g. `"7"`, `"7.0"`). On macOS, selects the `redis@<version>` Homebrew formula. On Ubuntu, apt has no versioned redis package names — use the official Redis apt repository for version pinning, then omit this field. |

In single-instance mode, one `redis` process appears in the Procfile and one `redis.conf` is written to `config/`. In multi-instance mode, three separate processes (`redis_cache`, `redis_queue`, `redis_socketio`) and three config files are generated. All ports must be in the range 1024–65535.

### `[[workers]]`

An array of worker groups. Each group spawns `count` worker processes that
listen to the queues in `queues`. Omitting the table entirely defaults to a
single worker handling all three standard queues (`default`, `short`, `long`).

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `queues` | list of strings | yes | — | Queues this group's workers listen to (e.g. `["default", "short", "long"]`). |
| `count` | int | yes | — | Number of worker processes to spawn for this group (≥ 1). |

```toml
# One worker per queue:
[[workers]]
queues = ["default"]
count = 2

[[workers]]
queues = ["short"]
count = 1

[[workers]]
queues = ["long"]
count = 1
```

### `[production]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `process_manager` | string | no | `none` | Production process manager: `none`, `supervisor`, or `systemd`. |
| `nginx` | bool | no | `false` | Run nginx setup as part of `bench setup production`. |
| `use_companion_manager` | bool | no | `false` | Run scheduler, RQ workers, and socket.io as Gunicorn companion processes under a single preloaded master. Requires the Frappe Gunicorn fork with companion support. |

### `[nginx]` _(production only)_

Omit this section entirely for development benches. The section is only read by `bench setup nginx` and `bench setup production`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool | yes | `false` | Must be `true` for `bench setup nginx` to proceed. Acts as an explicit opt-in to production nginx setup. |
| `http_port` | int | no | `80` | Port Nginx listens on for plain HTTP. |
| `https_port` | int | no | `443` | Port Nginx listens on for HTTPS. |
| `config_dir` | string | no | `/etc/nginx/conf.d` | System directory where the bench include-pointer file is symlinked. Requires sudo. |
| `worker_processes` | string or int | no | `auto` | Passed to the Nginx `worker_processes` directive. |
| `client_max_body_size` | string | no | `50m` | Maximum upload size. Increase for large file imports. |

### `[gunicorn]` _(production only)_

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `workers` | int | no | `4` | Number of Gunicorn worker processes. |
| `threads` | int | no | `4` | Threads per worker. Used by the `gthread` worker class. |
| `timeout` | int | no | `120` | Request timeout in seconds. |
| `worker_class` | string | no | `sync` | Gunicorn worker class. |
| `malloc_arena_max` | int | no | `2` (new benches); `0` if absent | Caps glibc malloc arenas (`MALLOC_ARENA_MAX`) for the web/companion/worker Python processes to keep idle RSS down on these multi-threaded processes. `0` leaves the system default unset. |
| `max_requests` | int | no | `0` | Recycle each web worker after this many requests, re-forking it from the preloaded master to release the heap it accreted under load. `0` disables it (safe for production); set e.g. `2000` on demo/overcommit benches to bound RSS. |
| `max_requests_jitter` | int | no | `0` | Random ± spread on `max_requests` so workers don't all recycle at once. |

### `[letsencrypt]` _(production only)_

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `email` | string | yes (if any site has `ssl = true`) | — | Contact email for ACME account registration. |
| `webroot_path` | string | no | `/var/www/letsencrypt` | Directory certbot writes challenge files to. Nginx serves this path at `/.well-known/acme-challenge/`. |

### `[admin]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `port` | int | no | `8002` | Port the admin process listens on. |
| `password` | string | yes | — | Password for the admin UI. The process refuses all requests with HTTP 503 if this is empty. |
| `domain` | string | no | `""` | Hostname to serve the admin UI over HTTPS in production (e.g. `admin.example.com`). When set, `bench setup production` obtains a certificate and generates an nginx proxy block. |

### `[volume]`

Volume management is opt-in and Linux-only. All `[volume.*]` sections are ignored unless `volume.enabled = true`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool | no | `false` | Activate ZFS volume management. |
| `pool` | string | yes (if enabled) | — | ZFS pool name. Created on `device` during `bench init` if it does not exist. |
| `device` | string | yes (if enabled) | — | Block device path (e.g. `/dev/sdb`). Used only if the pool does not yet exist. |

### `[volume.benches]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reservation` | string | no | `"10G"` | Guaranteed space for bench directories. ZFS will not allow this dataset to fall below this allocation. Must be a valid ZFS size (e.g. `"10G"`, `"500M"`). |
| `quota` | string | no | `"50G"` | Hard space cap. Writes beyond this limit are rejected. Must be greater than `reservation`. Can be updated live via the Settings modal without restarting. |

### `[volume.mariadb]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `reservation` | string | no | `"5G"` | Guaranteed space for MariaDB data files. |
| `quota` | string | no | `"20G"` | Hard space cap for MariaDB data. bench validates that the new quota is not less than the dataset's current used size before applying. |
| `data_dir` | string | no | `"/var/lib/mysql"` | MariaDB data directory. During `bench init`, the dataset is remounted here via `zfs set mountpoint`. |

### `[volume.snapshots]`

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `enabled` | bool | no | `false` | Allow `bench volume snapshot` and `bench volume restore-snapshot`. Set to `false` to block accidental snapshots. Togglable via the ZFS Volume tab in the Settings modal. |

---

## Validation rules

bench validates `bench.toml` before executing any command. Violations produce a clear error message that names the offending field.

1. Required fields (`bench.name`, `bench.python`, `mariadb.root_password`) must be present.
2. `bench.name` must match `^[a-zA-Z][a-zA-Z0-9_-]*$`.
3. All `apps[].name` values must be unique.
4. All Redis ports must be integers in the range 1024–65535. In multi-instance mode (`cache_port`/`queue_port`/`socketio_port`), each port must be distinct.
5. Worker counts must be positive integers.
6. `letsencrypt.email` must match a basic email pattern (`^[^@]+@[^@]+\.[^@]+$`) when present.
7. `nginx.http_port` and `nginx.https_port` must be distinct.
8. `gunicorn.workers`, `gunicorn.threads`, and `gunicorn.timeout` must be positive integers; `gunicorn.worker_class` must be a non-empty string; `gunicorn.malloc_arena_max`, `gunicorn.max_requests`, and `gunicorn.max_requests_jitter` must be non-negative integers.
9. `mariadb.version` and `redis.version`, when present, must match `^\d+(\.\d+)*$` (e.g. `"10.6"`, `"7"`, `"7.0"`).
10. When `volume.enabled = true`: `pool` and `device` must be non-empty; `reservation` and `quota` values must match a valid ZFS size pattern (e.g. `"10G"`, `"500M"`, `"1T"`); quota must be greater than reservation for both datasets.

---

## Minimal example

```toml
[bench]
name = "dev"
python = "3.14"

[[apps]]
name = "frappe"
repo = "https://github.com/frappe/frappe"
branch = "version-16"

[mariadb]
root_password = "root"

[redis]
port = 13000
```

After `bench init`, run `bench new-site site1.localhost` to create your first site.

---

## Sites and apps after init

Sites and apps are **not** tracked in `bench.toml`. They are managed by commands and discovered from disk:

| What | How to add | Where stored |
|------|-----------|--------------|
| Additional apps | `bench get-app <repo>` | `apps/<name>/` (git clone) + `sites/apps.txt` |
| Sites | `bench new-site <name>` | `sites/<name>/site_config.json` |

`Bench.apps()` scans `apps/` for directories with a `.git` folder. `Bench.sites()` scans `sites/` for directories with a `site_config.json`. Neither reads `bench.toml`.
