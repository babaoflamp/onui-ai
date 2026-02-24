import sqlite3

db_path = 'data/users.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    target_email = 'admin@urimalzen.com'

    # 삭제 전 확인
    cursor.execute("SELECT id, nickname, email FROM users WHERE email = ?", (target_email,))
    user = cursor.fetchone()

    if user:
        print(f"삭제할 계정 확인: ID {user[0]}, {user[1]} ({user[2]})")
        
        # 삭제 실행
        cursor.execute("DELETE FROM users WHERE email = ?", (target_email,))
        conn.commit()
        print(f"✅ {target_email} 계정이 삭제되었습니다.")
    else:
        print(f"⚠️ {target_email} 계정을 찾을 수 없습니다.")

    # 최종 계정 목록 확인
    print("\n[최종 계정 목록]")
    print(f"{'ID':<5} {'Nickname':<15} {'Email':<30} {'Role':<15}")
    print("-" * 70)
    
    cursor.execute("SELECT id, nickname, email, role FROM users ORDER BY id")
    for row in cursor.fetchall():
        print(f"{row[0]:<5} {row[1]:<15} {row[2]:<30} {row[3]:<15}")

except sqlite3.Error as e:
    print(f"❌ 데이터베이스 오류: {e}")
finally:
    if conn:
        conn.close()
