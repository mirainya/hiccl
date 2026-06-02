# Hiccl 框架快速入门指南：像搭积木一样开发全栈 Web 应用 🧪🥒

欢迎来到 **Hiccl**（读作 `/ˈhɪk.l̩/`）的世界！

Hiccl 是一个全栈反应式 Python Web 框架，旨在解决现代 Web 开发中前后端分离带来的复杂性（繁琐的 API 接口、多语言切换、状态管理包袱）。它继承了 Clojure **Hiccup** 的声明式 UI 基因与 Pythonic **Pickle** 的状态追踪管理，让你可以仅用纯 Python 语言，就能开发出高颜值、响应式且运行丝滑的现代全栈 Web 应用。

本指南将结合直观的工程比喻，带你快速上手 Hiccl，并拆解它的核心机制。

---

## 🎯 核心设计哲学：全栈单一语言模型

在传统开发中，你需要同时编写前端（React/Vue/TS）与后端（Python/Go），并在它们之间用 REST API 或 GraphQL 搭建桥梁。

Hiccl 彻底打破了这一边界：
```
传统模式: [ 浏览器 (JS/TS) ] <=== REST API / JSON ===> [ 服务器 (Python) ]
Hiccl 模式: [ 浏览器 ] <=========== WebSocket 自动增量 Diff ===========> [ Python Component 类 (全栈) ]
```
你的界面、业务逻辑、状态和并发控制都在同一个 Python 类中声明，框架会自动在底层处理所有的网络同步。

---

## 📦 前端技术栈：No-Build 与离线就绪

为了实现“无需任何打包构建步骤（No-Build）”和“完全离线/内网就绪（Air-gapped Ready）”，Hiccl 的前端并没有使用繁琐的 Webpack/Vite 编译链，而是由一个轻量级的自研客户端核心配合 4 个经典的前端库共同驱动：

1. **Alpine.js (`alpine.js`)**：轻量级客户端响应式框架。用于处理本地高频交互（如毫秒级本地计时器、滑块、手风琴菜单），避免每一次微小的本地状态变化都产生网络往返延迟。
2. **HTMX (`htmx.js`)**：声明式行为捕捉与通信降级。在网络正常时，Hiccl 会自动拦截 HTMX 的常规 HTTP 动作并重定向到高效的 **WebSocket 通道** 进行双向通信；而在网络断开或异常时，它会自动降级回 HTMX 经典的 **HTTP AJAX/SSE**，保证服务健壮性。
3. **Tailwind CSS (`tailwind.js`)**：运行时的原子化 CSS 框架。采用本地托管的 Play CDN 运行时，免去了开发者在本地运行 Node.js 编译器的打包步骤，直接在前端实时渲染样式。
4. **DaisyUI (`daisyui.css`)**：基于 Tailwind 的高颜值毛玻璃/暗色调组件库。提供开箱即用的各种卡片、按钮和聊天气泡样式，令拼装出的界面天生具备现代化质感。
5. **Hiccl 客户端核心 (`hiccl.js`)**：自研的前端核心胶水。负责维护 WebSocket/SSE 的长连接与重连，接收服务器发来的局部补丁（Patch）并精准替换 DOM 节点，并桥接 HTMX 转场与 Alpine.js 树节点的激活初始化。

---

## 🚀 1. 快速上手：运行你的第一个计数器

在开始之前，确保你已安装 `uv`（现代化 Python 包管理工具）。

### 编写 `app.py`

创建一个 `app.py`，写入以下极简的响应式计数器代码：

```python
from hiccl import (
    Component,
    ComponentRegistry,
    HicclConfig,
    create_hiccl_app,
    menu,
    server,
    signal,
)
from hiccl.hiccup import button, div, h2

# 1. 创建组件注册表
registry = ComponentRegistry()

# 2. 定义组件类
class Counter(Component):
    """一个响应式的计数器组件"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 初始化状态信号，默认值为 0
        self.count = signal(0)

    @server
    def increment(self, step: int = 1):
        """服务器端事件处理器：加分"""
        if isinstance(step, str):
            step = int(step)
        self.count.set(self.count.get() + step)

    @server
    def decrement(self, step: int = 1):
        """服务器端事件处理器：减分"""
        if isinstance(step, str):
            step = int(step)
        self.count.set(self.count.get() - step)

    def render(self):
        """渲染函数：使用 Python 列表声明式表达 UI"""
        count = self.count.get()
        return div(
            {"class": "card w-96 bg-base-200 shadow-xl border border-base-300 mx-auto mt-10"},
            div(
                {"class": "card-body items-center text-center"},
                h2(
                    {"class": "card-title text-3xl font-extrabold mb-4"},
                    f"Count: {count}",
                ),
                div(
                    {"class": "card-actions justify-center gap-2"},
                    button(
                        {"class": "btn btn-error", "on_click": self.decrement(1)}, 
                        "-1"
                    ),
                    button(
                        {"class": "btn btn-success", "on_click": self.increment(1)},
                        "+1",
                    ),
                ),
            ),
        )

# 3. 配置并启动应用 (menu 自动生成对应的路由和导航栏)
app = create_hiccl_app(
    HicclConfig(
        component_registry=registry, 
        pages=menu(Counter),
        brand_name="Hiccl Quickstart"
    )
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

### 运行应用

1. 启动服务：
   ```bash
   uv run python app.py
   ```
2. 打开浏览器访问 `http://127.0.0.1:8000`。
3. 点击 `+1` 或 `-1` 按钮，你会发现分数变化非常流畅，且没有任何页面闪烁。

---

## 🛠 2. 深度拆解：Hiccl 核心概念

通过上述例子，我们来看看 Hiccl 是如何在底层协同工作的。

### 概念 A：Hiccup 声明式积木 (UI 表达)
传统的网页通过写各种 HTML 标签（如 `<div>`）来砌墙。Hiccl 引入了 **Hiccup 语法糖**，让你用纯粹的 Python 列表或辅助函数来声明界面结构：
```python
# 传统的 HTML 表达:
# <div class="btn-group"><button class="btn">Click me</button></div>

# Hiccl 表达:
div({"class": "btn-group"}, 
    button({"class": "btn"}, "Click me")
)
```
* **特点**：结构完全对应，不需要处理 HTML 标签未闭合的语法问题，支持 Python 类型检查。
* **事件映射**：当你在属性中写 `"on_click": self.increment(1)` 时，Hiccl 会在渲染时将它捕捉并转化为底层的网络异步调用。

---

### 概念 B：多米诺联动系统 (Signals 反应式状态)
在网页里，数据是会变动的。Hiccl 提供了三个基础响应式原语：
* **`Signal(value)` (数据源)**：持有一个基本数据。调用 `.get()` 会读取数据并自动建立依赖关系；调用 `.set(new_value)` 会改变数据并通知相关联动者。
* **`ComputedSignal` (派生计算)**：它的值依赖于其他的 Signal。当源头数据改变时，它会自动重新计算。
* **`Effect` (副作用)**：当它依赖的 Signal 变化时，它会自动重新执行相关的逻辑（例如重新渲染组件）。

```python
from hiccl import signal, computed, effect

score = signal(10)
# 联动计算：当 score 改变时，level 会自动重新算值
level = computed(lambda: "Legend" if score.get() >= 100 else "Rookie")

# 联动执行：自动打印
effect(lambda: print(f"当前等级: {level.get()}")) 

score.set(120)  # 触发多米诺联动，控制台会自动打印: "当前等级: Legend"
```

为了防止高频连续修改引起页面无意义的反复刷新，你可以使用 `batch()` 将修改打包。只有在 block 结束时，框架才会合并触发一次渲染更新：
```python
from hiccl import batch

with batch():
    score.set(20)
    score.set(30)  # 只会在退出 batch 时触发一次页面重绘
```

---

### 概念 C：聪明的增量刷新 (Diff & Patch 引擎)
当数据变动触发重绘时，Hiccl 不会粗暴地把整个网页拆掉重建，而是按以下流程工作：
1. **虚拟对比**：重新在内存中生成该组件的新虚拟节点，并与旧节点对比。
2. **生成补丁**：计算并提取变化的最小差异（例如，仅第 5 行文本发生了改变）。
3. **精准推送**：通过 WebSocket/SSE 通道发送一个包含最小 HTML 补丁的 JSON 数据。
4. **局部置换**：浏览器端的轻量级 JS 脚本接收到补丁后，仅仅局部替换变动的地方，完全无卡顿和闪烁。

---

### 概念 D：时光倒流快照 (Time Travel)
做错事了想要撤销？Hiccl 提供内置的状态快照历史追踪。只需使用 `Signal.with_history()`：

```python
class TextEditor(Component):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 启用带历史快照的状态信号（默认最多存 50 个历史版本）
        self.text = signal_with_history("Hello")

    @server
    def undo(self):
        self.text.undo()  # 回退到上一个版本

    @server
    def redo(self):
        self.text.redo()  # 前进到撤销前的版本
```
每次状态的 `.set()` 都会拍摄不可变的数据快照，让你的应用具备天然的撤销/重做（Undo/Redo）和时间穿梭（Time Travel）能力。

---

### 概念 E：名侦探数据检索 (Datalog 声明式查询)
当你在全栈应用中需要处理复杂的网状关系数据时，传统的数据库检索往往需要复杂的 SQL 或者大量的 Python 循环。Hiccl 内置了一个极简的声明式查询引擎 **Datalog**：

```python
from hiccl.datalog import Database, var

db = Database()
# 写入一系列“事实” (Entity, Attribute, Value)
db.transact([
    ("alice", "parent", "bob"),    # bob 是 alice 的父亲
    ("bob", "parent", "charlie"),  # charlie 是 bob 的父亲
    ("bob", "age", 45),
])

# 逻辑查询：找出所有祖父 (谁的父亲的父亲是 charlie)
x, y = var("x", "y")
results = db.query(x).where(
    (x, "parent", y),
    (y, "parent", "charlie")
).execute()

print(results)  # {('alice',)}
```
* **Time Travel 查询**：Datalog 支持通过 `db.as_of(tx_id)` 创建任意历史时刻的只读快照。你可以直接查询“昨天下午 3 点”时数据库的数据关系，极其强大。

---

### 概念 F：有条不紊的“数据管道” (CSP 并发)
在处理多任务实时并发（例如：实时行情刷新、多人聊天总线、定时器）时，为了防止状态抢占和死锁，Hiccl 提供了 CSP 管道模型：
* **`Channel`**：非阻塞的数据传送带，支持同步阻塞或容量限制。
* **`alts_`**：多路公平监听器，能同时监听多个管道，哪个先来就处理哪个。
* **`@go`**：将函数投递到后台静默运行的协程调度器。

```python
from hiccl.csp import Channel, go, timeout, alts_

async def process_inputs():
    chan_a = Channel()
    chan_b = Channel()
    
    # 模拟后台往管道放数据
    @go
    async def sender():
        await chan_a.put("Message A")
    
    # 同时监听 chan_a、chan_b 以及一个 2 秒的超时通道
    # 哪一个通道最先准备好，就立刻处理哪一个
    selected, value = await alts_([chan_a, chan_b, timeout(2000)])
    print(f"最快胜出的通道是: {selected}, 值是: {value}")
```

---

## 🤖 3. AI Agent 友好特性

Hiccl 能够极大提高使用 AI（如 Claude, Copilot）自动生成网页的成功率。原因在于：
1. **单一文件闭环**：AI 不需要理解庞大的前端工程目录（Vite/Node/TS），只需要读懂一个 Python 组件类的逻辑。
2. **零 API 接口**：省去了 REST 路由和强类型传输格式（Pydantic Schema）的对齐，排除了 80% 的 AI “脑子打结”（幻觉）报错。
3. **强类型与契约守卫**：支持声明 `hiccl.spec` 契约，类型报错信息非常直观，AI 程序员能极其容易地通过测试报错实现“自主纠错与自愈”。

---

## 🎨 4. 高级实战：用 EventBus 搭建多人实时聊天室

下面是一个基于 MQTT 风格层级通配符总线的**多人实时同步聊天室**示例。只要在两个不同的浏览器窗口打开此页面，它们之间就可以通过后台的广播机制实现同步聊天：

```python
from datetime import datetime
from hiccl import Component, ComponentRegistry, HicclConfig, create_hiccl_app, menu, server, signal
from hiccl.hiccup import button, div, form, h2, input_

# 全局共享消息内存
shared_messages = []

class ChatRoom(Component):
    # 订阅主题，当此主题有广播时，自动触发 on_broadcast
    topics = ["chat-messages"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages = signal([])

    @server
    def send_message(self, text: str = "", user: str = "Anonymous"):
        if not text.strip():
            return
        
        msg = {
            "user": user,
            "text": text,
            "time": datetime.now().strftime("%H:%M:%S")
        }
        shared_messages.append(msg)
        # 通过事件总线向所有在线用户的该组件广播更新
        self._session.event_bus.publish("chat-messages", msg)

    def on_broadcast(self, topic: str, payload: dict = None) -> None:
        """事件总线监听到消息，自动触发刷新"""
        if topic == "chat-messages":
            self.messages.set(list(shared_messages))

    def render(self):
        msgs = self.messages.get()
        return div(
            {"class": "card bg-base-200 shadow-xl w-full max-w-xl mx-auto mt-10 p-6"},
            h2({"class": "text-2xl font-bold mb-4 text-center"}, "Hiccl Chat Room"),
            # 消息展示区
            div(
                {"class": "bg-base-100 border border-base-300 rounded-xl p-4 h-80 overflow-y-auto flex flex-col gap-2"},
                *[
                    div(
                        {"class": "p-2 bg-base-200 rounded-lg"},
                        div({"class": "text-xs text-secondary font-bold"}, f"{m['user']} ({m['time']})"),
                        div({"class": "text-sm mt-1"}, m["text"])
                    ) for m in msgs
                ]
            ),
            # 输入表单
            form(
                {"class": "join mt-4", "on_submit": self.send_message},
                input_({
                    "type": "text",
                    "name": "user",
                    "value": "Anonymous",
                    "class": "input input-bordered join-item w-24"
                }),
                input_({
                    "type": "text",
                    "name": "text",
                    "placeholder": "输入你的消息...",
                    "required": True,
                    "class": "input input-bordered join-item flex-1"
                }),
                button({"type": "submit", "class": "btn btn-primary join-item"}, "发送")
            )
        )

registry = ComponentRegistry()
app = create_hiccl_app(
    HicclConfig(
        component_registry=registry, 
        pages=menu(ChatRoom),
        brand_name="Hiccl Chat Demo"
    )
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
```

---

## 🚀 结语与下一步

Hiccl 巧妙地融合了声明式 UI 与反应式状态管理，提供了极高的开发体验（Developer Experience）和稳固的并发模型。

* 想了解更高级的路由和主题配置？查看 [ROADMAP.md](file:///Volumes/udisk/code/pwicip/volt/ROADMAP.md)；
* 想参考复杂的综合应用？启动并阅读 [combined_app.py](file:///Volumes/udisk/code/pwicip/volt/examples/combined_app.py)；
* 想深入研读整体设计思路？查阅 [design.md](file:///Volumes/udisk/code/pwicip/volt/design.md)。

现在，带上你的想法，开启你的 Hiccl 编程之旅吧！🥒🧪
