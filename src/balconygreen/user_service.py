from __future__ import annotations

import sqlite3
import uuid

from fastapi import HTTPException  # type: ignore
from passlib.context import CryptContext  # type: ignore


pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


class UserService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def hash_password(self, password: str):
        return pwd_context.hash(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        return pwd_context.verify(password, hashed)

    def get_user(self, username: str):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = ?",
                (username,),
            )
            return cur.fetchone()

    def get_user_by_id(self, user_id: str):
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, email, name, password_hash FROM users WHERE id = ?",
                (user_id,),
            )
            return cur.fetchone()

    def create_user(self, username: str, password: str, name: str | None):
        user_id = str(uuid.uuid4())
        hashed_pw = self.hash_password(password)

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                cur.execute(
                    """
                    INSERT INTO users (id, email, password_hash, name)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, username, hashed_pw, name),
                )
            except sqlite3.IntegrityError as exc:
                raise HTTPException(400, "Username already exists") from exc

        return user_id
