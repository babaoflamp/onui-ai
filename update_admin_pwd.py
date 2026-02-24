import sqlite3
import sys

try:
    from passlib.hash import pbkdf2_sha256
except ImportError:
    print("passlib not installed")
    sys.exit(1)

try:
    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()
    
    # Check users
    c.execute('SELECT id, email, nickname FROM users WHERE nickname = ?', ('admin',))
    users = c.fetchall()
    print(f"Found {len(users)} users with nickname 'admin'")
    
    # Update password
    new_pw_hash = pbkdf2_sha256.hash('mz1234!@')
    c.execute('UPDATE users SET password_hash = ? WHERE nickname = ?', (new_pw_hash, 'admin'))
    print(f'Updated {c.rowcount} accounts with new password mz1234!@')
    
    conn.commit()
    conn.close()
except Exception as e:
    print(e)
