import sqlite3

db_path = 'data/users.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 유지할 닉네임 목록
    keep_nicknames = ('student', 'teacher', 'admin')

    # 삭제 대상 확인
    cursor.execute(f"SELECT id, nickname, email FROM users WHERE nickname NOT IN {keep_nicknames}")
    to_delete = cursor.fetchall()

    print(f"총 {len(to_delete)}개의 계정을 삭제합니다:")
    for user in to_delete:
        print(f" - [삭제] {user[1]} ({user[2]})")

    # 삭제 실행
    cursor.execute(f"DELETE FROM users WHERE nickname NOT IN {keep_nicknames}")
    deleted_count = cursor.rowcount
    conn.commit()

    print(f"\n✅ 삭제 완료: {deleted_count}개 계정 삭제됨")

    # 남은 계정 확인
    print("\n[현재 유지된 계정 목록]")
    cursor.execute("SELECT id, nickname, email, role FROM users ORDER BY id")
    remaining = cursor.fetchall()
    
    # 포맷팅하여 출력
    print(f"{'ID':<5} {'Nickname':<15} {'Email':<30} {'Role':<15}")
    print("-" * 70)
    for user in remaining:
        print(f"{user[0]:<5} {user[1]:<15} {user[2]:<30} {user[3]:<15}")

except sqlite3.Error as e:
    print(f"❌ 데이터베이스 오류: {e}")
finally:
    if conn:
        conn.close()
