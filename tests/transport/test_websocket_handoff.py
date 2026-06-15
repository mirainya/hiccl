"""Regression tests for WebSocket connection handoff on a shared session.

When a user navigates between pages that reuse the same session cookie, a new
WebSocket connection attaches to the *same* ``Session`` object while the old
connection may still be open. The old connection's disconnect handler must not
clobber the transport / ``on_signal_change`` slot that the new connection now
owns — otherwise live updates silently stop reaching the client.
"""

import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed

from hiccl import (
    Component,
    ComponentRegistry,
    HicclConfig,
    create_hiccl_app,
    server,
    signal,
)
from hiccl.renderer import HiccupRenderer
from hiccl.session import Session, _sessions


class HandoffCounter(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = signal(0)

    @server
    def increment(self):
        self.count.set(self.count.get() + 1)

    def render(self):
        return ["div", None, f"Count: {self.count.get()}"]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"server on port {port} did not start")


@pytest.fixture
def live_ws_server():
    port = _free_port()
    registry = ComponentRegistry()
    registry.register("handoff-counter", HandoffCounter)
    config = HicclConfig(component_registry=registry, transport_modes={"ws"})
    app = create_hiccl_app(config)

    session = Session("ws-handoff", registry, HiccupRenderer())
    session.mount_component("handoff-counter", cid="handoff-1")
    _sessions["ws-handoff"] = session

    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(cfg)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_port(port)
    try:
        yield f"ws://127.0.0.1:{port}/hiccl/ws/ws-handoff"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        _sessions.pop("ws-handoff", None)


async def _drain(ws, timeout: float = 0.25):
    out = []
    while True:
        try:
            out.append(await asyncio.wait_for(ws.recv(), timeout=timeout))
        except asyncio.TimeoutError:
            break
    return out


@pytest.mark.timeout(30)
class TestWSConnectionHandoff:
    async def test_new_connection_survives_stale_disconnect(self, live_ws_server):
        url = live_ws_server

        ws_a = await websockets.connect(url)
        await _drain(ws_a)

        ws_b = await websockets.connect(url)
        await _drain(ws_b)

        await ws_a.close()
        await asyncio.sleep(0.4)

        await ws_b.send(
            json.dumps(
                {
                    "type": "action",
                    "component_id": "handoff-1",
                    "method": "increment",
                    "args": {},
                }
            )
        )

        received = []
        for _ in range(10):
            try:
                received.append(await asyncio.wait_for(ws_b.recv(), timeout=0.4))
            except asyncio.TimeoutError:
                break
            except ConnectionClosed:
                break

        blob = " ".join(str(m) for m in received)
        assert "Count: 1" in blob, (
            f"new WS received no update after handoff: {received}"
        )
        await ws_b.close()
