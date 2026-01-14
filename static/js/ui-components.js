/**
 * 공통 UI 컴포넌트 JavaScript 유틸리티
 * 로딩, 알림, 에러 처리 등
 */

// ============================================
// 로딩 상태 관리
// ============================================

const LoadingManager = {
  /**
   * 전체 화면 로딩 오버레이 표시
   * @param {string} message - 표시할 메시지
   */
  show: function (message = "처리 중...") {
    let overlay = document.getElementById("global-loading-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "global-loading-overlay";
      overlay.className = "loading-overlay";
      overlay.innerHTML = `
        <div class="loading-overlay-content">
          <div class="loading-overlay-spinner"></div>
          <div class="loading-overlay-text">${message}</div>
        </div>
      `;
      document.body.appendChild(overlay);
    } else {
      overlay.querySelector(".loading-overlay-text").textContent = message;
      overlay.classList.remove("hidden");
    }
  },

  /**
   * 전체 화면 로딩 오버레이 숨기기
   */
  hide: function () {
    const overlay = document.getElementById("global-loading-overlay");
    if (overlay) {
      overlay.classList.add("hidden");
    }
  },

  /**
   * 버튼에 로딩 상태 표시
   * @param {HTMLElement} button - 대상 버튼 엘리먼트
   * @param {string} loadingText - 로딩 중 표시 텍스트
   */
  setButtonLoading: function (button, loadingText = "처리 중...") {
    button.disabled = true;
    button.dataset.originalText = button.textContent;
    button.innerHTML = `<span class="loading-spinner sm"></span> ${loadingText}`;
  },

  /**
   * 버튼 로딩 상태 해제
   * @param {HTMLElement} button - 대상 버튼 엘리먼트
   */
  clearButtonLoading: function (button) {
    button.disabled = false;
    if (button.dataset.originalText) {
      button.textContent = button.dataset.originalText;
    }
  },
};

// ============================================
// 알림 메시지 관리
// ============================================

const AlertManager = {
  /**
   * 알림 메시지 표시
   * @param {string} message - 메시지 텍스트
   * @param {string} type - 타입 (success, error, warning, info)
   * @param {string} title - 제목
   * @param {HTMLElement} container - 표시 위치 (기본값: body)
   */
  show: function (message, type = "info", title = "", container = null) {
    const typeIcons = {
      success: "✓",
      error: "✕",
      warning: "⚠",
      info: "ⓘ",
    };

    if (!container) {
      container = document.body;
    }

    const alert = document.createElement("div");
    alert.className = `alert alert-${type}`;
    alert.setAttribute("role", "alert");

    const closeBtn = document.createElement("button");
    closeBtn.className = "alert-close";
    closeBtn.textContent = "✕";
    closeBtn.onclick = () => alert.remove();

    alert.innerHTML = `
      <div class="alert-icon">${typeIcons[type] || typeIcons.info}</div>
      <div class="alert-content">
        ${title ? `<div class="alert-title">${title}</div>` : ""}
        <div class="alert-message">${message}</div>
      </div>
    `;
    alert.appendChild(closeBtn);

    container.insertBefore(alert, container.firstChild);

    return alert;
  },

  /**
   * 성공 메시지
   */
  success: function (message, title = "성공") {
    return this.show(message, "success", title);
  },

  /**
   * 에러 메시지
   */
  error: function (message, title = "오류") {
    return this.show(message, "error", title);
  },

  /**
   * 경고 메시지
   */
  warning: function (message, title = "경고") {
    return this.show(message, "warning", title);
  },

  /**
   * 정보 메시지
   */
  info: function (message, title = "알림") {
    return this.show(message, "info", title);
  },
};

// ============================================
// 토스트 알림 (Snackbar)
// ============================================

const ToastManager = {
  /**
   * 토스트 메시지 표시
   * @param {string} message - 메시지 텍스트
   * @param {string} type - 타입 (success, error, warning, info)
   * @param {number} duration - 표시 시간 (ms, 기본값: 3000)
   */
  show: function (message, type = "info", duration = 3000) {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("role", "status");
    toast.textContent = message;

    document.body.appendChild(toast);

    // 자동 숨기기
    setTimeout(() => {
      toast.classList.add("hide");
      setTimeout(() => toast.remove(), 300);
    }, duration);

    return toast;
  },

  /**
   * 성공 토스트
   */
  success: function (message, duration = 3000) {
    return this.show(message, "success", duration);
  },

  /**
   * 에러 토스트
   */
  error: function (message, duration = 3000) {
    return this.show(message, "error", duration);
  },

  /**
   * 경고 토스트
   */
  warning: function (message, duration = 3000) {
    return this.show(message, "warning", duration);
  },

  /**
   * 정보 토스트
   */
  info: function (message, duration = 3000) {
    return this.show(message, "info", duration);
  },
};

// ============================================
// 폼 검증 헬퍼
// ============================================

const FormValidator = {
  /**
   * 이메일 유효성 검사
   */
  isValidEmail: function (email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  },

  /**
   * 필수 필드 검사
   */
  isRequired: function (value) {
    return value && value.trim().length > 0;
  },

  /**
   * 최소 길이 검사
   */
  minLength: function (value, length) {
    return value && value.length >= length;
  },

  /**
   * 최대 길이 검사
   */
  maxLength: function (value, length) {
    return value && value.length <= length;
  },

  /**
   * 정규식 검사
   */
  matches: function (value, regex) {
    return regex.test(value);
  },

  /**
   * 필드에 에러 메시지 표시
   */
  showFieldError: function (field, message) {
    field.classList.add(
      "border-red-500",
      "focus:border-red-500",
      "focus:ring-red-500"
    );

    let errorEl = field.nextElementSibling;
    if (!errorEl || !errorEl.classList.contains("field-error")) {
      errorEl = document.createElement("div");
      errorEl.className = "field-error text-red-600 text-sm mt-1";
      field.parentNode.insertBefore(errorEl, field.nextSibling);
    }
    errorEl.textContent = message;
  },

  /**
   * 필드 에러 메시지 제거
   */
  clearFieldError: function (field) {
    field.classList.remove(
      "border-red-500",
      "focus:border-red-500",
      "focus:ring-red-500"
    );

    let errorEl = field.nextElementSibling;
    if (errorEl && errorEl.classList.contains("field-error")) {
      errorEl.remove();
    }
  },
};

// ============================================
// API 호출 헬퍼
// ============================================

const APIClient = {
  /**
   * GET 요청
   */
  get: async function (url, options = {}) {
    return this._request(url, { ...options, method: "GET" });
  },

  /**
   * POST 요청
   */
  post: async function (url, data, options = {}) {
    return this._request(url, {
      ...options,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      body: JSON.stringify(data),
    });
  },

  /**
   * PUT 요청
   */
  put: async function (url, data, options = {}) {
    return this._request(url, {
      ...options,
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      body: JSON.stringify(data),
    });
  },

  /**
   * DELETE 요청
   */
  delete: async function (url, options = {}) {
    return this._request(url, { ...options, method: "DELETE" });
  },

  /**
   * 내부: 실제 요청 수행
   */
  _request: async function (url, options = {}) {
    try {
      // 토큰 자동 추가
      const token = localStorage.getItem("auth_token");
      if (token && !options.headers) {
        options.headers = {};
      }
      if (token) {
        options.headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(url, options);

      // 401 Unauthorized: 로그인 필요
      if (response.status === 401) {
        localStorage.removeItem("auth_token");
        window.location.href = "/login";
        return null;
      }

      // 응답 파싱
      const contentType = response.headers.get("content-type");
      let data = null;

      if (contentType && contentType.includes("application/json")) {
        data = await response.json();
      } else {
        data = await response.text();
      }

      // 에러 처리
      if (!response.ok) {
        const error = new Error(data?.message || data?.error || "요청 실패");
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    } catch (error) {
      console.error("API 요청 오류:", error);
      throw error;
    }
  },
};

// ============================================
// 유틸리티 함수
// ============================================

/**
 * 밀리초를 HH:MM:SS 형식으로 변환
 */
function formatTime(ms) {
  const seconds = Math.floor((ms / 1000) % 60);
  const minutes = Math.floor((ms / (1000 * 60)) % 60);
  const hours = Math.floor((ms / (1000 * 60 * 60)) % 24);

  const pad = (num) => String(num).padStart(2, "0");

  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

/**
 * 텍스트 복사
 */
function copyToClipboard(text) {
  navigator.clipboard
    .writeText(text)
    .then(() => {
      ToastManager.success("복사되었습니다!");
    })
    .catch((err) => {
      ToastManager.error("복사에 실패했습니다.");
      console.error("Copy failed:", err);
    });
}

/**
 * 날짜 포매팅
 */
function formatDate(date) {
  if (typeof date === "string") {
    date = new Date(date);
  }

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

/**
 * 숫자 포매팅 (1000 -> "1,000")
 */
function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}
