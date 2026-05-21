# Admin Interface Specification

bench2 ships a lightweight web-based admin interface built on Flask with no Python dependencies beyond Flask itself. It is started with `bench admin` and intended for local inspection and day-to-day operations.

---

## Design constraints

- **Stateless.** The Flask app stores nothing in memory between requests. Every page reads current state from the filesystem (bench.yml, git, log files, site_config.json) or from MariaDB on each request. There is no session, no cache, no background thread.
- **No extra Python dependencies.** Only Flask and the Python standard library. No SQLAlchemy, no Celery, no frontend framework.
- **No frontend framework.** Plain HTML templates with minimal inline CSS. A small amount of vanilla JS is acceptable for auto-refresh and SSE output streaming.
- **Localhost only by default.** Binds to `127.0.0.1` unless overridden. No authentication — treat this as a local developer/ops tool.

---

## Starting the admin

```bash
bench admin               # start on default port 8001
bench admin --port 9000   # custom port
bench admin --host 0.0.0.0  # expose to the network (your responsibility)
```

The admin can also be included in the Procfile/supervisor config so it starts alongside the bench:

```
admin: bench admin --port 8001
```

---

## Package layout

```
bench2/
└── bench2/
    └── admin/
        ├── __init__.py
        ├── app.py                   # Flask app factory — create_app(bench_root: Path)
        │
        ├── readers/                 # Stateless filesystem/DB readers
        │   ├── __init__.py
        │   ├── bench_reader.py      # BenchReader
        │   ├── app_reader.py        # AppReader
        │   ├── site_reader.py       # SiteReader
        │   ├── process_reader.py    # ProcessReader
        │   ├── log_reader.py        # LogReader
        │   └── database_reader.py   # DatabaseReader
        │
        ├── views/                   # Flask blueprints — one per section
        │   ├── __init__.py
        │   ├── dashboard.py         # GET /
        │   ├── apps.py              # GET /apps
        │   ├── sites.py             # GET /sites, /sites/<name>
        │   ├── processes.py         # GET /processes, POST /processes/<name>/restart
        │   ├── logs.py              # GET /logs, /logs/<filename>
        │   ├── database.py          # GET /database/binlogs, /database/slow-queries
        │   └── commands.py          # POST /commands/run, GET /commands/stream/<token>
        │
        └── templates/
            ├── base.html
            ├── dashboard.html
            ├── apps.html
            ├── sites/
            │   ├── list.html
            │   └── detail.html
            ├── processes.html
            ├── logs/
            │   ├── list.html
            │   └── viewer.html
            ├── database/
            │   ├── binlogs.html
            │   ├── binlog_detail.html
            │   └── slow_queries.html
            └── commands.html
```

---

## App factory

```python
def create_app(bench_root: Path) -> Flask:
    app = Flask(__name__)
    app.config['BENCH_ROOT'] = bench_root

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(apps_bp,      url_prefix='/apps')
    app.register_blueprint(sites_bp,     url_prefix='/sites')
    app.register_blueprint(processes_bp, url_prefix='/processes')
    app.register_blueprint(logs_bp,      url_prefix='/logs')
    app.register_blueprint(database_bp,  url_prefix='/database')
    app.register_blueprint(commands_bp,  url_prefix='/commands')

    return app
```

`bench_root` is injected once at startup and is available to every view via `current_app.config['BENCH_ROOT']`. This is the only persistent state the app holds — it is configuration, not runtime state.

---

## Readers layer

Each reader is instantiated per-request. They have no `__init__`-level side effects beyond storing the path they will read from.

### `BenchReader`

```python
class BenchReader:
    def __init__(self, bench_root: Path): ...

    def config(self) -> BenchConfig:
        """Parse bench.yml. Returns BenchConfig or raises ConfigError."""

    def summary(self) -> BenchSummary:
        """
        Return a lightweight summary struct: bench name, python version,
        process_manager, app count, site count. Reads only bench.yml.
        """
```

```python
@dataclass
class BenchSummary:
    name: str
    python_version: str
    process_manager: str
    app_count: int
    site_count: int
```

### `AppReader`

```python
class AppReader:
    def __init__(self, bench_root: Path): ...

    def read_all(self) -> List[AppInfo]:
        """
        For each app in bench.yml: check if cloned, read git state, read installed version.
        """

    def read_one(self, app_name: str) -> AppInfo: ...
```

```python
@dataclass
class AppInfo:
    name: str
    repo: str
    branch: str
    is_cloned: bool
    current_commit: str          # short SHA; empty string if not cloned
    commit_message: str          # first line of last commit message
    uncommitted_changes: bool    # True if `git status --porcelain` returns output
    installed_version: str       # from `pip show <name>` Version field; empty if not installed
```

Git state is read by running `git` as a subprocess — no Python git library needed.

### `SiteReader`

```python
class SiteReader:
    def __init__(self, bench_root: Path): ...

    def read_all(self) -> List[SiteInfo]: ...
    def read_one(self, site_name: str) -> SiteInfo: ...
```

```python
@dataclass
class SiteInfo:
    name: str
    exists: bool                 # True if sites/<name>/site_config.json is present
    db_name: str                 # from bench.yml
    db_host: str                 # from site_config.json
    installed_apps: List[str]    # from sites/<name>/site_config.json "installed_apps"
    site_config: dict            # full parsed site_config.json; empty dict if not found
```

### `ProcessReader`

```python
class ProcessReader:
    def __init__(self, bench_root: Path): ...

    def read_all(self) -> List[ProcessInfo]:
        """
        If process_manager is supervisor: parse `supervisorctl status` output.
        If process_manager is honcho: check pids/ directory for PID files
        and verify each PID is alive via os.kill(pid, 0).
        """
```

```python
@dataclass
class ProcessInfo:
    name: str
    status: str          # 'running' | 'stopped' | 'error' | 'unknown'
    pid: Optional[int]
    uptime: Optional[str]   # e.g. "0:03:12" — only available from supervisor
    log_file: Path
```

### `LogReader`

```python
class LogReader:
    def __init__(self, bench_root: Path): ...

    def list_logs(self) -> List[LogFileInfo]:
        """Scan logs/ directory. Return metadata for each .log file."""

    def read_tail(self, filename: str, lines: int = 200) -> List[str]:
        """
        Return the last N lines of logs/<filename>.
        Raises FileNotFoundError if the file does not exist.
        Validates that filename stays within logs/ (no path traversal).
        """

    def stream_tail(self, filename: str) -> Generator[str, None, None]:
        """
        Yield lines from the end of the file as they are written.
        Used for SSE log streaming. Stops after yielding 5000 lines
        or when the generator is garbage-collected.
        """
```

```python
@dataclass
class LogFileInfo:
    filename: str
    size_bytes: int
    last_modified: datetime
    process_name: str     # derived from filename by stripping .log suffix
```

### `DatabaseReader`

```python
class DatabaseReader:
    def __init__(self, mariadb_config: MariaDBConfig): ...

    def _connect(self) -> Connection:
        """Open a short-lived root connection. Closed after each method call."""

    # Binary log methods
    def list_binary_logs(self) -> List[BinaryLogInfo]:
        """Run SHOW BINARY LOGS."""

    def read_binary_log_events(
        self,
        log_name: str,
        limit: int = 200,
        offset: int = 0,
    ) -> List[BinlogEvent]:
        """Run SHOW BINLOG EVENTS IN '<log_name>' LIMIT <offset>,<limit>."""

    # Slow query methods
    def slow_query_log_path(self) -> Optional[Path]:
        """
        Run SHOW VARIABLES LIKE 'slow_query_log_file'.
        Return the path if slow_query_log is ON, else None.
        """

    def read_slow_queries(self, limit: int = 50) -> List[SlowQuery]:
        """
        Parse the slow query log file from the end.
        Return up to <limit> most recent entries.
        """
```

```python
@dataclass
class BinaryLogInfo:
    log_name: str
    file_size: int

@dataclass
class BinlogEvent:
    log_name: str
    pos: int
    event_type: str
    server_id: int
    end_log_pos: int
    info: str

@dataclass
class SlowQuery:
    timestamp: datetime
    query_time: float      # seconds
    lock_time: float
    rows_examined: int
    rows_sent: int
    user_host: str
    sql: str
```

---

## Routes

### `GET /` — Dashboard

Reads `BenchReader.summary()`, `AppReader.read_all()`, `SiteReader.read_all()`, `ProcessReader.read_all()`. Displays a single-page overview:

- Bench name and process manager mode
- Apps table: name, branch, short commit hash, uncommitted changes indicator
- Sites table: name, installed apps, DB name, exists flag
- Processes table: name, status (coloured), PID, uptime

### `GET /apps` — Apps list

Full `AppReader.read_all()` output in a table. Shows per-app: repo URL, branch, current commit + message, uncommitted changes, pip-installed version.

### `GET /sites` — Sites list

`SiteReader.read_all()` in a table. Shows: name, exists, installed apps, DB name.

### `GET /sites/<name>` — Site detail

`SiteReader.read_one(name)`. Shows:

- Installed apps list
- Full `site_config.json` rendered as a formatted JSON block
- Action buttons (see Commands section)

### `GET /processes` — Process status

`ProcessReader.read_all()`. Shows name, status, PID, uptime, link to its log file.

For supervisor benches, also shows a note: "manage via `supervisorctl -c config/supervisor.conf`".

### `GET /logs` — Log file list

`LogReader.list_logs()` in a table: filename, process name, size, last modified time.

### `GET /logs/<filename>` — Log viewer

`LogReader.read_tail(filename, lines=request.args.get('lines', 200))`. Renders the lines in a `<pre>` block.

Query parameters:
- `?lines=N` — how many lines to show (default 200, max 5000)
- `?stream=1` — switches the page to live-tail mode (see Streaming section)

### `GET /database/binlogs` — Binary logs list

`DatabaseReader.list_binary_logs()`. Table: log name, file size.

### `GET /database/binlogs/<log_name>` — Binary log detail

`DatabaseReader.read_binary_log_events(log_name, limit, offset)`. Table: pos, event type, server_id, end_log_pos, info. Pagination via `?offset=N&limit=N`.

### `GET /database/slow-queries` — Slow query log

`DatabaseReader.read_slow_queries(limit=50)`. Table: timestamp, query_time, lock_time, rows_examined, rows_sent, user/host, SQL.

Query parameter: `?limit=N` (default 50, max 500).

### `POST /commands/run` — Execute a command

Request body (form-encoded):
```
command=migrate&site=site1.localhost
```

Allowed commands and their parameters:

| `command` | Extra params | Runs |
|-----------|-------------|------|
| `migrate` | `site` | `bench --site <site> migrate` |
| `clear-cache` | `site` | `bench --site <site> clear-cache` |
| `install-app` | `site`, `app` | `bench --site <site> install-app <app>` |
| `build` | — | `bench build` |
| `update` | — | `bench update --yes` |
| `reload-supervisor` | — | `supervisorctl -c config/supervisor.conf reload` (supervisor only) |

Any command not in this list returns HTTP 400.

The endpoint runs the command as a subprocess, streams stdout+stderr line-by-line via **Server-Sent Events**, and closes the stream when the process exits. The response `Content-Type` is `text/event-stream`.

```
GET /commands/run?command=migrate&site=site1.localhost
```

(GET is acceptable here because SSE requires a GET. The URL is not bookmarkable — navigating to it starts the command.)

The commands page (`commands.html`) uses JavaScript's `EventSource` to connect to this URL and appends each line to a `<pre>` block. When the stream closes, it shows the exit code.

---

## Log streaming (live tail)

`GET /logs/<filename>?stream=1` returns a page whose JavaScript opens an `EventSource` pointing at `GET /logs/<filename>/stream`.

`GET /logs/<filename>/stream` is a streaming Flask response:

```python
@logs_bp.route('/<filename>/stream')
def stream_log(filename):
    reader = LogReader(current_app.config['BENCH_ROOT'])
    def generate():
        for line in reader.stream_tail(filename):
            yield f"data: {line}\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

The JavaScript appends each `data:` line to a `<pre>` block and scrolls to the bottom. No library needed — `EventSource` is built into all modern browsers.

---

## Error handling

Views catch `ConfigError`, `FileNotFoundError`, and database connection errors and render a plain error page rather than a 500. This lets the admin remain usable even when the bench is partially broken.

---

## Security notes

- Bind to `127.0.0.1` by default.
- `LogReader.read_tail` and `stream_tail` validate that the requested filename contains no path separators and resolves to a file inside `logs/`. Any traversal attempt returns HTTP 400.
- The commands whitelist prevents arbitrary shell execution.
- Root MariaDB credentials come from `bench.yml` — the admin must be run by a user who can read that file.

---

## CLI command additions

Two additions to `bench2/cli.py`:

```python
@cli.command()
@click.option('--port', default=8001, help='Port to listen on')
@click.option('--host', default='127.0.0.1', help='Host to bind to')
def admin(port: int, host: str):
    """Start the admin web interface."""
    from bench2.admin.app import create_app
    app = create_app(bench_root=Path.cwd())
    app.run(host=host, port=port)
```

The admin is also listed as an optional entry in the generated Procfile/supervisor config (see commands.md — `bench init` step 12). It is commented out by default so it only starts when the user explicitly opts in.
