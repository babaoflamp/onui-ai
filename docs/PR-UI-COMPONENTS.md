# PR #1: 공통 UI 컴포넌트 표준화

## 개요
onui-ai 프로젝트의 UI/UX 일관성을 높이기 위해 공통 버튼, 로딩, 알림, 에러 메시지 컴포넌트를 표준화합니다.

## 변경 사항

### 1. 새로운 파일

#### `/static/css/components.css` (416줄)
공통 UI 컴포넌트 스타일 정의:
- **Button Styles** (`.btn`, `.btn-primary`, `.btn-secondary`, `.btn-danger`, `.btn-ghost`)
  - 기본 크기: md (12px padding, 16px font)
  - 크기 변형: sm, lg, xl
  - 상태: normal, hover, active, disabled
  - 반응형: 모바일 (640px 이하) 자동 조정

- **Loading Spinner** (`.loading-spinner`)
  - 크기: sm, md, lg
  - 애니메이션: 0.8초 무한 회전
  - `.loading-overlay`: 전체 화면 덮이기

- **Alert Messages** (`.alert`, `.alert-{type}`)
  - 타입: success (초록), error (빨강), warning (노랑), info (파랑)
  - 구조: 아이콘 + 제목 + 메시지 + 닫기 버튼
  - 접근성: focus states, ARIA labels 지원

- **Toast Notifications** (`.toast`, `.toast-{type}`)
  - 위치: 오른쪽 아래 고정
  - 애니메이션: slideIn (0.3s), slideOut (0.3s)
  - 자동 사라지기: 3초 후

#### `/static/js/ui-components.js` (419줄)
자바스크립트 유틸리티 라이브러리:

**LoadingManager**
```javascript
LoadingManager.show('처리 중...')        // 전체 오버레이 표시
LoadingManager.hide()                     // 오버레이 숨기기
LoadingManager.setButtonLoading(btn, '로딩 중...')  // 버튼에 스피너 추가
LoadingManager.clearButtonLoading(btn)   // 버튼 상태 복구
```

**AlertManager**
```javascript
AlertManager.success(message, title)  // 성공 메시지
AlertManager.error(message, title)    // 에러 메시지
AlertManager.warning(message, title)  // 경고 메시지
AlertManager.info(message, title)     // 정보 메시지
AlertManager.show(message, type, title, container)  // 사용자 정의
```

**ToastManager**
```javascript
ToastManager.success(message, duration)   // 성공 토스트 (3초)
ToastManager.error(message, duration)     // 에러 토스트
ToastManager.warning(message, duration)   // 경고 토스트
ToastManager.info(message, duration)      // 정보 토스트
ToastManager.show(message, type, duration) // 사용자 정의
```

**FormValidator**
```javascript
FormValidator.isValidEmail(email)               // 이메일 검증
FormValidator.isRequired(value)                 // 필수값 검증
FormValidator.minLength(value, length)         // 최소 길이
FormValidator.maxLength(value, length)         // 최대 길이
FormValidator.matches(value, regex)            // 정규식 검증
FormValidator.showFieldError(field, message)   // 필드 에러 표시
FormValidator.clearFieldError(field)           // 필드 에러 제거
```

**APIClient**
```javascript
await APIClient.get(url)                       // GET 요청
await APIClient.post(url, data)               // POST 요청
await APIClient.put(url, data)                // PUT 요청
await APIClient.delete(url)                   // DELETE 요청
// 자동 기능:
// - Authorization 헤더에 토큰 추가
// - 401 Unauthorized 처리 (자동 로그인 리다이렉트)
```

**유틸리티 함수**
```javascript
formatTime(ms)              // 밀리초를 HH:MM:SS로 변환
copyToClipboard(text)       // 클립보드 복사
formatDate(date)            // YYYY-MM-DD 형식
formatNumber(num)           // 1000 -> "1,000"
```

### 2. 수정된 파일

#### `/templates/base.html`
- CSS 포함: `<link rel="stylesheet" href="/static/css/components.css" />`
- JS 포함: `<script src="/static/js/ui-components.js"></script>`
- 모든 페이지에서 컴포넌트 자동으로 사용 가능

#### `/templates/login.html`
- 기존 `setStatus()` 함수 → `AlertManager.error()` + `FormValidator`로 변경
- 필드 검증 추가:
  - 닉네임 필수 확인
  - 비밀번호 필수 확인
- 에러 표시: 필드 아래 빨간 텍스트 + 상단 Alert 박스
- 성공: Toast 알림 (자동 3초 사라짐)
- 로딩: 버튼에 스피너 추가 + `LoadingManager.setButtonLoading()`

#### `/templates/signup.html`
- `alert()` 함수 → `AlertManager` + `FormValidator`로 변경
- 전체 검증 재구성:
  - 이름: 필수
  - 이메일: 필수 + 이메일 형식 검증
  - 닉네임: 필수
  - 비밀번호: 필수 + 8자 이상
  - 비밀번호 확인: 일치 여부 확인
- 에러 표시: 각 필드에 개별 에러 메시지
- 성공: Toast 알림 후 로그인 페이지로 리다이렉트

## 사용 예시

### 로그인 폼 (이미 적용됨)
```html
<!-- HTML -->
<input id="emailInput" type="email" />
<div id="alertsContainer"></div>

<!-- JavaScript -->
<script>
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    // 검증
    if (!FormValidator.isValidEmail(emailInput.value)) {
      FormValidator.showFieldError(emailInput, "유효한 이메일을 입력해주세요.");
      return;
    }
    
    // 로딩
    LoadingManager.setButtonLoading(submitBtn, "처리 중...");
    
    try {
      const result = await APIClient.post("/api/login", { email, password });
      LoadingManager.clearButtonLoading(submitBtn);
      ToastManager.success("로그인 성공!");
      window.location.href = "/dashboard";
    } catch (error) {
      LoadingManager.clearButtonLoading(submitBtn);
      AlertManager.error(error.message, "오류 발생", alertsContainer);
    }
  });
</script>
```

### 이미지 생성 페이지 (새로 적용)
```html
<button id="generateBtn" class="btn btn-primary">생성</button>

<script>
  generateBtn.addEventListener("click", async () => {
    LoadingManager.show("이미지 생성 중...");
    
    try {
      const data = await APIClient.post("/api/generate-image", { prompt });
      LoadingManager.hide();
      ToastManager.success("생성 완료!");
      displayImage(data.url);
    } catch (error) {
      LoadingManager.hide();
      AlertManager.error(error.message);
    }
  });
</script>
```

## 설계 원칙

### 1. 접근성 (Accessibility)
- ARIA labels 사용
- Focus states 명확함
- 색상 외 다른 표시 방법 사용

### 2. 반응형 (Responsive)
- 모바일 (< 640px): 자동으로 작은 크기
- 태블릿/데스크톱: 전체 크기 활용

### 3. 색상 일관성
- `--accent`: 주요 색상 (orange)
- `--text-main`: 주 텍스트 (gray-900)
- `--text-sub`: 보조 텍스트 (gray-600)
- 타입별 색상: success(green), error(red), warning(yellow), info(blue)

### 4. 성능
- CSS-only 애니메이션 (GPU 가속)
- JavaScript 번들 크기 최소화
- 자동 메모리 정리 (Alert 자동 제거)

## 다음 단계

### PR #2: 기존 페이지 적용
- dashboard.html: 출석 체크 에러 처리
- 발음 연습: LoadingManager로 로딩 상태 개선
- 이미지 생성: 진행률 표시

### PR #3: 추가 기능
- 폼 그룹 컴포넌트
- 진행 바 (Progress Bar)
- 모달 다이얼로그
- 탭/아코디언

## 테스트 체크리스트

- [x] 로그인 페이지 에러 표시
- [x] 회원가입 페이지 검증
- [ ] 대시보드 출석 체크 에러 처리
- [ ] 발음 연습 로딩 상태
- [ ] 이미지 생성 진행 상황
- [ ] 모바일 반응형 테스트
- [ ] 다크 모드 (향후)

## 마이그레이션 가이드

### 기존 코드
```javascript
alert("오류가 발생했습니다");
setStatus("처리 중...", true);
```

### 새 코드
```javascript
AlertManager.error("오류가 발생했습니다");
LoadingManager.setButtonLoading(button, "처리 중...");
```

## 파일 구조

```
static/
├── css/
│   └── components.css          (NEW) 공통 스타일
├── js/
│   └── ui-components.js        (NEW) 공통 유틸리티
└── ...

templates/
├── base.html                   (MODIFIED) 컴포넌트 포함
├── login.html                  (MODIFIED) 새 컴포넌트 적용
├── signup.html                 (MODIFIED) 새 컴포넌트 적용
└── ...
```

## 의존성
- Tailwind CSS v3 (이미 사용 중)
- 추가 라이브러리 없음

## 호환성
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+
