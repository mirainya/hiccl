"""Hiccl Datalog-lite Web Premium Demo 🧪✨

Interactive web showcase demonstrating:
1. JSON state tree flattening with `Database.from_state`
2. Fluent logic queries & Clause Reordering optimization
3. Declarative Pull API nested visualizer
4. Lazy Entity Graph Traversal navigator
5. Transaction log & `as_of` time travel

Refactored into fine-grained subcomponents to target specific DOM areas for HTMX updates,
ensuring smooth rendering without reloading the entire window.
"""

from __future__ import annotations

import ast
import json
import time
from typing import Any

import uvicorn

from hiccl import (
    Component,
    ComponentRegistry,
    HicclConfig,
    create_hiccl_app,
    set_registry,
    signal,
    server,
    Database,
    component,
)
from hiccl.datalog import Var
from hiccl.hiccup import (
    button,
    div,
    form,
    h1,
    h3,
    input_,
    p,
    raw,
    span,
    table,
    thead,
    tbody,
    tr,
    th,
    td,
    textarea,
)

# ---------------------------------------------------------------------------
# 0. Global Registry & App Configuration presets
# ---------------------------------------------------------------------------
registry = ComponentRegistry()
set_registry(registry)

PRESET_STATE = {
    "id": "comp_1",
    "name": "Volt Technologies",
    "employees": [
        {
            "id": "e_shiunko",
            "name": "Shiunko",
            "role": "Lead Architect",
            "skills": ["Python", "Clojure", "Datalog"],
        },
        {
            "id": "e_alice",
            "name": "Alice",
            "role": "Senior UI Engineer",
            "skills": ["Hiccup", "Tailwind", "Alpine.js"],
        },
        {
            "id": "e_bob",
            "name": "Bob",
            "role": "Backend Engineer",
            "skills": ["Python", "FastAPI", "SQL"],
        },
    ],
    "projects": [
        {
            "id": "p_hiccl",
            "name": "Hiccl Reactive Engine",
            "lead": "e_shiunko",
            "status": "critical",
        },
        {
            "id": "p_volt",
            "name": "Volt Builder Dashboard",
            "lead": "e_alice",
            "status": "active",
        },
    ],
}

PRESETS = [
    {
        "name": "🔍 查找研发项目中所有核心成员及分工",
        "vars": "?proj_name, ?lead_name, ?lead_role",
        "where": "?proj, name, ?proj_name\n?proj, lead, ?lead\n?lead, name, ?lead_name\n?lead, role, ?lead_role",
    },
    {
        "name": "🔍 寻找掌握 Datalog 技能的所有员工姓名及当前角色",
        "vars": "?name, ?role",
        "where": "?emp, name, ?name\n?emp, role, ?role\n?emp, skills, Datalog",
    },
    {
        "name": "🔍 关联查询：查出被指派到 critical 项目下的员工所掌握的所有技能",
        "vars": "?proj_name, ?emp_name, ?skill",
        "where": "?proj, status, critical\n?proj, name, ?proj_name\n?proj, lead, ?lead\n?lead, name, ?emp_name\n?lead, skills, ?skill",
    },
]

# ---------------------------------------------------------------------------
# 1. Subcomponents Design (Fine-Grained UI Scopes)
# ---------------------------------------------------------------------------


@component("datalog-sidebar")
class DatalogSidebar(Component):
    """Sidebar component wrapping Database stats, time timeline, EAVT datoms, and Fact creation."""

    parent: Any = None
    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    new_e: Any = None
    new_a: Any = None
    new_v: Any = None

    @server
    def set_view_tx(self, tx_id: str) -> None:
        self.view_tx.set(int(tx_id))

    @server
    def add_fact(self, new_e: str, new_a: str, new_v: str) -> None:
        self.new_e.set(new_e)
        self.new_a.set(new_a)
        self.new_v.set(new_v)

        if not new_e.strip() or not new_a.strip() or not new_v.strip():
            return

        try:
            val = new_v.strip()
            if val.isdigit():
                val = int(val)
            elif (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]

            self.base_db.transact([(new_e.strip(), new_a.strip(), val)])
            self.db_version.set(self.db_version.get() + 1)
            self.view_tx.set(0)

            self.new_e.set("")
            self.new_a.set("")
            self.new_v.set("")
        except Exception:
            pass

    def render(self) -> list:
        # Register dependencies
        _version = self.db_version.get()
        tx_current = self.view_tx.get()
        latest_tx = self.base_db._tx

        # Get active db snapshot
        db = self.base_db if tx_current == 0 else self.base_db.as_of(tx_current)
        all_datoms = sorted(list(db.datoms), key=lambda d: (d.t, d.e, d.a))

        timeline_pills = []
        timeline_pills.append(
            button(
                {
                    "class": f"btn btn-xs rounded-lg font-bold transition-all duration-300 {'btn-success shadow-[0_0_10px_rgba(34,197,94,0.4)]' if tx_current == 0 else 'btn-outline border-success/30 text-success hover:bg-success hover:text-white'}",
                    "on_click": self.set_view_tx("0"),
                },
                "⚡ Latest Present",
            )
        )
        for tx in range(1, latest_tx + 1):
            is_active = tx_current == tx
            timeline_pills.append(
                button(
                    {
                        "class": f"btn btn-xs rounded-lg font-mono transition-all duration-300 {'btn-warning shadow-[0_0_10px_rgba(234,179,8,0.4)]' if is_active else 'btn-outline border-warning/30 text-warning hover:bg-warning hover:text-white'}",
                        "on_click": self.set_view_tx(str(tx)),
                    },
                    f"Tx-{tx}",
                )
            )

        datom_rows = []
        for d in all_datoms:
            is_val_entity = any(e == d.v for (e, _) in db._eav.keys())
            val_display = d.v
            if is_val_entity:
                val_display = button(
                    {
                        "class": "badge badge-primary hover:scale-105 transition-all text-[10px] py-1 border-none",
                        "on_click": self.parent.navigate_entity(str(d.v)),
                    },
                    f"🔗 {d.v}",
                )

            datom_rows.append(
                tr(
                    {
                        "class": "hover:bg-white/5 border-b border-white/5 font-mono text-xs"
                    },
                    td({"class": "text-white/80 font-bold"}, d.e),
                    td({"class": "text-primary"}, d.a),
                    td(None, val_display),
                    td({"class": "text-warning text-center"}, f"tx-{d.t}"),
                )
            )

        return div(
            {"class": "flex flex-col gap-6 w-full"},
            # Status Indicator
            div(
                {
                    "class": "card bg-neutral/40 border border-white/10 p-5 rounded-2xl backdrop-blur-md flex flex-col gap-3 shadow-xl"
                },
                div(
                    {"class": "flex justify-between items-center"},
                    span(
                        {"class": "text-sm font-bold text-white/90"},
                        "🧬 Datalog-lite 核心状态",
                    ),
                    span(
                        {
                            "class": f"badge text-xs px-2.5 py-1.5 border-none font-bold {'bg-success/20 text-success' if tx_current == 0 else 'bg-warning/20 text-warning animate-pulse'}"
                        },
                        "🔴 实时最新"
                        if tx_current == 0
                        else f"🕰️ 时空回溯 (Tx-{tx_current})",
                    ),
                ),
                div(
                    {
                        "class": "flex flex-wrap gap-1.5 mt-2 bg-black/30 p-2 rounded-xl border border-white/5"
                    },
                    *timeline_pills,
                ),
            ),
            # Add Fact Panel
            div(
                {
                    "class": "card bg-neutral/40 border border-white/10 p-5 rounded-2xl backdrop-blur-md flex flex-col gap-3 shadow-xl"
                },
                h3(
                    {
                        "class": "text-xs font-black text-primary uppercase tracking-wider"
                    },
                    "✍ Transact 新事实",
                ),
                form(
                    {"class": "flex flex-col gap-2.5", "on_submit": self.add_fact},
                    div(
                        {"class": "grid grid-cols-3 gap-1.5"},
                        input_(
                            {
                                "type": "text",
                                "name": "new_e",
                                "value": self.new_e.get(),
                                "class": "input input-bordered input-xs bg-black/20 text-xs w-full",
                                "placeholder": "Entity (e_id)",
                            }
                        ),
                        input_(
                            {
                                "type": "text",
                                "name": "new_a",
                                "value": self.new_a.get(),
                                "class": "input input-bordered input-xs bg-black/20 text-xs w-full",
                                "placeholder": "Attr (name)",
                            }
                        ),
                        input_(
                            {
                                "type": "text",
                                "name": "new_v",
                                "value": self.new_v.get(),
                                "class": "input input-bordered input-xs bg-black/20 text-xs w-full",
                                "placeholder": "Value",
                            }
                        ),
                    ),
                    button(
                        {
                            "type": "submit",
                            "class": "btn btn-primary btn-xs font-bold w-full shadow-lg",
                        },
                        "🚀 Transact 写入",
                    ),
                ),
            ),
            # EAVT Table explorer
            div(
                {
                    "class": "card bg-neutral/40 border border-white/10 p-4 rounded-2xl backdrop-blur-md flex flex-col gap-3 shadow-xl"
                },
                div(
                    {"class": "flex justify-between items-center"},
                    h3(
                        {
                            "class": "text-xs font-black text-white/70 uppercase tracking-wider"
                        },
                        f"📊 EAVT 事实仓库 ({len(all_datoms)} 条)",
                    ),
                    span(
                        {"class": "text-[10px] opacity-40 font-mono"},
                        f"tx: {latest_tx}",
                    ),
                ),
                div(
                    {
                        "class": "max-h-[360px] overflow-y-auto border border-white/5 rounded-xl"
                    },
                    table(
                        {"class": "table table-pin-rows w-full bg-black/20"},
                        thead(
                            None,
                            tr(
                                {
                                    "class": "bg-black/40 border-b border-white/10 text-[10px] opacity-60"
                                },
                                th(None, "Entity (E)"),
                                th(None, "Attr (A)"),
                                th(None, "Value (V)"),
                                th({"class": "text-center"}, "Tx (T)"),
                            ),
                        ),
                        tbody(None, *datom_rows),
                    ),
                ),
            ),
        )


@component("datalog-tab-nav")
class DatalogTabNav(Component):
    """Tab header selector component to toggle active workspaces."""

    parent: Any = None
    selected_tab: Any = None

    @server
    def set_tab(self, tab_name: str) -> None:
        self.selected_tab.set(tab_name)

    def render(self) -> list:
        tab_list = [
            ("query", "🔍 声明式逻辑查询", "text-primary"),
            ("pull", "🌳 Pull 树拉取", "text-accent"),
            ("entity", "🚀 Entity 图漫游", "text-secondary"),
            ("flatten", "📦 JSON 状态扁平化", "text-success"),
        ]

        tabs_html = []
        curr_tab = self.selected_tab.get()
        for t_id, label_text, color_cls in tab_list:
            is_active = curr_tab == t_id
            tabs_html.append(
                button(
                    {
                        "class": f"btn btn-sm px-4 font-bold border-none transition-all duration-300 rounded-xl {'bg-white/10 text-white shadow-inner scale-105' if is_active else 'bg-transparent text-base-content/50 hover:text-white hover:bg-white/5'}",
                        "on_click": self.set_tab(t_id),
                    },
                    label_text,
                )
            )

        return div(
            {
                "class": "flex flex-wrap gap-2 bg-neutral/60 border border-white/10 p-1.5 rounded-2xl backdrop-blur-md mb-6 shadow-md justify-start"
            },
            *tabs_html,
        )


@component("datalog-query-console")
class DatalogQueryConsole(Component):
    """Tab 1: Logic Query console displaying presets, custom input form and output rows."""

    parent: Any = None
    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    query_vars: Any = None
    query_where: Any = None
    query_results: Any = None
    query_headers: Any = None
    query_error: Any = None
    query_time: Any = None

    @server
    def load_preset_query(self, idx: str) -> None:
        preset = PRESETS[int(idx)]
        self.query_vars.set(preset["vars"])
        self.query_where.set(preset["where"])
        self.run_query(preset["vars"], preset["where"])

    @server
    def run_query(self, query_vars: str, query_where: str) -> None:
        self.query_vars.set(query_vars)
        self.query_where.set(query_where)
        self.query_error.set("")

        try:
            find_names = [
                v.strip().lstrip("?") for v in query_vars.split(",") if v.strip()
            ]
            find_vars = [Var(name) for name in find_names]
            if not find_vars:
                raise ValueError("请指定至少一个要查询的变量 (例如 ?name)")

            clauses = []
            lines = [line.strip() for line in query_where.split("\n") if line.strip()]
            for line in lines:
                if line.startswith("#") or line.startswith("//"):
                    continue
                parts = []
                for p in line.split(","):
                    p_str = p.strip()
                    if (p_str.startswith('"') and p_str.endswith('"')) or (
                        p_str.startswith("'") and p_str.endswith("'")
                    ):
                        p_str = p_str[1:-1]

                    if p_str.startswith("?"):
                        parts.append(Var(p_str[1:]))
                    elif p_str.isdigit():
                        parts.append(int(p_str))
                    else:
                        parts.append(p_str)

                if len(parts) != 3:
                    raise ValueError(
                        f"每个过滤子句必须包含三个部分 (以英文逗号分隔): '{line}'"
                    )
                clauses.append(tuple(parts))

            if not clauses:
                raise ValueError("请指定过滤条件子句")

            tx = self.view_tx.get()
            db = self.base_db if tx == 0 else self.base_db.as_of(tx)

            start_time = time.perf_counter()
            results = db.solve(find_vars, clauses)
            elapsed = (time.perf_counter() - start_time) * 1000

            self.query_results.set(list(results))
            self.query_headers.set(find_names)
            self.query_time.set(elapsed)
        except Exception as e:
            self.query_error.set(str(e))
            self.query_results.set([])
            self.query_headers.set([])
            self.query_time.set(0.0)

    def render(self) -> list:
        # Register dependencies
        _ = self.db_version.get()
        _ = self.view_tx.get()

        tx = self.view_tx.get()
        db = self.base_db if tx == 0 else self.base_db.as_of(tx)

        preset_pills = []
        for i, p_info in enumerate(PRESETS):
            preset_pills.append(
                button(
                    {
                        "class": "btn btn-outline btn-xs border-primary/20 text-primary hover:bg-primary/20 hover:text-white transition-all text-left justify-start truncate max-w-full font-medium rounded-lg",
                        "on_click": self.load_preset_query(str(i)),
                    },
                    p_info["name"],
                )
            )

        q_err = self.query_error.get()
        q_res = self.query_results.get()
        q_hdrs = self.query_headers.get()
        q_dur = self.query_time.get()

        result_section = ""
        if q_err:
            result_section = div(
                {
                    "class": "alert alert-error bg-red-950/40 border border-red-500/20 text-red-200 text-xs p-4 rounded-xl font-mono"
                },
                f"❌ 查询编译失败: {q_err}",
            )
        elif not q_hdrs:
            result_section = div(
                {"class": "text-center py-10 opacity-30 italic text-sm"},
                "暂无匹配结果，请编写查询并执行",
            )
        else:
            hdr_cols = [
                th({"class": "bg-black/30 font-mono text-[10px] text-primary"}, f"?{h}")
                for h in q_hdrs
            ]
            row_items = []
            for row in q_res:
                row_cols = []
                for item in row:
                    is_e = any(e == item for (e, _) in db._eav.keys())
                    if is_e:
                        row_cols.append(
                            td(
                                None,
                                button(
                                    {
                                        "class": "badge badge-primary hover:scale-105 transition-all text-[10px] border-none font-bold",
                                        "on_click": self.parent.navigate_entity(
                                            str(item)
                                        ),
                                    },
                                    f"🔗 {item}",
                                ),
                            )
                        )
                    else:
                        row_cols.append(
                            td({"class": "font-mono font-bold text-xs"}, str(item))
                        )
                row_items.append(
                    tr({"class": "hover:bg-white/5 border-b border-white/5"}, *row_cols)
                )

            result_section = div(
                {"class": "flex flex-col gap-2"},
                div(
                    {
                        "class": "flex justify-between items-center text-xs opacity-60 px-2 font-semibold"
                    },
                    span(
                        {"class": "text-success"},
                        f"✔ 逻辑 Join 成功计算: {len(q_res)} 行匹配",
                    ),
                    span({"class": "font-mono"}, f"耗时: {q_dur:.3f} ms"),
                ),
                div(
                    {"class": "overflow-x-auto border border-white/5 rounded-xl"},
                    table(
                        {"class": "table table-zebra w-full bg-black/20"},
                        thead(None, tr(None, *hdr_cols)),
                        tbody(None, *row_items),
                    ),
                ),
            )

        return div(
            {"class": "flex flex-col gap-6"},
            div(
                {
                    "class": "flex flex-col gap-2 bg-black/25 p-4 rounded-xl border border-white/5"
                },
                span(
                    {
                        "class": "text-[10px] font-black text-primary uppercase tracking-wider"
                    },
                    "💡 逻辑查询预设 (点击一键载入)",
                ),
                div({"class": "flex flex-col gap-2 mt-1"}, *preset_pills),
            ),
            form(
                {
                    "class": "flex flex-col gap-4 bg-black/15 p-5 rounded-2xl border border-white/5",
                    "on_submit": self.run_query,
                },
                div(
                    {"class": "flex flex-col gap-1"},
                    span(
                        {"class": "text-xs font-bold text-white/80"},
                        "Find 目标逻辑变量:",
                    ),
                    input_(
                        {
                            "type": "text",
                            "name": "query_vars",
                            "value": self.query_vars.get(),
                            "class": "input input-bordered input-sm bg-black/30 font-mono text-primary text-xs",
                            "placeholder": "?name, ?role",
                        }
                    ),
                ),
                div(
                    {"class": "flex flex-col gap-1"},
                    span(
                        {"class": "text-xs font-bold text-white/80"},
                        "Where 条件子句 (每一行一个事实匹配, 以逗号分隔):",
                    ),
                    textarea(
                        {
                            "name": "query_where",
                            "class": "textarea textarea-bordered bg-black/30 font-mono text-xs text-white/90 leading-relaxed min-h-36 focus:outline-none",
                            "placeholder": "?proj, status, critical\n?proj, lead, ?lead",
                        },
                        self.query_where.get(),
                    ),
                ),
                button(
                    {
                        "type": "submit",
                        "class": "btn btn-primary btn-sm font-bold shadow-lg shadow-primary/20 w-full",
                    },
                    "⚡ 编译并执行 Datalog 求解",
                ),
            ),
            result_section,
        )


@component("datalog-pull-visualizer")
class DatalogPullVisualizer(Component):
    """Tab 2: Pull API controller extracting nested attributes trees."""

    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    pull_entity: Any = None
    pull_pattern: Any = None
    pull_result: Any = None
    pull_error: Any = None

    @server
    def run_pull(self, pull_entity: str, pull_pattern: str) -> None:
        self.pull_entity.set(pull_entity)
        self.pull_pattern.set(pull_pattern)
        self.pull_error.set("")
        self.pull_result.set("")

        try:
            try:
                pattern = ast.literal_eval(pull_pattern)
            except Exception:
                pattern = json.loads(pull_pattern)

            if not isinstance(pattern, list):
                raise ValueError("Pull Pattern 必须是一个嵌套列表结构")

            tx = self.view_tx.get()
            db = self.base_db if tx == 0 else self.base_db.as_of(tx)
            res = db.pull(pull_entity, pattern)
            self.pull_result.set(json.dumps(res, indent=2, ensure_ascii=False))
        except Exception as e:
            self.pull_error.set(str(e))

    def render(self) -> list:
        _ = self.db_version.get()
        _ = self.view_tx.get()

        pull_err = self.pull_error.get()
        pull_res = self.pull_result.get()

        result_box = ""
        if pull_err:
            result_box = div(
                {
                    "class": "alert alert-error bg-red-950/40 border border-red-500/20 text-red-200 text-xs p-4 rounded-xl font-mono"
                },
                f"❌ Pull 执行失败: {pull_err}",
            )
        elif pull_res:
            pre_style = "background-color: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.05); padding: 16px; border-radius: 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #a7f3d0; overflow-x: auto; white-space: pre-wrap;"
            result_box = div(
                {"class": "flex flex-col gap-2"},
                span(
                    {
                        "class": "text-[10px] font-black text-accent uppercase tracking-wider"
                    },
                    "🌳 Pull 树结构化导出结果",
                ),
                raw(f'<pre style="{pre_style}">{pull_res}</pre>'),
            )
        else:
            result_box = div(
                {"class": "text-center py-10 opacity-30 italic text-sm"},
                "输入 Entity 与 Pattern 并执行 Pull",
            )

        return div(
            {"class": "flex flex-col gap-6"},
            p(
                {"class": "text-xs text-base-content/70"},
                "Pull API 是 Datomic 的灵魂特性之一。它允许你通过一个类似 GraphQL Schema 的声明式列表模式 (Pattern)，一次性提取嵌套的属性图，引擎会自动拼装关联实体：",
            ),
            form(
                {
                    "class": "flex flex-col gap-4 bg-black/15 p-5 rounded-2xl border border-white/5",
                    "on_submit": self.run_pull,
                },
                div(
                    {"class": "grid grid-cols-1 md:grid-cols-3 gap-3"},
                    div(
                        {"class": "flex flex-col gap-1 col-span-1"},
                        span(
                            {"class": "text-xs font-bold text-white/80"},
                            "起点 Entity ID:",
                        ),
                        input_(
                            {
                                "type": "text",
                                "name": "pull_entity",
                                "value": self.pull_entity.get(),
                                "class": "input input-bordered input-sm bg-black/30 font-mono text-accent text-xs",
                                "placeholder": "p_hiccl",
                            }
                        ),
                    ),
                    div(
                        {"class": "flex flex-col gap-1 col-span-2"},
                        span(
                            {"class": "text-xs font-bold text-white/80"},
                            "Pull Pattern 树结构定义:",
                        ),
                        input_(
                            {
                                "type": "text",
                                "name": "pull_pattern",
                                "value": self.pull_pattern.get(),
                                "class": "input input-bordered input-sm bg-black/30 font-mono text-xs text-white/90",
                                "placeholder": '["name", {"lead": ["name"]}]',
                            }
                        ),
                    ),
                ),
                button(
                    {
                        "type": "submit",
                        "class": "btn btn-accent btn-sm font-bold shadow-lg shadow-accent/20 w-full",
                    },
                    "🌳 声明式拉取属性树",
                ),
            ),
            result_box,
        )


@component("datalog-entity-navigator")
class DatalogEntityNavigator(Component):
    """Tab 3: Entity navigator with lazy graph jumps."""

    parent: Any = None
    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    nav_entity_id: Any = None

    @server
    def navigate_entity(self, entity_id: str) -> None:
        self.nav_entity_id.set(entity_id)

    def render(self) -> list:
        _ = self.db_version.get()
        _ = self.view_tx.get()

        tx = self.view_tx.get()
        db = self.base_db if tx == 0 else self.base_db.as_of(tx)
        nav_e = self.nav_entity_id.get()
        attrs_found = {a for (e, a) in db._eav.keys() if e == nav_e}

        entity_card = ""
        if not attrs_found:
            entity_card = div(
                {
                    "class": "text-center py-10 opacity-30 italic text-sm border border-dashed border-white/10 rounded-2xl bg-black/10"
                },
                f"未能在当前数据库中找到实体 ID: '{nav_e}'",
            )
        else:
            card_rows = []
            for attr in sorted(attrs_found):
                vals = list(db._eav.get((nav_e, attr), set()))
                val_items = []
                for v in vals:
                    is_ref = any(e == v for (e, _) in db._eav.keys())
                    if is_ref:
                        val_items.append(
                            button(
                                {
                                    "class": "btn btn-xs btn-outline border-secondary/30 text-secondary hover:bg-secondary hover:text-white rounded-lg transition-all font-bold font-mono px-2",
                                    "on_click": self.parent.navigate_entity(str(v)),
                                },
                                f"👉 Entity({v})",
                            )
                        )
                    else:
                        val_items.append(
                            span(
                                {
                                    "class": "badge bg-white/5 border-white/10 text-white font-mono px-2.5 py-1.5 text-xs"
                                },
                                str(v),
                            )
                        )

                card_rows.append(
                    tr(
                        {"class": "border-b border-white/5 hover:bg-white/5"},
                        td(
                            {"class": "font-bold text-xs text-secondary/90 font-mono"},
                            attr,
                        ),
                        td({"class": "flex flex-wrap gap-1.5"}, *val_items),
                    )
                )

            entity_card = div(
                {
                    "class": "card bg-black/25 border border-white/10 p-5 rounded-2xl shadow-2xl flex flex-col gap-4 animate-fade-in"
                },
                div(
                    {
                        "class": "flex justify-between items-center border-b border-white/5 pb-2"
                    },
                    span(
                        {
                            "class": "text-sm font-black text-white/90 flex items-center gap-2"
                        },
                        f"🚀 Entity: {nav_e}",
                    ),
                    span(
                        {
                            "class": "badge bg-secondary/20 text-secondary border-none text-[10px] font-bold"
                        },
                        "惰性 Entity 代理包装器",
                    ),
                ),
                table(
                    {"class": "table w-full"},
                    thead(
                        None,
                        tr(
                            {"class": "text-[10px] opacity-40 border-none"},
                            th(None, "属性 (Attribute)"),
                            th(None, "值 (Value / Entity Reference)"),
                        ),
                    ),
                    tbody(None, *card_rows),
                ),
            )

        return div(
            {"class": "flex flex-col gap-6"},
            p(
                {"class": "text-xs text-base-content/70"},
                "Entity API 提供了一个极佳的惰性属性漫游器。它包装了 Entity ID，允许你利用 Python 属性点号在图关系中无感漫游。点击下面实体卡的属性连接，直接“闪现跳转”漫游到目标实体：",
            ),
            form(
                {
                    "class": "flex gap-2 bg-black/15 p-4 rounded-xl border border-white/5 items-center w-full",
                    "on_submit": self.navigate_entity,
                },
                span({"class": "text-xs font-bold text-white/80"}, "跳转到实体 ID:"),
                input_(
                    {
                        "type": "text",
                        "name": "entity_id",
                        "value": nav_e,
                        "class": "input input-bordered input-sm bg-black/30 font-mono text-secondary text-xs flex-1",
                        "placeholder": "comp_1",
                    }
                ),
                button(
                    {
                        "type": "submit",
                        "class": "btn btn-secondary btn-sm font-bold shadow-md",
                    },
                    "🔍 查看",
                ),
            ),
            entity_card,
        )


@component("datalog-flatten-loader")
class DatalogFlattenLoader(Component):
    """Tab 4: JSON text loader flattening nested lists into Database datoms."""

    parent: Any = None
    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    json_state: Any = None
    json_error: Any = None

    @server
    def load_json_state(self, json_state: str) -> None:
        self.json_state.set(json_state)
        self.json_error.set("")
        try:
            data = json.loads(json_state)
            new_db = Database.from_state(data)
            self.base_db.datoms = new_db.datoms
            self.base_db._eav = new_db._eav
            self.base_db._ave = new_db._ave
            self.base_db._vae = new_db._vae
            self.base_db._cardinality_many = new_db._cardinality_many
            self.base_db._tx = new_db._tx

            self.db_version.set(self.db_version.get() + 1)
            self.view_tx.set(0)

            # Reset navigation focus
            keys = list(self.base_db._eav.keys())
            if keys:
                self.parent.nav_entity_id.set(keys[0][0])
        except Exception as e:
            self.json_error.set(str(e))

    def render(self) -> list:
        json_err = self.json_error.get()

        return div(
            {"class": "flex flex-col gap-6"},
            p(
                {"class": "text-xs text-base-content/70"},
                "无需声明 Schema，Datalog-lite 提供了 `Database.from_state(state)` 便捷工具。输入嵌套的 JSON/状态树（如 re-frame 的全局 db 结构），它将以约定优于配置的形式，自动递归铺平并自动建立 Entity 属性和 Ref 图关系：",
            ),
            form(
                {
                    "class": "flex flex-col gap-4 bg-black/15 p-5 rounded-2xl border border-white/5",
                    "on_submit": self.load_json_state,
                },
                textarea(
                    {
                        "name": "json_state",
                        "class": "textarea textarea-bordered bg-black/30 font-mono text-xs text-success/90 leading-relaxed min-h-64 focus:outline-none",
                        "placeholder": '{\n  "id": "comp_1"\n}',
                    },
                    self.json_state.get(),
                ),
                button(
                    {
                        "type": "submit",
                        "class": "btn btn-success btn-sm font-bold shadow-lg shadow-success/20 w-full",
                    },
                    "📦 扁平化导入 (from_state) 并覆盖数据库",
                ),
            ),
            div(
                {
                    "class": "alert alert-error bg-red-950/40 border border-red-500/20 text-red-200 text-xs p-4 rounded-xl font-mono"
                },
                f"❌ JSON 解析错误: {json_err}",
            )
            if json_err
            else "",
        )


# ---------------------------------------------------------------------------
# 2. Tab Content Swapper Component
# ---------------------------------------------------------------------------


@component("datalog-tab-content")
class DatalogTabContent(Component):
    """Wraps active tab content, isolating the selected_tab signal dependency.

    When selected_tab changes, only this container and the tab nav rerender.
    The outer DatalogWebDemo and DatalogSidebar remain untouched.
    """

    parent: Any = None
    selected_tab: Any = None
    base_db: Any = None
    db_version: Any = None
    view_tx: Any = None
    query_vars: Any = None
    query_where: Any = None
    query_results: Any = None
    query_headers: Any = None
    query_error: Any = None
    query_time: Any = None
    pull_entity: Any = None
    pull_pattern: Any = None
    pull_result: Any = None
    pull_error: Any = None
    nav_entity_id: Any = None
    json_state: Any = None
    json_error: Any = None

    def render(self) -> list:
        session = self._session
        renderer = session.renderer

        # Read signal to register dependency
        curr_tab = self.selected_tab.get()
        active_tab_html = ""

        if curr_tab == "query":
            comp = session.get_component("datalog-query-main")
            if comp is None:
                comp = session.mount_component(
                    "datalog-query-console",
                    cid="datalog-query-main",
                    base_db=self.base_db,
                    db_version=self.db_version,
                    view_tx=self.view_tx,
                    query_vars=self.query_vars,
                    query_where=self.query_where,
                    query_results=self.query_results,
                    query_headers=self.query_headers,
                    query_error=self.query_error,
                    query_time=self.query_time,
                    parent=self.parent,
                )
            active_tab_html = renderer.render_component(comp)

        elif curr_tab == "pull":
            comp = session.get_component("datalog-pull-main")
            if comp is None:
                comp = session.mount_component(
                    "datalog-pull-visualizer",
                    cid="datalog-pull-main",
                    base_db=self.base_db,
                    db_version=self.db_version,
                    view_tx=self.view_tx,
                    pull_entity=self.pull_entity,
                    pull_pattern=self.pull_pattern,
                    pull_result=self.pull_result,
                    pull_error=self.pull_error,
                )
            active_tab_html = renderer.render_component(comp)

        elif curr_tab == "entity":
            comp = session.get_component("datalog-entity-main")
            if comp is None:
                comp = session.mount_component(
                    "datalog-entity-navigator",
                    cid="datalog-entity-main",
                    base_db=self.base_db,
                    db_version=self.db_version,
                    view_tx=self.view_tx,
                    nav_entity_id=self.nav_entity_id,
                    parent=self.parent,
                )
            active_tab_html = renderer.render_component(comp)

        elif curr_tab == "flatten":
            comp = session.get_component("datalog-flatten-main")
            if comp is None:
                comp = session.mount_component(
                    "datalog-flatten-loader",
                    cid="datalog-flatten-main",
                    base_db=self.base_db,
                    db_version=self.db_version,
                    view_tx=self.view_tx,
                    json_state=self.json_state,
                    json_error=self.json_error,
                    parent=self.parent,
                )
            active_tab_html = renderer.render_component(comp)

        return div(
            {
                "class": "card bg-neutral/20 border border-white/10 p-6 rounded-2xl backdrop-blur-md shadow-2xl min-h-[500px]"
            },
            raw(active_tab_html),
        )


# ---------------------------------------------------------------------------
# 3. Main Controller Layout (Page-level Coordinator)
# ---------------------------------------------------------------------------


@component("datalog-web-demo")
class DatalogWebDemo(Component):
    """Visual page layout coordinating headers, layouts and embedding subcomponents."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.base_db = Database.from_state(PRESET_STATE)

        # Coordinating signals
        self.db_version = signal(1)
        self.view_tx = signal(0)
        self.selected_tab = signal("query")

        # Nested Console states shared with kids
        self.query_vars = signal("?proj_name, ?lead_name")
        self.query_where = signal(
            "?proj, name, ?proj_name\n?proj, lead, ?lead\n?lead, name, ?lead_name"
        )
        self.query_error = signal("")
        self.query_results = signal([])
        self.query_headers = signal([])
        self.query_time = signal(0.0)

        self.pull_entity = signal("p_hiccl")
        self.pull_pattern = signal(
            '["name", "status", {"lead": ["name", "role", "skills"]}]'
        )
        self.pull_result = signal("")
        self.pull_error = signal("")

        self.nav_entity_id = signal("comp_1")

        self.json_state = signal(json.dumps(PRESET_STATE, indent=2, ensure_ascii=False))
        self.json_error = signal("")

        self.new_e = signal("")
        self.new_a = signal("")
        self.new_v = signal("")

        self._initial_query_run = False

    @server
    def navigate_entity(self, entity_id: str) -> None:
        self.nav_entity_id.set(entity_id)
        self.selected_tab.set("entity")

    def render(self) -> list:
        session = self._session
        renderer = session.renderer

        # Mount subcomponents in session once
        sidebar_comp = session.get_component("datalog-sidebar-main")
        if sidebar_comp is None:
            sidebar_comp = session.mount_component(
                "datalog-sidebar",
                cid="datalog-sidebar-main",
                base_db=self.base_db,
                db_version=self.db_version,
                view_tx=self.view_tx,
                new_e=self.new_e,
                new_a=self.new_a,
                new_v=self.new_v,
                parent=self,
            )

        tab_nav_comp = session.get_component("datalog-tab-nav-main")
        if tab_nav_comp is None:
            tab_nav_comp = session.mount_component(
                "datalog-tab-nav",
                cid="datalog-tab-nav-main",
                selected_tab=self.selected_tab,
                parent=self,
            )

        tab_content_comp = session.get_component("datalog-tab-content-main")
        if tab_content_comp is None:
            tab_content_comp = session.mount_component(
                "datalog-tab-content",
                cid="datalog-tab-content-main",
                selected_tab=self.selected_tab,
                base_db=self.base_db,
                db_version=self.db_version,
                view_tx=self.view_tx,
                query_vars=self.query_vars,
                query_where=self.query_where,
                query_results=self.query_results,
                query_headers=self.query_headers,
                query_error=self.query_error,
                query_time=self.query_time,
                pull_entity=self.pull_entity,
                pull_pattern=self.pull_pattern,
                pull_result=self.pull_result,
                pull_error=self.pull_error,
                nav_entity_id=self.nav_entity_id,
                json_state=self.json_state,
                json_error=self.json_error,
                parent=self,
            )

        return div(
            {"class": "flex flex-col gap-6 w-full max-w-7xl px-4 py-6"},
            # Top Banner header
            div(
                {
                    "class": "flex flex-col md:flex-row justify-between items-start md:items-center border-b border-white/10 pb-6 gap-4"
                },
                div(
                    {"class": "flex items-center gap-4"},
                    raw(
                        '<div class="w-12 h-12 bg-gradient-to-tr from-primary via-accent to-secondary rounded-xl flex items-center justify-center shadow-lg"><svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg></div>'
                    ),
                    div(
                        None,
                        h1(
                            {
                                "class": "text-2xl font-black bg-gradient-to-r from-primary via-accent to-secondary bg-clip-text text-transparent tracking-tight"
                            },
                            "Hiccl Datalog-lite 极简逻辑查询引擎",
                        ),
                        p(
                            {
                                "class": "text-xs text-base-content/50 font-medium mt-0.5"
                            },
                            "Clojure Datomic 关系图数据库在 Python 反应式栈下的精简融合与极致演示",
                        ),
                    ),
                ),
                span(
                    {
                        "class": "badge bg-white/5 border-white/10 text-white font-mono text-xs px-3 py-2"
                    },
                    "📦 v0.7.0 (Phase 5b)",
                ),
            ),
            # Gridded layout
            div(
                {"class": "grid grid-cols-1 lg:grid-cols-3 gap-6 items-start w-full"},
                # Left Sidebar - Renders as autonomous sidebar_comp DOM
                div(
                    {"class": "col-span-1 w-full"},
                    raw(renderer.render_component(sidebar_comp)),
                ),
                # Right content panel - Renders as autonomous tab_nav_comp and tab_content_comp DOM
                div(
                    {"class": "col-span-1 lg:col-span-2 w-full flex flex-col"},
                    raw(renderer.render_component(tab_nav_comp)),
                    raw(renderer.render_component(tab_content_comp)),
                ),
            ),
        )


# ---------------------------------------------------------------------------
# 3. Main Entrypoint & FastAPI Bootstrap
# ---------------------------------------------------------------------------

config = HicclConfig(
    component_registry=registry,
    title="Hiccl Datalog-lite Web Center 🧪",
    brand_name="Hiccl Datalog-lite",
    theme="dark",
    live_reload=True,  # Enables time travel panel in browser for global state
    pages={"/": DatalogWebDemo},
)

app = create_hiccl_app(config)

if __name__ == "__main__":
    print("🧬 Starting Hiccl Datalog-lite Web Demo on http://127.0.0.1:8001 ...")
    uvicorn.run(app, host="127.0.0.1", port=8001)
