"""
학습 진도 추적 및 캐릭터 Pop-Up 관리 서비스
"""
import sqlite3
import json
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Static dataset paths for coverage calculations
DATA_DIR = Path("data")
VOCAB_PATH = DATA_DIR / "vocabulary.json"
SENTENCE_PATH = DATA_DIR / "sentences.json"


@lru_cache(maxsize=1)
def _load_dataset_totals():
    """Load total counts for vocab/sentences once."""
    vocab_total = 0
    sentence_total = 0
    try:
        if VOCAB_PATH.exists():
            with open(VOCAB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    vocab_total = len(data)
                elif isinstance(data, dict):
                    vocab_total = len(data.get("words", []))
    except Exception:
        vocab_total = 0

    try:
        if SENTENCE_PATH.exists():
            with open(SENTENCE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    sentence_total = len(data)
                elif isinstance(data, dict):
                    sentence_total = len(data.get("sentences", []))
    except Exception:
        sentence_total = 0

    return {
        "vocab_total": vocab_total,
        "sentence_total": sentence_total,
        # 콘텐츠 생성 목표치는 명시적 데이터가 없으므로 기본 20건으로 설정
        "content_total": 20,
    }


class LearningProgressService:
    def __init__(self, db_path: str = "data/users.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 스키마 생성
        cursor.executescript(
            """
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

            CREATE TABLE IF NOT EXISTS user_sentence_learning_state (
                user_id TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'all',
                current_sentence_id INTEGER,
                current_index INTEGER DEFAULT 0,
                completed_sentence_ids TEXT DEFAULT '[]',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, scope)
            );
            
            CREATE INDEX IF NOT EXISTS idx_user_progress_user_date 
                ON user_learning_progress(user_id, date);
            CREATE INDEX IF NOT EXISTS idx_popup_history_user 
                ON popup_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_session_log_user 
                ON user_session_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_sentence_state_user 
                ON user_sentence_learning_state(user_id);
            """
        )
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
                   last_learning_date = ?, total_points = total_points + ?, updated_at = CURRENT_TIMESTAMP
               WHERE user_id = ? AND date = ?""",
            (count, new_avg, today, min(score // 10, 10), user_id, today)
        )
        conn.commit()

        # Update streak / total learning days based on actual activity days.
        try:
            streak_days, total_days = self._compute_activity_streak_and_total_days(
                cursor, user_id
            )
            cursor.execute(
                """UPDATE user_learning_progress
                   SET consecutive_days = ?, total_learning_days = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ? AND date = ?""",
                (streak_days, total_days, user_id, today),
            )
            conn.commit()
        except Exception:
            # Non-fatal; keep pronunciation record even if streak calc fails.
            pass
        finally:
            conn.close()
        
        return {"updated": True, "new_score": new_avg}

    def update_sentence_learned(self, user_id: str, count: int = 1):
        """문장 학습 완료 기록 (일일 학습 통계 반영)."""
        if count is None:
            count = 1
        try:
            count = int(count)
        except Exception:
            count = 1
        if count <= 0:
            count = 1

        self.get_or_create_today_progress(user_id)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            cursor.execute(
                """UPDATE user_learning_progress
                   SET sentences_learned = sentences_learned + ?,
                       last_learning_date = ?,
                       total_points = total_points + ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE user_id = ? AND date = ?""",
                (count, today, min(count, 10), user_id, today),
            )
            conn.commit()

            try:
                streak_days, total_days = self._compute_activity_streak_and_total_days(
                    cursor, user_id
                )
                cursor.execute(
                    """UPDATE user_learning_progress
                       SET consecutive_days = ?, total_learning_days = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE user_id = ? AND date = ?""",
                    (streak_days, total_days, user_id, today),
                )
                conn.commit()
            except Exception:
                pass
        finally:
            conn.close()

        return {"updated": True, "count": count}

    def get_or_create_sentence_learning_state(self, user_id: str, scope: str = "all") -> Dict:
        """문장 학습(일반) 마지막 상태 조회 또는 생성."""
        user_id = (user_id or "").strip() or "anonymous"
        scope = (scope or "all").strip() or "all"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT user_id, scope, current_sentence_id, current_index, completed_sentence_ids, updated_at
               FROM user_sentence_learning_state
               WHERE user_id = ? AND scope = ?""",
            (user_id, scope),
        )
        row = cursor.fetchone()
        if not row:
            cursor.execute(
                """INSERT INTO user_sentence_learning_state (user_id, scope, current_sentence_id, current_index, completed_sentence_ids)
                   VALUES (?, ?, NULL, 0, '[]')""",
                (user_id, scope),
            )
            conn.commit()
            cursor.execute(
                """SELECT user_id, scope, current_sentence_id, current_index, completed_sentence_ids, updated_at
                   FROM user_sentence_learning_state
                   WHERE user_id = ? AND scope = ?""",
                (user_id, scope),
            )
            row = cursor.fetchone()
        conn.close()

        completed_ids = []
        try:
            completed_ids = json.loads(row[4] or "[]")
            if not isinstance(completed_ids, list):
                completed_ids = []
        except Exception:
            completed_ids = []

        return {
            "user_id": row[0],
            "scope": row[1],
            "current_sentence_id": row[2],
            "current_index": int(row[3] or 0),
            "completed_sentence_ids": completed_ids,
            "updated_at": row[5],
        }

    def update_sentence_learning_state(
        self,
        user_id: str,
        scope: str = "all",
        current_sentence_id: Optional[int] = None,
        current_index: int = 0,
        completed_sentence_ids: Optional[List[int]] = None,
    ) -> Dict:
        """문장 학습(일반) 마지막 상태 저장."""
        user_id = (user_id or "").strip() or "anonymous"
        scope = (scope or "all").strip() or "all"

        try:
            current_index = int(current_index or 0)
        except Exception:
            current_index = 0
        current_index = max(0, current_index)

        if completed_sentence_ids is None:
            completed_sentence_ids = []
        if not isinstance(completed_sentence_ids, list):
            completed_sentence_ids = []
        normalized_completed = []
        seen = set()
        for item in completed_sentence_ids:
            try:
                sid = int(item)
            except Exception:
                continue
            if sid in seen:
                continue
            seen.add(sid)
            normalized_completed.append(sid)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO user_sentence_learning_state (user_id, scope, current_sentence_id, current_index, completed_sentence_ids, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id, scope)
               DO UPDATE SET
                   current_sentence_id = excluded.current_sentence_id,
                   current_index = excluded.current_index,
                   completed_sentence_ids = excluded.completed_sentence_ids,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                user_id,
                scope,
                current_sentence_id,
                current_index,
                json.dumps(normalized_completed, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

        return self.get_or_create_sentence_learning_state(user_id, scope=scope)

    def _is_activity_day(self, row: Dict) -> bool:
        """학습이 발생한 날인지 판정 (0값 row 생성만으로는 학습으로 보지 않음)."""
        if not isinstance(row, dict):
            return False
        return any(
            [
                int(row.get("pronunciation_practice_count") or 0) > 0,
                int(row.get("words_learned") or 0) > 0,
                int(row.get("sentences_learned") or 0) > 0,
                int(row.get("content_generated") or 0) > 0,
                int(row.get("fluency_test_count") or 0) > 0,
                int(row.get("total_learning_time") or 0) > 0,
            ]
        )

    def _compute_activity_streak_and_total_days(self, cursor, user_id: str):
        """DB cursor 기반으로 연속 학습일(streak)과 총 학습일을 계산."""
        cursor.execute(
            """SELECT date, total_learning_time, pronunciation_practice_count,
                      words_learned, sentences_learned, content_generated, fluency_test_count
               FROM user_learning_progress
               WHERE user_id = ?
               ORDER BY date DESC""",
            (user_id,),
        )
        rows = cursor.fetchall() or []
        parsed = []
        for r in rows:
            parsed.append(
                {
                    "date": r[0],
                    "total_learning_time": r[1],
                    "pronunciation_practice_count": r[2],
                    "words_learned": r[3],
                    "sentences_learned": r[4],
                    "content_generated": r[5],
                    "fluency_test_count": r[6],
                }
            )

        activity_dates = [
            item["date"] for item in parsed if self._is_activity_day(item)
        ]
        total_days = len(set(activity_dates))

        if not activity_dates:
            return 0, total_days

        # streak: count consecutive days from today backwards where activity exists
        today = datetime.now().date()
        activity_set = set(activity_dates)
        streak = 0
        current = today
        while True:
            key = current.strftime("%Y-%m-%d")
            if key not in activity_set:
                break
            streak += 1
            current = current - timedelta(days=1)
        return streak, total_days
    
    def check_popup_trigger(self, user_id: str) -> Optional[Dict]:
        """Pop-Up 트리거 확인 - 하루 1회 제한"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")

        # 오늘 이미 팝업 표시했는지 확인
        cursor.execute(
            """SELECT COUNT(*) FROM popup_history
               WHERE user_id = ? AND DATE(shown_at) = ?""",
            (user_id, today)
        )
        popup_count_today = cursor.fetchone()[0]
        conn.close()

        if popup_count_today > 0:
            return None  # 오늘 이미 표시함

        progress = self.get_or_create_today_progress(user_id)
        stats = self.get_user_stats(user_id)

        # 트리거 조건 확인 (우선순위 순서)
        triggers = []

        # 1. 연속 학습일 달성 (오빠: 상황 안내)
        consecutive_days = stats.get('consecutive_days', 0)
        if consecutive_days in [3, 7, 14, 30]:
            message = self._get_consecutive_message(consecutive_days)
            triggers.append(('achievement', 'oppa', message, f'{consecutive_days}일 연속 학습'))

        # 2. 발음 점수 우수 (동생: 칭찬)
        avg_score = progress.get('pronunciation_avg_score', 0)
        practice_count = progress.get('pronunciation_practice_count', 0)
        if practice_count >= 3 and avg_score >= 85:
            message = f"와! 오늘 평균 점수가 {avg_score:.0f}점이에요! 정말 멋져요! 이 실력이면 곧 완벽한 발음이 될 거예요! 💕"
            triggers.append(('praise', 'sister', message, '높은 평균 점수'))

        # 3. 학습 목표 달성 (동생: 칭찬)
        if practice_count >= 10:
            message = f"헉! 오늘 발음 연습을 {practice_count}번이나 했어요! 진짜 대단해요! 이렇게 열심히 하면 금방 고수가 될 거예요! 👏"
            triggers.append(('praise', 'sister', message, '학습 목표 달성'))

        # 4. 발음 점수 낮음 (호랑이: 독려)
        if practice_count >= 3 and avg_score < 60:
            message = f"흠... 오늘 평균 점수가 {avg_score:.0f}점이네요. 괜찮아요! 천천히 또박또박 발음해보세요. 꾸준히 연습하면 분명 좋아질 거예요! 🐯"
            triggers.append(('encouragement', 'tiger', message, '낮은 점수 독려'))

        # 5. 첫 학습 (오빠: 환영)
        if stats.get('total_practices', 0) == 1:
            message = "오누이 한국어에 오신 걸 환영해요! 오늘부터 함께 한국어 발음을 연습해볼까요? 천천히 하나씩 해나가면 돼요 😊"
            triggers.append(('greeting', 'oppa', message, '첫 학습'))

        # 6. 학습 재개 (호랑이: 경고)
        last_learning = progress.get('last_learning_date')
        if last_learning:
            last_date = datetime.strptime(last_learning, "%Y-%m-%d")
            days_gap = (datetime.now() - last_date).days
            if days_gap >= 3 and days_gap < 7:
                message = f"어? {days_gap}일 동안 안 오셨네요! 😿 연속 학습 기록이 끊어지기 전에 지금 바로 시작해볼까요? 조금만 더 힘내요!"
                triggers.append(('warning', 'tiger', message, f'{days_gap}일 미접속'))

        # 7. 오늘 첫 학습 (오빠: 상황 안내)
        if practice_count == 1:
            message = f"오늘 첫 발음 연습을 시작했네요! 현재 총 {stats.get('total_practices', 0)}번 연습했어요. 오늘도 화이팅! 📚"
            triggers.append(('status', 'oppa', message, '오늘 첫 학습'))

        if triggers:
            popup_type, character, message, trigger_reason = triggers[0]
            return {
                'should_show': True,
                'type': popup_type,
                'character': character,
                'message': message,
                'trigger': trigger_reason,
                'stats': {
                    'consecutive_days': consecutive_days,
                    'avg_score': avg_score,
                    'practice_count': practice_count
                }
            }

        return None

    def _get_consecutive_message(self, days: int) -> str:
        """연속 학습일 메시지 생성"""
        messages = {
            3: "축하해요! 3일 연속 학습을 달성했어요! 🎉 이 페이스를 유지하면 한국어 실력이 쑥쑥 늘 거예요!",
            7: "대단해요! 벌써 일주일 연속 학습이에요! 🌟 꾸준함이 최고의 실력이랍니다!",
            14: "와! 2주 연속 학습! 정말 대단해요! 💪 이 정도면 진정한 한국어 학습자예요!",
            30: "완전 놀라워요! 한 달 연속 학습! 🏆 이제 한국어가 완전히 익숙해졌을 거예요!"
        }
        return messages.get(days, f"{days}일 연속 학습 달성!")
    
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
        
        # 일별 데이터 (그래프/주간 통계용)
        cursor.execute(
            """SELECT date, total_learning_time, pronunciation_practice_count, pronunciation_avg_score,
                      words_learned, sentences_learned, content_generated, fluency_test_count
               FROM user_learning_progress
               WHERE user_id = ?
               ORDER BY date DESC""",
            (user_id,),
        )
        day_rows = cursor.fetchall() or []

        def to_day_dict(r):
            return {
                "date": r[0],
                "duration": int(r[1] or 0),
                "practices": int(r[2] or 0),
                "avg_score": float(r[3] or 0),
                "words_learned": int(r[4] or 0),
                "sentences_learned": int(r[5] or 0),
                "content_generated": int(r[6] or 0),
                "fluency_tests": int(r[7] or 0),
            }

        all_days = [to_day_dict(r) for r in day_rows]
        activity_days = [d for d in all_days if self._is_activity_day(
            {
                "total_learning_time": d["duration"],
                "pronunciation_practice_count": d["practices"],
                "words_learned": d["words_learned"],
                "sentences_learned": d["sentences_learned"],
                "content_generated": d["content_generated"],
                "fluency_test_count": d["fluency_tests"],
            }
        )]

        total_practices = sum(d["practices"] for d in all_days)
        weighted_score_sum = sum(d["avg_score"] * d["practices"] for d in all_days if d["practices"] > 0)
        avg_score = round((weighted_score_sum / total_practices) if total_practices else 0, 1)
        best_score = round(max((d["avg_score"] for d in all_days if d["practices"] > 0), default=0), 1)
        total_duration = sum(d["duration"] for d in all_days)
        learning_days = len({d["date"] for d in activity_days})

        # streak based on activity days
        consecutive_days = 0
        if activity_days:
            activity_set = {d["date"] for d in activity_days}
            today = datetime.now().date()
            while True:
                key = today.strftime("%Y-%m-%d")
                if key not in activity_set:
                    break
                consecutive_days += 1
                today = today - timedelta(days=1)

        last_learning_date = max((d["date"] for d in activity_days), default=None)

        # Weekly stats (last 7 days) + previous week delta
        def parse_date(s):
            return datetime.strptime(s, "%Y-%m-%d").date()

        today_date = datetime.now().date()
        start_7 = today_date - timedelta(days=6)
        start_prev7 = start_7 - timedelta(days=7)
        end_prev7 = start_7 - timedelta(days=1)

        week_days = [d for d in all_days if start_7 <= parse_date(d["date"]) <= today_date]
        prev_week_days = [d for d in all_days if start_prev7 <= parse_date(d["date"]) <= end_prev7]

        def summarize(days):
            total_p = sum(d["practices"] for d in days)
            score_sum = sum(d["avg_score"] * d["practices"] for d in days if d["practices"] > 0)
            avg = round((score_sum / total_p) if total_p else 0, 1)
            dur = sum(d["duration"] for d in days)
            active = sum(1 for d in days if d["practices"] > 0)
            best = None
            for d in days:
                if d["practices"] <= 0:
                    continue
                if best is None or d["avg_score"] > best["avg_score"]:
                    best = {"date": d["date"], "avg_score": round(d["avg_score"], 1), "practices": d["practices"]}
            return {"total_practices": total_p, "avg_score": avg, "total_duration": dur, "active_days": active, "best_day": best}

        weekly = summarize(week_days)
        prev_week = summarize(prev_week_days)
        weekly_delta = {
            "practices": weekly["total_practices"] - prev_week["total_practices"],
            "avg_score": round(weekly["avg_score"] - prev_week["avg_score"], 1),
            "duration": weekly["total_duration"] - prev_week["total_duration"],
            "active_days": weekly["active_days"] - prev_week["active_days"],
        }

        # Daily log (last 30 days, ascending for charts)
        daily_window_start = today_date - timedelta(days=29)
        daily_window = [d for d in all_days if daily_window_start <= parse_date(d["date"]) <= today_date]
        daily_log = sorted(daily_window, key=lambda d: d["date"])

        # Accuracy distribution (approx. weighted by practice count by day avg_score)
        acc = {"excellent": 0, "good": 0, "fair": 0, "need_improvement": 0}
        for d in all_days:
            if d["practices"] <= 0:
                continue
            score = d["avg_score"]
            if score >= 90:
                acc["excellent"] += d["practices"]
            elif score >= 80:
                acc["good"] += d["practices"]
            elif score >= 70:
                acc["fair"] += d["practices"]
            else:
                acc["need_improvement"] += d["practices"]
        
        # 배지 및 업적 정보
        cursor.execute(
            """SELECT badges FROM user_learning_progress
               WHERE user_id = ? AND badges IS NOT NULL
               LIMIT 1""",
            (user_id,)
        )
        badges_row = cursor.fetchone()
        badges = []
        if badges_row and badges_row[0]:
            try:
                badges = json.loads(badges_row[0])
            except:
                badges = []
        
        # 추가 합계: 사용자가 학습한 단어/문장/콘텐츠 건수 합산
        cursor.execute(
            """SELECT
                    SUM(words_learned) as words_learned,
                    SUM(sentences_learned) as sentences_learned,
                    SUM(content_generated) as content_generated
                 FROM user_learning_progress
                 WHERE user_id = ?""",
            (user_id,)
        )
        totals_row = cursor.fetchone()
        words_learned = int(totals_row[0] or 0)
        sentences_learned = int(totals_row[1] or 0)
        content_generated = int(totals_row[2] or 0)

        conn.close()

        dataset_totals = _load_dataset_totals()

        return {
            "total_practices": int(total_practices or 0),
            "avg_score": avg_score,
            "best_score": best_score,
            "total_duration": int(total_duration or 0),
            "learning_days": int(learning_days or 0),
            "consecutive_days": int(consecutive_days or 0),
            "last_learning_date": last_learning_date,
            "weekly": {**weekly, "delta": weekly_delta},
            'achievements': badges,
            "accuracy_distribution": acc,
            "daily_log": daily_log,
            # 커버리지용 필드
            'words_learned': words_learned,
            'words_total': dataset_totals.get('vocab_total', 0),
            'sentences_learned': sentences_learned,
            'sentences_total': dataset_totals.get('sentence_total', 0),
            'content_completed': content_generated,
            'content_total': dataset_totals.get('content_total', 20),
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
