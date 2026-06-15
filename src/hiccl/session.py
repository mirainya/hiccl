"""Hiccl Session — per-connection state management with transport & EventBus."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from hiccl.component import Component, get_server_methods
from hiccl.eventbus import event_bus
from hiccl.registry import ComponentRegistry
from hiccl.renderer import HiccupRenderer
from hiccl.signal import Effect
from hiccl.transport.protocol import NullTransport, Transport
from hiccl.transport.stream import Stream, StreamRegistry

# Global session store
_sessions: dict[str, Session] = {}


class Session:
    """Per-connection state: holds mounted components, effects, and transport.

    Attributes:
        session_id:      Unique session identifier.
        transport:       Push channel (WS, SSE, or NullTransport).
        on_signal_change: Callback invoked when a watched signal changes.
    """

    def __init__(
        self,
        session_id: str,
        registry: ComponentRegistry,
        renderer: HiccupRenderer,
        store: Any = None,
    ) -> None:
        self.session_id = session_id
        self._components: dict[str, Component] = {}
        self._registry = registry
        self.renderer = renderer
        self.on_signal_change: Callable[[str], None] | None = None
        self.transport: Transport = NullTransport()
        self.last_accessed: float = time.time()
        self._store = store

        # Initialize re-frame states for this session
        import copy
        from hiccl.signal import HistorySignal
        from hiccl.re_frame import _re_frame_initial_state

        self._re_frame_db = HistorySignal(
            copy.deepcopy(_re_frame_initial_state), max_snapshots=50
        )
        self._history_signals: dict[str, HistorySignal] = {
            "@re-frame-db": self._re_frame_db
        }
        self._re_frame_subs: dict[Any, Any] = {}

        # EventBus integration
        self._event_queue: asyncio.Queue[Any] | None = None
        self._subscribed_topics: set[str] = set()

        # Stream registry — lazy until the first transport attaches. Defaults
        # are used until ``attach_stream_transport`` overrides them from config.
        self._stream_max_channels: int = 16
        self._stream_buffer_size: int = 64
        self._stream_registry: StreamRegistry | None = None
        self._stream_send_binary: Any = None
        self._stream_on_close: Any = None

    def touch(self) -> None:
        """Refresh the last accessed timestamp."""
        self.last_accessed = time.time()

    # -- Component lifecycle -----------------------------------------------

    def mount_component(
        self, name: str, cid: str | None = None, **props: Any
    ) -> Component:
        """Create and mount a component instance."""
        self.touch()
        from hiccl.re_frame import _current_session
        from hiccl.signal import HistorySignal

        token = _current_session.set(self)
        try:
            component = self._registry.create(name, **props)
        finally:
            _current_session.reset(token)
        if cid:
            component.component_id = cid
        self._components[component.component_id] = component
        component._session = self
        component.mount()

        # Subscribe to EventBus topics declared by the component
        topics = getattr(component, "topics", [])
        if topics:
            if self._event_queue is None:
                self._event_queue = asyncio.Queue()
            for topic in topics:
                if topic not in self._subscribed_topics:
                    event_bus.subscribe(topic, self._event_queue)
                    self._subscribed_topics.add(topic)

        # Create effects that watch all component signals
        for sig_name in component._signals:
            sig = component._signals[sig_name]

            if isinstance(sig, HistorySignal):
                key = f"{component.component_id}.{sig_name}"
                self._history_signals[key] = sig

            def make_effect(signal_obj, comp_id):
                def watch():
                    signal_obj.get()
                    if self.on_signal_change:
                        self.on_signal_change(comp_id)

                return watch

            effect = Effect(make_effect(sig, component.component_id))
            component._effects.append(effect)

        return component

    def get_component(self, component_id: str) -> Component | None:
        """Look up a mounted component by ID."""
        self.touch()
        return self._components.get(component_id)

    # -- Action execution --------------------------------------------------

    async def execute_action(
        self, component_id: str, method_name: str, args: dict[str, Any]
    ) -> Any:
        """Execute a ``@server`` method and auto-publish to EventBus.

        Returns the method's return value (if any).
        """
        self.touch()
        from hiccl.re_frame import _current_session

        token_session = _current_session.set(self)
        try:
            component = self._components.get(component_id)
            if component is None:
                return None

            methods = get_server_methods(component)
            if method_name not in methods:
                return None

            result = methods[method_name](**args)
            if asyncio.iscoroutine(result):
                result = await result

            # Auto-publish to EventBus for the component's non-wildcard topics
            topics = getattr(component, "topics", [])
            for topic in topics:
                if "*" in topic or "#" in topic:
                    continue
                await event_bus.publish(
                    topic,
                    {
                        "topic": topic,
                        "source": component_id,
                        "source_session": self.session_id,
                    },
                )

            return result
        finally:
            _current_session.reset(token_session)

    # -- EventBus processing -----------------------------------------------

    async def process_eventbus_events(self) -> None:
        """Drain EventBus queue and trigger ``on_broadcast`` on components.

        Should be called periodically by the transport handler (WS/SSE).
        """
        self.touch()
        if self._event_queue is None:
            return
        from hiccl.eventbus import match_topic

        while not self._event_queue.empty():
            try:
                msg = self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not isinstance(msg, dict):
                continue
            topic = msg.get("topic")
            source_cid = msg.get("source")
            source_session = msg.get("source_session")
            for cid, comp in self._components.items():
                # Skip the originator — it already updated its own signal
                if self.session_id == source_session and cid == source_cid:
                    continue
                comp_topics = getattr(comp, "topics", [])
                for pattern in comp_topics:
                    if match_topic(pattern, topic):
                        comp.on_broadcast(topic)
                        break

    # -- Streams ------------------------------------------------------------

    def attach_stream_transport(
        self,
        on_send_binary: Any = None,
        on_stream_close: Any = None,
        max_channels: int | None = None,
        buffer_size: int | None = None,
    ) -> StreamRegistry:
        """Bind (or rebind) the session's stream registry to a live transport.

        Lazily creates the registry on first call. Subsequent calls (e.g. on
        WebSocket reconnect) re-wire the transport callbacks without dropping
        already-open streams. Returns the active registry.
        """
        if max_channels is not None:
            self._stream_max_channels = max_channels
        if buffer_size is not None:
            self._stream_buffer_size = buffer_size
        self._stream_send_binary = on_send_binary
        self._stream_on_close = on_stream_close
        if self._stream_registry is None:
            self._stream_registry = StreamRegistry(
                max_channels=self._stream_max_channels,
                buffer_size=self._stream_buffer_size,
                on_send_binary=on_send_binary,
                on_stream_close=on_stream_close,
            )
        else:
            self._stream_registry._on_send_binary = on_send_binary
            self._stream_registry._on_stream_close = on_stream_close
        return self._stream_registry

    def _ensure_registry(self) -> StreamRegistry:
        """Return the registry, creating an unbound one if needed."""
        if self._stream_registry is None:
            self._stream_registry = StreamRegistry(
                max_channels=self._stream_max_channels,
                buffer_size=self._stream_buffer_size,
            )
        return self._stream_registry

    def get_stream(self, name: str) -> Stream | None:
        """Look up an open stream by logical name."""
        if self._stream_registry is None:
            return None
        return self._stream_registry.find(name)

    def open_stream(self, name: str, component_id: str | None = None) -> Stream:
        """Open a new named stream and return it.

        Raises ``StreamLimitError`` if the per-session concurrency cap is hit.
        """
        return self._ensure_registry().open(name, component_id=component_id)

    async def close_stream(self, name: str) -> bool:
        """Close a stream by logical name. Returns True if a stream was closed."""
        registry = self._stream_registry
        if registry is None:
            return False
        stream = registry.find(name)
        if stream is None:
            return False
        await registry.close(stream.channel_id)
        return True

    # -- Cleanup -----------------------------------------------------------

    def dispose(self) -> None:
        """Dispose all mounted components, effects, and EventBus subscriptions."""
        # Unsubscribe from EventBus
        if self._event_queue is not None:
            event_bus.unsubscribe_all(self._event_queue)
            self._event_queue = None
        self._subscribed_topics.clear()

        # Close all open streams (synchronous best-effort; the WS/SSE
        # disconnect paths perform the full async close_all with notifications).
        if self._stream_registry is not None:
            self._stream_registry.shutdown()
            self._stream_registry = None

        # Dispose components
        for component in self._components.values():
            for effect in component._effects:
                effect.dispose()
            component._effects.clear()
            component.unmount()
        self._components.clear()
