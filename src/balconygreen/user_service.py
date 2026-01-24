from passlib.context import CryptContext # type: ignore
import sqlite3
import uuid
from fastapi import FastAPI, HTTPException # type: ignore

# -------------------------
# Config
# -------------------------
SECRET_KEY = "CHANGE_ME_TO_ENV_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
DB_PATH = "balcony.db"


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



# -------------------------
# User Service (OOP)
# -------------------------
class UserService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def hash_password(self, password: str):
        return pwd_context.hash(password)


    def verify_password(self, password: str, hashed: str) -> bool:
        return pwd_context.verify(password, hashed)

    def get_user(self, email: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?",
            (email,)
        )
        return cur.fetchone()


    def get_user_by_id(self, user_id: str):
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, email, password_hash FROM users WHERE id = ?",
            (user_id,)
        )
        return cur.fetchone()
    
    def create_user(self, email: str, password: str, name: str | None):
        user_id = str(uuid.uuid4())
        hashed_pw = self.hash_password(password)

        conn = self._connect()
        cur = conn.cursor()

        
        # ---------------------
        # Create users table if not exists
        # ---------------------
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()
        try:
            cur.execute(
                """
                INSERT INTO users (id, email, password_hash, name)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, email, hashed_pw, name)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(400, "Email already exists")

        return user_id
