import sqlite3
import hashlib
import json
from datetime import datetime
from pathlib import Path
from soc_copilot.config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
        """)


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


def save_analysis(run_id: int, analysis: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_helper
               (run_id, resumo_json, hipoteses_json, lacunas_json, qualidade_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                run_id,
                json.dumps(analysis.get("resumo_factual", {}), ensure_ascii=False),
                json.dumps(analysis.get("hipoteses", []), ensure_ascii=False),
                json.dumps(analysis.get("lacunas", []), ensure_ascii=False),
                json.dumps(analysis.get("alertas_de_qualidade", []), ensure_ascii=False),
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
