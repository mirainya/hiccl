"""Hiccl SSE transport — Server-Sent Events handler with real-time push."""

from __future__ import annotations

import asyncio
import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter()


# ---------------------------------------------------------------------------
# SSE Transport adapter
# ---------------------------------------------------------------------------


class SSETransport:
    """Transport that pushes patches via an asyncio.Queue (consumed by SSE stream).

    SSE cannot carry binary frames, so stream payloads are base64-encoded and
    emitted as ``event: hiccl-stream`` messages. This makes streams effectively
    server→client only over SSE; client→server traffic must fall back to HTTP.
    """

    def __init__(self, queue: asyncio.Queue) -> None:
        self._queue = queue
        self._connected = True

    async def push(self, patches: list[dict]) -> None:
        data = json.dumps({"type": "batch", "patches": patches})
        await self._queue.put(f"event: hiccl\ndata: {data}\n\n")

    async def send_binary(self, channel_id: int, data: bytes) -> None:
        if not self._connected:
            return
        encoded = base64.b64encode(data).decode("ascii")
        payload = json.dumps({"channel_id": channel_id, "data": encoded})
        await self._queue.put(f"event: hiccl-stream\ndata: {payload}\n\n")

    def supports_streams(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return self._connected

    def disconnect(self) -> None:
        self._connected = False


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------


async def get_session_sse(session_id: str, request: Request):
    """Dependency: look up session from URL path."""
    hiccl_state = getattr(request.app.state, "hiccl", {})
    session_store = (
        hiccl_state.get("session_store") if isinstance(hiccl_state, dict) else None
    )

    session = await session_store.get(session_id) if session_store else None
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/hiccl/sse/{session_id}")
async def hiccl_sse(
    session_id: str, request: Request, session=Depends(get_session_sse)
):
    """SSE endpoint — streams component updates to the client.

    Flow:
        1. Create SSETransport + RenderScheduler for this session.
        2. Signal changes → RenderScheduler → render dirty → push via SSE.
        3. EventBus messages → on_broadcast → signal changes → same flow.
        4. Heartbeat every 15 s for keepalive.
    """
    from hiccl.scheduler import RenderScheduler

    sse_queue: asyncio.Queue[str] = asyncio.Queue()
    transport = SSETransport(sse_queue)
    session.transport = transport

    hiccl_state = getattr(request.app.state, "hiccl", {})
    config = hiccl_state.get("config") if isinstance(hiccl_state, dict) else None
    coalesce_ms = getattr(config, "scheduler_coalesce_ms", 0.0) if config else 0.0
    scheduler = RenderScheduler(coalesce_ms=coalesce_ms)

    # Wire up the stream registry to this SSE transport so that Stream.send()
    # emits base64-encoded hiccl-stream events. Note: stream_open/close control
    # messages from the client still arrive over HTTP (SSE is server→client only).
    stream_enabled = getattr(config, "stream_enabled", True) if config else True
    if stream_enabled:
        max_channels = getattr(config, "stream_max_channels", 16) if config else 16
        buffer_size = getattr(config, "stream_buffer_size", 64) if config else 64
        session.attach_stream_transport(
            on_send_binary=transport.send_binary,
            on_stream_close=None,
            max_channels=max_channels,
            buffer_size=buffer_size,
        )

    # Force a silent initial render of all mounted components that don't have active effects
    # to register all reactive effects, subscription watches, and setup their dependency tracking
    # while session.on_signal_change is STILL None. This prevents any render-phase signal modifications
    # from triggering recursive dirty marking or infinite scheduler loops.
    for comp in list(session._components.values()):
        if not comp._effects:
            session.renderer.render_component(comp)

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
            comp = session.get_component(cid)
            if comp is None:
                continue
            html = session.renderer.render_component_cached(comp)
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
        if patches:
            data = json.dumps({"type": "batch", "patches": patches})
            await sse_queue.put(f"event: hiccl\ndata: {data}\n\n")

    async def event_stream():
        import time

        loop = asyncio.get_running_loop()
        scheduler.start(loop, render_fn, push_fn)
        heartbeat_interval = 15  # seconds
        last_heartbeat = 0.0
        try:
            while transport.is_connected():
                # Drain SSE queue (rendered patches)
                while not sse_queue.empty():
                    try:
                        event = sse_queue.get_nowait()
                        yield event
                    except asyncio.QueueEmpty:
                        break

                # Process EventBus → on_broadcast → signal changes → scheduler
                await session.process_eventbus_events()

                # Throttled heartbeat
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_interval:
                    yield "event: heartbeat\ndata: \n\n"
                    last_heartbeat = now

                await asyncio.sleep(0.05)  # 20 Hz check rate
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            transport.disconnect()
            from hiccl.transport.protocol import NullTransport

            if session.transport is transport:
                session.transport = NullTransport()
            if session.on_signal_change is wrap_mark_dirty:
                session.on_signal_change = None
            await scheduler.stop()
            # Tear down any streams that were open on this SSE connection.
            registry = getattr(session, "_stream_registry", None)
            if registry is not None:
                await registry.close_all()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
