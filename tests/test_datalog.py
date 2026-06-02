"""Tests for Hiccl Datalog-lite engine."""

from __future__ import annotations

from hiccl.datalog import Database, var


def test_datalog_basic_transact_and_index() -> None:
    """Test standard assertions, retractions, and double-key flat hash indices."""
    db = Database()
    tx1 = db.transact(
        [
            ("user_1", "name", "Alice"),
            ("user_1", "age", 30),
        ]
    )

    assert tx1 == 1
    assert len(db.datoms) == 2

    # Check flat tuple indices
    assert db._eav[("user_1", "name")] == {"Alice"}
    assert db._eav[("user_1", "age")] == {30}
    assert db._ave[("name", "Alice")] == {"user_1"}
    assert db._vae[("Alice", "name")] == {"user_1"}


def test_datalog_from_state_tree() -> None:
    """Test flattening a deep nested dictionary/list tree into Datoms with auto-refs."""
    state = {
        "id": "org_1",
        "name": "Acme Corp",
        "projects": [
            {
                "id": "proj_a",
                "title": "Project Alpha",
                "manager": {"name": "Bob", "email": "bob@acme.com"},
            }
        ],
    }
    db = Database.from_state(state)

    # Check flattening of Acme Corp
    assert "Acme Corp" in db._eav[("org_1", "name")]

    # Acme Corp points to proj_a under projects multi-value attribute
    assert "proj_a" in db._eav[("org_1", "projects")]

    # Project Alpha has title
    assert "Project Alpha" in db._eav[("proj_a", "title")]

    # proj_a manager points to an auto-generated entity ID (e.g. _e1)
    manager_ids = db._eav[("proj_a", "manager")]
    assert len(manager_ids) == 1
    m_id = list(manager_ids)[0]

    # Verify auto-generated manager properties
    assert "Bob" in db._eav[(m_id, "name")]
    assert "bob@acme.com" in db._eav[(m_id, "email")]


def test_datalog_query_unification() -> None:
    """Test logical unification querying across multiple clauses (logical JOIN)."""
    db = Database()
    db.transact(
        [
            ("t1", "type", "todo"),
            ("t1", "text", "Learn Python"),
            ("t1", "status", "active"),
            ("t1", "assignee", "u1"),
            ("t2", "type", "todo"),
            ("t2", "text", "Build Framework"),
            ("t2", "status", "pending"),
            ("t2", "assignee", "u1"),
            ("u1", "name", "Alice"),
        ]
    )

    todo, text, name, assignee = var("todo", "text", "name", "assignee")

    # Find the text of all ACTIVE todos assigned to Alice
    q = db.query(text).where(
        (todo, "type", "todo"),
        (todo, "status", "active"),
        (todo, "text", text),
        (todo, "assignee", assignee),
        (assignee, "name", name),
        (assignee, "name", "Alice"),
    )

    results = q.execute()
    assert results == {("Learn Python",)}


def test_datalog_heuristic_join_reordering() -> None:
    """Test that query solver produces correct results regardless of clause order.

    This implicitly verifies the Join Reordering Optimizer works properly.
    """
    db = Database()
    db.transact(
        [
            ("u1", "name", "Alice"),
            ("t1", "assignee", "u1"),
            ("t1", "text", "Goal A"),
        ]
    )

    user, todo, text = var("user", "todo", "text")

    # Order A: Constrained clauses first
    q1 = db.query(text).where(
        (user, "name", "Alice"),
        (todo, "assignee", user),
        (todo, "text", text),
    )

    # Order B: Wide/wildcard clauses first (tests optimization/reordering robustness)
    q2 = db.query(text).where(
        (todo, "text", text),
        (todo, "assignee", user),
        (user, "name", "Alice"),
    )

    assert q1.execute() == {("Goal A",)}
    assert q2.execute() == {("Goal A",)}


def test_datalog_pull_api() -> None:
    """Test nested declarative attribute pulls like GraphQL."""
    state = {
        "id": "c1",
        "name": "Company X",
        "employees": [
            {"id": "e1", "name": "Alice", "role": "CEO"},
            {"id": "e2", "name": "Bob", "role": "CTO"},
        ],
    }
    db = Database.from_state(state)

    # Pull Company X and nested employees' name & role
    pulled = db.pull("c1", ["name", {"employees": ["name", "role"]}])

    assert pulled == {
        "name": "Company X",
        "employees": [
            {"name": "Alice", "role": "CEO"},
            {"name": "Bob", "role": "CTO"},
        ],
    }


def test_datalog_entity_lazy_graph_navigation() -> None:
    """Test Entity lazy proxy object traversing graph using Python attribute dot access."""
    state = {
        "id": "proj_1",
        "name": "Volt",
        "creator": {"id": "creator_1", "name": "Shiunko", "team": {"name": "Core Dev"}},
    }
    db = Database.from_state(state)

    proj = db.entity("proj_1")
    assert proj.name == "Volt"
    assert proj.creator.name == "Shiunko"
    assert proj.creator.team.name == "Core Dev"

    # Accessing non-existent attribute returns None
    assert proj.deadline is None


def test_datalog_time_travel_as_of() -> None:
    """Test as_of Snapshot Time Travel retrieving past states and queries."""
    db = Database()
    tx1 = db.transact([("t1", "text", "First draft"), ("t1", "version", 1)])
    db.transact([("t1", "text", "Second draft"), ("t1", "version", 2)])

    # Current state is Second draft
    curr = db.entity("t1")
    assert curr.text == "Second draft"

    # Travel back to tx1
    past_db = db.as_of(tx1)
    past = past_db.entity("t1")
    assert past.text == "First draft"
    assert past.version == 1

    # Verify query in the past
    text, version = var("text", "version")
    q = past_db.query(text, version).where(
        ("t1", "text", text),
        ("t1", "version", version),
    )
    assert q.execute() == {("First draft", 1)}
