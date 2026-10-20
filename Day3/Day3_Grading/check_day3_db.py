"""Automatic database check for «تکلیف ۳»: inspects the student's SQLite file, no human and no PostgreSQL needed.

The same file is shipped to students as ``check_day3_db.py`` (standard library only), so they can see the result
before they submit; the grader runs it again on the uploaded file, which is what counts.

    python check_day3_db.py day3.sqlite [--output database_check.json]     exit code 0 passed, 1 failed, 2 file unreadable

Safety (the file is untrusted): it is only opened, never executed. The file is copied to a temporary path and opened
read-only; probes that write (a rejected orphan row, a rolled-back transaction) run on an in-memory copy. An authorizer
blocks ATTACH, DETACH and every PRAGMA except the read-only ones used here, ``trusted_schema`` is off (triggers and
views cannot call unsafe functions), and a progress handler aborts anything running longer than a few seconds.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import struct
import sys
import tempfile
import time
from typing import Any

DIM = 384
MAX_BYTES = 80 * 1024 * 1024
MAX_SECONDS = 20.0

REQUIRED = {
    "users": {"user_id", "role", "tenant"},
    "cases": {"case_id", "owner_id", "topic", "summary"},
    "sessions": {"session_id", "owner_id", "case_id", "idempotency_key"},
    "messages": {"message_id", "session_id", "content"},
    "documents": {"doc_id", "version", "content_hash"},
    "chunks": {"chunk_id", "doc_id", "content", "embedding", "model_id", "model_revision"},
}
RELATIONS = {
    ("cases", "owner_id", "users", "user_id"),
    ("sessions", "owner_id", "users", "user_id"),
    ("sessions", "case_id", "cases", "case_id"),
    ("messages", "session_id", "sessions", "session_id"),
    ("chunks", "doc_id", "documents", "doc_id"),
}
ALLOWED_PRAGMAS = {"foreign_keys", "table_info", "table_xinfo", "foreign_key_list", "index_list", "index_info", "integrity_check",
                   "quick_check", "trusted_schema", "page_count", "schema_version"}
SQLITE_ATTACH, SQLITE_DETACH, SQLITE_PRAGMA = 24, 25, 19


def _guard(con: sqlite3.Connection) -> None:
    deadline = time.monotonic() + MAX_SECONDS

    def authorizer(action: int, arg1: Any, arg2: Any, dbname: Any, source: Any) -> int:
        if action in (SQLITE_ATTACH, SQLITE_DETACH):
            return sqlite3.SQLITE_DENY
        if action == SQLITE_PRAGMA and str(arg1).lower() not in ALLOWED_PRAGMAS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    con.set_authorizer(authorizer)
    con.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20000)
    try:
        con.execute("PRAGMA trusted_schema=OFF")
    except sqlite3.Error:
        pass


def decode_embedding(value: Any) -> list[float] | None:
    """A BLOB of 384 float32 (or float64), or a JSON array / '[a, b, ...]' text of numbers; None when it is neither."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        if len(raw) == DIM * 4:
            return list(struct.unpack(f"<{DIM}f", raw))
        if len(raw) == DIM * 8:
            return list(struct.unpack(f"<{DIM}d", raw))
        return None
    if isinstance(value, str):
        try:
            arr = json.loads(value)
        except ValueError:
            return None
        if isinstance(arr, list) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in arr):
            return [float(x) for x in arr]
    return None


def _check(checks: list[dict[str, Any]], name: str, passed: bool, **detail: Any) -> bool:
    checks.append({"name": name, "passed": bool(passed), **detail})
    return bool(passed)


def _cols(con: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return con.execute(f'PRAGMA table_info("{table}")').fetchall()


def _placeholder(col: sqlite3.Row, overrides: dict[str, Any], n: int) -> Any:
    if col["name"] in overrides:
        return overrides[col["name"]]
    typ = (col["type"] or "").upper()
    if "INT" in typ or "REAL" in typ or "NUM" in typ:
        return 900000 + n
    if "BLOB" in typ:
        return b"probe"
    return f"probe-{n}"


def _insert(con: sqlite3.Connection, table: str, overrides: dict[str, Any], n: int) -> None:
    cols = _cols(con, table)
    names = [c["name"] for c in cols]
    vals = [_placeholder(c, overrides, n) for c in cols]
    con.execute(f'INSERT INTO "{table}" ({",".join(chr(34) + x + chr(34) for x in names)}) VALUES ({",".join("?" * len(names))})', vals)


def _missing(con: sqlite3.Connection, table: str, column: str) -> Any:
    """A value that exists in no parent table, of the column's own type (a typed column would otherwise fail for the wrong reason)."""
    typ = next(((c["type"] or "").upper() for c in _cols(con, table) if c["name"] == column), "")
    return 987654321 if "INT" in typ else "__missing__"


def _one(con: sqlite3.Connection, sql: str) -> Any:
    return con.execute(sql).fetchone()[0]


def check_sqlite_bytes(raw: bytes) -> dict[str, Any]:
    """The report for the bytes of an uploaded SQLite file. ``status`` is passed, failed, or error (unreadable file)."""
    report: dict[str, Any] = {"schema_version": "1.0", "engine": "SQLite", "status": "error", "checks": [], "credentials_included": False}
    if not raw or len(raw) > MAX_BYTES:
        report["message"] = "The file is empty or larger than the limit."
        return report
    if raw[:16] != b"SQLite format 3\x00":
        report["message"] = "Not a SQLite database file."
        return report
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        return _run(path, report)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _run(path: str, report: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = report["checks"]
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        _guard(con)
        report["sqlite_version"] = sqlite3.sqlite_version
        ok = _one(con, "PRAGMA quick_check") == "ok"
    except sqlite3.Error as err:
        report["message"] = f"The file could not be opened: {type(err).__name__}"
        return report
    _check(checks, "sqlite_file_ok", True)
    _check(checks, "integrity_ok", ok)
    try:
        _contract(con, checks, path)
    except sqlite3.Error as err:  # a corrupt or hostile file: report, do not crash
        _check(checks, "checker_completed", False, error=type(err).__name__)
    finally:
        con.close()
    report["status"] = "passed" if all(c["passed"] for c in checks) else "failed"
    return report


def _contract(con: sqlite3.Connection, checks: list[dict[str, Any]], path: str) -> None:
    tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t, need in REQUIRED.items():
        have = {c["name"] for c in _cols(con, t)} if t in tables else set()
        _check(checks, f"schema_{t}", need <= have, missing_columns=sorted(need - have))
    if not all(c["passed"] for c in checks if c["name"].startswith("schema_")):
        return  # the rest needs the contract tables
    n_users = _one(con, "SELECT count(*) FROM users")
    n_cases = _one(con, "SELECT count(*) FROM cases")
    n_docs = _one(con, "SELECT count(*) FROM documents")
    n_chunks = _one(con, "SELECT count(*) FROM chunks")
    _check(checks, "seed_users", n_users == 20, observed=n_users)
    _check(checks, "seed_cases", n_cases == 120, observed=n_cases)
    _check(checks, "seed_documents", n_docs >= 24, observed=n_docs)
    _check(checks, "seed_chunks", n_chunks >= max(24, n_docs), observed=n_chunks)
    orphan_cases = _one(con, "SELECT count(*) FROM cases c LEFT JOIN users u ON u.user_id=c.owner_id WHERE u.user_id IS NULL")
    orphan_chunks = _one(con, "SELECT count(*) FROM chunks c LEFT JOIN documents d ON d.doc_id=c.doc_id WHERE d.doc_id IS NULL")
    _check(checks, "no_orphan_cases", orphan_cases == 0, observed=orphan_cases)
    _check(checks, "no_orphan_chunks", orphan_chunks == 0, observed=orphan_chunks)

    declared = set()
    for t in REQUIRED:
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            declared.add((t, fk["from"], fk["table"], fk["to"]))
    missing = sorted(RELATIONS - declared)
    _check(checks, "foreign_keys_declared", not missing, missing_relations=[list(m) for m in missing])

    owner_index = False
    for idx in con.execute('PRAGMA index_list("cases")'):
        cols = [r["name"] for r in con.execute(f'PRAGMA index_info("{idx["name"]}")')]
        if cols and cols[0] == "owner_id":
            owner_index = True
    _check(checks, "owner_index", owner_index)

    def unique_on(table: str, column: str) -> bool:
        pk = [c["name"] for c in _cols(con, table) if c["pk"]]
        if pk == [column]:
            return True
        for idx in con.execute(f'PRAGMA index_list("{table}")'):
            cols = [r["name"] for r in con.execute(f'PRAGMA index_info("{idx["name"]}")')]
            if idx["unique"] and column in cols and len(cols) <= 2:
                return True
        return False

    _check(checks, "idempotency_unique", unique_on("sessions", "idempotency_key"))
    _check(checks, "documents_unique", unique_on("documents", "doc_id"))

    wrong = bad = missing_meta = 0
    for row in con.execute("SELECT embedding, model_id, model_revision FROM chunks"):
        vec = decode_embedding(row["embedding"])
        if vec is None or len(vec) != DIM:
            wrong += 1
        elif not all(math.isfinite(x) for x in vec):
            bad += 1
        if not (row["model_id"] or "").strip() or not (row["model_revision"] or "").strip():
            missing_meta += 1
    _check(checks, "embedding_dimensions", n_chunks > 0 and wrong == 0 and bad == 0, wrong_or_unreadable=wrong, non_finite=bad, rows=n_chunks)
    _check(checks, "embedding_metadata_present", n_chunks > 0 and missing_meta == 0, missing=missing_meta)

    # Probes that write run on an in-memory copy and are rolled back; the uploaded file is never modified.
    mem = sqlite3.connect(":memory:")
    mem.row_factory = sqlite3.Row
    con.backup(mem)
    _guard(mem)
    mem.execute("PRAGMA foreign_keys=ON")
    mem.isolation_level = None
    rejected = False
    try:
        mem.execute("BEGIN")
        try:
            _insert(mem, "cases", {"owner_id": _missing(mem, "cases", "owner_id")}, 1)
        except sqlite3.IntegrityError as err:
            rejected = "FOREIGN KEY" in str(err).upper()
        mem.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    _check(checks, "fk_rejects_orphan_case", rejected)

    atomic = False
    try:
        owner = mem.execute("SELECT user_id FROM users LIMIT 1").fetchone()[0]
        case = mem.execute("SELECT case_id FROM cases LIMIT 1").fetchone()[0]
        before = mem.execute("SELECT count(*) FROM sessions").fetchone()[0]
        mem.execute("BEGIN")
        errored = False
        try:
            _insert(mem, "sessions", {"owner_id": owner, "case_id": case, "idempotency_key": "probe-key"}, 2)
            _insert(mem, "messages", {"session_id": _missing(mem, "messages", "session_id")}, 3)
        except sqlite3.IntegrityError as err:
            errored = "FOREIGN KEY" in str(err).upper()
        mem.execute("ROLLBACK")
        after = mem.execute("SELECT count(*) FROM sessions").fetchone()[0]
        atomic = errored and before == after
    except (sqlite3.Error, TypeError):
        pass
    _check(checks, "transaction_rollback", atomic)
    mem.close()


def check_file(path: str) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return check_sqlite_bytes(fh.read(MAX_BYTES + 1))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = "database_check.json"
    if "--output" in args:
        i = args.index("--output")
        out = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print("usage: python check_day3_db.py day3.sqlite [--output database_check.json]")
        return 2
    try:
        report = check_file(args[0])
    except OSError as err:
        report = {"schema_version": "1.0", "engine": "SQLite", "status": "error", "checks": [], "message": f"Cannot read the file: {type(err).__name__}"}
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    for c in report["checks"]:
        print(("OK   " if c["passed"] else "FAIL ") + c["name"])
    print(f"status: {report['status']}" + (f" ({report.get('message')})" if report.get("message") else ""))
    return {"passed": 0, "failed": 1, "error": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
