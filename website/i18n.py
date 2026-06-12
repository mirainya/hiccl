"""Bilingual (zh/en) translation strings for hiccl.dev official website."""

from __future__ import annotations

from typing import TypedDict


class NavDict(TypedDict):
    features: str
    stack: str
    quickstart: str
    install: str
    github: str


class HeroDict(TypedDict):
    badge: str
    title_line1: str
    title_line2: str
    subtitle: str
    cta_quickstart: str
    cta_github: str
    version_label: str


class FeatureDict(TypedDict):
    title: str
    subtitle: str
    items: list[dict[str, str]]


class StackDict(TypedDict):
    title: str
    subtitle: str
    layers: list[dict[str, str]]


class QuickStartDict(TypedDict):
    title: str
    subtitle: str
    step1_title: str
    step1_desc: str
    step2_title: str
    step2_desc: str
    step3_title: str
    step3_desc: str
    code_title: str


class InstallDict(TypedDict):
    title: str
    subtitle: str
    pip_label: str
    uv_label: str
    repo_title: str
    repo_desc: str
    stars: str
    license_label: str


class FooterDict(TypedDict):
    made_with: str
    rights: str


class I18nDict(TypedDict):
    nav: NavDict
    hero: HeroDict
    features: FeatureDict
    stack: StackDict
    quickstart: QuickStartDict
    install: InstallDict
    footer: FooterDict


ZH: I18nDict = {
    "nav": {
        "features": "特性",
        "stack": "技术栈",
        "quickstart": "快速上手",
        "install": "安装",
        "github": "GitHub",
    },
    "hero": {
        "badge": "🧪 v0.7.0 — 全栈反应式 Web 框架",
        "title_line1": "融合 Clojure 声明式基因",
        "title_line2": "与 Pythonic 全栈反应式",
        "subtitle": "纯 Python 编写全栈应用。零构建、零 API 胶水、天生离线就绪。用嵌套列表表达 UI，框架自动完成 WebSocket 双向同步与最小化 DOM 补丁推送。",
        "cta_quickstart": "🚀 快速上手",
        "cta_github": "⭐ GitHub",
        "version_label": "最新版本 v0.7.0 · MIT 开源",
    },
    "features": {
        "title": "⚡️ 核心特性",
        "subtitle": "Hiccl 继承了 Clojure 的优雅哲学，在 Python 生态中打造现代化全栈开发体验。",
        "items": [
            {
                "emoji": "🧩",
                "title": "Hiccup 声明式 UI",
                "desc": "纯 Python 嵌套列表表达整个 DOM 结构，告别模板语言和 JSX。自动绑定事件到服务端方法。",
            },
            {
                "emoji": "🔌",
                "title": "Signal 反应式状态",
                "desc": "signal / computed / effect 三大原语，搭配 batch() 批量事务。状态变更自动触发最小化虚拟 DOM Diff。",
            },
            {
                "emoji": "🛡️",
                "title": "Spec 运行时契约",
                "desc": "Clojure-like 声明式数据契约守卫 @server 方法边界。结构化 explain_data 报错，赋能 AI Agent 自愈闭环。",
            },
            {
                "emoji": "🔀",
                "title": "MQTT 通配符 EventBus",
                "desc": "原生层级通配符订阅（* 单层 / # 多层），高性能正则缓存路由，轻松构建多人实时协作应用。",
            },
            {
                "emoji": "🧩",
                "title": "Reagent 纯函数组件",
                "desc": "use_signal() / subscribe() / dispatch() 单向数据流。展示层纯函数 + 状态层 OOP，UI 与副作用深度解耦。",
            },
            {
                "emoji": "📡",
                "title": "CSP 并发管道",
                "desc": "Pythonic Channel（背压/缓冲/安全关闭）、alts_ 公平多路选择、@go 后台协程调度器。",
            },
            {
                "emoji": "🔀",
                "title": "Transducers 渲染中间件",
                "desc": "DFS 不可变树变换管线。内置 LoadingTransducer（自动加载态）与 SanitizingTransducer（敏感数据脱敏）。",
            },
            {
                "emoji": "⏳",
                "title": "时间旅行调试器",
                "desc": "Signal.with_history() 状态快照，可视化撤销/重做面板，多会话安全隔离。",
            },
            {
                "emoji": "🧬",
                "title": "Datalog 声明式查询",
                "desc": "Datomic 风格 EAVT/AVE/VAE 索引，Logic Unification 求解器，GraphQL-like Pull API，as_of 历史回溯。",
            },
            {
                "emoji": "🎨",
                "title": "内置 DaisyUI + TailwindCSS",
                "desc": "开箱即用暗色毛玻璃组件库与原子化样式。零构建步骤，纯 Play CDN 运行时。",
            },
            {
                "emoji": "🌿",
                "title": "Alpine.js 客户端加速",
                "desc": "高频本地交互（60fps 计时器、滑块、手风琴）无需网络往返，标准 HTML 属性声明式激活。",
            },
            {
                "emoji": "📦",
                "title": "100% 离线与内网就绪",
                "desc": "所有静态依赖完全本地托管。物理隔离网络内高速运行，零外部 CDN 依赖。",
            },
        ],
    },
    "stack": {
        "title": "🛠 技术栈",
        "subtitle": "Hiccl 的全栈架构由五个精心编排的层次构成，每一层都聚焦于特定的职责。",
        "layers": [
            {
                "name": "🎯 Hiccl 内核",
                "desc": "Signal 反应式引擎 · Hiccup DSL 渲染器 · 虚拟 DOM Diff · 会话管理 · 组件生命周期",
                "color": "border-emerald-400",
            },
            {
                "name": "⚡ FastAPI / Starlette",
                "desc": "高性能异步 HTTP 服务 · WebSocket/SSE 双通道传输 · CORS 中间件 · 静态文件服务",
                "color": "border-cyan-400",
            },
            {
                "name": "🌐 通信胶水层",
                "desc": "HTMX — 声明式请求拦截与降级 · hiccl.js — WebSocket 长连接管理 · DOM 补丁精准替换",
                "color": "border-violet-400",
            },
            {
                "name": "🎨 样式 & 组件库",
                "desc": "TailwindCSS Play CDN 运行时 · DaisyUI 毛玻璃暗色组件 · 完全本地托管，零构建步骤",
                "color": "border-pink-400",
            },
            {
                "name": "🌿 客户端响应式",
                "desc": "Alpine.js — 轻量级客户端 MVVM · 高频本地交互无网络延迟 · 与 Hiccl 服务端状态无缝桥接",
                "color": "border-amber-400",
            },
        ],
    },
    "quickstart": {
        "title": "🚀 快速上手",
        "subtitle": "30 行代码，从零到运行一个全栈响应式计数器。",
        "step1_title": "① 安装 Hiccl",
        "step1_desc": "使用 pip 或 uv 安装框架本体。",
        "step2_title": "② 编写组件",
        "step2_desc": "创建一个 Python 文件，用 Hiccup DSL 声明 UI，用 @server 声明事件。",
        "step3_title": "③ 启动服务",
        "step3_desc": "一行命令启动开发服务器，浏览器即刻看到响应式界面。",
        "code_title": "📄 counter_app.py — 极简全栈计数器",
    },
    "install": {
        "title": "📦 安装 Hiccl",
        "subtitle": "一行命令即可将 Hiccl 添加到你的 Python 项目中。",
        "pip_label": "使用 pip",
        "uv_label": "使用 uv（推荐）",
        "repo_title": "GitHub 开源仓库",
        "repo_desc": "欢迎 ⭐ Star、🐛 Issue、🤝 PR！完整源码、210+ 单元测试、路线图尽在 GitHub。",
        "stars": "GitHub Stars",
        "license_label": "MIT License · Python ≥ 3.11",
    },
    "footer": {
        "made_with": "由 Hiccl 自举构建 · 本网站使用 Hiccl 框架自身编写",
        "rights": "© 2025 Hiccl Contributors. MIT License.",
    },
}

EN: I18nDict = {
    "nav": {
        "features": "Features",
        "stack": "Stack",
        "quickstart": "QuickStart",
        "install": "Install",
        "github": "GitHub",
    },
    "hero": {
        "badge": "🧪 v0.7.0 — Full-Stack Reactive Web Framework",
        "title_line1": "Clojure's Declarative Gene",
        "title_line2": "Meets Pythonic Full-Stack Reactivity",
        "subtitle": "Build full-stack apps in pure Python. Zero build, zero API glue, air-gapped ready. Express UI with nested lists — the framework handles WebSocket bidirectional sync and minimal DOM patch pushes automatically.",
        "cta_quickstart": "🚀 Quick Start",
        "cta_github": "⭐ GitHub",
        "version_label": "Latest v0.7.0 · MIT Open Source",
    },
    "features": {
        "title": "⚡️ Key Features",
        "subtitle": "Hiccl inherits Clojure's elegant philosophy, crafting a modern full-stack development experience within the Python ecosystem.",
        "items": [
            {
                "emoji": "🧩",
                "title": "Hiccup Declarative UI",
                "desc": "Express entire DOM structures with pure Python nested lists. Say goodbye to template languages and JSX. Events auto-bind to server-side methods.",
            },
            {
                "emoji": "🔌",
                "title": "Signal Reactive State",
                "desc": "Three primitives — signal / computed / effect — plus batch() transactions. State changes auto-trigger minimal virtual-DOM diffs.",
            },
            {
                "emoji": "🛡️",
                "title": "Spec Runtime Contracts",
                "desc": "Clojure-like declarative data contracts guarding @server method boundaries. Structured explain_data errors empower AI agent self-healing loops.",
            },
            {
                "emoji": "🔀",
                "title": "MQTT Wildcard EventBus",
                "desc": "Native hierarchical wildcard subscriptions (* single / # multi level) with high-performance regex cache routing for real-time collaboration.",
            },
            {
                "emoji": "🧩",
                "title": "Reagent Functional Components",
                "desc": "use_signal() / subscribe() / dispatch() unidirectional data flow. Pure-function presentation layer + OOP state layer, deeply decoupled.",
            },
            {
                "emoji": "📡",
                "title": "CSP Concurrency Channels",
                "desc": "Pythonic Channel (backpressure/buffered/safe-close), alts_ fair multiplexing, @go background coroutine scheduler.",
            },
            {
                "emoji": "🔀",
                "title": "Transducers Middleware",
                "desc": "DFS immutable tree transformation pipeline. Built-in LoadingTransducer (auto-spinner) and SanitizingTransducer (data masking).",
            },
            {
                "emoji": "⏳",
                "title": "Time-Travel Debugger",
                "desc": "Signal.with_history() state snapshots. Visual undo/redo panel with multi-session isolation, out of the box.",
            },
            {
                "emoji": "🧬",
                "title": "Datalog Declarative Query",
                "desc": "Datomic-style EAVT/AVE/VAE indices, Logic Unification solver, GraphQL-like Pull API, as_of historical snapshot querying.",
            },
            {
                "emoji": "🎨",
                "title": "Built-in DaisyUI + TailwindCSS",
                "desc": "Dark-mode glassmorphic component library + utility-first styling out of the box. Zero build steps, pure Play CDN runtime.",
            },
            {
                "emoji": "🌿",
                "title": "Alpine.js Client Acceleration",
                "desc": "High-frequency local interactions (60fps timers, sliders, accordions) without network round-trips. Declarative HTML attribute activation.",
            },
            {
                "emoji": "📦",
                "title": "100% Offline & Air-Gapped",
                "desc": "All static dependencies hosted locally. Run at full speed in physically isolated networks with zero external CDN dependencies.",
            },
        ],
    },
    "stack": {
        "title": "🛠 Tech Stack",
        "subtitle": "Hiccl's full-stack architecture is composed of five carefully orchestrated layers, each focused on a specific responsibility.",
        "layers": [
            {
                "name": "🎯 Hiccl Core",
                "desc": "Signal Reactive Engine · Hiccup DSL Renderer · Virtual DOM Diff · Session Management · Component Lifecycle",
                "color": "border-emerald-400",
            },
            {
                "name": "⚡ FastAPI / Starlette",
                "desc": "High-Performance Async HTTP · WebSocket/SSE Dual Transport · CORS Middleware · Static File Serving",
                "color": "border-cyan-400",
            },
            {
                "name": "🌐 Communication Glue",
                "desc": "HTMX — Declarative Request Interception & Fallback · hiccl.js — WebSocket Keep-Alive · DOM Patch Precision Replacement",
                "color": "border-violet-400",
            },
            {
                "name": "🎨 Styling & Components",
                "desc": "TailwindCSS Play CDN Runtime · DaisyUI Glassmorphic Dark Components · Fully Local Hosting, Zero Build Steps",
                "color": "border-pink-400",
            },
            {
                "name": "🌿 Client-Side Reactivity",
                "desc": "Alpine.js — Lightweight Client MVVM · High-Frequency Local Interactions · Seamless Bridge with Hiccl Server State",
                "color": "border-amber-400",
            },
        ],
    },
    "quickstart": {
        "title": "🚀 Quick Start",
        "subtitle": "30 lines of code, from zero to a running full-stack reactive counter.",
        "step1_title": "① Install Hiccl",
        "step1_desc": "Install the framework via pip or uv.",
        "step2_title": "② Write a Component",
        "step2_desc": "Create a Python file, declare UI with Hiccup DSL, declare events with @server.",
        "step3_title": "③ Launch the Server",
        "step3_desc": "One command to start the dev server. See your reactive UI instantly in the browser.",
        "code_title": "📄 counter_app.py — Minimal Full-Stack Counter",
    },
    "install": {
        "title": "📦 Install Hiccl",
        "subtitle": "Add Hiccl to your Python project with a single command.",
        "pip_label": "Using pip",
        "uv_label": "Using uv (recommended)",
        "repo_title": "GitHub Repository",
        "repo_desc": "Welcome ⭐ Star, 🐛 Issue, 🤝 PR! Full source code, 210+ unit tests, and roadmap all on GitHub.",
        "stars": "GitHub Stars",
        "license_label": "MIT License · Python ≥ 3.11",
    },
    "footer": {
        "made_with": "Built with Hiccl itself · This website is written using the Hiccl framework",
        "rights": "© 2025 Hiccl Contributors. MIT License.",
    },
}

# QuickStart code — same for both languages
COUNTER_CODE = """from hiccl import (
    Component, ComponentRegistry,
    HicclConfig, create_hiccl_app,
    menu, server, signal,
)
from hiccl.hiccup import button, div, h2

registry = ComponentRegistry()

class Counter(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.count = signal(0)

    @server
    def increment(self, step: int = 1):
        if isinstance(step, str):
            step = int(step)
        self.count.set(self.count.get() + step)

    @server
    def decrement(self, step: int = 1):
        if isinstance(step, str):
            step = int(step)
        self.count.set(self.count.get() - step)

    def render(self):
        count = self.count.get()
        return div(
            {"class": "card w-96 bg-base-200 shadow-xl mx-auto mt-10"},
            div({"class": "card-body items-center text-center"},
                h2({"class": "card-title text-3xl font-extrabold"},
                   f"Count: {count}"),
                div({"class": "card-actions justify-center gap-2"},
                    button({"class": "btn btn-error",
                            "on_click": self.decrement(1)}, "-1"),
                    button({"class": "btn btn-success",
                            "on_click": self.increment(1)}, "+1"),
                ),
            ),
        )

app = create_hiccl_app(HicclConfig(
    component_registry=registry,
    pages=menu(Counter),
    brand_name="Hiccl Quickstart"
))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)"""


def detect_lang(accept_language: str) -> str:
    """Detect preferred language from Accept-Language header."""
    if not accept_language:
        return "en"
    # Simple detection: look for 'zh' in the first language tag
    first = accept_language.split(",")[0].strip().lower()
    if first.startswith("zh"):
        return "zh"
    return "en"
