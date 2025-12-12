# 캐릭터 팝업 시스템 구현 완료 보고서

**작성일**: 2025년 12월 11일
**구현자**: Claude Code
**상태**: ✅ 완료

---

## 📋 구현 개요

학습자에게 AI 에이전트가 학습을 관리하는 듯한 경험을 제공하기 위한 **캐릭터 기반 팝업 시스템**을 구현했습니다.

### 핵심 기능

- ✅ 3가지 캐릭터 (오빠, 호랑이, 여동생) 역할 구분
- ✅ 조선시대 편지 스타일 UI 디자인
- ✅ 7가지 트리거 이벤트 자동 감지
- ✅ 하루 1회 제한으로 사용자 피로도 방지
- ✅ 학습 진도 데이터 기반 맞춤 메시지

---

## 🎭 캐릭터 역할

### 👦 오빠 (남동생)
**역할**: 현재 상황 안내
- 연속 학습일 달성 축하 (3일, 7일, 14일, 30일)
- 오늘 첫 학습 시작 안내
- 통계 정보 제공

**메시지 예시**:
> "축하해요! 3일 연속 학습을 달성했어요! 🎉 이 페이스를 유지하면 한국어 실력이 쑥쑥 늘 거예요!"

### 🐯 호랑이
**역할**: 경고 및 독려
- 발음 점수가 낮을 때 격려
- 장기간 미접속 시 경고
- 꾸준한 학습 독려

**메시지 예시**:
> "어? 3일 동안 안 오셨네요! 😿 연속 학습 기록이 끊어지기 전에 지금 바로 시작해볼까요?"

### 👧 여동생
**역할**: 칭찬 및 응원
- 높은 발음 점수 달성 시 칭찬
- 학습 목표 달성 시 축하
- 긍정적 피드백 제공

**메시지 예시**:
> "와! 오늘 평균 점수가 85점이에요! 정말 멋져요! 💕"

---

## 🔔 트리거 이벤트 (우선순위 순서)

| 우선순위 | 이벤트 | 캐릭터 | 조건 |
|---------|--------|--------|------|
| 1 | 연속 학습일 달성 | 오빠 | 3, 7, 14, 30일 달성 시 |
| 2 | 발음 점수 우수 | 여동생 | 3회 이상 연습 & 평균 85점 이상 |
| 3 | 학습 목표 달성 | 여동생 | 오늘 10회 이상 연습 |
| 4 | 발음 점수 낮음 | 호랑이 | 3회 이상 연습 & 평균 60점 미만 |
| 5 | 첫 학습 | 오빠 | 전체 1회 연습 시 (환영 메시지) |
| 6 | 학습 재개 | 호랑이 | 3일 이상 미접속 |
| 7 | 오늘 첫 학습 | 오빠 | 오늘 1회 연습 시 |

**로직**:
- 위에서부터 순서대로 조건 확인
- 첫 번째 조건 충족 시 해당 팝업만 표시
- 하루 1회 제한 (동일 날짜에 이미 표시한 경우 스킵)

---

## 🏗️ 구현 구조

### 1. 백엔드 (Python)

#### `backend/services/learning_progress_service.py`

**주요 메서드**:

```python
class LearningProgressService:
    def check_popup_trigger(user_id: str) -> Optional[Dict]:
        """팝업 트리거 확인 - 하루 1회 제한"""
        # 1. 오늘 이미 팝업 표시했는지 확인
        # 2. 사용자 진도 및 통계 조회
        # 3. 7가지 트리거 조건 순서대로 확인
        # 4. 첫 번째 조건 충족 시 팝업 데이터 반환

    def record_popup_shown(user_id, popup_type, character, message, trigger_reason):
        """팝업 표시 기록 (히스토리 및 진도 업데이트)"""

    def _get_consecutive_message(days: int) -> str:
        """연속 학습일 메시지 생성"""
```

**데이터베이스 스키마**:

```sql
-- 팝업 히스토리
CREATE TABLE popup_history (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    popup_type TEXT NOT NULL,     -- 'greeting', 'achievement', 'warning' 등
    character TEXT NOT NULL,       -- 'oppa', 'tiger', 'sister'
    message TEXT NOT NULL,
    trigger_reason TEXT,
    shown_at TIMESTAMP,
    user_action TEXT DEFAULT 'viewed'
);
```

#### `main.py` - API 엔드포인트

```python
# 팝업 트리거 확인 (페이지 로드 시)
POST /api/learning/check-popup
- 인증 필요
- 반환: {"popup": {...}} 또는 {"popup": null}

# 팝업 표시 기록
POST /api/learning/popup-shown
- 인증 필요
- Body: {popup_type, character, message, trigger_reason}

# 발음 연습 완료 기록 (기존 엔드포인트 활용)
POST /api/learning/pronunciation-completed
- Body: {user_id, score}
- 반환: {success, updated, popup}  # popup 자동 포함
```

### 2. 프론트엔드 (HTML/JavaScript)

#### `templates/components/character-popup.html`

**UI 구성**:
- 조선시대 편지 스타일 박스
- 캐릭터 아바타 (이모지)
- 왁스 씰 (상단 우측)
- 편지 본문 (메시지)
- 날짜 표시
- 확인 버튼

**캐릭터별 색상 테마**:
- 오빠: 파란색 계열 (`.popup-oppa`)
- 호랑이: 오렌지색 계열 (`.popup-tiger`)
- 여동생: 분홍색 계열 (`.popup-sister`)

**JavaScript 함수**:

```javascript
// 서버에서 팝업 트리거 확인
async function checkPopupTrigger()

// 팝업 표시
function showCharacterPopup(popupData)

// 팝업 닫기
function closeCharacterPopup()

// 팝업 기록
async function recordPopupShown(popupData)
```

**자동 실행**:
- 페이지 로드 3초 후 자동으로 `checkPopupTrigger()` 호출
- 로그인된 사용자만 팝업 확인

#### `templates/base.html`

```html
<!-- body 닫는 태그 직전에 포함 -->
{% include 'components/character-popup.html' %}
```

모든 페이지에서 자동으로 팝업 컴포넌트 사용 가능

---

## 🎨 UI 디자인

### 조선시대 편지 스타일

```
┌─────────────────────────────┐
│         🧑 (왁스 씰)         │
│  ┌─────────────────────┐   │
│  │ 👦                   │   │
│  │                      │   │
│  │ 오빠 (남동생)로부터   │   │
│  │ 2025년 12월 11일      │   │
│  │ ───────────────────  │   │
│  │                      │   │
│  │ 축하해요! 3일 연속   │   │
│  │ 학습을 달성했어요!   │   │
│  │                      │   │
│  │ — 너의 학습 도우미 — │   │
│  └─────────────────────┘   │
│                             │
│   [다음에 보기] [확인!]     │
└─────────────────────────────┘
```

### 애니메이션

- 페이드 인 (0.3초)
- 슬라이드 업 (0.4초, elastic easing)
- 종이 질감 효과 (repeating gradient)

---

## 🧪 테스트 시나리오

### 1. 첫 사용자 테스트

```bash
# 1. 회원가입
# 2. 첫 발음 연습 완료
# 3. 예상: 오빠 캐릭터 "환영 메시지" 팝업 표시
```

### 2. 연속 학습 테스트

```bash
# 1. 3일 연속 로그인 및 학습
# 2. 3일째에 첫 연습 완료
# 3. 예상: 오빠 캐릭터 "3일 연속 학습" 팝업 표시
```

### 3. 높은 점수 테스트

```bash
# 1. 발음 연습 3회 이상
# 2. 평균 점수 85점 이상
# 3. 예상: 여동생 캐릭터 "칭찬 메시지" 팝업 표시
```

### 4. 낮은 점수 테스트

```bash
# 1. 발음 연습 3회 이상
# 2. 평균 점수 60점 미만
# 3. 예상: 호랑이 캐릭터 "독려 메시지" 팝업 표시
```

### 5. 장기 미접속 테스트

```bash
# 1. 3일 이상 로그인 안 함
# 2. 다시 로그인
# 3. 예상: 호랑이 캐릭터 "경고 메시지" 팝업 표시
```

### 6. 하루 1회 제한 테스트

```bash
# 1. 오늘 이미 팝업 1개 표시됨
# 2. 다른 조건 충족
# 3. 예상: 팝업 표시 안 됨 (하루 1회 제한)
```

---

## 📊 데이터베이스 쿼리 예시

### 팝업 히스토리 조회

```sql
-- 사용자별 팝업 히스토리
SELECT
    popup_type,
    character,
    message,
    trigger_reason,
    shown_at
FROM popup_history
WHERE user_id = 'user123'
ORDER BY shown_at DESC;

-- 오늘 팝업 표시 여부 확인
SELECT COUNT(*)
FROM popup_history
WHERE user_id = 'user123'
  AND DATE(shown_at) = DATE('now');

-- 캐릭터별 표시 횟수
SELECT
    character,
    COUNT(*) as count
FROM popup_history
WHERE user_id = 'user123'
GROUP BY character;
```

---

## 🔧 설정 및 커스터마이징

### 트리거 조건 수정

`backend/services/learning_progress_service.py` 파일의 `check_popup_trigger()` 메서드에서 조건 수정:

```python
# 예: 연속 학습일 조건 변경
if consecutive_days in [3, 7, 14, 30]:  # 기존
if consecutive_days in [5, 10, 15, 30]:  # 새로운 조건
```

### 메시지 수정

`_get_consecutive_message()` 메서드에서 메시지 수정:

```python
messages = {
    3: "새로운 메시지 작성",  # 수정
    7: "...",
}
```

### 캐릭터 이모지 변경

`templates/components/character-popup.html`의 `characterInfo` 객체 수정:

```javascript
const characterInfo = {
    oppa: {
        emoji: "👨",  // 변경
        name: "멘토",  // 변경
        style: "popup-oppa",
    },
    // ...
};
```

### 팝업 표시 시간 조절

`templates/components/character-popup.html` 하단:

```javascript
// 페이지 로드 후 팝업 확인 시간
setTimeout(checkPopupTrigger, 3000);  // 3초 (기본)
setTimeout(checkPopupTrigger, 5000);  // 5초로 변경
```

---

## 📈 향후 개선 사항

### 1. 다음에 보기 기능 구현
현재 `dismissCharacterPopup()` 함수는 팝업만 닫습니다.

**개선 방안**:
- localStorage에 "다음에 보기" 상태 저장
- 다음 로그인 시 다시 표시
- 사용자별 "다시 보지 않기" 옵션

### 2. 팝업 우선순위 동적 조정
현재는 하드코딩된 우선순위입니다.

**개선 방안**:
- 데이터베이스에 우선순위 저장
- 관리자 페이지에서 우선순위 조정
- A/B 테스트로 효과적인 순서 찾기

### 3. 캐릭터 추가
현재 3개 캐릭터만 있습니다.

**개선 방안**:
- 선생님 캐릭터 추가 (교육적 조언)
- 친구 캐릭터 추가 (동기부여)
- 사용자가 캐릭터 선택 가능

### 4. 메시지 개인화
현재는 고정 메시지입니다.

**개선 방안**:
- 사용자 이름 포함
- 학습 목표에 맞춘 메시지
- AI로 메시지 자동 생성 (Gemini/Ollama)

### 5. 통계 대시보드
현재는 팝업만 표시합니다.

**개선 방안**:
- 팝업 효과성 분석
- 사용자 참여도 측정
- 캐릭터별 선호도 분석

---

## 🐛 알려진 이슈 및 해결 방법

### Issue 1: 팝업이 표시되지 않음

**원인**:
- 사용자가 로그인하지 않음
- 오늘 이미 팝업 표시됨
- 트리거 조건 불충족

**해결**:
```javascript
// 브라우저 콘솔에서 확인
localStorage.getItem('session_token')  // 토큰 있는지 확인
```

### Issue 2: 팝업이 여러 번 표시됨

**원인**: 하루 1회 제한이 작동하지 않음

**해결**: 데이터베이스 확인
```sql
SELECT * FROM popup_history
WHERE user_id = 'user123'
  AND DATE(shown_at) = DATE('now');
```

### Issue 3: 잘못된 캐릭터 표시

**원인**: 백엔드 character 값이 프론트엔드와 불일치

**해결**: 백엔드 값 확인
```python
# backend/services/learning_progress_service.py
# 'oppa', 'tiger', 'sister' 일치 확인
```

---

## ✅ 구현 체크리스트

- [x] 백엔드 로직 구현
  - [x] `check_popup_trigger()` 메서드
  - [x] `record_popup_shown()` 메서드
  - [x] `_get_consecutive_message()` 메서드
  - [x] 7가지 트리거 조건 구현
  - [x] 하루 1회 제한 로직

- [x] API 엔드포인트
  - [x] `POST /api/learning/check-popup` (인증 추가)
  - [x] `POST /api/learning/popup-shown` (인증 추가)
  - [x] `POST /api/learning/pronunciation-completed` (기존 활용)

- [x] 프론트엔드 UI
  - [x] 조선시대 편지 스타일 디자인
  - [x] 캐릭터별 색상 테마
  - [x] 애니메이션 효과
  - [x] 종이 질감 효과

- [x] JavaScript 로직
  - [x] `checkPopupTrigger()` 함수
  - [x] `showCharacterPopup()` 함수
  - [x] `recordPopupShown()` 함수
  - [x] ESC 키로 닫기
  - [x] 자동 실행 (페이지 로드 3초 후)

- [x] 통합
  - [x] `base.html`에 컴포넌트 포함
  - [x] 모든 페이지에서 사용 가능

- [x] 문서화
  - [x] 구현 보고서 작성
  - [x] API 문서 작성
  - [x] 테스트 시나리오 작성

---

## 🎉 결론

캐릭터 팝업 시스템이 **100% 완료**되었습니다!

### 주요 성과

1. ✅ **차별화된 UX**: 조선시대 편지 스타일로 독특한 경험 제공
2. ✅ **지능형 트리거**: 7가지 학습 상황 자동 감지
3. ✅ **캐릭터 개성**: 3가지 역할로 다양한 피드백 제공
4. ✅ **사용자 친화적**: 하루 1회 제한으로 피로도 방지
5. ✅ **확장 가능**: 향후 AI 에이전트 통합 준비 완료

### 다음 단계

1. **실사용자 테스트**: 실제 사용자 피드백 수집
2. **메시지 최적화**: 효과적인 메시지 A/B 테스트
3. **AI 통합**: Gemini/Ollama로 메시지 자동 생성
4. **통계 분석**: 팝업 효과성 측정

---

**구현 완료 일시**: 2025년 12월 11일
**소요 시간**: 약 2시간
**코드 변경 사항**:
- 수정: 3개 파일 (learning_progress_service.py, character-popup.html, main.py)
- 추가: 0개 파일
- 통합: base.html에 컴포넌트 포함
