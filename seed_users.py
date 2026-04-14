import sqlite3
import hashlib
import base64
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/users.db")
PBKDF_ITERATIONS = 120000

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

def seed_users():
    if not DB_PATH.exists():
        print("DB not found")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        created_at = datetime.utcnow().isoformat()
        
        # 1. Admin (already exists maybe, but ensure role)
        password_hash = hash_password('mz1234!@')
        cursor.execute("SELECT id FROM users WHERE email = ?", ('admin@mediazen.co.kr',))
        if not cursor.fetchone():
            print("Creating Admin...")
            cursor.execute("""
                INSERT INTO users (email, name, nickname, password_hash, created_at, is_admin, role)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, ('admin@mediazen.co.kr', 'Admin', 'Admin', password_hash, created_at, 'system_admin'))
        else:
            print("Admin exists, ensuring role...")
            cursor.execute("UPDATE users SET role = 'system_admin', is_admin = 1 WHERE email = ?", ('admin@mediazen.co.kr',))

        # 2. Teacher
        cursor.execute("SELECT id FROM users WHERE email = ?", ('teacher@mediazen.co.kr',))
        if not cursor.fetchone():
            print("Creating Teacher...")
            cursor.execute("""
                INSERT INTO users (email, name, nickname, password_hash, created_at, is_admin, role)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, ('teacher@mediazen.co.kr', 'Teacher', 'teacher', password_hash, created_at, 'instructor'))
        else:
            print("Teacher already exists")

        # 3. Teach
        cursor.execute("SELECT id FROM users WHERE email = ?", ('teach@mediazen.co.kr',))
        if not cursor.fetchone():
            print("Creating Teach...")
            cursor.execute("""
                INSERT INTO users (email, name, nickname, password_hash, created_at, is_admin, role)
                VALUES (?, ?, ?, ?, ?, 0, ?)
            """, ('teach@mediazen.co.kr', 'Teach', 'teach', password_hash, created_at, 'instructor'))
        else:
            print("Teach already exists")

        conn.commit()
        print("Seeding complete.")
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    seed_users()
