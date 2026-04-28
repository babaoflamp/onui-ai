// 오늘의 표현 - Daily Expression Card Slider JavaScript

(function() {
  'use strict';

  let expressions = [];
  let currentIndex = 0;
  let currentAudio = null;

  const card = document.getElementById("expressionCard");
  const sentenceKrEl = document.getElementById("sentenceKr");
  const sentenceEnEl = document.getElementById("sentenceEn");
  const romanizedEl = document.getElementById("romanizedText");
  const cultureNoteEl = document.getElementById("cultureNote");
  const levelChipEl = document.getElementById("levelChip");
  const situationLabelEl = document.getElementById("situationLabel");
  const tagLabelEl = document.getElementById("tagLabel");
  const sliderCaptionEl = document.getElementById("sliderCaption");
  const dotsContainer = document.getElementById("dots");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const ttsBtn = document.getElementById("ttsBtn");
  const ttsIcon = document.getElementById("ttsIcon");
  const doneBtn = document.getElementById("doneBtn");
  const doneIcon = document.getElementById("doneIcon");
  const doneLbl = document.getElementById("doneLbl");

  const DONE_KEY = "expr_done_v1";
  function getDoneSet() {
    try { return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || "[]")); } catch { return new Set(); }
  }
  function saveDoneSet(s) {
    localStorage.setItem(DONE_KEY, JSON.stringify([...s]));
  }

  // 오늘 날짜 기반 시작 인덱스 (매일 다른 표현으로 시작)
  function getDailyStartIndex(total) {
    const now = new Date();
    const dayOfYear = Math.floor((now - new Date(now.getFullYear(), 0, 0)) / 86400000);
    return dayOfYear % total;
  }

  function showToast(msg, isError = false) {
    const t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = `position:fixed;bottom:24px;left:50%;transform:translateX(-50%);padding:10px 20px;border-radius:999px;font-size:13px;font-weight:700;color:#fff;background:${isError ? "rgba(239,68,68,0.9)" : "rgba(249,115,22,0.9)"};z-index:9999;pointer-events:none;opacity:1;transition:opacity 0.4s`;
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 400); }, 2500);
  }

  // Load expressions from API, pass current month so this month comes first
  async function loadExpressions() {
    try {
      const month = new Date().getMonth() + 1; // 1-12
      const response = await fetch(`/api/expressions?month=${month}`);
      const data = await response.json();
      expressions = data.expressions || [];

      if (expressions.length > 0) {
        currentIndex = getDailyStartIndex(expressions.length);
        createDots();
        renderCard();
      } else {
        card.innerHTML = '<p class="text-gray-500">No expression data found.</p>';
      }
    } catch (error) {
      console.error('Error loading expressions:', error);
      card.innerHTML = '<p class="text-red-500">Error loading data.</p>';
    }
  }

  // Create navigation dots
  function createDots() {
    dotsContainer.innerHTML = '';
    expressions.forEach((_, idx) => {
      const dot = document.createElement("div");
      dot.className = "dot";
      dot.dataset.index = idx;
      dot.addEventListener("click", () => {
        currentIndex = idx;
        renderCard();
      });
      dotsContainer.appendChild(dot);
    });
  }

  // Render current card
  function renderCard() {
    if (!expressions.length) return;
    stopTTS();

    const data = expressions[currentIndex];
    const lang = localStorage.getItem("app_lang") || "en";

    sentenceKrEl.textContent = data.sentenceKr;
    romanizedEl.textContent = data.romanized || '';
    sentenceEnEl.textContent = data.sentenceEn;

    if (lang === "ko") {
      cultureNoteEl.textContent = data.cultureNote;
      situationLabelEl.textContent = data.situation;
      tagLabelEl.textContent = data.tag;
    } else {
      cultureNoteEl.textContent = data.cultureNoteEn || data.cultureNote;
      situationLabelEl.textContent = data.situationEn || data.situation;
      tagLabelEl.textContent = data.tagEn || data.tag;
    }

    levelChipEl.textContent = "CEFR " + data.level;
    sliderCaptionEl.textContent = `${currentIndex + 1} / ${expressions.length}`;

    // Update dots
    document.querySelectorAll(".dot").forEach((d, idx) => {
      d.classList.toggle("active", idx === currentIndex);
    });

    // 완료 버튼 상태
    if (doneBtn) {
      const done = getDoneSet().has(String(currentIndex));
      doneIcon.textContent = done ? "✅" : "✓";
      doneLbl.textContent = done ? "Done!" : "Done";
      doneBtn.style.background = done ? "rgba(34,197,94,0.2)" : "rgba(255,255,255,0.05)";
      doneBtn.style.borderColor = done ? "rgba(34,197,94,0.4)" : "rgba(255,255,255,0.1)";
      doneBtn.style.color = done ? "#4ade80" : "rgba(255,255,255,0.4)";
    }
    // 완료된 dots에 초록 표시
    const doneSet = getDoneSet();
    document.querySelectorAll(".dot").forEach((d, idx) => {
      d.style.background = doneSet.has(String(idx)) ? "#4ade80" : "";
    });

    // Animation effect
    card.style.opacity = "0";
    card.style.transform = "translateY(8px)";
    card.style.transition = "opacity 0.25s ease, transform 0.25s ease";
    requestAnimationFrame(() => {
      setTimeout(() => {
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      }, 30);
    });
  }

  // ── IndexedDB TTS Cache ──────────────────────────────
  const DB_NAME = 'OnuiTTSCache';
  const STORE_NAME = 'audio_cache';
  const DB_VERSION = 1;

  async function getDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME);
        }
      };
      request.onsuccess = (e) => resolve(e.target.result);
      request.onerror = (e) => reject(e.target.error);
    });
  }

  async function getCachedAudio(text) {
    try {
      const db = await getDB();
      return new Promise((resolve) => {
        const transaction = db.transaction(STORE_NAME, 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        const request = store.get(text);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => resolve(null);
      });
    } catch { return null; }
  }

  async function saveAudioToCache(text, blob) {
    try {
      const db = await getDB();
      const transaction = db.transaction(STORE_NAME, 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      store.put(blob, text);
    } catch (e) { console.warn('Cache save failed:', e); }
  }

  // TTS
  async function playTTS(text) {
    if (!text) return;

    if (currentAudio && !currentAudio.paused) {
      stopTTS();
      return; // toggle off on second click
    }

    ttsBtn.disabled = true;
    ttsBtn.classList.add('playing');
    ttsIcon.textContent = '⏸';

    try {
      // 1. 로컬 캐시 확인
      let audioBlob = await getCachedAudio(text);
      let isFromCache = !!audioBlob;

      if (!audioBlob) {
        // 2. 캐시 없으면 서버 요청
        const resp = await fetch('/api/tts/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, language_code: 'ko' })
        });

        if (!resp.ok) throw new Error('TTS failed');
        audioBlob = await resp.blob();
        
        // 3. 서버 응답 로컬 캐시에 저장
        await saveAudioToCache(text, audioBlob);
      } else {
        console.log(`[TTS] Playing from local cache: "${text.substring(0, 15)}..."`);
      }

      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      currentAudio = audio;

      ttsBtn.disabled = false;

      audio.onended = () => {
        stopTTS();
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        stopTTS();
        URL.revokeObjectURL(url);
      };

      audio.play();
    } catch (err) {
      console.error('TTS error:', err);
      stopTTS();
      showToast('TTS 재생에 실패했습니다.', true);
    }
  }

  function stopTTS() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if (ttsBtn) {
      ttsBtn.disabled = false;
      ttsBtn.classList.remove('playing');
    }
    if (ttsIcon) ttsIcon.textContent = '🔊';
  }

  // TTS button click
  if (ttsBtn) {
    ttsBtn.addEventListener('click', () => {
      const text = expressions[currentIndex]?.sentenceKr;
      if (text) playTTS(text);
    });
  }

  // 완료 버튼
  if (doneBtn) {
    doneBtn.addEventListener('click', () => {
      const s = getDoneSet();
      const key = String(currentIndex);
      if (s.has(key)) { s.delete(key); } else { s.add(key); showToast('완료 표시했습니다! 👍'); }
      saveDoneSet(s);
      renderCard();
    });
  }

  // Navigation buttons
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      currentIndex = (currentIndex - 1 + expressions.length) % expressions.length;
      renderCard();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      currentIndex = (currentIndex + 1) % expressions.length;
      renderCard();
    });
  }

  // Keyboard navigation
  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft") prevBtn?.click();
    if (e.key === "ArrowRight") nextBtn?.click();
  });

  // Initialize
  loadExpressions();
})();
