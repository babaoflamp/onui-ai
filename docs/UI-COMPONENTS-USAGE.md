# UI 컴포넌트 적용 현황

## PR #1 완료 항목

### 신규 파일 생성
- ✅ `/static/css/components.css` - 공통 스타일 (416줄)
- ✅ `/static/js/ui-components.js` - 공통 유틸리티 (419줄)

### 파일 수정
- ✅ `/templates/base.html` - 컴포넌트 CSS/JS 포함
- ✅ `/templates/login.html` - AlertManager + FormValidator 적용
- ✅ `/templates/signup.html` - AlertManager + FormValidator 적용

### 제공되는 API

#### 로딩 상태 관리
```javascript
// 전체 화면 오버레이 (스피너 + 메시지)
LoadingManager.show('처리 중...')
LoadingManager.hide()

// 버튼 로딩 상태
LoadingManager.setButtonLoading(button, '로딩 중...')
LoadingManager.clearButtonLoading(button)
```

#### 알림 메시지
```javascript
// 알림 박스 (상단에 표시, 닫기 버튼 포함)
AlertManager.success(message, title, container)
AlertManager.error(message, title, container)
AlertManager.warning(message, title, container)
AlertManager.info(message, title, container)

// 토스트 (우측 아래 자동 사라짐)
ToastManager.success(message, duration)
ToastManager.error(message, duration)
ToastManager.warning(message, duration)
ToastManager.info(message, duration)
```

#### 폼 검증
```javascript
// 검증
FormValidator.isRequired(value)
FormValidator.isValidEmail(email)
FormValidator.minLength(value, minLength)
FormValidator.maxLength(value, maxLength)
FormValidator.matches(value, regex)

// UI 업데이트
FormValidator.showFieldError(field, '에러 메시지')
FormValidator.clearFieldError(field)
```

#### API 호출
```javascript
// 자동 토큰 주입, 401 처리
const result = await APIClient.get(url)
const result = await APIClient.post(url, data)
const result = await APIClient.put(url, data)
const result = await APIClient.delete(url)
```

#### 유틸리티
```javascript
formatTime(ms)          // 5000 → "00:05"
copyToClipboard(text)   // 복사 + 토스트 표시
formatDate(date)        // "2025-01-15"
formatNumber(num)       // 1000 → "1,000"
```

## 현재 버전의 컴포넌트

### 버튼 (Button)
- `.btn` - 기본
- `.btn-primary` - 주요 (주황색)
- `.btn-secondary` - 보조 (회색)
- `.btn-danger` - 위험 (빨강)
- `.btn-ghost` - 유령 (테두리만)
- 크기: `.btn-sm`, `.btn-lg`, `.btn-xl`
- 상태: `:hover`, `:active`, `:disabled`

### 로딩 스피너 (Spinner)
- `.loading-spinner` - 인라인 (16px)
- `.loading-spinner.sm` - 작음 (12px)
- `.loading-spinner.lg` - 큼 (24px)
- `.loading-overlay` - 전체 화면 (고정 위치)
- 애니메이션: 0.8초 무한 회전

### 알림 박스 (Alert)
- `.alert` 기본 구조
- `.alert-success` - 녹색 (배경 + 왼쪽 보더)
- `.alert-error` - 빨강
- `.alert-warning` - 노랑
- `.alert-info` - 파랑
- 내부: `.alert-icon`, `.alert-title`, `.alert-message`, `.alert-close`

### 토스트 (Toast)
- `.toast` - 기본
- `.toast-success`, `.toast-error`, `.toast-warning`, `.toast-info`
- 위치: 고정 (오른쪽 아래, 모바일은 전체 너비)
- 애니메이션: slideIn (0.3s), slideOut (0.3s)

### 폼 필드 에러
- `.field-error` - 빨간색 텍스트 (에러 메시지)
- 필드: `.border-red-500`, `.focus:ring-red-500` 자동 추가

## 적용 예시

### login.html 예시
```html
<!-- HTML -->
<form id="loginForm">
  <input id="nicknameInput" type="text" />
  <input id="passwordInput" type="password" />
  <button id="loginBtn" type="submit" class="btn btn-primary">로그인</button>
</form>
<div id="alertsContainer"></div>

<!-- JavaScript -->
<script>
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    // 검증
    if (!FormValidator.isRequired(nicknameInput.value)) {
      FormValidator.showFieldError(nicknameInput, "닉네임은 필수입니다.");
      return;
    }
    
    // 로딩
    LoadingManager.setButtonLoading(loginBtn, "로그인 중...");
    
    try {
      const res = await APIClient.post("/api/login", {
        nickname: nicknameInput.value,
        password: passwordInput.value
      });
      
      LoadingManager.clearButtonLoading(loginBtn);
      ToastManager.success("환영합니다!");
      window.location.href = "/dashboard";
    } catch (err) {
      LoadingManager.clearButtonLoading(loginBtn);
      AlertManager.error(err.message, "로그인 실패", alertsContainer);
    }
  });
</script>
```

## 대기 중인 페이지

다음 PR에서 다음 페이지들이 새 컴포넌트를 적용받을 예정:

1. **대시보드 (dashboard.html)**
   - 출석 체크 에러 처리
   - 캘린더 로딩 상태

2. **발음 연습 (speechpro-practice.html)**
   - 녹음 로딩 오버레이
   - API 에러 처리

3. **이미지 생성 (content-generation.html, media-generation.html)**
   - 생성 중 로딩 (진행 바 추가?)
   - 생성 완료/실패 메시지

4. **문제 풀이 페이지들**
   - listening-dictation.html
   - fluency-test.html
   - initial-quiz.html
   - pronunciation-rules.html

5. **관리자 페이지들**
   - admin-dashboard.html
   - admin-learner-status.html
   - admin-recordings.html

## 마이그레이션 패턴

### 패턴 1: 간단한 에러 처리
```javascript
// 이전
try {
  const res = await fetch(url);
  if (!res.ok) throw new Error(res.status);
} catch (err) {
  alert("오류: " + err);
}

// 이후
try {
  const data = await APIClient.post(url, {});
} catch (err) {
  AlertManager.error(err.message);
}
```

### 패턴 2: 로딩 상태
```javascript
// 이전
button.disabled = true;
button.textContent = "처리 중...";

// 이후
LoadingManager.setButtonLoading(button, "처리 중...");
// ... 완료 후
LoadingManager.clearButtonLoading(button);
```

### 패턴 3: 폼 검증
```javascript
// 이전
if (email.length === 0) {
  alert("이메일을 입력해주세요");
  return;
}
if (!email.includes("@")) {
  alert("유효한 이메일을 입력해주세요");
  return;
}

// 이후
if (!FormValidator.isRequired(email)) {
  FormValidator.showFieldError(emailInput, "이메일을 입력해주세요");
  return;
}
if (!FormValidator.isValidEmail(email)) {
  FormValidator.showFieldError(emailInput, "유효한 이메일을 입력해주세요");
  return;
}
```

## 브라우저 호환성

| 브라우저 | 버전 | 지원 |
|---------|------|------|
| Chrome  | 90+  | ✅   |
| Firefox | 88+  | ✅   |
| Safari  | 14+  | ✅   |
| Edge    | 90+  | ✅   |
| IE 11   | -    | ❌   |

## CSS 커스터마이징

### 색상 변수 (components.css 상단)
```css
:root {
  --accent: #f97316;      /* 주요 색상 */
  --text-main: #111827;   /* 주 텍스트 */
  --text-sub: #4b5563;    /* 보조 텍스트 */
}
```

### 크기 변수
- 버튼: padding, font-size
- 스피너: width, height (내부 계산)
- 스페이싱: gap, padding (Tailwind 클래스 이용)

## 주의사항

1. **JavaScript 필수**: ui-components.js가 로드되어야 함
2. **CSS 필수**: components.css가 로드되어야 함 (Tailwind 이후)
3. **로컬스토리지 필요**: APIClient는 auth_token을 localStorage에서 읽음
4. **비동기 처리**: APIClient는 Promise를 반환함 (await 필수)

## 개발 속도

- 에러 메시지 통합: 30분
- 버튼 스타일 통합: 20분
- 로딩 상태 추가: 15분
- 전체 페이지 마이그레이션: 2-3시간
