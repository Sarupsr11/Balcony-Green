import logging
import sqlite3
import uuid

from fastapi import HTTPException  # type: ignore
from passlib.context import CryptContext  # type: ignore

# -------------------------
# Config
# -------------------------
SECRET_KEY = "CHANGE_ME_TO_ENV_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
DB_PATH = "balcony.db"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -------------------------
# User Service (OOP)
# -------------------------
class UserService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        logger.info(f"UserService initialized with db_path: {db_path}")

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def hash_password(self, password: str):
        logger.debug("Hashing password")
        return pwd_context.hash(password)

    def verify_password(self, password: str, hashed: str) -> bool:
        logger.debug("Verifying password")
        result = pwd_context.verify(password, hashed)
        logger.debug(f"Password verification result: {result}")
        return result

    def get_user(self, email: str):
        logger.debug(f"Fetching user by email: {email}")
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, email, password_hash FROM users WHERE email = ?", (email,))
        user = cur.fetchone()
        if user:
            logger.debug(f"User found: {email}")
        else:
            logger.warning(f"User not found: {email}")
        return user

    def get_user_by_id(self, user_id: str):
        logger.debug(f"Fetching user by id: {user_id}")
        conn = self._connect()
        cur = conn.cursor()
        cur.execute("SELECT id, email, password_hash FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        if user:
            logger.debug(f"User found: {user_id}")
        else:
            logger.warning(f"User not found: {user_id}")
        return user

    def create_user(self, email: str, password: str, name: str | None):
        user_id = str(uuid.uuid4())
        hashed_pw = self.hash_password(password)
        logger.info(f"Creating new user: {email}")

        conn = self._connect()
        cur = conn.cursor()

        # ---------------------
        # Create users table if not exists
        # ---------------------
        logger.debug("Creating users table if not exists")
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
                (user_id, email, hashed_pw, name),
            )
            conn.commit()
            logger.info(f"User created successfully: {email} (id: {user_id})")
        except sqlite3.IntegrityError:
            logger.error("Email already exists: %s", email)
            raise HTTPException(400, "Email already exists") from None

        return user_id
