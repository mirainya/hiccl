"""Tests for hiccl.transport.stream — Stream + StreamRegistry + errors."""

import asyncio

import pytest

from hiccl.transport.stream import (
    Stream,
    StreamClosedError,
    StreamError,
    StreamLimitError,
    StreamRegistry,
)


class TestStreamErrors:
    def test_hierarchy(self):
        assert issubclass(StreamClosedError, StreamError)
        assert issubclass(StreamLimitError, StreamError)


class TestStreamBasics:
    async def test_defaults(self):
        s = Stream(channel_id=1, name="t")
        assert s.channel_id == 1
        assert s.name == "t"
        assert s.closed is False
        assert s.component_id is None

    def test_invalid_channel_id(self):
        with pytest.raises(ValueError):
            Stream(channel_id=0, name="x")
        with pytest.raises(ValueError):
            Stream(channel_id=256, name="x")

    async def test_send_recv_roundtrip(self):
        s = Stream(channel_id=1, name="t", buffer_size=4)
        s._feed(b"hello")
        got = await s.recv()
        assert got == b"hello"

    async def test_recv_order_preserved(self):
        s = Stream(channel_id=1, name="t", buffer_size=8)
        for chunk in (b"a", b"bb", b"ccc"):
            s._feed(chunk)
        assert [await s.recv() for _ in range(3)] == [b"a", b"bb", b"ccc"]

    async def test_send_after_close_raises(self):
        s = Stream(channel_id=1, name="t")
        await s.close()
        with pytest.raises(StreamClosedError):
            await s.send(b"x")

    async def test_recv_after_close_raises(self):
        s = Stream(channel_id=1, name="t")
        await s.close()
        with pytest.raises(StreamClosedError):
            await s.recv()

    async def test_close_is_idempotent(self):
        s = Stream(channel_id=1, name="t")
        await s.close()
        await s.close()
        assert s.closed is True

    async def test_close_callback_invoked(self):
        calls = []

        async def on_close():
            calls.append("closed")

        s = Stream(channel_id=1, name="t", on_close=on_close)
        await s.close()
        assert calls == ["closed"]

    async def test_send_callback_invoked(self):
        sent = []

        async def on_send(data):
            sent.append(data)

        s = Stream(channel_id=1, name="t", on_send=on_send)
        await s.send(b"payload")
        assert sent == [b"payload"]


class TestStreamBackpressure:
    async def test_send_blocks_when_full_then_drains(self):
        s = Stream(channel_id=1, name="t", buffer_size=2)
        # Fill the buffer without blocking.
        await s.send(b"1")
        await s.send(b"2")

        started = asyncio.Event()
        finished = []

        async def producer():
            started.set()
            await s.send(b"3")  # should block until close drains the queue
            finished.append(True)

        task = asyncio.create_task(producer())
        await asyncio.wait_for(started.wait(), timeout=1.0)
        # Producer is blocked; close should wake it by draining.
        await asyncio.wait_for(asyncio.sleep(0.05), timeout=1.0)
        assert finished == []
        await s.close()
        await asyncio.wait_for(asyncio.shield(task), timeout=1.0)
        assert finished == [True]


class TestStreamIteration:
    async def test_async_for_drains_until_close(self):
        s = Stream(channel_id=1, name="t", buffer_size=8)
        s._feed(b"a")
        s._feed(b"b")
        asyncio.create_task(s.close())
        chunks = [c async for c in s]
        assert chunks == [b"a", b"b"]

    async def test_async_for_empty_closes_cleanly(self):
        s = Stream(channel_id=1, name="t")
        asyncio.create_task(s.close())
        chunks = [c async for c in s]
        assert chunks == []


class TestStreamRegistry:
    async def test_open_allocates_incremental_ids(self):
        reg = StreamRegistry(max_channels=5)
        a = reg.open("a")
        b = reg.open("b")
        c = reg.open("c")
        assert {a.channel_id, b.channel_id, c.channel_id} == {1, 2, 3}
        assert reg.get(a.channel_id) is a
        assert reg.find("b") is b
        assert reg.find("missing") is None

    async def test_open_duplicate_name_raises(self):
        reg = StreamRegistry()
        reg.open("dup")
        with pytest.raises(ValueError):
            reg.open("dup")

    async def test_limit_exceeded_raises(self):
        reg = StreamRegistry(max_channels=2)
        reg.open("a")
        reg.open("b")
        with pytest.raises(StreamLimitError):
            reg.open("c")

    async def test_id_recycled_after_close(self):
        reg = StreamRegistry(max_channels=3)
        a = reg.open("a")
        await reg.close(a.channel_id)
        b = reg.open("b")
        assert b.channel_id == a.channel_id
        assert len(reg) == 1

    async def test_close_via_stream_object_detaches(self):
        reg = StreamRegistry(max_channels=3)
        a = reg.open("a")
        await a.close()
        assert len(reg) == 0
        assert reg.get(a.channel_id) is None
        # channel id is now free again
        b = reg.open("b")
        assert b.channel_id == a.channel_id

    async def test_close_unknown_id_is_noop(self):
        reg = StreamRegistry()
        await reg.close(999)  # no error
        assert len(reg) == 0

    async def test_close_all(self):
        reg = StreamRegistry(max_channels=5)
        reg.open("a")
        reg.open("b")
        reg.open("c")
        await reg.close_all()
        assert len(reg) == 0
        assert reg.all() == []

    async def test_shutdown_is_synchronous(self):
        reg = StreamRegistry(max_channels=5)
        a = reg.open("a")
        b = reg.open("b")
        reg.shutdown()
        assert a.closed and b.closed
        assert len(reg) == 0

    async def test_transport_callbacks_wired(self):
        sent = []
        closed = []

        async def on_send_binary(channel_id, data):
            sent.append((channel_id, data))

        async def on_stream_close(channel_id):
            closed.append(channel_id)

        reg = StreamRegistry(
            max_channels=3,
            on_send_binary=on_send_binary,
            on_stream_close=on_stream_close,
        )
        s = reg.open("t")
        await s.send(b"payload")
        assert sent == [(s.channel_id, b"payload")]
        await s.close()
        assert closed == [s.channel_id]

    async def test_buffer_size_propagated(self):
        reg = StreamRegistry(max_channels=3, buffer_size=1)
        s = reg.open("t")
        assert s._send_queue.maxsize == 1
        assert s._recv_queue.maxsize == 1
