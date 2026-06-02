"""Hiccl Datalog-lite declarative query engine.

Designed for simplicity, elegance, and extreme developer experience.
Provides multi-index Datom storage, Logic Unification Solver, Pull API,
and Lazy Entity Graph Traversal with full as_of Time Travel support.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class Datom(NamedTuple):
    """Immutable representation of a single fact in the database (Entity-Attribute-Value-Tx)."""

    e: Any  # Entity ID (string or integer)
    a: str  # Attribute (string)
    v: Any  # Value (any Python object or entity ID)
    t: int = 0  # Transaction ID / Timestamp


class Var:
    """A Datalog logic variable used for unification in queries."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"?{self.name}"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Var) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)


def var(*names: str) -> Any:
    """Convenience helper to declare one or multiple Logic Variables.

    Usage:
        todo, text = var("todo", "text")
    """
    if len(names) == 1:
        return Var(names[0])
    return tuple(Var(name) for name in names)


class Query:
    """Fluent query builder for Datalog-lite."""

    def __init__(self, db: Database, find_vars: list[Var]) -> None:
        self.db = db
        self.find_vars = find_vars
        self.clauses: list[tuple[Any, str, Any]] = []

    def where(self, *clauses: tuple[Any, str, Any]) -> Query:
        """Add one or multiple logic constraints to the query."""
        self.clauses.extend(clauses)
        return self

    def execute(self) -> set[tuple[Any, ...]]:
        """Run the logic unification solver on the database and return matching tuples."""
        return self.db.solve(self.find_vars, self.clauses)


class Entity:
    """Lazy proxy object for seamless Graph Navigation / Traversal over entities."""

    def __init__(self, db: Database, entity_id: Any) -> None:
        self._db = db
        self._id = entity_id

    def __getattr__(self, name: str) -> Any:
        vals = list(self._db._eav.get((self._id, name), set()))
        if not vals:
            return None

        def wrap_val(val: Any) -> Any:
            # Convention: if the value points to another entity in the database, return a lazy Entity proxy
            is_entity = any(e == val for (e, _) in self._db._eav.keys())
            if is_entity:
                return Entity(self._db, val)
            return val

        if len(vals) == 1:
            return wrap_val(vals[0])
        return [wrap_val(v) for v in vals]

    def __getitem__(self, name: str) -> Any:
        return self.__getattr__(name)

    def __repr__(self) -> str:
        return f"Entity({self._id!r})"


class Database:
    """Datalog-lite Database storing facts in double-key flat hash indices."""

    def __init__(self) -> None:
        self.datoms: set[Datom] = set()
        self._tx: int = 0
        self._cardinality_many: set[str] = (
            set()
        )  # Tracks multi-value attributes (e.g. lists)

        # Flat Double-Key Hash Indices for O(1) matching
        self._eav: dict[tuple[Any, str], set[Any]] = {}  # (e, a) -> set(v)
        self._ave: dict[tuple[str, Any], set[Any]] = {}  # (a, v) -> set(e)
        self._vae: dict[
            tuple[Any, str], set[Any]
        ] = {}  # (v, a) -> set(e) (reverse reference index)

    def transact(self, assertions: list[tuple[Any, str, Any] | Datom]) -> int:
        """Submit a list of facts/assertions into the database. Returns current Transaction ID."""
        self._tx += 1

        # Convert all to Datoms and sort by transaction/time order to ensure proper overwrite sequence
        new_datoms: list[Datom] = []
        for item in assertions:
            if isinstance(item, Datom):
                datom = item._replace(t=self._tx) if item.t == 0 else item
            else:
                datom = Datom(item[0], item[1], item[2], self._tx)
            new_datoms.append(datom)

        new_datoms.sort(key=lambda d: d.t)

        for datom in new_datoms:
            self.datoms.add(datom)

            # Single-value overwrite logic:
            # If the attribute is not marked as cardinality_many, overwrite existing value in active indices
            if datom.a not in self._cardinality_many:
                old_vals = self._eav.get((datom.e, datom.a), set())
                if old_vals:
                    for old_v in list(old_vals):
                        self._eav[(datom.e, datom.a)].discard(old_v)
                        self._ave.get((datom.a, old_v), set()).discard(datom.e)
                        self._vae.get((old_v, datom.a), set()).discard(datom.e)

            # Insert new assertion into active indices
            self._eav.setdefault((datom.e, datom.a), set()).add(datom.v)
            self._ave.setdefault((datom.a, datom.v), set()).add(datom.e)
            self._vae.setdefault((datom.v, datom.a), set()).add(datom.e)

        return self._tx

    @classmethod
    def from_state(cls, state: Any) -> Database:
        """Convention-based State Tree to Database converter.

        Recursively flattens dict/list trees into Datoms and automatically resolves references.
        """
        db = cls()
        assertions: list[tuple[Any, str, Any]] = []
        entity_counter = 0

        def get_next_id() -> str:
            nonlocal entity_counter
            entity_counter += 1
            return f"_e{entity_counter}"

        def traverse(node: Any) -> Any:
            if isinstance(node, dict):
                # Auto-detect or generate an entity ID
                e_id = node.get("id") or node.get("uid") or get_next_id()
                for k, v in node.items():
                    if k in ("id", "uid"):
                        assertions.append((e_id, k, v))
                        continue

                    if isinstance(v, list):
                        db._cardinality_many.add(k)

                    child_v = traverse(v)
                    assertions.append((e_id, k, child_v))
                return e_id
            elif isinstance(node, list):
                return [traverse(item) for item in node]
            else:
                return node

        traverse(state)

        # Flatten list values into multiple multi-value Datom assertions
        flat_assertions: list[tuple[Any, str, Any]] = []
        for e, a, v in assertions:
            if isinstance(v, list):
                db._cardinality_many.add(a)
                for item in v:
                    flat_assertions.append((e, a, item))
            else:
                flat_assertions.append((e, a, v))

        db.transact(flat_assertions)
        return db

    def query(self, *find_vars: Var) -> Query:
        """Fluent interface to construct a Datalog logic query."""
        return Query(self, list(find_vars))

    def entity(self, entity_id: Any) -> Entity:
        """Get a lazy graph navigation proxy for the specified entity."""
        return Entity(self, entity_id)

    def pull(self, entity_id: Any, pattern: list[Any]) -> dict[str, Any]:
        """Datomic-like declarative Pull API to extract nested attribute trees."""
        res: dict[str, Any] = {}
        attrs = {a for (e, a) in self._eav.keys() if e == entity_id}
        if not attrs:
            return res

        for item in pattern:
            if isinstance(item, str):
                if item == "*":
                    for a in sorted(attrs):
                        vals = sorted(
                            list(self._eav.get((entity_id, a), set())),
                            key=lambda x: str(x),
                        )
                        if vals:
                            res[a] = vals[0] if len(vals) == 1 else vals
                elif item in attrs:
                    vals = sorted(
                        list(self._eav.get((entity_id, item), set())),
                        key=lambda x: str(x),
                    )
                    if vals:
                        res[item] = vals[0] if len(vals) == 1 else vals
            elif isinstance(item, dict):
                for k, sub_pattern in item.items():
                    if k in attrs:
                        vals = sorted(
                            list(self._eav.get((entity_id, k), set())),
                            key=lambda x: str(x),
                        )
                        if vals:
                            pulled_vals = [self.pull(v, sub_pattern) for v in vals]
                            pulled_vals = [pv for pv in pulled_vals if pv]
                            if pulled_vals:
                                res[k] = (
                                    pulled_vals[0] if len(vals) == 1 else pulled_vals
                                )
        return res

    def as_of(self, tx_id: int) -> Database:
        """Time Travel view: returns a read-only database snapshotted up to tx_id."""
        historic_datoms = [d for d in self.datoms if d.t <= tx_id]
        db_snapshot = Database()
        db_snapshot._cardinality_many = self._cardinality_many.copy()
        db_snapshot.transact(historic_datoms)
        db_snapshot._tx = tx_id
        return db_snapshot

    def solve(
        self, find_vars: list[Var], clauses: list[tuple[Any, str, Any]]
    ) -> set[tuple[Any, ...]]:
        """Datalog engine solver using Dynamic Logic Unification with Clause Reordering Optimization."""
        results: set[tuple[Any, ...]] = set()

        def get_unknown_vars_count(
            clause: tuple[Any, str, Any], bound_vars: set[Var]
        ) -> int:
            count = 0
            e, a, v = clause
            if isinstance(e, Var) and e not in bound_vars:
                count += 1
            if isinstance(v, Var) and v not in bound_vars:
                count += 1
            return count

        def search(
            remaining_clauses: list[tuple[Any, str, Any]], bindings: dict[Var, Any]
        ) -> None:
            if not remaining_clauses:
                res = tuple(bindings.get(var) for var in find_vars)
                results.add(res)
                return

            # Dynamic Heuristic: choose the clause with the minimum number of unknown variables (Join Reordering)
            bound_vars = set(bindings.keys())
            best_idx = 0
            best_score = 999
            for idx, clause in enumerate(remaining_clauses):
                score = get_unknown_vars_count(clause, bound_vars)
                if score < best_score:
                    best_score = score
                    best_idx = idx

            clause = remaining_clauses[best_idx]
            next_remaining = (
                remaining_clauses[:best_idx] + remaining_clauses[best_idx + 1 :]
            )

            e_pat, a_pat, v_pat = clause
            e_val = bindings.get(e_pat) if isinstance(e_pat, Var) else e_pat
            v_val = bindings.get(v_pat) if isinstance(v_pat, Var) else v_pat

            # Unification using flat double-key index matching
            # Case 1: Both e and v are known/bound
            if e_val is not None and v_val is not None:
                if v_val in self._eav.get((e_val, a_pat), set()):
                    search(next_remaining, bindings)

            # Case 2: e is known/bound, v is unknown
            elif e_val is not None and v_val is None:
                for matched_v in self._eav.get((e_val, a_pat), set()):
                    new_bindings = bindings.copy()
                    if isinstance(v_pat, Var):
                        new_bindings[v_pat] = matched_v
                    search(next_remaining, new_bindings)

            # Case 3: v is known/bound, e is unknown (using reverse AVE index)
            elif e_val is None and v_val is not None:
                for matched_e in self._ave.get((a_pat, v_val), set()):
                    new_bindings = bindings.copy()
                    if isinstance(e_pat, Var):
                        new_bindings[e_pat] = matched_e
                    search(next_remaining, new_bindings)

            # Case 4: Both e and v are unknown (scan the indices for attribute `a`)
            else:
                for (a, v), entities in self._ave.items():
                    if a == a_pat:
                        for matched_e in entities:
                            new_bindings = bindings.copy()
                            if isinstance(e_pat, Var):
                                new_bindings[e_pat] = matched_e
                            if isinstance(v_pat, Var):
                                new_bindings[v_pat] = v
                            search(next_remaining, new_bindings)

        search(clauses, {})
        return results
