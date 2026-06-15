"""Smoke tests for the WebShell example module.

The heavy PTY/stream behavior is covered in ``tests/transport/test_webshell.py``;
these just guard that the example imports cleanly and exposes its public surface.
"""

from examples.webshell import app as webshell


def test_module_public_surface():
    assert hasattr(webshell, "app")
    assert hasattr(webshell, "WebShellComponent")
    assert hasattr(webshell, "PtyProcess")
    assert hasattr(webshell, "parse_terminal_frame")
    assert hasattr(webshell, "detect_command")
    assert callable(webshell.parse_terminal_frame)


def test_app_has_ws_route():
    routes = [r.path for r in webshell.app.routes if hasattr(r, "path")]
    assert "/hiccl/ws/{session_id}" in routes


def test_detect_command_returns_nonempty_argv(monkeypatch):
    monkeypatch.setenv("HICCL_SHELL_CMD", "echo hello")
    cmd = webshell.detect_command()
    assert cmd == ["echo", "hello"]


def test_detect_command_falls_back_to_shell(monkeypatch):
    monkeypatch.delenv("HICCL_SHELL_CMD", raising=False)
    cmd = webshell.detect_command()
    assert isinstance(cmd, list) and len(cmd) >= 1
