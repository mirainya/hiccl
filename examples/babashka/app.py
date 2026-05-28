"""Babashka Interactive REPL & Shared Terminal Example.

This example runs a local interactive `bb` process and shares its state
and streams across all connected browser sessions in real-time, resembling gotty.
"""

import asyncio
import re
import html
from hiccl import (
    Component,
    ComponentRegistry,
    HicclConfig,
    create_hiccl_app,
    menu,
    server,
    signal,
    event_bus,
)
from hiccl.hiccup import button, div, form, h2, input_, span, raw, p

# ---------------------------------------------------------------------------
# ANSI Code Stripper Helper
# ---------------------------------------------------------------------------
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    """Strip standard ANSI escape sequences from terminal streams."""
    return ANSI_ESCAPE.sub("", text)


# ---------------------------------------------------------------------------
# Shared Babashka Process Manager (Singleton)
# ---------------------------------------------------------------------------
class BabashkaManager:
    """Manages a single shared Babashka interactive REPL subprocess."""

    def __init__(self) -> None:
        self.process = None
        self.output_buffer = "--- Babashka Shared REPL Session Started ---\n"
        self.reader_tasks = []
        self.lock = asyncio.Lock()

    async def start(self) -> None:
        """Spawn the bb subprocess if not already running."""
        async with self.lock:
            if self.process is not None:
                return

            try:
                # Start Babashka REPL sub-process
                self.process = await asyncio.create_subprocess_exec(
                    "bb",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                # Create background reader tasks for stdout & stderr
                t1 = asyncio.create_task(
                    self._read_stream(self.process.stdout, "STDOUT")
                )
                t2 = asyncio.create_task(
                    self._read_stream(self.process.stderr, "STDERR")
                )
                self.reader_tasks = [t1, t2]
            except Exception as e:
                self.output_buffer += f"\nError spawning 'bb' process: {e}\nMake sure 'babashka' (bb) is installed and available in PATH.\n"
                event_bus.publish_sync("bb-output", {"topic": "bb-output"})

    async def _read_stream(self, stream, name: str) -> None:
        """Asynchronously read chunked outputs from the subprocess stream."""
        while True:
            try:
                data = await stream.read(4096)
                if not data:
                    break
                text = strip_ansi(data.decode("utf-8", errors="ignore"))
                async with self.lock:
                    # Keep only the last 100k characters to prevent memory bloating
                    self.output_buffer = (self.output_buffer + text)[-100000:]
                # Notify all sessions that terminal output has changed
                await event_bus.publish("bb-output", {"topic": "bb-output"})
            except asyncio.CancelledError:
                break
            except Exception as e:
                async with self.lock:
                    self.output_buffer += f"\n[{name} Reader Error]: {e}\n"
                await event_bus.publish("bb-output", {"topic": "bb-output"})
                break

    async def write_input(self, code: str) -> None:
        """Write user code to bb stdin and echo to the shared buffer."""
        async with self.lock:
            if self.process is None or self.process.stdin is None:
                self.output_buffer += (
                    "\n[Error]: Babashka REPL process is not running.\n"
                )
                await event_bus.publish("bb-output", {"topic": "bb-output"})
                return

            # Echo the code to the output log so users see what was sent
            self.output_buffer += f"{code}\n"
            try:
                self.process.stdin.write(f"{code}\n".encode("utf-8"))
                await self.process.stdin.drain()
            except Exception as e:
                self.output_buffer += f"\n[Write Error]: {e}\n"
                await event_bus.publish("bb-output", {"topic": "bb-output"})

    async def reset(self) -> None:
        """Terminate the active REPL process and spin up a fresh one."""
        async with self.lock:
            if self.process:
                try:
                    self.process.terminate()
                    await self.process.wait()
                except Exception:
                    pass
                self.process = None

            for t in self.reader_tasks:
                t.cancel()
            self.reader_tasks = []

            self.output_buffer = "--- Babashka REPL Session Reset ---\n"

        await self.start()
        await event_bus.publish("bb-output", {"topic": "bb-output"})

    async def clear(self) -> None:
        """Clear the current shared terminal buffer."""
        async with self.lock:
            self.output_buffer = ""
        await event_bus.publish("bb-output", {"topic": "bb-output"})


# Instantiate the shared global singleton manager
shared_bb = BabashkaManager()


# ---------------------------------------------------------------------------
# Babashka Terminal Hiccl Component
# ---------------------------------------------------------------------------
class BabashkaTerminal(Component):
    """Component for interactive multi-user shared terminal viewing & executing."""

    topics = ["bb-output"]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.output = signal(shared_bb.output_buffer)
        self.cleared_at = 0

    def mount(self) -> None:
        # Start the shared subprocess as soon as the first client mounts
        asyncio.create_task(shared_bb.start())
        self.output.set(shared_bb.output_buffer[self.cleared_at :])

    @server
    async def execute_code(self, code: str = "") -> None:
        if not code.strip():
            return
        await shared_bb.write_input(code)

    @server
    async def clear_console(self) -> None:
        # Clear only locally for the current user session by shifting the slice offset
        self.cleared_at = len(shared_bb.output_buffer)
        self.output.set("")

    @server
    async def restart_repl(self) -> None:
        await shared_bb.reset()

    def on_broadcast(self, topic: str) -> None:
        if topic == "bb-output":
            # If the global buffer is reset/cleared, reset the local offset
            if len(shared_bb.output_buffer) < self.cleared_at:
                self.cleared_at = 0
            self.output.set(shared_bb.output_buffer[self.cleared_at :])

    def render(self):
        output_text = self.output.get()
        viewer_count = len(event_bus._subscribers.get("bb-output", set()))
        escaped_output = html.escape(output_text)

        return div(
            {
                "class": "card bg-slate-900/90 border border-slate-700/50 backdrop-blur-xl shadow-2xl mx-auto w-full max-w-4xl"
            },
            div(
                {"class": "card-body p-6"},
                # 1. Header with Title & Metadata Statuses
                div(
                    {
                        "class": "flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4"
                    },
                    div(
                        {},
                        h2(
                            {
                                "class": "card-title text-2xl font-bold text-slate-100 flex items-center gap-2"
                            },
                            "🐚 Babashka REPL & Shared Terminal",
                        ),
                        p(
                            {"class": "text-xs text-slate-400 mt-1"},
                            "多用户共享终端演示。基于 Babashka (Clojure) 实现，支持实时协同输入与展示。",
                        ),
                    ),
                    div(
                        {"class": "flex items-center gap-2"},
                        div(
                            {
                                "class": "badge badge-success gap-1 text-xs py-3 font-semibold"
                            },
                            span(
                                {
                                    "class": "w-2 h-2 rounded-full bg-emerald-300 animate-pulse"
                                }
                            ),
                            "● Synced",
                        ),
                        div(
                            {
                                "class": "badge badge-neutral gap-1 text-xs py-3 font-semibold"
                            },
                            f"👥 Viewers: {viewer_count}",
                        ),
                    ),
                ),
                # 2. The Terminal Window Emulator
                div(
                    {
                        "class": "flex flex-col rounded-xl overflow-hidden border border-slate-800 shadow-inner bg-black"
                    },
                    # macOS Style Terminal Topbar
                    div(
                        {
                            "class": "bg-slate-950 px-4 py-2 flex items-center justify-between border-b border-slate-900"
                        },
                        # Colored window dots
                        div(
                            {"class": "flex gap-1.5"},
                            div({"class": "w-3 h-3 rounded-full bg-rose-500"}),
                            div({"class": "w-3 h-3 rounded-full bg-amber-500"}),
                            div({"class": "w-3 h-3 rounded-full bg-emerald-500"}),
                        ),
                        # Title
                        span(
                            {"class": "text-xs font-mono text-slate-500"},
                            "babashka --repl (shared session)",
                        ),
                        # Action bar buttons
                        div(
                            {"class": "flex gap-2"},
                            button(
                                {
                                    "class": "btn btn-xs btn-ghost text-slate-400 hover:text-rose-400 font-semibold px-2 py-0.5",
                                    "on_click": self.clear_console,
                                },
                                "Clear",
                            ),
                            button(
                                {
                                    "class": "btn btn-xs btn-ghost text-slate-400 hover:text-amber-400 font-semibold px-2 py-0.5",
                                    "on_click": self.restart_repl,
                                },
                                "Reset REPL",
                            ),
                        ),
                    ),
                    # Screen Output with Auto-scroll mutation observer
                    raw(
                        f'<pre id="bb-terminal-output" '
                        f'class="font-mono text-emerald-400 text-sm bg-black/95 p-4 h-96 overflow-y-auto w-full whitespace-pre-wrap rounded-b-xl border-t border-slate-900" '
                        f'x-init="new MutationObserver(() => {{ $el.scrollTop = $el.scrollHeight }}).observe($el, {{ childList: true, characterData: true, subtree: true }}); $el.scrollTop = $el.scrollHeight;">'
                        f"{escaped_output}"
                        f"</pre>"
                    ),
                ),
                # 3. Quick Snippets Board
                div(
                    {
                        "class": "mt-4 p-3 bg-slate-950/60 rounded-xl border border-slate-800/80"
                    },
                    div(
                        {
                            "class": "text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1"
                        },
                        "💡 快速代码模版 (点击快捷载入):",
                    ),
                    div(
                        {"class": "flex flex-wrap gap-2", "x-data": "{}"},
                        button(
                            {
                                "class": "btn btn-xs btn-outline btn-info font-mono text-[11px] lowercase",
                                "@click": "$dispatch('set-code', {val: '(+ 1 2 3)'})",
                            },
                            "(+ 1 2 3)",
                        ),
                        button(
                            {
                                "class": "btn btn-xs btn-outline btn-info font-mono text-[11px] lowercase",
                                "@click": "$dispatch('set-code', {val: '(map inc [10 20 30])'})",
                            },
                            "(map inc [10 20 30])",
                        ),
                        button(
                            {
                                "class": "btn btn-xs btn-outline btn-info font-mono text-[11px] lowercase",
                                "@click": "$dispatch('set-code', {val: '*clojure-version*'})",
                            },
                            "*clojure-version*",
                        ),
                        button(
                            {
                                "class": "btn btn-xs btn-outline btn-info font-mono text-[11px] lowercase",
                                "@click": "$dispatch('set-code', {val: '(clojure.java.shell/sh \\\"uname\\\" \\\"-a\\\")'})",
                            },
                            '(sh \\"uname\\" \\"-a\\")',
                        ),
                        button(
                            {
                                "class": "btn btn-xs btn-outline btn-info font-mono text-[11px] lowercase",
                                "@click": "$dispatch('set-code', {val: '(babashka.process/shell \\\"df -h\\\")'})",
                            },
                            '(shell \\"df -h\\")',
                        ),
                    ),
                ),
                # 4. Form and Input Prompt
                form(
                    {
                        "class": "join mt-4 w-full border border-slate-700/40 rounded-xl overflow-hidden shadow-md",
                        "on_submit": self.execute_code,
                        "x-data": "{ codeVal: '' }",
                        "@set-code.window": "codeVal = $event.detail.val; $nextTick(() => $refs.inputField.focus())",
                    },
                    span(
                        {
                            "class": "join-item btn btn-neutral no-animation font-mono text-emerald-400 bg-slate-950 border-r border-slate-800"
                        },
                        "user=>",
                    ),
                    input_(
                        {
                            "type": "text",
                            "name": "code",
                            "class": "input input-bordered join-item flex-1 font-mono bg-slate-950 text-emerald-300 border-none placeholder-slate-600 focus:outline-none focus:ring-0",
                            "placeholder": "输入 Clojure 表达式并回车...",
                            "required": True,
                            "x-model": "codeVal",
                            "x-ref": "inputField",
                        }
                    ),
                    button(
                        {
                            "class": "btn btn-success join-item font-semibold px-6",
                            "type": "submit",
                        },
                        "Execute",
                    ),
                ),
            ),
        )


# ---------------------------------------------------------------------------
# Application Initialization
# ---------------------------------------------------------------------------
registry = ComponentRegistry()
# Auto routing menu mapping first component to "/" and "/babashka-terminal"
app = create_hiccl_app(
    HicclConfig(
        component_registry=registry,
        transport_modes={"http", "ws", "sse"},
        pages=menu(BabashkaTerminal),
        brand_name="Hiccl Babashka REPL",
        theme="night",
    )
)

if __name__ == "__main__":
    import uvicorn

    print("Starting Babashka Shared Terminal standalone example...")
    print("URL: http://127.0.0.1:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
