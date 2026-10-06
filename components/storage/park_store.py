import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterable, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS parks (
    park_code    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    designation  TEXT,
    states       TEXT,
    data         TEXT NOT NULL,
    last_fetched TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS searches (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    query                TEXT,
    state_code           TEXT,
    national_only        INTEGER NOT NULL DEFAULT 0,
    result_count         INTEGER NOT NULL,
    camping_percent      INTEGER,
    hiking_percent       INTEGER,
    alerts_percent       INTEGER,
    most_common_activity TEXT,
    created_at           TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorites (
    park_code  TEXT PRIMARY KEY REFERENCES parks (park_code),
    note       TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_searches_created ON searches (created_at);
CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    park_code TEXT NOT NULL,
    data      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_park ON alerts (park_code);
CREATE TABLE IF NOT EXISTS collections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    parks_count  INTEGER NOT NULL,
    alerts_count INTEGER NOT NULL,
    collected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analyses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scope         TEXT NOT NULL,
    collection_id INTEGER REFERENCES collections (id),
    data          TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_analyses_scope ON analyses (scope, id);
"""


def default_database_path() -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.environ.get("DATABASE_PATH", os.path.join(repo_root, "instance", "parks.db"))


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


class ParkStore:
    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def ping(self) -> bool:
        with self._conn() as conn:
            conn.execute("SELECT 1")
        return True

    def upsert_parks(self, parks: Iterable[dict]) -> int:
        now = _now()
        rows = [
            (p["park_code"], p["name"], p.get("designation"), ",".join(p.get("states", [])), json.dumps(p), now)
            for p in parks
            if p.get("park_code")
        ]
        with self._conn() as conn:
            conn.executemany(
                """
                INSERT INTO parks (park_code, name, designation, states, data, last_fetched)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(park_code) DO UPDATE SET
                    name = excluded.name,
                    designation = excluded.designation,
                    states = excluded.states,
                    data = excluded.data,
                    last_fetched = excluded.last_fetched
                """,
                rows,
            )
        return len(rows)

    def get_park(self, park_code: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT data FROM parks WHERE park_code = ?", (park_code,)).fetchone()
        return json.loads(row["data"]) if row else None

    def all_parks(self) -> List[dict]:
        with self._conn() as conn:
            return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM parks ORDER BY name")]

    def record_search(self, query: str, state_code: str, national_only: bool, analysis: dict) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO searches (query, state_code, national_only, result_count, camping_percent,
                                      hiking_percent, alerts_percent, most_common_activity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query or None,
                    state_code or None,
                    int(national_only),
                    analysis["total_parks"],
                    analysis["camping_percent"],
                    analysis["hiking_percent"],
                    analysis["alerts_percent"],
                    analysis["most_common_activity"],
                    _now(),
                ),
            )
            return cur.lastrowid

    def recent_searches(self, limit: int = 10) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM searches ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def top_queries(self, limit: int = 5) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT LOWER(query) AS query, COUNT(*) AS n FROM searches
                WHERE query IS NOT NULL GROUP BY LOWER(query) ORDER BY n DESC, query LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [{"query": r["query"], "count": r["n"]} for r in rows]

    def add_favorite(self, park: dict, note: str = "") -> None:
        self.upsert_parks([park])
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO favorites (park_code, note, created_at) VALUES (?, ?, ?)
                ON CONFLICT(park_code) DO UPDATE SET note = excluded.note
                """,
                (park["park_code"], note or None, _now()),
            )

    def remove_favorite(self, park_code: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM favorites WHERE park_code = ?", (park_code,))
            return cur.rowcount > 0

    def list_favorites(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT f.park_code, f.note, f.created_at, p.data FROM favorites f
                JOIN parks p ON p.park_code = f.park_code ORDER BY f.created_at DESC, p.name
                """
            ).fetchall()
        favorites = []
        for r in rows:
            park = json.loads(r["data"])
            favorites.append({**park, "note": r["note"], "saved_at": r["created_at"]})
        return favorites

    def favorite_codes(self) -> set:
        with self._conn() as conn:
            return {r["park_code"] for r in conn.execute("SELECT park_code FROM favorites")}

    def counts(self) -> dict:
        with self._conn() as conn:
            return {
                "parks": conn.execute("SELECT COUNT(*) FROM parks").fetchone()[0],
                "searches": conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0],
                "favorites": conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0],
            }

    def record_collection(self, parks: List[dict], alerts: List[dict]) -> int:
        self.upsert_parks(parks)
        with self._conn() as conn:
            conn.execute("DELETE FROM alerts")
            conn.executemany(
                "INSERT INTO alerts (park_code, data) VALUES (?, ?)",
                [(a["park_code"], json.dumps(a)) for a in alerts],
            )
            cur = conn.execute(
                "INSERT INTO collections (parks_count, alerts_count, collected_at) VALUES (?, ?, ?)",
                (len(parks), len(alerts), _now()),
            )
            return cur.lastrowid

    def latest_collection(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM collections ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def all_alerts(self) -> List[dict]:
        with self._conn() as conn:
            return [json.loads(r["data"]) for r in conn.execute("SELECT data FROM alerts ORDER BY id")]

    def save_analysis(self, scope: str, analysis: dict, collection_id: Optional[int]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO analyses (scope, collection_id, data, created_at) VALUES (?, ?, ?, ?)",
                (scope, collection_id, json.dumps(analysis), _now()),
            )
            return cur.lastrowid

    def latest_analyses(self) -> dict:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT a.scope, a.collection_id, a.data, a.created_at FROM analyses a
                JOIN (SELECT scope, MAX(id) AS id FROM analyses GROUP BY scope) latest ON latest.id = a.id
                ORDER BY a.scope
                """
            ).fetchall()
        return {
            r["scope"]: {"collection_id": r["collection_id"], "created_at": r["created_at"],
                         "analysis": json.loads(r["data"])}
            for r in rows
        }
