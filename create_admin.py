#!/usr/bin/env python3
import sqlite3
import hashlib
import base64
import os
from datetime import datetime

DB_PATH = 'learning_progress.db'
PBKDF_ITERATIONS = 100000

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 비밀번호 해싱 함수 (main.py와 동일)
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF_ITERATIONS
    )
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"

password_hash = hash_password('mz1234!@')
created_at = datetime.utcnow().isoformat()

# 기존 admin 사용자 확인
cursor.execute('SELECT id FROM users WHERE nickname = ?', ('admin',))
existing = cursor.fetchone()

if existing:
    # 기존 admin 계정 업데이트
    cursor.execute('UPDATE users SET password_hash = ? WHERE nickname = ?', 
                   (password_hash, 'admin'))
    conn.commit()
    print('✓ 기존 admin 계정 비밀번호 업데이트 완료')
    print('닉네임: admin')
    print('비밀번호: mz1234!@')
else:
    # 새 관리자 계정 생성
    try:
        cursor.execute('''
            INSERT INTO users (
                email, nickname, password_hash, native_lang, affiliation, time_pref,
                interests, goal, exam_level, reason, style, created_at, is_admin
            ) VALUES (?, ?, ?, '', '', '', '[]', '', '', '', '', ?, 1)
        ''', (
            'admin@mediazen.co.kr',
            'admin',
            password_hash,
            created_at
        ))
        conn.commit()
        print('✓ 새 admin 계정 생성 완료')
        print('닉네임: admin')
        print('비밀번호: mz1234!@')
    except Exception as e:
        print(f'오류: {e}')
    finally:
        conn.close()
