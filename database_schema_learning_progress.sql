-- 사용자 학습 진도 추적
CREATE TABLE IF NOT EXISTS user_learning_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    
    -- 학습 활동 통계
    total_learning_time INTEGER DEFAULT 0,          -- 전체 학습 시간 (분)
    pronunciation_practice_count INTEGER DEFAULT 0, -- 발음 연습 횟수
    pronunciation_avg_score REAL DEFAULT 0,         -- 발음 평가 평균 점수
    words_learned INTEGER DEFAULT 0,                -- 학습한 단어 수
    sentences_learned INTEGER DEFAULT 0,            -- 학습한 문장 수
    content_generated INTEGER DEFAULT 0,            -- 생성한 맞춤형 교재 수
    fluency_test_count INTEGER DEFAULT 0,           -- 유창성 테스트 횟수
    
    -- 연속 학습 정보
    consecutive_days INTEGER DEFAULT 0,             -- 연속 학습 일수
    last_learning_date TEXT,                        -- 마지막 학습 날짜
    total_learning_days INTEGER DEFAULT 0,          -- 총 학습 일수
    
    -- 성취도
    achievement_level TEXT DEFAULT 'beginner',      -- beginner, intermediate, advanced
    total_points INTEGER DEFAULT 0,                 -- 누적 포인트
    badges TEXT DEFAULT '[]',                       -- 획득 배지 (JSON)
    
    -- Pop-Up 상태
    last_popup_type TEXT,                           -- 마지막 Pop-Up 타입
    last_popup_date TEXT,                           -- 마지막 Pop-Up 날짜
    popup_shown_count INTEGER DEFAULT 0,            -- 표시된 Pop-Up 총 개수
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, date)
);

-- Pop-Up 히스토리 (분석용)
CREATE TABLE IF NOT EXISTS popup_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    popup_type TEXT NOT NULL,              -- 'greeting', 'achievement', 'warning', 'encouragement', 'praise'
    character TEXT NOT NULL,               -- 'oppa', 'tiger', 'sister'
    message TEXT NOT NULL,
    trigger_reason TEXT,                   -- 트리거 사유
    shown_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_action TEXT DEFAULT 'viewed'      -- viewed, dismissed, clicked
);

-- 사용자 세션 로그 (학습 활동 추적)
CREATE TABLE IF NOT EXISTS user_session_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_type TEXT NOT NULL,            -- 'pronunciation', 'content', 'fluency', 'vocabulary'
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_minutes INTEGER,              -- 세션 지속 시간
    score INTEGER,                         -- 성과 점수 (있는 경우)
    metadata TEXT                          -- 추가 정보 (JSON)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_user_progress_user_date ON user_learning_progress(user_id, date);
CREATE INDEX IF NOT EXISTS idx_popup_history_user ON popup_history(user_id);
CREATE INDEX IF NOT EXISTS idx_session_log_user ON user_session_log(user_id);
