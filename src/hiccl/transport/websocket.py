"""Hiccl WebSocket transport — real-time bidirectional handler."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from hiccl.session import Session

router = APIRouter()


# ---------------------------------------------------------------------------
# WS Transport adapter
# ---------------------------------------------------------------------------


class WSTransport:
    """Transport that pushes patches through a WebSocket connection.

    Carries two logical channels over one WebSocket connection:

        * text frames   → hiccl JSON control protocol (patches, actions, …)
        * binary frames → multiplexed raw byte streams (see ``stream.py``)

    Binary frames are prefixed with a single ``channel_id`` byte (1-255).
    """

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._connected = True

    async def push(self, patches: list[dict]) -> None:
        if self._connected:
            try:
                await self._ws.send_json({"type": "batch", "patches": patches})
            except Exception:
                self._connected = False

    async def send_binary(self, channel_id: int, data: bytes) -> None:
        """Send a raw payload on a stream channel as a binary WebSocket frame."""
        if not self._connected:
            return
        frame = bytes([channel_id]) + data
        try:
            await self._ws.send_bytes(frame)
        except Exception:
            self._connected = False

    def supports_streams(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


def _make_stream_close_sender(websocket: WebSocket, transport: WSTransport):
    """Return an async callback that emits a ``stream_close`` control message."""

    async def _send_close(channel_id: int) -> None:
        if not transport.is_connected():
            return
        try:
            await websocket.send_json(
                {"type": "stream_close", "channel_id": channel_id}
            )
        except Exception:
            transport.disconnect()

    return _send_close


def _route_binary(session: "Session", raw: bytes) -> None:
    """Dispatch an inbound binary frame to the stream that owns its channel id."""
    channel_id = raw[0]
    payload = raw[1:]
    registry = getattr(session, "_stream_registry", None)
    if registry is None:
        return
    stream = registry.get(channel_id)
    if stream is not None and not stream.closed:
        stream._feed(payload)


async def _handle_stream_open(
    websocket: WebSocket, transport: WSTransport, session: "Session", message: dict
) -> None:
    """Process a ``stream_open`` control message: create a Stream + ack.

    Idempotent: if a stream with the same name already exists (e.g. a client
    re-requesting the same logical stream), the existing channel is re-acked
    instead of erroring. After acking, the owning component's optional
    ``on_stream_open`` hook is invoked so it can attach data pumps.
    """
    registry = getattr(session, "_stream_registry", None)
    if registry is None or not transport.is_connected():
        return
    name = message.get("stream", "")
    component_id = message.get("component_id", "")
    stream = registry.find(name)
    if stream is None:
        try:
            stream = registry.open(name, component_id=component_id or None)
        except Exception as e:
            if transport.is_connected():
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"stream_open failed: {e}",
                        "status": 400,
                    }
                )
            return
    if transport.is_connected():
        await websocket.send_json(
            {"type": "stream_ack", "stream": name, "channel_id": stream.channel_id}
        )
    # Notify the owning component so it can attach data pumps (e.g. a PTY).
    if component_id:
        component = session.get_component(component_id)
        if component is not None:
            result = component.on_stream_open(stream)
            if asyncio.iscoroutine(result):
                await result


async def _handle_stream_close(session: "Session", message: dict) -> None:
    """Process a ``stream_close`` control message from the client."""
    registry = getattr(session, "_stream_registry", None)
    if registry is None:
        return
    channel_id = message.get("channel_id")
    if isinstance(channel_id, int):
        await registry.close(channel_id)


@router.websocket("/hiccl/ws/{session_id}")
async def hiccl_websocket(websocket: WebSocket, session_id: str):
    """WebSocket handler for real-time component updates.

    Flow:
        1. Accept connection, set up WSTransport + RenderScheduler.
        2. Signal changes → RenderScheduler → render dirty → push via WS.
        3. EventBus messages → on_broadcast → signal changes → same flow.
        4. Incoming JSON actions → execute_action → auto-publish to EventBus.
        5. On disconnect: session is NOT immediately disposed (supports reconnect).
    """
    import logging

    from hiccl.scheduler import RenderScheduler
    from hiccl.transport.protocol import NullTransport

    logger = logging.getLogger("hiccl.transport.websocket")

    await websocket.accept()

    hiccl_state = getattr(websocket.app.state, "hiccl", {})
    session_store = (
        hiccl_state.get("session_store") if isinstance(hiccl_state, dict) else None
    )
    session = await session_store.get(session_id) if session_store else None

    if session is None:
        await websocket.close(code=4404, reason="Session not found")
        return

    transport = WSTransport(websocket)
    session.transport = transport

    config = hiccl_state.get("config") if isinstance(hiccl_state, dict) else None
    coalesce_ms = getattr(config, "scheduler_coalesce_ms", 0.0) if config else 0.0
    scheduler = RenderScheduler(coalesce_ms=coalesce_ms)

    # Wire up stream registry to this transport so that Stream.send() emits
    # binary frames and Stream.close() notifies the client via stream_close.
    stream_enabled = getattr(config, "stream_enabled", True) if config else True
    if stream_enabled:
        max_channels = getattr(config, "stream_max_channels", 16) if config else 16
        buffer_size = getattr(config, "stream_buffer_size", 64) if config else 64
        session.attach_stream_transport(
            on_send_binary=transport.send_binary,
            on_stream_close=_make_stream_close_sender(websocket, transport),
            max_channels=max_channels,
            buffer_size=buffer_size,
        )

    try:
        for comp in list(session._components.values()):
            if not comp._effects:
                session.renderer.render_component(comp)
    except Exception as e:
        logger.warning("Initial render failed for session %s: %s", session_id, e)

    def wrap_mark_dirty(comp_id: str) -> None:
        scheduler.mark_dirty(comp_id)
        if comp_id != "time-travel-panel-main" and session.get_component(
            "time-travel-panel-main"
        ):
            scheduler.mark_dirty("time-travel-panel-main")

    session.on_signal_change = wrap_mark_dirty

    async def render_fn(dirty_ids: set[str]) -> list[dict]:
        patches = []
        for cid in dirty_ids:
            component = session.get_component(cid)
            if component is None:
                continue
            html = session.renderer.render_component_cached(component)
            if html is None:
                continue
            patches.append(
                {
                    "type": "patch",
                    "component_id": cid,
                    "html": html,
                    "swap": "outerHTML",
                }
            )
        return patches

    async def push_fn(patches: list[dict]) -> None:
        if patches and transport.is_connected():
            await transport.push(patches)

    scheduler.start(asyncio.get_running_loop(), render_fn, push_fn)

    try:
        while transport.is_connected():
            # Process EventBus events → on_broadcast → signal changes
            await session.process_eventbus_events()

            # Wait for incoming messages with a timeout to allow EventBus processing.
            # Use receive() (not receive_json()) so we can dispatch both text
            # (JSON control protocol) and binary (stream data) frames.
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception:
                break

            # Binary frame → route raw payload to the owning stream by channel id.
            if "bytes" in message and message["bytes"] is not None:
                raw = message["bytes"]
                if raw:
                    _route_binary(session, raw)
                continue

            # Text frame → JSON control protocol.
            text = message.get("text")
            if text is None:
                continue
            try:
                message = json.loads(text)
            except (ValueError, TypeError):
                continue

            msg_type = message.get("type")

            if msg_type == "action":
                cid = message.get("component_id", "")
                method = message.get("method", "")
                args = message.get("args", {})
                try:
                    await session.execute_action(cid, method, args)
                except Exception as e:
                    if transport.is_connected():
                        await websocket.send_json(
                            {
                                "type": "error",
                                "component_id": cid,
                                "message": str(e),
                                "status": 500,
                            }
                        )

            elif msg_type == "stream_open":
                await _handle_stream_open(websocket, transport, session, message)

            elif msg_type == "stream_close":
                await _handle_stream_close(session, message)

            elif msg_type == "reconnect":
                # Client is reconnecting — re-send all component HTML
                patches = []
                for cid, comp in session._components.items():
                    html = session.renderer.render_component(comp)
                    patches.append(
                        {
                            "type": "patch",
                            "component_id": cid,
                            "html": html,
                            "swap": "outerHTML",
                        }
                    )
                if patches and transport.is_connected():
                    await transport.push(patches)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        transport.disconnect()
        if session.transport is transport:
            session.transport = NullTransport()
        if session.on_signal_change is wrap_mark_dirty:
            session.on_signal_change = None
        await scheduler.stop()
        # Tear down any streams that were open on this connection.
        registry = getattr(session, "_stream_registry", None)
        if registry is not None:
            await registry.close_all()
        # Note: session is NOT disposed here to support reconnect
        # Session cleanup happens via app shutdown or timeout
