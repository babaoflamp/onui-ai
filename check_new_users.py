import sqlite3
import os
from datetime import datetime

db_path = "data/users.db"
today = "2026-04-24"

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

try:
    # Check column names
    cursor.execute("PRAGMA table_info(users)")
    columns = [row['name'] for row in cursor.fetchall()]
    print(f"Columns: {columns}")

    # Search for users created today
    # created_at might be a timestamp or a string
    query = "SELECT id, email, nickname, created_at FROM users WHERE created_at LIKE ?"
    cursor.execute(query, (f"{today}%",))
    users = cursor.fetchall()

    if not users:
        print(f"No users found created on {today}")
    else:
        print(f"Found {len(users)} users created on {today}:")
        for user in users:
            print(f"ID: {user['id']}, Email: {user['email']}, Nickname: {user['nickname']}, Created At: {user['created_at']}")

except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
