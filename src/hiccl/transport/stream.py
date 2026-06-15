"""Hiccl stream transport — multiplexed raw byte channels over WebSocket binary frames.

A ``Stream`` is a bidirectional raw byte channel multiplexed onto a single
WebSocket connection. Text frames continue to carry the hiccl JSON control
protocol (unchanged); binary frames carry raw payloads prefixed with a single
``channel_id`` byte (1-255). ``Channel 0`` is reserved.

This module is deliberately transport-agnostic: ``Stream`` / ``StreamRegistry``
only know about ``asyncio.Queue`` backpressure. The transport layer
(``WSTransport`` / ``SSETransport``) is responsible for actually moving bytes
on and off the wire and for routing inbound binary frames into the right
stream via ``StreamRegistry.get``.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class StreamError(Exception):
    """Base class for all stream-related errors."""


class StreamClosedError(StreamError):
    """Raised when operating on a stream that has been closed."""


class StreamLimitError(StreamError):
    """Raised when a session exceeds its maximum number of concurrent streams."""


# Sentinel placed on the recv queue to signal remote / local close.
_CLOSE_SENTINEL: Any = object()


# ---------------------------------------------------------------------------
# Stream — a single bidirectional raw data channel
# ---------------------------------------------------------------------------


class Stream:
    """A single bidirectional raw byte channel multiplexed onto a connection.

    Directional convention (relative to the server-side ``Stream`` object):

        ``send(data)``  → pushes bytes toward the client (server→client).
        ``recv()``      → pulls bytes received from the client (client→server).

    Backpressure is provided by two bounded ``asyncio.Queue`` instances. When
    the send queue is full, ``send()`` blocks until the transport drains it;
    when the recv queue is full, the inbound router blocks — giving natural
    flow control with no dropped frames.
    """

    def __init__(
        self,
        channel_id: int,
        name: str,
        component_id: str | None = None,
        buffer_size: int = 64,
        on_close: "Callable[[], Awaitable[None]] | None" = None,
        on_send: "Callable[[bytes], Awaitable[None]] | None" = None,
    ) -> None:
        if not (1 <= channel_id <= 255):
            raise ValueError(f"channel_id must be in 1..255, got {channel_id}")
        self.channel_id: int = channel_id
        self.name: str = name
        self.component_id: str | None = component_id
        self.closed: bool = False
        self._on_close = on_close
        self._on_send = on_send
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=buffer_size)
        self._recv_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=buffer_size)

    # -- client direction (server → client) --------------------------------

    async def send(self, data: bytes) -> None:
        """Queue ``data`` for delivery to the client.

        Blocks if the send buffer is full (backpressure). Raises
        ``StreamClosedError`` if the stream is already closed.
        """
        if self.closed:
            raise StreamClosedError(f"stream {self.name!r} is closed")
        await self._send_queue.put(data)
        if self._on_send is not None:
            await self._on_send(data)

    # -- server direction (client → server) --------------------------------

    async def recv(self) -> bytes:
        """Return the next data chunk received from the client.

        Raises ``StreamClosedError`` once the stream is closed and all queued
        data has been drained.
        """
        while True:
            item = await self._recv_queue.get()
            if item is _CLOSE_SENTINEL:
                self.closed = True
                raise StreamClosedError(f"stream {self.name!r} is closed")
            return item

    def _feed(self, data: bytes) -> None:
        """Internal: route an inbound binary payload into the recv queue."""
        if self.closed:
            return
        self._recv_queue.put_nowait(data)

    # -- async iteration ----------------------------------------------------

    def __aiter__(self) -> "Stream":
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except StreamClosedError:
            raise StopAsyncIteration from None

    # -- close --------------------------------------------------------------

    async def close(self) -> None:
        """Close the stream and notify the peer via a stream_close message.

        Idempotent: closing an already-closed stream is a no-op.
        """
        if self.closed:
            return
        self.closed = True
        # Unblock any pending recv() consumers.
        self._recv_queue.put_nowait(_CLOSE_SENTINEL)
        # Drain + drop any buffered outbound data so blocked send() callers wake.
        self._drain_send_queue()
        if self._on_close is not None:
            try:
                await self._on_close()
            except Exception:
                pass

    def _drain_send_queue(self) -> None:
        """Wake any coroutine blocked on ``send()`` by emptying the queue."""
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def close_sync(self) -> None:
        """Synchronously mark the stream closed without transport callbacks.

        Used for shutdown paths that run outside an event loop (component
        ``unmount``, session ``dispose``). The async ``close()`` remains
        preferred because it also notifies the peer.
        """
        if self.closed:
            return
        self.closed = True
        self._recv_queue.put_nowait(_CLOSE_SENTINEL)
        self._drain_send_queue()

    def __repr__(self) -> str:
        state = "closed" if self.closed else "open"
        return f"Stream(channel_id={self.channel_id}, name={self.name!r}, {state})"


# ---------------------------------------------------------------------------
# StreamRegistry — per-session stream manager
# ---------------------------------------------------------------------------


class StreamRegistry:
    """Tracks all open streams for a single session.

    Allocates ``channel_id`` values starting from 1, recycles freed ids, and
    enforces a per-session concurrency cap (``max_channels``).
    """

    def __init__(
        self,
        max_channels: int = 16,
        buffer_size: int = 64,
        on_send_binary: "Callable[[int, bytes], Awaitable[None]] | None" = None,
        on_stream_close: "Callable[[int], Awaitable[None]] | None" = None,
    ) -> None:
        self.max_channels: int = max_channels
        self.buffer_size: int = buffer_size
        self._streams: dict[int, Stream] = {}
        self._free_ids: list[int] = []
        self._next_id: int = 1
        self._on_send_binary = on_send_binary
        self._on_stream_close = on_stream_close

    def get(self, channel_id: int) -> Stream | None:
        """Look up a stream by channel id, or ``None`` if not found."""
        return self._streams.get(channel_id)

    def find(self, name: str) -> Stream | None:
        """Look up a stream by logical name, or ``None`` if not found."""
        for stream in self._streams.values():
            if stream.name == name:
                return stream
        return None

    def all(self) -> list[Stream]:
        """Return a snapshot of all currently-open streams."""
        return list(self._streams.values())

    def __len__(self) -> int:
        return len(self._streams)

    def __bool__(self) -> bool:
        return bool(self._streams)

    def open(
        self,
        name: str,
        component_id: str | None = None,
    ) -> Stream:
        """Allocate a channel id and create a new open ``Stream``.

        Raises ``StreamLimitError`` if the session already has ``max_channels``
        open streams. Raises ``ValueError`` if a stream with the same ``name``
        is already open.
        """
        if self.find(name) is not None:
            raise ValueError(f"a stream named {name!r} is already open")
        if len(self._streams) >= self.max_channels:
            raise StreamLimitError(
                f"stream limit reached ({self.max_channels} concurrent streams)"
            )

        channel_id = self._allocate_id()
        stream = Stream(
            channel_id=channel_id,
            name=name,
            component_id=component_id,
            buffer_size=self.buffer_size,
            on_close=self._make_close_callback(channel_id),
            on_send=self._make_send_callback(channel_id),
        )
        self._streams[channel_id] = stream
        return stream

    def _detach(self, channel_id: int) -> None:
        """Remove a stream from the registry and recycle its channel id."""
        if self._streams.pop(channel_id, None) is not None:
            self._release_id(channel_id)

    def _allocate_id(self) -> int:
        if self._free_ids:
            return self._free_ids.pop(0)
        allocated = self._next_id
        self._next_id += 1
        return allocated

    def _release_id(self, channel_id: int) -> None:
        if channel_id in self._free_ids:
            return
        self._free_ids.append(channel_id)

    def _make_send_callback(
        self, channel_id: int
    ) -> "Callable[[bytes], Awaitable[None]] | None":
        if self._on_send_binary is None:
            return None
        on_send_binary = self._on_send_binary

        async def _send(data: bytes) -> None:
            await on_send_binary(channel_id, data)

        return _send

    def _make_close_callback(
        self, channel_id: int
    ) -> "Callable[[], Awaitable[None]] | None":
        on_peer_close = self._on_stream_close

        async def _close() -> None:
            # Remove from the registry first so the channel id is recycled.
            self._detach(channel_id)
            if on_peer_close is not None:
                try:
                    await on_peer_close(channel_id)
                except Exception:
                    pass

        return _close

    async def close(self, channel_id: int) -> None:
        """Close a specific stream by channel id and release its id."""
        stream = self._streams.pop(channel_id, None)
        if stream is None:
            return
        await stream.close()
        self._release_id(channel_id)

    async def close_all(self) -> None:
        """Close every open stream (called on session dispose / disconnect)."""
        channel_ids = list(self._streams.keys())
        for channel_id in channel_ids:
            await self.close(channel_id)

    def shutdown(self) -> None:
        """Synchronously mark every stream closed without invoking callbacks.

        Used as a last-resort cleanup from ``Session.dispose`` (which runs
        synchronously and may execute with no transport attached). Async
        ``close_all`` remains the preferred path because it also notifies the
        peer via ``stream_close`` control messages.
        """
        for channel_id in list(self._streams.keys()):
            stream = self._streams.pop(channel_id, None)
            if stream is None or stream.closed:
                continue
            stream.closed = True
            stream._recv_queue.put_nowait(_CLOSE_SENTINEL)
            stream._drain_send_queue()
            self._release_id(channel_id)
