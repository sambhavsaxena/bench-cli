# bench2 — Specification

bench2 is a command-line tool for setting up and managing a Frappe development environment on Ubuntu. It replaces the original frappe/bench with a simpler, YAML-driven approach that avoids Docker and keeps everything transparent and hackable.

---

## Core ideas

- **One config file** (`bench.yml`) describes the entire environment: apps, sites, databases, workers.
- **No Docker.** Services (MariaDB, Redis) are installed directly on the host via apt/pip.
- **Plain Python OOP.** Classes map directly to real-world concepts (Bench, App, Site, Manager). No clever metaprogramming.
- **Four commands** cover the full lifecycle: `init`, `run`, `build`, `update`.
- **Web admin** (`bench admin`) provides a read/operate interface over the bench without maintaining its own state.

---

## Quick start

```bash
pip install bench2          # install the CLI

mkdir my-bench && cd my-bench
bench new                   # scaffold a starter bench.yml

# edit bench.yml to taste, then:
bench init                  # install deps, clone apps, create sites
bench run                   # start all processes
```

---

## Sub-specifications

| File | What it covers |
|------|---------------|
| [specs/config.md](specs/config.md) | Full `bench.yml` schema with field descriptions and a complete example |
| [specs/architecture.md](specs/architecture.md) | Python package layout, classes, responsibilities, and relationships |
| [specs/commands.md](specs/commands.md) | Step-by-step behaviour of each CLI command |
| [specs/admin.md](specs/admin.md) | Flask admin interface — pages, readers, command execution, log streaming |
| [specs/production.md](specs/production.md) | DNS multitenancy, Nginx config generation, Let's Encrypt SSL, `bench setup` commands |

---

## Guiding constraints

1. **Readable over clever.** A new contributor should be able to understand any class without reading surrounding code.
2. **Fail loudly.** Validate `bench.yml` up-front and print actionable errors before touching the filesystem.
3. **Idempotent where possible.** Running `bench init` twice should not break a working bench.
4. **Ubuntu-first.** System package installation targets Ubuntu 22.04 LTS. Other Debian-based distros are best-effort.
5. **Single virtualenv.** All Python apps share one virtualenv inside the bench directory.
