# bench2

A command-line tool for setting up and managing [Frappe](https://frappeframework.com) environments on Ubuntu. Configuration lives in a single `bench.yml` file. No Docker.

## Requirements

- Ubuntu 22.04 LTS (other Debian-based distros are best-effort)
- Python 3.10+
- `sudo` access (needed during `bench init` to install system packages)

## Installation

```bash
pip install bench2
```

That's it. `bench init` will install MariaDB, Redis, Node.js, and any other system dependencies itself.

---

## Development quick start

**1. Create a directory for your bench and scaffold a config:**

```bash
mkdir my-bench && cd my-bench
bench new
```

This writes a starter `bench.yml`. Open it and fill in your apps, sites, and database passwords.

**2. Run the setup:**

```bash
bench init
```

This will:
- Install MariaDB, Redis, Node.js via `apt`
- Create a Python virtualenv at `env/`
- Clone your apps into `apps/` and `pip install -e` each one
- Create your sites and install apps on them
- Generate a `Procfile` for running all processes

**3. Start everything:**

```bash
bench run
```

All processes (web, workers, Redis) start in the foreground. Press `Ctrl-C` to stop.

**4. Open the app:**

Visit `http://site1.localhost:8000` (or whatever site name you configured).

---

## bench.yml

A minimal config for a single Frappe + ERPNext site:

```yaml
bench:
  name: my-bench
  python: "3.11"

apps:
  - name: frappe
    repo: https://github.com/frappe/frappe
    branch: version-15
  - name: erpnext
    repo: https://github.com/frappe/erpnext
    branch: version-15

sites:
  - name: site1.localhost
    db_name: site1_db
    db_password: "secret"
    apps:
      - frappe
      - erpnext

mariadb:
  root_password: "root"

redis:
  cache_port: 13000
  queue_port: 11000
  socketio_port: 12000
```

---

## Commands

| Command | What it does |
|---------|-------------|
| `bench new` | Scaffold a starter `bench.yml` in the current directory |
| `bench init` | Install system packages, clone apps, create sites, generate process config |
| `bench run` | Start all processes (web, workers, Redis) |
| `bench build` | Build JavaScript and CSS assets |
| `bench update` | Pull latest app commits, reinstall packages, migrate all sites |
| `bench admin` | Start the web admin interface on `http://localhost:8001` |

All commands read `bench.yml` from the current directory (or the nearest parent directory that contains one).

---

## Production setup

For production you need three extra steps after `bench init`.

**1. Update `bench.yml`:**

```yaml
bench:
  name: prod-bench
  python: "3.11"
  process_manager: supervisor   # run as a background daemon

apps:
  - name: frappe
    repo: https://github.com/frappe/frappe
    branch: version-15

sites:
  - name: mysite.example.com
    db_name: mysite_db
    db_password: "s3cr3t"
    apps: [frappe]
    ssl: true                   # enable Let's Encrypt

mariadb:
  root_password: "root_s3cr3t"

redis:
  cache_port: 13000
  queue_port: 11000
  socketio_port: 12000

nginx:
  enabled: true

letsencrypt:
  email: ops@example.com
```

**2. Run `bench init`** to set up the bench as normal.

**3. Point your DNS** — create an A record for `mysite.example.com` pointing at your server's IP.

**4. Set up Nginx and SSL:**

```bash
bench setup production
```

This installs and configures Nginx, obtains a Let's Encrypt certificate, and starts all processes under supervisor. Your site will be live at `https://mysite.example.com`.

To add more sites later: add them to `bench.yml` and re-run `bench setup production`.

---

## Web admin

```bash
bench admin
```

Opens a local web interface at `http://localhost:8001` for inspecting the bench without touching the terminal:

- App git status and installed versions
- Site configuration and installed apps
- Process status (running / stopped)
- Live log tailing
- MariaDB binary logs and slow query log
- Run common commands (migrate, clear-cache, build) with streamed output

The admin reads all state directly from the filesystem on each request — it keeps no state of its own.

---

## Updating

```bash
bench update
```

Pulls the latest commits for all apps, re-installs Python packages (to pick up new dependencies), and runs `bench --site <name> migrate` on every site.

After updating, rebuild assets:

```bash
bench build
```

---

## Directory layout

After `bench init`, your bench directory looks like this:

```
my-bench/
├── bench.yml          # your config
├── apps/              # cloned app source code
│   ├── frappe/
│   └── erpnext/
├── sites/             # site data
│   ├── assets/        # built JS/CSS
│   └── site1.localhost/
├── env/               # shared Python virtualenv
├── logs/              # per-process log files
└── config/            # generated Procfile, Redis configs, Nginx configs
```

---

## Further reading

- [specs/config.md](specs/config.md) — complete `bench.yml` field reference
- [specs/commands.md](specs/commands.md) — what each command does, step by step
- [specs/production.md](specs/production.md) — Nginx, Let's Encrypt, and DNS multitenancy in detail
- [specs/admin.md](specs/admin.md) — admin interface design
- [specs/architecture.md](specs/architecture.md) — Python package layout and class design
