"""Tests for Phase 4 — CSP channels, alts_ multiplexing, and Transducer pipelines."""

import asyncio
import pytest
from typing import Any

import hiccl
from hiccl import (
    Channel,
    alts_,
    go,
    timeout,
    Transducer,
    LoadingTransducer,
    SanitizingTransducer,
    walk_tree,
    HiccupRenderer,
    Component,
    div,
    button,
)
from hiccl.eventbus import event_bus


# ---------------------------------------------------------------------------
# 1. CSP Channel Sync & Buffered Buffering Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_synchronous_channel_blocking():
    """Verify that a sync channel (maxsize=0) blocks put until a get is present."""
    chan = Channel(maxsize=0)
    put_done = False

    async def run_put():
        nonlocal put_done
        await chan.put("msg-sync")
        put_done = True

    # Start put task
    task = asyncio.create_task(run_put())
    await asyncio.sleep(0.01)
    # Putter must be blocked because no getter has called get
    assert not put_done

    # Getter consumes
    val = await chan.get()
    assert val == "msg-sync"

    # Wait for put task to complete
    await task
    assert put_done


@pytest.mark.asyncio
async def test_buffered_channel():
    """Verify that a buffered channel (maxsize > 0) does not block put until it is full."""
    chan = Channel(maxsize=2)

    # These puts should return immediately
    await chan.put("a")
    await chan.put("b")

    # This put should block
    put_done = False

    async def run_put_3():
        nonlocal put_done
        await chan.put("c")
        put_done = True

    task = asyncio.create_task(run_put_3())
    await asyncio.sleep(0.01)
    assert not put_done

    # Consume first
    val_a = await chan.get()
    assert val_a == "a"

    # Now the third put should succeed
    await task
    assert put_done

    # Consume rest
    assert await chan.get() == "b"
    assert await chan.get() == "c"


# ---------------------------------------------------------------------------
# 2. CSP Channel Closing Behavior Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_channel_close_and_drain():
    """Verify that close unblocks pending putters and getters, and drains existing buffer."""
    chan = Channel(maxsize=2)
    await chan.put("buffered-1")
    await chan.put("buffered-2")

    # Add a putter that will block because the buffer is full
    put_error = None

    async def blocked_putter():
        nonlocal put_error
        try:
            await chan.put("blocked")
        except RuntimeError as e:
            put_error = e

    put_task = asyncio.create_task(blocked_putter())
    await asyncio.sleep(0.01)

    # Close the channel
    chan.close()

    # The blocked putter should fail immediately
    await put_task
    assert isinstance(put_error, RuntimeError)
    assert "Channel is closed" in str(put_error)

    # Existing buffered items can still be drained/read
    assert await chan.get() == "buffered-1"
    assert await chan.get() == "buffered-2"

    # After draining, further gets return None immediately
    assert await chan.get() is None
    assert await chan.get() is None

    # Subsequent puts fail immediately
    with pytest.raises(RuntimeError, match="Channel is closed"):
        await chan.put("new-item")


# ---------------------------------------------------------------------------
# 3. alts_ Multi-Channel Multiplexing Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alts_synchronous_matching():
    """Verify that alts_ instantly resolves synchronously if one of the channels is ready."""
    c1 = Channel(maxsize=1)
    c2 = Channel(maxsize=1)

    await c2.put("ready-val")

    # Since c2 has a value, alts_ should resolve c2 immediately
    selected, val = await alts_([c1, c2])
    assert selected is c2
    assert val == "ready-val"


@pytest.mark.asyncio
async def test_alts_asynchronous_wait_and_cleanup():
    """Verify that alts_ waits for the first active channel and deregisters/cancels from other channels."""
    c1 = Channel(maxsize=0)
    c2 = Channel(maxsize=0)

    # Run alts_ in background
    task = asyncio.create_task(alts_([c1, c2]))
    await asyncio.sleep(0.01)

    # Both channels should have exactly one waiter
    assert len(c1._get_waiters) == 1
    assert len(c2._get_waiters) == 1

    # Send value to c2
    await c2.put("c2-wins")

    # Get results of alts_
    selected, val = await task
    assert selected is c2
    assert val == "c2-wins"

    # Waiter of c1 MUST have been cleaned up/deregistered to prevent leaks
    assert len(c1._get_waiters) == 0
    assert len(c2._get_waiters) == 0


@pytest.mark.asyncio
async def test_alts_put_and_get_mixing():
    """Verify that alts_ supports mixing channel get ports and put tuples."""
    c_get = Channel(maxsize=0)
    c_put = Channel(maxsize=0)

    # Run alts_ mixed: get from c_get, or put "hello" to c_put
    task = asyncio.create_task(alts_([c_get, (c_put, "hello")]))
    await asyncio.sleep(0.01)

    assert len(c_get._get_waiters) == 1
    assert len(c_put._put_waiters) == 1

    # Get from c_put, causing the put port to win
    val = await c_put.get()
    assert val == "hello"

    selected, result = await task
    assert selected is c_put
    assert result is True  # Put success sentinel

    # Cleanup verify
    assert len(c_get._get_waiters) == 0
    assert len(c_put._put_waiters) == 0


@pytest.mark.asyncio
async def test_alts_timeout_abort():
    """Verify that alts_ can be aborted by a timeout channel."""
    c1 = Channel(maxsize=0)

    # c1 is empty. Wait for it or a 20ms timeout
    selected, val = await alts_([c1, timeout(20)])

    assert isinstance(selected, Channel)
    assert selected is not c1
    assert val is True  # timeout put sentinel


# ---------------------------------------------------------------------------
# 4. @go Coroutine Scheduler & EventBus Error Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_go_scheduler_success():
    """Verify that @go decorates and runs background tasks successfully."""
    c = Channel(maxsize=1)

    @go
    async def process():
        await c.put("done-go")

    task = process()
    assert isinstance(task, asyncio.Task)

    val = await c.get()
    assert val == "done-go"
    await task


@pytest.mark.asyncio
async def test_go_scheduler_unhandled_exception_broadcast():
    """Verify that @go unhandled exceptions are broadcasted via EventBus under 'hiccl.error.csp'."""
    queue = asyncio.Queue()
    event_bus.subscribe("hiccl.error.csp", queue)

    @go
    async def failing_task():
        await asyncio.sleep(0.01)
        raise ValueError("Oops in background CSP task")

    task = failing_task()

    # Wait for task exception and EventBus broadcast
    try:
        await task
    except ValueError:
        pass

    await asyncio.sleep(0.02)

    assert not queue.empty()
    msg = await queue.get()
    assert msg["topic"] == "hiccl.error.csp"
    assert msg["data"]["task_name"] == "failing_task"
    assert "Oops in background CSP task" in msg["data"]["error"]

    # Cleanup
    event_bus.unsubscribe_all(queue)


# ---------------------------------------------------------------------------
# 5. Transducers WalkTree & Preset Pipeline Tests
# ---------------------------------------------------------------------------


def test_transducer_walk_tree_immutable_dfs():
    """Verify that walk_tree recursively traverses DFS and transforms in a purely immutable way."""

    class CustomTransducer(Transducer):
        def transform(self, node: Any) -> Any:
            if isinstance(node, list) and node[0] == "span":
                attrs = node[1] if (len(node) > 1 and isinstance(node[1], dict)) else {}
                return ["span", {**attrs, "transformed": "yes"}] + node[2:]
            return node

    tree = ["div", None, ["span", {"class": "s1"}, "Hello"], ["p", "World"]]
    original_copy = ["div", None, ["span", {"class": "s1"}, "Hello"], ["p", "World"]]

    transformed = walk_tree(tree, CustomTransducer())

    # Deep checking the transformed sub-tree
    assert transformed[0] == "div"
    assert transformed[2] == ["span", {"class": "s1", "transformed": "yes"}, "Hello"]

    # Immutable verification (the original tree structure MUST not be mutated!)
    assert tree == original_copy
    assert tree[2] == ["span", {"class": "s1"}, "Hello"]


def test_loading_transducer_preset():
    """Verify LoadingTransducer automatically injects loading classes/indicator selectors into interactive buttons."""
    t = LoadingTransducer(loading_class="is-loading")

    # Interactive button: has on_click
    btn_interactive = ["button", {"class": "btn", "on_click": "ref"}, "Click me"]
    res1 = t.transform(btn_interactive)
    assert res1[1]["class"] == "btn is-loading"
    assert res1[1]["hx-indicator"] == "#global-spinner"

    # Static button: no action attributes
    btn_static = ["button", {"class": "btn"}, "Just static"]
    res2 = t.transform(btn_static)
    assert res2 == btn_static


def test_sanitizing_transducer_preset():
    """Verify SanitizingTransducer replaces blacklisted words recursively in string nodes."""
    t = SanitizingTransducer(
        blacklist=["sensitive", "badword"], replacement="[CENSORED]"
    )

    # String node
    assert (
        t.transform("This contains sensitive info") == "This contains [CENSORED] info"
    )

    # Non-string node
    node = ["div", None, "This contains badword!"]
    walked = walk_tree(node, t)
    assert walked[2] == "This contains [CENSORED]!"


# ---------------------------------------------------------------------------
# 6. HiccupRenderer Integration & Component Middleware Pipeline Tests
# ---------------------------------------------------------------------------


def test_renderer_transducers_integration():
    """Verify that registering transducers on HiccupRenderer correctly applies transformation during component rendering."""

    class ButtonStylingTransducer(Transducer):
        def transform(self, node: Any) -> Any:
            if isinstance(node, list) and node[0] == "button":
                attrs = node[1] if (len(node) > 1 and isinstance(node[1], dict)) else {}
                return ["button", {**attrs, "class": "btn-fancy"}] + node[2:]
            return node

    @hiccl.component("fancy-card")
    class FancyCard(Component):
        def render(self):
            return div({"class": "card"}, button({"on_click": lambda: None}, "Action"))

    renderer = HiccupRenderer()
    renderer.transducers.append(ButtonStylingTransducer())
    renderer.transducers.append(LoadingTransducer(loading_class="btn-loading"))

    comp = FancyCard()
    html = renderer.render_component(comp)

    # Verify both transducers successfully intercepted and modified the button element
    assert 'class="btn-fancy btn-loading"' in html
    assert 'hx-indicator="#global-spinner"' in html
