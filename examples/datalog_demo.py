"""Hiccl Datalog-lite Interactive Premium Demo 🧪

Showcases convention-based state flattening, fluent Pythonic logic queries,
declarative Pull API, lazy Entity graph navigation, and Time Travel as_of retrieval.
"""

from __future__ import annotations

import time

from hiccl.datalog import Database, var

# ANSI terminal colors for premium presentation
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"


def main() -> None:
    print(f"\n{BOLD}{CYAN}🧬 欢迎体验 Hiccl Datalog-lite 极简逻辑查询引擎演示{RESET}\n")

    # =========================================================================
    # 1. Convention-based State Tree Flattening
    # =========================================================================
    print(f"{BOLD}[1/5] 载入复杂深层嵌套的组织状态树 (from_state)...{RESET}")
    state = {
        "id": "company_x",
        "name": "Volt Technologies",
        "departments": [
            {
                "id": "dept_rnd",
                "name": "研发部",
                "projects": [
                    {
                        "id": "proj_volt",
                        "title": "Volt Web Framework",
                        "status": "critical",
                        "tasks": [
                            {
                                "id": "task_1",
                                "text": "实现 Datalog 查询引擎",
                                "status": "active",
                                "assignee": {"id": "user_shiunko", "name": "Shiunko"},
                            },
                            {
                                "id": "task_2",
                                "text": "优化 DOM 渲染管线",
                                "status": "pending",
                                "assignee": {"id": "user_alice", "name": "Alice"},
                            },
                        ],
                    }
                ],
            }
        ],
    }

    db = Database.from_state(state)
    print(
        f"{GREEN}✓ 状态扁平化导入完成。当前活动事实库（Datoms）条数: {BOLD}{len(db.datoms)}{RESET}{GREEN} 条{RESET}\n"
    )

    # =========================================================================
    # 2. Fluent Pythonic Datalog Logic Query (Logical JOIN)
    # =========================================================================
    print(f"{BOLD}[2/5] 运行极致 Pythonic 的 Fluent API 逻辑多表关联查询...{RESET}")
    print(
        f"    {YELLOW}需求: 寻找所有【研发部】中状态为【active】的紧急任务及其负责人姓名{RESET}"
    )

    # 声明逻辑变量
    dept, proj, task, text, assignee, name = var(
        "dept", "proj", "task", "text", "assignee", "name"
    )

    query = db.query(text, name).where(
        # 逻辑链条：研发部 -> 下辖项目 -> 项目中的任务 -> 紧急任务文本 -> 负责人 -> 负责人名字
        (dept, "name", "研发部"),
        (dept, "projects", proj),
        (proj, "tasks", task),
        (task, "status", "active"),
        (task, "text", text),
        (task, "assignee", assignee),
        (assignee, "name", name),
    )

    start_time = time.perf_counter()
    results = query.execute()
    elapsed = (time.perf_counter() - start_time) * 1000

    print(
        f"{GREEN}✓ 逻辑 Join 求解完成 (耗时: {BOLD}{elapsed:.3f} ms{RESET}{GREEN}):{RESET}"
    )
    for row in results:
        print(
            f"    👉 任务: {BOLD}{MAGENTA}“{row[0]}”{RESET} | 负责人: {BOLD}{GREEN}{row[1]}{RESET}"
        )
    print()

    # =========================================================================
    # 3. Declarative Pull API
    # =========================================================================
    print(
        f"{BOLD}[3/5] 使用声明式 Pull API (类 GraphQL) 拉取特定项目及任务树...{RESET}"
    )
    print(
        f"    {YELLOW}需求: 拉取项目 proj_volt 的标题、状态，以及旗下所有任务和其负责人的名字{RESET}"
    )

    pull_pattern = [
        "title",
        "status",
        {"tasks": ["text", "status", {"assignee": ["name"]}]},
    ]

    pulled_data = db.pull("proj_volt", pull_pattern)
    print(f"{GREEN}✓ 嵌套属性树声明式提取成功:{RESET}")
    import json

    print(
        f"    {BOLD}{CYAN}{json.dumps(pulled_data, indent=6, ensure_ascii=False)}{RESET}\n"
    )

    # =========================================================================
    # 4. Lazy Entity API for Seamless Graph Navigation
    # =========================================================================
    print(
        f"{BOLD}[4/5] 体验惰性 Entity 代理进行极简点号图漫游漫步 (Graph Navigation)...{RESET}"
    )
    proj_entity = db.entity("proj_volt")

    print(f"    👉 项目标题 (proj.title): {BOLD}{CYAN}{proj_entity.title}{RESET}")
    print(f"    👉 项目状态 (proj.status): {BOLD}{CYAN}{proj_entity.status}{RESET}")

    # 对于列表（多值），Entity 自动返回代理列表
    tasks = proj_entity.tasks
    print(f"    👉 下属任务列表数量 (len(proj.tasks)): {BOLD}{len(tasks)}{RESET}")
    for idx, t in enumerate(tasks, 1):
        # 链式点号：任务.负责人.名字 (t.assignee.name)！极其顺滑！
        print(
            f"        {idx}. {BOLD}{YELLOW}“{t.text}”{RESET} (状态: {t.status}) — 负责人: {BOLD}{GREEN}{t.assignee.name}{RESET}"
        )
    print()

    # =========================================================================
    # 5. Time Travel Snapshot Query (as_of)
    # =========================================================================
    print(
        f"{BOLD}[5/5] 结合时间旅行事务 ID，进行只读历史时空快照查询 (as_of)...{RESET}"
    )

    # 模拟用户进行操作：更新任务状态并修改指派人
    print(f"    {YELLOW}步骤 A: 获取当前事务 tx (目前为 1)...{RESET}")
    tx_original = db._tx

    print(
        f"    {YELLOW}步骤 B: 在新事务中修改状态，将 task_1 的状态设为 'completed' 并将负责人改为 Bob...{RESET}"
    )
    tx_new = db.transact(
        [
            ("task_1", "status", "completed"),
            # 指派给 Bob
            ("user_bob", "name", "Bob"),
            ("task_1", "assignee", "user_bob"),
        ]
    )

    print(f"    👉 数据库全局事务 ID 升级为: {BOLD}{tx_new}{RESET}")
    print(
        f"    👉 【当前时刻】task_1 负责人 (db.entity('task_1').assignee.name): {BOLD}{GREEN}{db.entity('task_1').assignee.name}{RESET}"
    )
    print(
        f"    👉 【当前时刻】task_1 状态 (db.entity('task_1').status): {BOLD}{GREEN}{db.entity('task_1').status}{RESET}"
    )

    print(
        f"    {YELLOW}步骤 C: 开始时空回溯！查询 tx_original ({tx_original}) 时刻的历史快照...{RESET}"
    )
    past_db = db.as_of(tx_original)
    past_task = past_db.entity("task_1")

    print(
        f"    👉 {BOLD}{GREEN}【历史时刻 tx={tx_original}】{RESET}task_1 负责人: {BOLD}{CYAN}{past_task.assignee.name}{RESET}"
    )
    print(
        f"    👉 {BOLD}{GREEN}【历史时刻 tx={tx_original}】{RESET}task_1 状态: {BOLD}{CYAN}{past_task.status}{RESET}"
    )

    print(
        f"\n{BOLD}{GREEN}✓ Datalog-lite 核心用例全部演示完毕！如此丰富强大的特性，核心仅用约 300 行 Python 代码优雅搞定。{RESET}\n"
    )


if __name__ == "__main__":
    main()
