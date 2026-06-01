"""Hiccl CSP (Communicating Sequential Processes) Concurrency Module."""

import asyncio
import collections
import random
import logging
import traceback
from typing import Any, Coroutine, Union, Callable
from functools import wraps
from hiccl.eventbus import event_bus

logger = logging.getLogger("hiccl.csp")


class Channel:
    """A non-blocking CSP-style communication channel.

    Supports synchronization (maxsize=0) or buffering (maxsize > 0),
    backpressure on put, and safe close operations.
    """

    def __init__(self, maxsize: int = 0) -> None:
        self.maxsize = maxsize
        self._buf: collections.deque[Any] = collections.deque()
        self._get_waiters: list[asyncio.Future[Any]] = []
        self._put_waiters: list[tuple[Any, asyncio.Future[None]]] = []
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return True if the channel is closed."""
        return self._closed

    def close(self) -> None:
        """Close the channel.

        Any pending values in the buffer can still be read.
        Any pending getters will be unblocked and receive None.
        Any pending putters will fail with a RuntimeError.
        """
        if self._closed:
            return
        self._closed = True

        # Unblock all getters with None
        for fut in list(self._get_waiters):
            if not fut.done():
                fut.set_result(None)
        self._get_waiters.clear()

        # Unblock all putters with a RuntimeError
        for _, fut in list(self._put_waiters):
            if not fut.done():
                fut.set_exception(RuntimeError("Channel is closed"))
        self._put_waiters.clear()

    async def put(self, val: Any) -> None:
        """Put a value into the channel.

        If there is a pending getter, the value is delivered immediately.
        If there is buffer space, the value is buffered immediately.
        Otherwise, this blocks until buffer space becomes available or
        a getter consumes a value.

        Raises RuntimeError if the channel is closed.
        """
        if self._closed:
            raise RuntimeError("Channel is closed")

        # 1. Try to deliver immediately to a pending getter
        while self._get_waiters:
            fut = self._get_waiters.pop(0)
            if not fut.done():
                fut.set_result(val)
                return

        # 2. Try to append to the buffer if not full
        if self.maxsize > 0 and len(self._buf) < self.maxsize:
            self._buf.append(val)
            return

        # 3. Synchronous channel or buffer full: block
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._put_waiters.append((val, fut))
        await fut

    async def get(self) -> Any:
        """Get a value from the channel.

        Consumes from the buffer if not empty, unblocking a pending putter.
        If empty and open, this blocks until a value is put.
        If empty and closed, this returns None immediately.
        """
        # 1. If buffer has items, return the first one and unblock one putter
        if self._buf:
            val = self._buf.popleft()
            self._unblock_one_putter()
            return val

        # 2. If empty and closed, return None
        if self._closed:
            return None

        # 3. Synchronous channel or empty: check if there's a pending putter waiting to sync-transfer
        if self.maxsize == 0:
            while self._put_waiters:
                put_val, put_fut = self._put_waiters.pop(0)
                if not put_fut.done():
                    put_fut.set_result(None)
                    return put_val

        # 4. Block until value is available
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._get_waiters.append(fut)
        return await fut

    def _unblock_one_putter(self) -> None:
        """Unblock the next pending putter and move its value to the buffer."""
        while self._put_waiters:
            val, fut = self._put_waiters.pop(0)
            if not fut.done():
                self._buf.append(val)
                fut.set_result(None)
                break

    def _can_get_immediately(self) -> bool:
        """Return True if a get operation can complete immediately without blocking."""
        if self._buf or self._closed:
            return True
        if self.maxsize == 0:
            # Sync channel can get immediately if there is a pending active putter
            return any(not fut.done() for _, fut in self._put_waiters)
        return False

    def _can_put_immediately(self) -> bool:
        """Return True if a put operation can complete immediately without blocking."""
        if self._closed:
            return True  # Will raise RuntimeError immediately
        if self._get_waiters:
            return any(not fut.done() for fut in self._get_waiters)
        if self.maxsize > 0 and len(self._buf) < self.maxsize:
            return True
        return False

    def _try_get_immediately(self) -> tuple[bool, Any]:
        """Try to get a value immediately. Returns (success, value)."""
        if self._buf:
            val = self._buf.popleft()
            self._unblock_one_putter()
            return True, val
        if self._closed:
            return True, None
        if self.maxsize == 0:
            while self._put_waiters:
                put_val, put_fut = self._put_waiters.pop(0)
                if not put_fut.done():
                    put_fut.set_result(None)
                    return True, put_val
        return False, None

    def _try_put_immediately(self, val: Any) -> tuple[bool, bool]:
        """Try to put a value immediately. Returns (success, true_or_false)."""
        if self._closed:
            raise RuntimeError("Channel is closed")
        while self._get_waiters:
            fut = self._get_waiters.pop(0)
            if not fut.done():
                fut.set_result(val)
                return True, True
        if self.maxsize > 0 and len(self._buf) < self.maxsize:
            self._buf.append(val)
            return True, True
        return False, False


async def alts_(
    ports: list[Union[Channel, tuple[Channel, Any]]],
) -> tuple[Channel, Any]:
    """Asynchronously monitor multiple ports (channels or put tuples).

    Returns (selected_channel, value).
    - If a get port wins: returns (channel, received_value).
    - If a put port (channel, val) wins: returns (channel, True).
    - If channel is closed on get: returns (channel, None).
    """
    if not ports:
        raise ValueError("alts_ requires at least one port")

    # 1. Synchronous pass: check if any port is ready immediately
    ready_indices = []
    for i, port in enumerate(ports):
        if isinstance(port, Channel):
            if port._can_get_immediately():
                ready_indices.append(i)
        else:
            chan, val = port
            if chan._can_put_immediately():
                ready_indices.append(i)

    if ready_indices:
        # Randomly choose one to ensure fairness
        idx = random.choice(ready_indices)
        selected = ports[idx]
        if isinstance(selected, Channel):
            success, val = selected._try_get_immediately()
            if success:
                return selected, val
        else:
            chan, val = selected
            success, _ = chan._try_put_immediately(val)
            if success:
                return chan, True

    # 2. Asynchronous pass: register futures on all ports
    loop = asyncio.get_running_loop()
    shared_fut: asyncio.Future[tuple[Channel, Any]] = loop.create_future()
    registered: list[
        tuple[Union[Channel, tuple[Channel, Any]], asyncio.Future[Any]]
    ] = []

    def make_get_cb(c, f):
        def get_cb(_):
            if not shared_fut.done():
                cleanup(c, f)
                # If exception occurred, propagate it
                if f.exception() is not None:
                    shared_fut.set_exception(f.exception())
                else:
                    shared_fut.set_result((c, f.result()))

        return get_cb

    def make_put_cb(c, f):
        def put_cb(_):
            if not shared_fut.done():
                cleanup(c, f)
                if f.exception() is not None:
                    shared_fut.set_exception(f.exception())
                else:
                    shared_fut.set_result((c, True))

        return put_cb

    def cleanup(winning_chan, winning_fut):
        for port, fut in registered:
            if isinstance(port, Channel):
                if port is winning_chan and fut is winning_fut:
                    continue
                if fut in port._get_waiters:
                    port._get_waiters.remove(fut)
            else:
                chan, val = port
                if chan is winning_chan and fut is winning_fut:
                    continue
                for item in list(chan._put_waiters):
                    if item[1] is fut:
                        chan._put_waiters.remove(item)
            if not fut.done():
                fut.cancel()

    try:
        for port in ports:
            fut = loop.create_future()
            if isinstance(port, Channel):
                port._get_waiters.append(fut)
                fut.add_done_callback(make_get_cb(port, fut))
                registered.append((port, fut))
            else:
                chan, val = port
                chan._put_waiters.append((val, fut))
                fut.add_done_callback(make_put_cb(chan, fut))
                registered.append((port, fut))

        return await shared_fut
    finally:
        # If the alts_ call itself gets cancelled externally
        if not shared_fut.done():
            for port, fut in registered:
                if isinstance(port, Channel):
                    if fut in port._get_waiters:
                        port._get_waiters.remove(fut)
                else:
                    chan, val = port
                    for item in list(chan._put_waiters):
                        if item[1] is fut:
                            chan._put_waiters.remove(item)
                if not fut.done():
                    fut.cancel()


def go(fn: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., asyncio.Task[Any]]:
    """Decorator that executes the decorated async function in the background.

    If the coroutine raises an unhandled exception, it is caught and broadcasted
    via EventBus under the topic 'hiccl.error.csp' to enable error boundary handling.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs) -> asyncio.Task[Any]:
        async def runner():
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                err_msg = f"Exception in @go task {fn.__name__}: {str(e)}"
                logger.error(err_msg, exc_info=True)
                await event_bus.publish(
                    "hiccl.error.csp",
                    {
                        "task_name": fn.__name__,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    },
                )
                raise e

        return asyncio.create_task(runner())

    return wrapper


def timeout(delay_ms: int) -> Channel:
    """Return a Channel that closes and delivers a value after the specified delay in milliseconds."""
    chan = Channel(maxsize=1)

    async def waiter():
        await asyncio.sleep(delay_ms / 1000.0)
        try:
            await chan.put(True)
        except RuntimeError:
            pass  # Already closed
        finally:
            chan.close()

    asyncio.create_task(waiter())
    return chan
