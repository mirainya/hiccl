"""Hiccl protocol — message models and transport protocol definitions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Wire protocol messages (JSON between server and client)
# ---------------------------------------------------------------------------


class PatchMessage(BaseModel):
    """A patch to apply to a component's DOM."""

    type: str = "patch"
    component_id: str
    html: str
    swap: str = "outerHTML"
    oob: list["PatchMessage"] | None = None


class ActionMessage(BaseModel):
    """An action request from the client."""

    type: str = "action"
    component_id: str
    method: str
    args: dict = {}


class ErrorMessage(BaseModel):
    """An error message from the server."""

    type: str = "error"
    component_id: str
    message: str
    status: int = 500


class BatchMessage(BaseModel):
    """A batch of patch messages."""

    type: str = "batch"
    patches: list[PatchMessage]


# ---------------------------------------------------------------------------
# Stream control messages (carried over text frames, JSON protocol)
# ---------------------------------------------------------------------------


class StreamOpenMessage(BaseModel):
    """Client → server request to open a named stream."""

    type: str = "stream_open"
    stream: str
    component_id: str = ""


class StreamAckMessage(BaseModel):
    """Server → client reply allocating a channel id for a stream."""

    type: str = "stream_ack"
    stream: str
    channel_id: int


class StreamCloseMessage(BaseModel):
    """Either direction: tear down a stream by channel id."""

    type: str = "stream_close"
    channel_id: int


# ---------------------------------------------------------------------------
# Transport protocol — abstract interface for push channels
# ---------------------------------------------------------------------------


@runtime_checkable
class Transport(Protocol):
    """Interface that Session uses to push rendered patches to the client."""

    async def push(self, patches: list[dict[str, Any]]) -> None:
        """Send rendered patches to the client."""
        ...

    def is_connected(self) -> bool:
        """Return True if the transport is alive and can push."""
        ...

    async def send_binary(self, channel_id: int, data: bytes) -> None:
        """Send a raw binary payload on the given stream channel.

        Optional capability: transports that cannot carry binary frames
        (e.g. ``NullTransport``) either omit this method or no-op. Check
        ``supports_streams()`` before relying on it.
        """
        ...

    def supports_streams(self) -> bool:
        """Return True if this transport can carry multiplexed byte streams."""
        ...


class NullTransport:
    """No-op transport — used when only HTTP request/response is available."""

    async def push(self, patches: list[dict[str, Any]]) -> None:
        pass

    def is_connected(self) -> bool:
        return False

    async def send_binary(self, channel_id: int, data: bytes) -> None:
        pass

    def supports_streams(self) -> bool:
        return False
