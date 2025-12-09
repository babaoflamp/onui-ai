"""
학습 진도 추적 및 캐릭터 Pop-Up 관리 서비스
"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class LearningProgressService:
    def __init__(self, db_path: str = "data/users.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 스키마 생성
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS user_learning_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                total_learning_time INTEGER DEFAULT 0,
                pronunciation_practice_count INTEGER DEFAULT 0,
                pronunciation_avg_score REAL DEFAULT 0,
                words_learned INTEGER DEFAULT 0,
                sentences_learned INTEGER DEFAULT 0,
                content_generated INTEGER DEFAULT 0,
                fluency_test_count INTEGER DEFAULT 0,
                consecutive_days INTEGER DEFAULT 0,
                last_learning_date TEXT,
                total_learning_days INTEGER DEFAULT 0,
                achievement_level TEXT DEFAULT 'beginner',
                total_points INTEGER DEFAULT 0,
                badges TEXT DEFAULT '[]',
                last_popup_type TEXT,
                last_popup_date TEXT,
                popup_shown_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            );
            
            CREATE TABLE IF NOT EXISTS popup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                popup_type TEXT NOT NULL,
                character TEXT NOT NULL,
                message TEXT NOT NULL,
                trigger_reason TEXT,
                shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                user_action TEXT DEFAULT 'viewed'
            );
            
            CREATE TABLE IF NOT EXISTS user_session_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_type TEXT NOT NULL,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                duration_minutes INTEGER,
                score INTEGER,
                metadata TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_user_progress_user_date 
                ON user_learning_progress(user_id, date);
            CREATE INDEX IF NOT EXISTS idx_popup_history_user 
                ON popup_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_session_log_user 
                ON user_session_log(user_id);
        """)
        conn.commit()
        conn.close()
    
    def get_or_create_today_progress(self, user_id: str) -> Dict:
        """오늘의 학습 진도 조회 또는 생성"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        cursor.execute(
            "SELECT * FROM user_learning_progress WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        row = cursor.fetchone()
        
        if row:
            result = self._row_to_dict(row)
        else:
            cursor.execute(
                """INSERT INTO user_learning_progress (user_id, date) 
                   VALUES (?, ?)""",
                (user_id, today)
            )
            conn.commit()
            result = self.get_or_create_today_progress(user_id)
        
        conn.close()
        return result
    
    def update_pronunciation_practice(self, user_id: str, score: int):
        """발음 연습 기록"""
        progress = self.get_or_create_today_progress(user_id)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        
        count = progress.get('pronunciation_practice_count', 0) + 1
        avg_score = progress.get('pronunciation_avg_score', 0)
        new_avg = (avg_score * (count - 1) + score) / count
        
        cursor.execute(
            """UPDATE user_learning_progress 
               SET pronunciation_practice_count = ?, pronunciation_avg_score = ?,
                   total_points = total_points + ?, updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ? AND date = ?""",
            (count, new_avg, min(score // 10, 10), user_id, today)
        )
        conn.commit()
        conn.close()
        
        return {"updated": True, "new_score": new_avg}
    
    def check_popup_trigger(self, user_id: str) -> Optional[Dict]:
        """Pop-Up 트리거 확인"""
        progress = self.get_or_create_today_progress(user_id)
        
        # 트리거 조건 확인
        triggers = []
        
        # 1. 첫 학습 (인사)
        if progress.get('pronunciation_practice_count', 0) == 1:
            triggers.append(('greeting', 'oppa', '첫 발음 연습을 시작했네요! 화이팅!'))
        
        # 2. 연속 3일 학습 (호랑이 격려)
        if progress.get('consecutive_days', 0) == 3:
            triggers.append(('achievement', 'tiger', '3일 연속 학습! 정말 대단해요!'))
        
        # 3. 평균 점수 80점 이상 (동생 칭찬)
        if progress.get('pronunciation_avg_score', 0) >= 80:
            triggers.append(('praise', 'sister', '발음이 정말 좋아지고 있어요! 계속 화이팅!'))
        
        # 4. 발음 연습 5회 (호랑이 독려)
        if progress.get('pronunciation_practice_count', 0) == 5:
            triggers.append(('encouragement', 'tiger', '5번 연습했어요! 꾸준함이 최고입니다!'))
        
        # 5. 평균 점수 60점 이하 (호랑이 경고)
        if progress.get('pronunciation_avg_score', 0) < 60 and progress.get('pronunciation_practice_count', 0) > 0:
            triggers.append(('warning', 'tiger', '발음 점수가 낮네요. 천천히 다시 시도해보세요!'))
        
        if triggers:
            popup_type, character, message = triggers[0]
            return {
                'should_show': True,
                'type': popup_type,
                'character': character,
                'message': message,
                'trigger': triggers[0][0]
            }
        
        return None
    
    def record_popup_shown(self, user_id: str, popup_type: str, character: str, message: str, trigger_reason: str):
        """Pop-Up 표시 기록"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 팝업 히스토리 기록
        cursor.execute(
            """INSERT INTO popup_history (user_id, popup_type, character, message, trigger_reason)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, popup_type, character, message, trigger_reason)
        )
        
        # 진도 업데이트
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute(
            """UPDATE user_learning_progress 
               SET last_popup_type = ?, last_popup_date = ?, popup_shown_count = popup_shown_count + 1,
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ? AND date = ?""",
            (popup_type, today, user_id, today)
        )
        
        conn.commit()
        conn.close()
    
    def get_user_stats(self, user_id: str) -> Dict:
        """사용자 통계 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT SUM(total_learning_time) as total_time,
                      SUM(pronunciation_practice_count) as total_practices,
                      AVG(pronunciation_avg_score) as avg_score,
                      COUNT(DISTINCT date) as learning_days
               FROM user_learning_progress
               WHERE user_id = ?""",
            (user_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            'total_learning_time': row[0] or 0,
            'total_pronunciation_practices': row[1] or 0,
            'average_pronunciation_score': round(row[2] or 0, 1),
            'total_learning_days': row[3] or 0
        }
    
    def _row_to_dict(self, row) -> Dict:
        """DB 행을 딕셔너리로 변환"""
        columns = [
            'id', 'user_id', 'date', 'total_learning_time',
            'pronunciation_practice_count', 'pronunciation_avg_score',
            'words_learned', 'sentences_learned', 'content_generated',
            'fluency_test_count', 'consecutive_days', 'last_learning_date',
            'total_learning_days', 'achievement_level', 'total_points',
            'badges', 'last_popup_type', 'last_popup_date', 'popup_shown_count'
        ]
        return dict(zip(columns, row))
