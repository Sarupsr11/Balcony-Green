# db.py
import logging
import sqlite3
from contextlib import contextmanager

from balconygreen.db_implementation.schema import SCHEMA_SQL

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        logger.info(f"Database initialized with path: {db_path}")
        self._init_db()

    def _init_db(self):
        logger.debug("Initializing database schema")
        with sqlite3.connect(self.db_path, check_same_thread=False) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for stmt in SCHEMA_SQL:
                try:
                    conn.execute(stmt)
                except Exception as e:
                    logger.debug(f"Schema statement execution: {e}")
            conn.commit()
        logger.info("Database initialization complete")

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
        logger.debug(f"Executing query: {query[:50]}... with params: {params}")
        with self.get_conn() as conn:
            conn.execute(query, params)
        logger.debug("Query executed successfully")

    def fetch_one(self, query, params=()):
        logger.debug(f"Fetching one row: {query[:50]}... with params: {params}")
        with self.get_conn() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            if row:
                logger.debug("Row fetched successfully")
            else:
                logger.debug("No row found")
            return dict(row) if row else None

    def fetch_all(self, query, params=()):
        logger.debug(f"Fetching all rows: {query[:50]}... with params: {params}")
        with self.get_conn() as conn:
            cur = conn.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]
            logger.debug(f"Fetched {len(rows)} rows")
            return rows
