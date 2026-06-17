"""WSGI entrypoint for running the admin under gunicorn.

The bench root is passed via the BENCH_ADMIN_ROOT environment variable (set by
the systemd service unit) since gunicorn imports a module-level callable rather
than invoking a main() with argv.
"""

from __future__ import annotations

import os
from pathlib import Path

from admin.backend.app import create_app

application = create_app(Path(os.environ["BENCH_ADMIN_ROOT"]))
