import hashlib
import os
import base64
import sqlite3

PBKDF_ITERATIONS = 120_000

def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

if __name__ == "__main__":
    conn = sqlite3.connect('data/users.db')
    cursor = conn.cursor()
    
    new_hash = _hash_password('mz1234!@')
    
    cursor.execute('UPDATE users SET password_hash = ? WHERE nickname = ?', (new_hash, 'admin'))
    print(f"Updated {cursor.rowcount} users with nickname 'admin'")
    
    conn.commit()
    conn.close()
