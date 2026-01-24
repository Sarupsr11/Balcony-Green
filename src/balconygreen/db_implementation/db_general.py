# db.py
import sqlite3
from contextlib import contextmanager
from balconygreen.db_implementation.schema import SCHEMA_SQL



class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, check_same_thread= False) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for stmt in SCHEMA_SQL:
                conn.execute(stmt)
            conn.commit()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, query, params=()):
        with self.get_conn() as conn:
            conn.execute(query, params)

    def fetch_one(self, query, params=()):
        with self.get_conn() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetch_all(self, query, params=()):
        with self.get_conn() as conn:
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]
