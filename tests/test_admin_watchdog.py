"""Tests for the socket-activated admin's idle watchdog (admin.backend.app)."""
from __future__ import annotations

import signal
from unittest.mock import patch

from admin.backend.app import _install_idle_watchdog


class _FakeApp:
    def __init__(self) -> None:
        self.before_request_funcs: list = []

    def before_request(self, fn):
        self.before_request_funcs.append(fn)
        return fn


def test_watchdog_noop_without_env(monkeypatch) -> None:
    monkeypatch.delenv("BENCH_ADMIN_IDLE_TIMEOUT", raising=False)
    app = _FakeApp()
    with patch("threading.Thread") as thread:
        _install_idle_watchdog(app)
    thread.assert_not_called()
    assert app.before_request_funcs == []


def test_watchdog_noop_when_timeout_not_positive(monkeypatch) -> None:
    monkeypatch.setenv("BENCH_ADMIN_IDLE_TIMEOUT", "0")
    app = _FakeApp()
    with patch("threading.Thread") as thread:
        _install_idle_watchdog(app)
    thread.assert_not_called()


def test_watchdog_registers_touch_and_thread(monkeypatch) -> None:
    monkeypatch.setenv("BENCH_ADMIN_IDLE_TIMEOUT", "60")
    app = _FakeApp()
    with patch("threading.Thread") as thread:
        _install_idle_watchdog(app)
    assert len(app.before_request_funcs) == 1
    thread.assert_called_once()
    assert thread.call_args.kwargs.get("daemon") is True


def test_watchdog_kills_parent_after_idle(monkeypatch) -> None:
    monkeypatch.setenv("BENCH_ADMIN_IDLE_TIMEOUT", "60")
    app = _FakeApp()
    captured: dict = {}

    def fake_thread(target=None, daemon=None):
        captured["target"] = target

        class _T:
            def start(self_inner):
                pass

        return _T()

    # time advances past the timeout on the first sleep; getppid → arbiter.
    times = iter([0.0, 1000.0])
    with patch("threading.Thread", side_effect=fake_thread), patch(
        "admin.backend.app.time.monotonic", side_effect=lambda: next(times)
    ), patch("admin.backend.app.time.sleep"), patch(
        "admin.backend.app.os.getppid", return_value=4242
    ), patch("admin.backend.app.os.kill") as kill:
        _install_idle_watchdog(app)
        captured["target"]()

    kill.assert_called_once_with(4242, signal.SIGTERM)
