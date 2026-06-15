"""Tests for the WebShell example — real PTY over Hiccl streams.

These spawn real child processes in pseudo-terminals, so the whole module is
skipped on platforms without the stdlib ``pty`` module (i.e. Windows).
"""

import asyncio
import json
import os
import time

import pytest


pytest.importorskip("pty")  # PTY support is Unix-only

from examples.webshell import app as webshell  # noqa: E402
from hiccl.registry import ComponentRegistry  # noqa: E402
from hiccl.renderer import HiccupRenderer  # noqa: E402
from hiccl.session import Session  # noqa: E402


def _drain_fd(fd: int, needle: bytes, timeout: float = 2.0) -> bytes:
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline and needle not in buf:
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            chunk = b""
        if chunk:
            buf += chunk
        else:
            time.sleep(0.01)
    return buf


# ---------------------------------------------------------------------------
# PtyProcess — spawn, read, write, resize, kill
# ---------------------------------------------------------------------------


class TestPtyProcess:
    def test_spawn_echoes_output(self):
        proc = webshell.PtyProcess(["sh", "-c", "echo ptyworks"])
        proc.start()
        assert proc.pid is not None
        assert proc.master_fd is not None
        buf = _drain_fd(proc.master_fd, b"ptyworks")
        proc.kill()
        assert b"ptyworks" in buf

    def test_write_is_echoed_by_pty(self):
        proc = webshell.PtyProcess(["cat"])
        proc.start()
        try:
            os.write(proc.master_fd, b"writeme\n")
            buf = _drain_fd(proc.master_fd, b"writeme")
            assert b"writeme" in buf
        finally:
            proc.kill()

    def test_resize_does_not_raise(self):
        proc = webshell.PtyProcess(["sh", "-c", "sleep 1"])
        proc.start()
        proc.resize(rows=200, cols=50)
        assert proc.rows == 200 and proc.cols == 50
        proc.kill()

    def test_kill_reaps_process_and_closes_fd(self):
        proc = webshell.PtyProcess(["sh", "-c", "sleep 5"])
        proc.start()
        proc.kill()
        assert proc.master_fd is None
        assert proc.pid is None

    def test_kill_is_idempotent(self):
        proc = webshell.PtyProcess(["sh", "-c", "sleep 5"])
        proc.start()
        proc.kill()
        proc.kill()  # must not raise


# ---------------------------------------------------------------------------
# parse_terminal_frame — keystroke vs 0xFF resize control framing
# ---------------------------------------------------------------------------


class TestParseTerminalFrame:
    def test_plain_data_passes_through(self):
        assert webshell.parse_terminal_frame(b"ls\r\n") == ("data", b"ls\r\n")

    def test_resize_control_frame(self):
        payload = (
            bytes([0xFF])
            + json.dumps({"type": "resize", "cols": 120, "rows": 40}).encode()
        )
        assert webshell.parse_terminal_frame(payload) == ("resize", (40, 120))

    def test_malformed_control_degrades_to_empty_data(self):
        assert webshell.parse_terminal_frame(b"\xffnotjson") == ("data", b"")
        assert webshell.parse_terminal_frame(b"\xff") == ("data", b"")

    def test_empty_frame_is_data(self):
        assert webshell.parse_terminal_frame(b"") == ("data", b"")

    def test_normal_keystroke_starting_with_high_byte_is_data(self):
        # A real keystroke never starts with 0xFF (invalid UTF-8 lead byte),
        # but bytes like 0xC3 (Ã) are normal UTF-8 leads and must stay data.
        assert webshell.parse_terminal_frame(b"\xc3\xa9") == ("data", b"\xc3\xa9")


# ---------------------------------------------------------------------------
# WebShellComponent — PTY output/input flows over a Hiccl stream
# ---------------------------------------------------------------------------


def _make_webshell_session(monkeypatch, command: str):
    monkeypatch.setenv("HICCL_SHELL_CMD", command)
    reg = ComponentRegistry()
    reg.register("wsh", webshell.WebShellComponent)
    session = Session("wsh-sess", reg, HiccupRenderer())
    comp = session.mount_component("wsh", cid="wsh-1")
    sent: list[bytes] = []

    async def on_send_binary(channel_id, data):
        sent.append(bytes(data))

    session.attach_stream_transport(on_send_binary=on_send_binary)
    stream = session.open_stream("terminal", component_id="wsh-1")
    return session, comp, stream, sent


class TestWebShellComponent:
    async def test_pty_output_streams_to_client(self, monkeypatch):
        session, comp, stream, sent = _make_webshell_session(
            monkeypatch, 'sh -c "printf WEBPING"'
        )
        try:
            await comp.on_stream_open(stream)
            found = False
            for _ in range(80):
                if any(b"WEBPING" in chunk for chunk in sent):
                    found = True
                    break
                await asyncio.sleep(0.05)
            assert found, f"WEBPING not streamed, got {sent!r}"
        finally:
            comp.unmount()
            session.dispose()

    async def test_client_input_reaches_pty(self, monkeypatch):
        session, comp, stream, sent = _make_webshell_session(monkeypatch, "cat")
        try:
            await comp.on_stream_open(stream)
            # Let cat start, then feed a keystroke as the WS router would.
            await asyncio.sleep(0.15)
            stream._feed(b"greetz\n")
            found = False
            for _ in range(80):
                if any(b"greetz" in chunk for chunk in sent):
                    found = True
                    break
                await asyncio.sleep(0.05)
            assert found, f"greetz not echoed back, got {sent!r}"
        finally:
            comp.unmount()
            session.dispose()

    async def test_resize_control_frame_resizes_pty(self, monkeypatch):
        session, comp, stream, _ = _make_webshell_session(
            monkeypatch, 'sh -c "sleep 1"'
        )
        try:
            await comp.on_stream_open(stream)
            await asyncio.sleep(0.1)
            assert comp.pty is not None
            payload = (
                bytes([0xFF])
                + json.dumps({"type": "resize", "cols": 177, "rows": 33}).encode()
            )
            stream._feed(payload)
            await asyncio.sleep(0.1)
            assert comp.pty.cols == 177
            assert comp.pty.rows == 33
        finally:
            comp.unmount()
            session.dispose()

    async def test_unmount_kills_pty(self, monkeypatch):
        session, comp, stream, _ = _make_webshell_session(
            monkeypatch, 'sh -c "sleep 5"'
        )
        try:
            await comp.on_stream_open(stream)
            await asyncio.sleep(0.1)
            pty = comp.pty
            assert pty is not None and pty.master_fd is not None
            comp.unmount()
            assert comp.pty is None
            assert pty.master_fd is None
        finally:
            session.dispose()

    async def test_stream_close_tears_down_pty(self, monkeypatch):
        # Simulate a client disconnect: closing the stream should reap the PTY
        # even while it is idle (no output pending).
        session, comp, stream, _ = _make_webshell_session(
            monkeypatch, 'sh -c "sleep 5"'
        )
        try:
            await comp.on_stream_open(stream)
            await asyncio.sleep(0.1)
            assert comp.pty is not None
            await stream.close()
            # The watchdog tears down on the FIRST pump finishing; give it a beat.
            for _ in range(60):
                if comp.pty is None:
                    break
                await asyncio.sleep(0.05)
            assert comp.pty is None, "PTY not reaped after stream close"
        finally:
            comp.unmount()
            session.dispose()


# ---------------------------------------------------------------------------
# End-to-end through the real FastAPI app is verified manually (see the module
# docstring) rather than under pytest: the WS handler runs in Starlette's
# TestClient portal thread, and os.fork()-ing the PTY there deadlocks against
# pytest-timeout's watcher thread. The three layers above already exercise the
# real transport (WS binary routing in test_stream_integration, the
# on_stream_open hook) and the real PTY pump independently and deterministically.
# ---------------------------------------------------------------------------
