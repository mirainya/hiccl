"""Tests for hiccl.transport.sse — SSE handler."""

import asyncio

from hiccl.component import Component
from hiccl.registry import ComponentRegistry
from hiccl.renderer import HiccupRenderer
from hiccl.session import Session


class _Noop(Component):
    def render(self):
        return ["div", None, "x"]


def _make_session() -> Session:
    registry = ComponentRegistry()
    registry.register("noop", _Noop)
    session = Session("sse-sess", registry, HiccupRenderer())
    session.mount_component("noop", cid="noop-1")
    return session


class TestSSETransport:
    def test_sse_invalid_session(self):
        """Verify SSE returns 404 for non-existent session."""
        from fastapi.testclient import TestClient

        from hiccl.app import HicclConfig, create_hiccl_app

        registry = ComponentRegistry()
        config = HicclConfig(
            component_registry=registry,
            transport_modes={"sse"},
        )
        app = create_hiccl_app(config)

        with TestClient(app) as client:
            resp = client.get("/hiccl/sse/invalid-session")
            assert resp.status_code == 404

    def test_sse_route_exists(self):
        """Verify the SSE route is registered."""
        from hiccl.app import HicclConfig, create_hiccl_app

        registry = ComponentRegistry()
        config = HicclConfig(
            component_registry=registry,
            transport_modes={"sse"},
        )
        app = create_hiccl_app(config)

        # Check that the SSE route exists in the app routes
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert any("/hiccl/sse/" in r for r in routes)


class TestSSETransportBinary:
    async def test_supports_streams(self):
        from hiccl.transport.sse import SSETransport

        transport = SSETransport(asyncio.Queue())
        assert transport.supports_streams() is True

    async def test_send_binary_emits_hiccl_stream_event(self):
        import base64
        import json

        from hiccl.transport.sse import SSETransport

        queue: asyncio.Queue = asyncio.Queue()
        transport = SSETransport(queue)
        await transport.send_binary(5, b"hello")
        event = queue.get_nowait()
        assert event.startswith("event: hiccl-stream\ndata: ")
        payload = json.loads(event.split("data: ", 1)[1].strip())
        assert payload["channel_id"] == 5
        assert base64.b64decode(payload["data"]) == b"hello"

    async def test_send_binary_disconnected_noop(self):
        from hiccl.transport.sse import SSETransport

        queue: asyncio.Queue = asyncio.Queue()
        transport = SSETransport(queue)
        transport.disconnect()
        await transport.send_binary(1, b"x")
        assert queue.empty()

    async def test_send_binary_empty_payload(self):
        import json

        from hiccl.transport.sse import SSETransport

        queue: asyncio.Queue = asyncio.Queue()
        transport = SSETransport(queue)
        await transport.send_binary(2, b"")
        event = queue.get_nowait()
        payload = json.loads(event.split("data: ", 1)[1].strip())
        assert payload["channel_id"] == 2
        assert payload["data"] == ""


class TestSSEStreamWiring:
    """The SSE endpoint attaches the stream registry on connect.

    We exercise the endpoint's registry-wiring path directly (rather than via a
    streaming GET, which the synchronous TestClient cannot keep open) by invoking
    the same code the handler runs: ``session.attach_stream_transport`` with the
    SSE transport's ``send_binary``. Combined with the SSETransport unit tests,
    this covers the full Stream.send() → hiccl-stream event path.
    """

    async def test_attach_emits_hiccl_stream_via_send_binary(self):
        from hiccl.transport.sse import SSETransport

        queue: asyncio.Queue = asyncio.Queue()
        transport = SSETransport(queue)
        session = _make_session()
        session.attach_stream_transport(on_send_binary=transport.send_binary)
        stream = session.open_stream("term", component_id="noop-1")
        await stream.send(b"payload")
        event = queue.get_nowait()
        assert event.startswith("event: hiccl-stream\ndata: ")
        assert session.get_stream("term") is stream
