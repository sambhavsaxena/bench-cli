# bench

A command-line tool for setting up and managing [Frappe](https://frappeframework.com) environments. Configuration lives in a single `bench.toml` file. No Docker.

## How this differs from legacy bench

The original [frappe/bench](https://github.com/frappe/bench) is a Python package with a large dependency tree (click, honcho, supervisor, pymysql, and more). This rewrite takes a different approach:

| | Legacy bench | This bench |
|---|---|---|
| **Dependencies** | ~20 Python packages | Zero — stdlib only |
| **Config format** | Multiple JSON files scattered across the directory | Single `bench.toml` |
| **Folder layout** | Bench lives wherever you `bench init` | All benches under `bench-cli/benches/<name>/` |
| **Process manager** | Honcho (dev) or Supervisor (prod) | Built-in Procfile runner, no external tool needed |
| **Python env** | pip + virtualenv | [uv](https://github.com/astral-sh/uv) — auto-installed on first use |
| **Admin UI** | None | Built-in web UI (`bench admin`) — app status, site management, live logs, task runner |
| **Site/app tracking** | Config files | Filesystem — `apps/` and `sites/` directories are the source of truth |

The goal is a bench you can fully understand by reading the source, debug without hunting through installed packages, and extend without fighting framework abstractions.

---

## Requirements

**Ubuntu 22.04 LTS** (other Debian-based distros are best-effort)
- Python 3.11+
- `sudo` access (needed during `bench init` to install system packages via apt)

**macOS** (development only)
- Python 3.11+
- [Homebrew](https://brew.sh) (`brew` in `$PATH`)

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/frappe/bench-cli/main/install.sh | bash
```

This clones `bench-cli` to `~/bench-cli` and installs the `bench` command via [uv](https://github.com/astral-sh/uv) (auto-installed if absent). All benches are created inside `~/bench-cli/benches/`.

Or manually:

```bash
git clone https://github.com/frappe/bench-cli ~/bench-cli
uv tool install ~/bench-cli
```

`bench init` will then install MariaDB, Redis, Node.js, and any other system dependencies itself.

---

## Quick start

**1. Create a bench:**

```bash
bench new my-bench
```

This creates `~/bench-cli/benches/my-bench/bench.toml`. Open it and set your MariaDB root password and desired Python version.

**2. Run setup:**

```bash
bench init
```

This will:
- Install MariaDB, Redis, Node.js via `apt` (or `brew` on macOS)
- Create a Python virtualenv at `env/` using `uv`
- Clone the Frappe framework app and install it with `uv pip install -e`
- Generate a `Procfile` for running all processes

**3. Get additional apps (optional):**

```bash
bench get-app https://github.com/frappe/erpnext --branch version-16
```

**4. Create a site:**

```bash
bench new-site site1.localhost
```

**5. Start everything:**

```bash
bench start
```

All processes (web, workers, Redis) start in the foreground. Press `Ctrl-C` to stop.

**6. Open the app:**

Visit `http://site1.localhost:8000`.

---

## bench.toml

A minimal config — apps and sites are managed by commands, not tracked in the config file:

```toml
[bench]
name = "my-bench"
python = "3.14"

[[apps]]
name = "frappe"
repo = "https://github.com/frappe/frappe"
branch = "version-16"

[mariadb]
host = "localhost"
port = 3306
root_password = "your_root_password"
# version = "10.6"   # optional

[redis]
port = 13000
# or use separate ports:
# cache_port = 13000
# queue_port = 11000
# socketio_port = 12000

[workers]
default = 2
short = 1
long = 1
```

> **Note:** After `bench init`, use `bench get-app` to add more apps and `bench new-site` to create sites. Apps and sites are discovered from the filesystem — they don't need to be listed in `bench.toml`.

---

## Commands

| Command | What it does |
|---------|-------------|
| `bench new <name>` | Scaffold a new bench with a starter `bench.toml` |
| `bench init` | Install system packages, clone the framework app, set up venv, generate process config |
| `bench start` | Start all processes (web, workers, Redis) in the foreground |
| `bench stop` | Stop a running bench (works across terminal sessions via PID file) |
| `bench get-app <repo>` | Clone and install an app from a git repository |
| `bench new-site <name>` | Create a new site |
| `bench build` | Rebuild JavaScript and CSS assets |
| `bench update` | Pull latest app commits, reinstall packages, migrate all sites |
| `bench update-config` | Regenerate config files (Procfile, Redis, Nginx) from bench.toml |
| `bench start-admin` | Start the admin UI as a background daemon (default: `http://localhost:8002`) |
| `bench stop-admin` | Stop the background admin UI |
| `bench admin` | Start the admin UI in the foreground (dev use) |
| `bench setup nginx` | Generate and install nginx config |
| `bench setup letsencrypt` | Obtain SSL certificates |
| `bench setup production` | Full production setup (nginx + SSL) |

When multiple benches exist, specify which one with `-b`:

```bash
bench -b my-bench start
bench -b my-bench new-site site2.localhost
```

---

## Production setup

Update `bench.toml` to enable nginx and SSL:

```toml
[nginx]
enabled = true

[letsencrypt]
email = ops@example.com
```

Set `ssl = true` in each site config (via `bench frappe --site mysite.example.com set-config ssl 1`), then run:

```bash
bench setup production
```

This installs nginx, obtains a Let's Encrypt certificate, and generates all config files.

---

## Web admin

```bash
bench start-admin          # start on default port 8002 (background daemon)
bench stop-admin           # stop the daemon
bench start-admin --port 9000  # custom port
```

The admin starts as a background daemon and auto-stops after **3 minutes of inactivity**. Use `bench stop-admin` to stop it immediately.

For interactive/foreground use during development:

```bash
bench admin                # foreground, Ctrl-C to stop
```

The admin interface provides:

- App git status and installed versions
- Site configuration and installed apps
- Process status (running / stopped)
- Live log tailing
- Run common commands (migrate, clear-cache, build) with streamed output

---

## Directory layout

```
bench-cli/
└── benches/
    └── my-bench/
        ├── bench.toml         # infra config (python, db, redis, workers)
        ├── apps/              # cloned app source code
        │   └── frappe/
        ├── sites/             # site data
        │   ├── assets/        # built JS/CSS (symlinked from apps)
        │   ├── apps.txt       # installed app list read by frappe
        │   ├── common_site_config.json   # redis URLs, ports
        │   └── site1.localhost/
        │       └── site_config.json     # db credentials (set by frappe)
        ├── env/               # shared Python virtualenv (managed by uv)
        ├── logs/              # process log files
        ├── pids/              # bench.pid, per-process PID files
        └── config/            # Procfile, Redis configs, Nginx configs
```

---

## Further reading

- [taste.md](taste.md) — coding guidelines
- [SPEC.md](SPEC.md) — full specification
