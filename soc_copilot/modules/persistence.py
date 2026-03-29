import sqlite3
import hashlib
import json
import shutil
import gc
import time
from datetime import datetime
from pathlib import Path
from soc_copilot.config import DB_PATH

_SQLITE_CORRUPTION_MARKERS = (
    "database disk image is malformed",
    "malformed",
    "file is not a database",
    "not a database",
    "database corrupt",
)


class ManagedSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()


def _db_path() -> Path:
    return Path(DB_PATH)


def _db_related_paths(db_path: Path) -> list[Path]:
    return [
        db_path,
        Path(str(db_path) + "-wal"),
        Path(str(db_path) + "-shm"),
    ]


def _is_recoverable_sqlite_error(exc: Exception) -> bool:
    message = str(exc or "").strip().lower()
    return any(marker in message for marker in _SQLITE_CORRUPTION_MARKERS)


def _archive_corrupted_db_files(db_path: Path) -> list[Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archived: list[Path] = []
    for candidate in _db_related_paths(db_path):
        if not candidate.exists():
            continue
        destination = candidate.with_name(f"{candidate.name}.corrupted.{timestamp}")
        suffix = 1
        while destination.exists():
            destination = candidate.with_name(f"{candidate.name}.corrupted.{timestamp}.{suffix}")
            suffix += 1
        moved = False
        for attempt in range(5):
            try:
                shutil.move(str(candidate), str(destination))
                moved = True
                break
            except PermissionError:
                gc.collect()
                time.sleep(0.15 * (attempt + 1))
        if not moved:
            shutil.move(str(candidate), str(destination))
        archived.append(destination)
    return archived


def _validate_conn(conn: sqlite3.Connection) -> None:
    row = conn.execute("PRAGMA quick_check").fetchone()
    if not row:
        return
    result = str(row[0] or "").strip()
    if result and result.lower() != "ok":
        raise sqlite3.DatabaseError(f"sqlite quick_check failed: {result}")


def _open_conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10, factory=ManagedSQLiteConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def get_conn() -> sqlite3.Connection:
    db_path = _db_path()
    conn: sqlite3.Connection | None = None
    try:
        conn = _open_conn(db_path)
        _validate_conn(conn)
        return conn
    except sqlite3.Error as exc:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            finally:
                conn = None
        gc.collect()
        time.sleep(0.1)
        if not _is_recoverable_sqlite_error(exc):
            raise
        _archive_corrupted_db_files(db_path)
        conn = _open_conn(db_path)
        _validate_conn(conn)
        return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at       TEXT    NOT NULL,
                ofensa_id        TEXT,
                cliente          TEXT,
                regra            TEXT,
                input_hash       TEXT,
                classificacao_sugerida TEXT,
                template_usado   TEXT,
                status_execucao  TEXT    DEFAULT 'ok'
            );

            CREATE TABLE IF NOT EXISTS intel_results (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id           INTEGER NOT NULL,
                ioc              TEXT,
                tipo             TEXT,
                ferramenta       TEXT,
                resultado_resumido TEXT,
                timestamp_consulta TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS analysis_helper (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id       INTEGER NOT NULL UNIQUE,
                resumo_json  TEXT,
                hipoteses_json TEXT,
                lacunas_json TEXT,
                qualidade_json TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE TABLE IF NOT EXISTS analyst_feedback (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TEXT NOT NULL,
                run_id            INTEGER,
                session_id        TEXT,
                payload_hash      TEXT,
                feedback_type     TEXT NOT NULL,
                verdict_correction TEXT,
                comments          TEXT,
                source            TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS outputs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id    INTEGER NOT NULL,
                tipo_saida TEXT,
                conteudo  TEXT,
                salvo_em  TEXT,
                FOREIGN KEY (run_id) REFERENCES runs(id)
            );

            CREATE INDEX IF NOT EXISTS idx_runs_cliente  ON runs(cliente);
            CREATE INDEX IF NOT EXISTS idx_runs_regra    ON runs(regra);
            CREATE INDEX IF NOT EXISTS idx_feedback_run  ON analyst_feedback(run_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_session ON analyst_feedback(session_id, id DESC);

            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id        TEXT PRIMARY KEY,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                cliente           TEXT,
                titulo            TEXT
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id        TEXT NOT NULL,
                created_at        TEXT NOT NULL,
                role              TEXT NOT NULL,
                content           TEXT NOT NULL,
                skill             TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            );

            CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id, id DESC);
        """)
        _ensure_column(conn, "chat_messages", "metadata_json", "TEXT")
        _ensure_column(conn, "analysis_helper", "structured_json", "TEXT")


def checkpoint_db(truncate: bool = True) -> dict[str, object]:
    mode = "TRUNCATE" if truncate else "PASSIVE"
    with get_conn() as conn:
        row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
    values = tuple(row) if row is not None else tuple()
    return {
        "mode": mode.lower(),
        "result": list(values),
        "db_path": str(_db_path()),
    }


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def hash_input(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def save_run(
    ofensa_id: str,
    cliente: str,
    regra: str,
    raw_input: str,
    classificacao: str,
    template_usado: str,
    status: str = "ok",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO runs
               (created_at, ofensa_id, cliente, regra, input_hash,
                classificacao_sugerida, template_usado, status_execucao)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                ofensa_id,
                cliente,
                regra,
                hash_input(raw_input),
                classificacao,
                template_usado,
                status,
            ),
        )
        return cur.lastrowid


def save_intel(run_id: int, ioc: str, tipo: str, ferramenta: str, resultado: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO intel_results
               (run_id, ioc, tipo, ferramenta, resultado_resumido, timestamp_consulta)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                ioc,
                tipo,
                ferramenta,
                resultado,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def save_analysis(run_id: int, analysis: dict, structured_analysis: dict | None = None):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_helper
               (run_id, resumo_json, hipoteses_json, lacunas_json, qualidade_json, structured_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                json.dumps(analysis.get("resumo_factual", {}), ensure_ascii=False),
                json.dumps(analysis.get("hipoteses", []), ensure_ascii=False),
                json.dumps(analysis.get("lacunas", []), ensure_ascii=False),
                json.dumps(analysis.get("alertas_de_qualidade", []), ensure_ascii=False),
                json.dumps(structured_analysis or {}, ensure_ascii=False),
            ),
        )


def save_output(run_id: int, tipo_saida: str, conteudo: str, salvo_em: str = ""):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO outputs (run_id, tipo_saida, conteudo, salvo_em)
               VALUES (?, ?, ?, ?)""",
            (run_id, tipo_saida, conteudo, salvo_em),
        )


def list_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, created_at, ofensa_id, cliente, regra,
                      classificacao_sugerida, template_usado, status_execucao
               FROM runs ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_run(run_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, created_at, ofensa_id, cliente, regra, input_hash,
                      classificacao_sugerida, template_usado, status_execucao
               FROM runs WHERE id=?""",
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def ensure_chat_session(session_id: str, cliente: str = "", titulo: str = "") -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_sessions (session_id, created_at, updated_at, cliente, titulo)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   updated_at=excluded.updated_at,
                   cliente=CASE
                     WHEN excluded.cliente <> '' THEN excluded.cliente
                     ELSE chat_sessions.cliente
                   END,
                   titulo=CASE
                     WHEN excluded.titulo <> '' THEN excluded.titulo
                     ELSE chat_sessions.titulo
                   END
            """,
            (session_id, timestamp, timestamp, cliente, titulo),
        )


def save_chat_message(
    session_id: str,
    role: str,
    content: str,
    skill: str = "",
    metadata: dict | None = None,
) -> None:
    if not session_id or not role or not content:
        return

    ensure_chat_session(session_id=session_id)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO chat_messages (session_id, created_at, role, content, skill, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                datetime.now().isoformat(timespec="seconds"),
                role,
                content,
                skill,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.execute(
            """UPDATE chat_sessions
               SET updated_at=?
               WHERE session_id=?""",
            (datetime.now().isoformat(timespec="seconds"), session_id),
        )


def list_chat_messages(session_id: str, limit: int = 8) -> list[dict]:
    if not session_id:
        return []

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT role, content, skill, created_at, metadata_json
               FROM chat_messages
               WHERE session_id=?
               ORDER BY id DESC
               LIMIT ?""",
            (session_id, max(1, min(limit, 100))),
        ).fetchall()
    items = [dict(row) for row in rows]
    items.reverse()
    for item in items:
        metadata_raw = item.get("metadata_json") or ""
        try:
            item["metadata"] = json.loads(metadata_raw) if metadata_raw else {}
        except json.JSONDecodeError:
            item["metadata"] = {}
        item.pop("metadata_json", None)
    return items


def list_chat_sessions(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                s.session_id,
                s.created_at,
                s.updated_at,
                s.cliente,
                s.titulo,
                (
                    SELECT content
                    FROM chat_messages m
                    WHERE m.session_id = s.session_id
                    ORDER BY m.id DESC
                    LIMIT 1
                ) AS preview,
                (
                    SELECT role
                    FROM chat_messages m
                    WHERE m.session_id = s.session_id
                    ORDER BY m.id DESC
                    LIMIT 1
                ) AS last_role
            FROM chat_sessions s
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (max(1, min(limit, 200)),),
        ).fetchall()
    return [dict(row) for row in rows]


def save_feedback(
    feedback_type: str,
    run_id: int | None = None,
    session_id: str = "",
    payload_hash: str = "",
    verdict_correction: str = "",
    comments: str = "",
    source: str = "ui",
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO analyst_feedback
               (created_at, run_id, session_id, payload_hash, feedback_type,
                verdict_correction, comments, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(timespec="seconds"),
                run_id,
                session_id,
                payload_hash,
                feedback_type,
                verdict_correction,
                comments,
                source,
            ),
        )
        return cur.lastrowid
