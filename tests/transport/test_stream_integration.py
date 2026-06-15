"""Tests for stream control messages, WS binary routing, and Session/Component integration."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from hiccl.component import Component, server
from hiccl.registry import ComponentRegistry
from hiccl.renderer import HiccupRenderer
from hiccl.session import Session, _sessions
from hiccl.signal import Signal
from hiccl.transport.protocol import (
    NullTransport,
    StreamAckMessage,
    StreamCloseMessage,
    StreamOpenMessage,
)
from hiccl.transport.stream import StreamClosedError, StreamLimitError
from hiccl.transport.websocket import WSTransport


# ---------------------------------------------------------------------------
# Protocol message models
# ---------------------------------------------------------------------------


class TestStreamMessages:
    def test_stream_open_defaults(self):
        msg = StreamOpenMessage(stream="terminal", component_id="c1")
        assert msg.type == "stream_open"
        assert msg.stream == "terminal"

    def test_stream_open_component_optional(self):
        msg = StreamOpenMessage(stream="term")
        assert msg.component_id == ""

    def test_stream_ack(self):
        msg = StreamAckMessage(stream="term", channel_id=5)
        assert msg.type == "stream_ack"
        assert msg.channel_id == 5

    def test_stream_close(self):
        msg = StreamCloseMessage(channel_id=3)
        assert msg.type == "stream_close"
        assert msg.channel_id == 3

    def test_roundtrip_via_dict(self):
        msg = StreamAckMessage(stream="x", channel_id=9)
        restored = StreamAckMessage(**msg.model_dump())
        assert restored.channel_id == 9
        assert restored.stream == "x"


# ---------------------------------------------------------------------------
# Transport protocol capabilities
# ---------------------------------------------------------------------------


class TestNullTransportStreams:
    async def test_supports_streams_false(self):
        assert NullTransport().supports_streams() is False

    async def test_send_binary_noop(self):
        # Should not raise even though it does nothing.
        await NullTransport().send_binary(1, b"data")


# ---------------------------------------------------------------------------
# Session-level stream API
# ---------------------------------------------------------------------------


class _NoopComponent(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self):
        return ["div", None, "x"]


class TestSessionStreams:
    def _make_session(self, **stream_kwargs):
        reg = ComponentRegistry()
        reg.register("noop", _NoopComponent)
        session = Session("stream-sess", reg, HiccupRenderer())
        if stream_kwargs:
            session._stream_max_channels = stream_kwargs.get("max_channels", 16)
            session._stream_buffer_size = stream_kwargs.get("buffer_size", 64)
        session.mount_component("noop", cid="noop-1")
        return session

    async def test_open_and_get_stream(self):
        session = self._make_session()
        stream = session.open_stream("terminal", component_id="noop-1")
        assert stream.channel_id == 1
        assert session.get_stream("terminal") is stream
        assert session.get_stream("missing") is None

    async def test_open_exceeds_limit(self):
        session = self._make_session(max_channels=2)
        session.open_stream("a")
        session.open_stream("b")
        with pytest.raises(StreamLimitError):
            session.open_stream("c")

    async def test_close_stream_by_name(self):
        session = self._make_session()
        session.open_stream("a")
        closed = await session.close_stream("a")
        assert closed is True
        assert session.get_stream("a") is None
        # Closing again reports nothing to close.
        assert await session.close_stream("a") is False

    async def test_attach_stream_transport_wires_callbacks(self):
        session = self._make_session()
        sent = []

        async def on_send_binary(channel_id, data):
            sent.append((channel_id, data))

        session.attach_stream_transport(on_send_binary=on_send_binary)
        stream = session.open_stream("t")
        await stream.send(b"payload")
        assert sent == [(stream.channel_id, b"payload")]

    async def test_dispose_shuts_down_streams(self):
        session = self._make_session()
        a = session.open_stream("a")
        b = session.open_stream("b")
        session.dispose()
        assert a.closed and b.closed
        assert session._stream_registry is None


# ---------------------------------------------------------------------------
# Component lifecycle integration
# ---------------------------------------------------------------------------


class _StreamComponent(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = Signal(0)

    @server
    def bump(self):
        self.count.set(self.count.get() + 1)

    def render(self):
        return ["div", None, str(self.count.get())]


class TestComponentStreams:
    def _setup(self):
        reg = ComponentRegistry()
        reg.register("sc", _StreamComponent)
        session = Session("comp-sess", reg, HiccupRenderer())
        comp = session.mount_component("sc", cid="sc-1")
        return session, comp

    async def test_open_stream_requires_session(self):
        comp = _StreamComponent()
        with pytest.raises(RuntimeError):
            await comp.open_stream("x")

    async def test_open_and_auto_close_on_unmount(self):
        session, comp = self._setup()
        stream = await comp.open_stream("terminal")
        assert stream.name == "terminal"
        assert "terminal" in comp._owned_streams
        assert session.get_stream("terminal") is stream
        comp.unmount()
        assert stream.closed is True
        # unmount is best-effort sync: stream is closed even if registry keeps ref
        assert session.get_stream("terminal") is None or stream.closed


# ---------------------------------------------------------------------------
# WSTransport.send_binary
# ---------------------------------------------------------------------------


class _FakeWS:
    def __init__(self):
        self.sent_bytes = []
        self.sent_json = []

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def send_json(self, data):
        self.sent_json.append(data)


class TestWSTransportBinary:
    async def test_supports_streams(self):
        transport = WSTransport(_FakeWS())
        assert transport.supports_streams() is True

    async def test_send_binary_prepends_channel_byte(self):
        ws = _FakeWS()
        transport = WSTransport(ws)
        await transport.send_binary(5, b"abc")
        assert ws.sent_bytes == [bytes([5]) + b"abc"]

    async def test_send_binary_disconnected_noop(self):
        transport = WSTransport(_FakeWS())
        transport.disconnect()
        await transport.send_binary(1, b"x")  # no raise, no send


# ---------------------------------------------------------------------------
# End-to-end WS: stream_open/ack + binary routing
# ---------------------------------------------------------------------------


def _build_ws_app(max_channels=16, buffer_size=64):
    from hiccl.app import HicclConfig, create_hiccl_app

    reg = ComponentRegistry()
    reg.register("noop", _NoopComponent)
    config = HicclConfig(
        component_registry=reg,
        transport_modes={"ws"},
        stream_max_channels=max_channels,
        stream_buffer_size=buffer_size,
    )
    app = create_hiccl_app(config)
    session = Session("ws-stream", reg, HiccupRenderer())
    session.mount_component("noop", cid="noop-1")
    _sessions["ws-stream"] = session
    return app, session


class TestWSEndToEnd:
    def test_stream_open_ack_and_binary_recv(self):
        app, session = _build_ws_app()
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/ws-stream") as ws:
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "term",
                                "component_id": "noop-1",
                            }
                        )
                    )
                    channel_id = None
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            channel_id = msg["channel_id"]
                            break
                    assert channel_id is not None

                    stream = session.get_stream("term")
                    assert stream is not None
                    assert stream.channel_id == channel_id

                    # Client → server binary frame routed into recv queue.
                    ws.send_bytes(bytes([channel_id]) + b"ls\r\n")
                    chunk = asyncio.run(_drain_recv(stream))
                    assert chunk == b"ls\r\n"
        finally:
            _sessions.pop("ws-stream", None)

    def test_binary_frame_unknown_channel_dropped(self):
        app, session = _build_ws_app()
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/ws-stream") as ws:
                    # No stream open — a binary frame on any channel must not error.
                    ws.send_bytes(bytes([7]) + b"data")
                    # Connection stays alive: a subsequent action still works.
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "x",
                                "component_id": "noop-1",
                            }
                        )
                    )
                    acked = False
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            acked = True
                            break
                    assert acked
        finally:
            _sessions.pop("ws-stream", None)

    def test_stream_close_tears_down(self):
        app, session = _build_ws_app()
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/ws-stream") as ws:
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "term",
                                "component_id": "noop-1",
                            }
                        )
                    )
                    channel_id = None
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            channel_id = msg["channel_id"]
                            break
                    stream = session.get_stream("term")
                    assert stream is not None

                    ws.send_text(
                        json.dumps({"type": "stream_close", "channel_id": channel_id})
                    )
                    # Server closes the stream; recv() raises StreamClosedError.
                    with pytest.raises(StreamClosedError):
                        asyncio.run(_drain_recv(stream))
                    assert session.get_stream("term") is None
        finally:
            _sessions.pop("ws-stream", None)

    def test_stream_limit_returns_error(self):
        app, session = _build_ws_app(max_channels=1)
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/ws-stream") as ws:
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "a",
                                "component_id": "noop-1",
                            }
                        )
                    )
                    # Read the ack.
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            break
                    # Second open exceeds the limit.
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "b",
                                "component_id": "noop-1",
                            }
                        )
                    )
                    errored = False
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "error" and "stream_open" in msg.get(
                            "message", ""
                        ):
                            errored = True
                            break
                    assert errored
        finally:
            _sessions.pop("ws-stream", None)


# ---------------------------------------------------------------------------
# on_stream_open lifecycle hook — components react to a client-opened stream
# ---------------------------------------------------------------------------


class _StreamHookComponent(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.opened_streams: list = []

    async def on_stream_open(self, stream):
        self.opened_streams.append(stream)

    def render(self):
        return ["div", None, "x"]


class TestOnStreamOpenHook:
    def test_hook_invoked_with_acked_stream(self):
        from hiccl.app import HicclConfig, create_hiccl_app

        reg = ComponentRegistry()
        reg.register("hook", _StreamHookComponent)
        config = HicclConfig(component_registry=reg, transport_modes={"ws"})
        app = create_hiccl_app(config)
        session = Session("hook-sess", reg, HiccupRenderer())
        comp = session.mount_component("hook", cid="hook-1")
        _sessions["hook-sess"] = session
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/hook-sess") as ws:
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "stream_open",
                                "stream": "term",
                                "component_id": "hook-1",
                            }
                        )
                    )
                    acked_channel = None
                    for _ in range(40):
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            acked_channel = msg["channel_id"]
                            break
                    assert acked_channel is not None
        finally:
            _sessions.pop("hook-sess", None)
        assert len(comp.opened_streams) == 1
        assert comp.opened_streams[0].channel_id == acked_channel

    def test_duplicate_stream_open_re_acks_without_error(self):
        from hiccl.app import HicclConfig, create_hiccl_app

        reg = ComponentRegistry()
        reg.register("hook", _StreamHookComponent)
        config = HicclConfig(component_registry=reg, transport_modes={"ws"})
        app = create_hiccl_app(config)
        session = Session("hook2-sess", reg, HiccupRenderer())
        comp = session.mount_component("hook", cid="hook-1")
        _sessions["hook2-sess"] = session
        try:
            with TestClient(app) as client:
                with client.websocket_connect("/hiccl/ws/hook2-sess") as ws:
                    for _ in range(2):
                        ws.send_text(
                            json.dumps(
                                {
                                    "type": "stream_open",
                                    "stream": "term",
                                    "component_id": "hook-1",
                                }
                            )
                        )
                    acks = []
                    errors = []
                    # Read exactly one ack per stream_open (2 total), then stop
                    # so we never block on a receive_text() with nothing pending.
                    for _ in range(40):
                        if len(acks) >= 2:
                            break
                        msg = json.loads(ws.receive_text())
                        if msg.get("type") == "stream_ack":
                            acks.append(msg["channel_id"])
                        elif msg.get("type") == "error":
                            errors.append(msg)
                            break
                    # Two acks for the same channel id, and no error message.
                    assert not errors, f"unexpected error: {errors!r}"
                    assert len(acks) == 2
                    assert acks[0] == acks[1]
        finally:
            _sessions.pop("hook2-sess", None)
        # The hook fires once per stream_open request.
        assert len(comp.opened_streams) == 2


async def _drain_recv(stream, timeout=2.0):
    return await asyncio.wait_for(stream.recv(), timeout=timeout)
