  (function() {
    ["https://cdn.jsdelivr.net/npm/marked/marked.min.js","https://cdn.jsdelivr.net/npm/dompurify@2.4.0/dist/purify.min.js"].forEach(src => {
      const s = document.createElement("script"); s.src = src; s.async = true; document.head.appendChild(s);
    });
  })();

  function jsEsc(s) { return (s||"").toString().replace(/\\/g,"\\\\").replace(/'/g,"\\'").replace(/\"/g,'\\"').replace(/\n/g," "); }

  let isGenerating = false, abortController = null;
  let currentTopic = "", currentLevel = "중급";
  let currentDialogue = [], currentVocabulary = [];
  let currentImageUrl = null, currentAudio = null, isSpeaking = false;
  let coachHistory = [];
  let currentQuizQuestions = null, currentQuizKey = "";
  const actionDefaultCosts = {};

  function tr(key, fallback) {
    return translations[key] || fallback;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("`", "&#96;");
  }

  function getLessonKey(topic = currentTopic, level = currentLevel, dialogue = currentDialogue) {
    return JSON.stringify({
      topic: topic || "",
      level: level || "",
      dialogue: (dialogue || []).map(d => `${d?.speaker || ""}:${d?.text || ""}`)
    });
  }

  function resetQuizCache() {
    currentQuizQuestions = null;
    currentQuizKey = "";
  }

  function getDialogueVoiceProfile(speaker = "", index = 0) {
    const normalized = String(speaker || "").toLowerCase();
    const isMinjun = normalized.includes("민준") || normalized.includes("minjun") || normalized.includes("male");
    const isJisoo = normalized.includes("지수") || normalized.includes("jisoo") || normalized.includes("female");
    const maleTurn = isMinjun || (!isJisoo && index % 2 === 1);
    return maleTurn
      ? { speaker: 4, voice: "male", icon: "👨‍🎓", label: "민준" }
      : { speaker: 0, voice: "female", icon: "👩‍🎓", label: "지수" };
  }

  function renderDialogue(dialogue) {
    document.getElementById("dialogue-area").innerHTML = (dialogue || []).map((d, i) => {
      const text = d?.text || "";
      const voiceProfile = getDialogueVoiceProfile(d?.speaker, i);
      const speaker = d?.speaker || voiceProfile.label;
      const pronunciation = d?.pronunciation || "";
      return `
        <div class="dialogue-card" data-text="${escapeAttr(text)}" data-tts-speaker="${voiceProfile.speaker}" data-tts-voice="${escapeAttr(voiceProfile.voice)}">
          <div style="display:flex;align-items:flex-start;gap:8px;">
            <span style="font-size:18px;flex-shrink:0;">${voiceProfile.icon}</span>
            <div style="flex:1;">
              <div class="speaker">${escapeHtml(speaker)}</div>
              <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
                <button class="tts-btn" onclick="speakDialogueCard(this.closest('.dialogue-card'))">🔊</button>
                <span class="d-text">${escapeHtml(text)}</span>
              </div>
              ${pronunciation ? `<div class="d-pron">${escapeHtml(pronunciation)}</div>` : ""}
            </div>
          </div>
        </div>`;
    }).join("");
  }

  function renderVocabulary(vocabulary) {
    document.getElementById("vocab-area").innerHTML = `
      <div style="font-size:10px;font-weight:900;color:rgba(255,255,255,0.25);text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">${escapeHtml(translations["cg.vocab_header"] || "Vocabulary")}</div>
      ${(vocabulary || []).map(w => `<span class="vocab-tag">${escapeHtml(w)}</span>`).join("")}`;
  }

  function renderQuizQuestions(questions) {
    const qDiv = document.getElementById("quiz-questions");
    qDiv.innerHTML = (questions || []).map((q,i) => {
      const display = String(q.display || "");
      const parts = display.split("___");
      return `<div class="quiz-q">Q${i+1}. ${escapeHtml(parts[0])}<input class="quiz-blank" data-answer="${escapeAttr(q.blank_word || "")}" placeholder="  " />${escapeHtml(parts.slice(1).join("___") || "")}<div class="quiz-hint">💡 ${escapeHtml(q.hint || "")}</div></div>`;
    }).join("");
  }

  function setTopicError(message = "") {
    const input = document.getElementById("topic");
    const error = document.getElementById("topic-error");
    if (!input || !error) return;
    input.classList.toggle("is-invalid", Boolean(message));
    error.textContent = message;
  }

  function clearTopicError() {
    setTopicError("");
  }

  function renderResultStatus(type, title, message = "", retry = false) {
    document.getElementById("result-placeholder").style.display = "none";
    document.getElementById("result-content").style.display = "block";
    document.getElementById("scene-image-wrap").innerHTML = "";
    document.getElementById("scene-image-wrap").classList.add("hidden");
    document.getElementById("vocab-area").innerHTML = "";
    const icon = type === "loading" ? "⏳" : type === "error" ? "⚠️" : "⏹️";
    const retryButton = retry ? `<button class="status-retry-btn" onclick="generateContent()">${escapeHtml(tr("cg.retry", "다시 시도"))}</button>` : "";
    document.getElementById("dialogue-area").innerHTML = `
      <div class="result-status result-status-${escapeAttr(type)}">
        <div class="result-status-icon">${icon}</div>
        <div>
          <div class="result-status-title">${escapeHtml(title)}</div>
          ${message ? `<div class="result-status-message">${escapeHtml(message)}</div>` : ""}
          ${retryButton}
        </div>
      </div>`;
  }

  async function readJsonResponse(res) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || data.detail || data.error || `${tr("cg.err_prefix", "오류")} (${res.status})`);
    }
    return data;
  }

  function setButtonLoading(btnId, loading, loadingIcon = "⏳") {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    const icon = btn.querySelector(".ac-icon");
    if (loading) {
      if (!btn.dataset.defaultIcon && icon) btn.dataset.defaultIcon = icon.textContent;
      btn.disabled = true;
      btn.classList.add("is-loading");
      if (icon) icon.textContent = loadingIcon;
    } else {
      btn.disabled = false;
      btn.classList.remove("is-loading");
      if (icon && btn.dataset.defaultIcon) icon.textContent = btn.dataset.defaultIcon;
    }
  }

  // ── 생성 ────────────────────────────────────────────────────────
  function toggleGeneration() { isGenerating ? stopGeneration() : generateContent(); }

  function stopGeneration() {
    if (abortController) { abortController.abort(); abortController = null; }
    isGenerating = false; setBtnState(false);
    setActionBtnsEnabled(Boolean(currentDialogue.length));
    renderResultStatus("stopped", tr("cg.stopped_title", "생성이 중지되었습니다"), tr("cg.stopped_desc", "필요하면 같은 주제로 다시 생성할 수 있습니다."), true);
  }

  function setBtnState(on) {
    isGenerating = on;
    document.getElementById("gen-icon").textContent = on ? "⏹️" : "🪄";
    document.getElementById("gen-label").textContent = on ? (translations["cg.btn_stop"] || "중지") : (translations["cg.btn_generate"] || "생성");
    document.getElementById("gen-btn").className = "gen-btn" + (on ? " stop" : "");
  }

  async function generateContent() {
    currentTopic = document.getElementById("topic").value.trim();
    currentLevel = document.getElementById("level").value;
    if (!currentTopic) {
      setTopicError(tr("cg.topic_required", "레슨 주제를 입력해주세요."));
      document.getElementById("topic").focus();
      showToast(tr("cg.topic_required", "레슨 주제를 입력해주세요."));
      return;
    }
    clearTopicError();

    abortController = new AbortController();
    setBtnState(true);
    setActionBtnsEnabled(false);
    currentImageUrl = null;
    currentDialogue = []; currentVocabulary = [];
    resetQuizCache();
    hideLevelUp(); hideQuiz();

    renderResultStatus("loading", tr("cg.loading", "AI가 교재를 만들고 있어요..."), tr("cg.loading_desc", "잠시만 기다려주세요."));

    const fd = new FormData();
    fd.append("topic", currentTopic); fd.append("level", currentLevel);

    try {
      const res = await fetch("/api/generate-content", { method:"POST", body:fd, signal:abortController.signal });
      const data = await readJsonResponse(res);

      let obj = data;
      if (data.text) {
        try { const m = data.text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i); obj = JSON.parse(m ? m[1] : data.text); } catch(e) {}
      }

      if (!obj.dialogue) {
        renderResultStatus("error", tr("cg.err_parse_title", "교재 형식을 읽지 못했습니다"), tr("cg.err_parse_desc", "응답 형식이 예상과 달랐습니다. 다시 시도해주세요."), true);
        setBtnState(false); return;
      }

      currentDialogue = obj.dialogue;
      currentVocabulary = obj.vocabulary || [];

      renderDialogue(obj.dialogue);
      renderVocabulary(currentVocabulary);

      setBtnState(false);
      setActionBtnsEnabled(true);
      fetchCredits();
      loadSavedTextbooks();
    } catch(e) {
      if (e.name === "AbortError") return;
      renderResultStatus("error", tr("cg.err_generate_title", "교재 생성에 실패했습니다"), e.message, true);
      showToast(e.message);
      setActionBtnsEnabled(false);
      setBtnState(false);
    }
  }

  // ── TTS ─────────────────────────────────────────────────────────
  async function playTTS(text, options = {}) {
    if (!text) return;
    try {
      const payload = {
        text,
        speaker: Number.isFinite(options.speaker) ? options.speaker : 0,
        voice: options.voice || undefined,
        source: "content-generation"
      };
      const res = await fetch("/api/tts/generate", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload) });
      if (!res.ok) {
        let message = `TTS failed (${res.status})`;
        try {
          const data = await res.json();
          message = data?.details || data?.message || data?.error || message;
        } catch (_) {}
        throw new Error(message);
      }
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      currentAudio = audio; await audio.play();
      return new Promise(r => { audio.onended = r; audio.onerror = r; });
    } catch(e) {
      console.error(e);
      showToast(e.message || "TTS playback failed.");
      throw e;
    }
  }

  function speakDialogueCard(card) {
    if (!card) return;
    if(currentAudio) currentAudio.pause();
    playTTS(card.dataset.text, {
      speaker: Number(card.dataset.ttsSpeaker || 0),
      voice: card.dataset.ttsVoice || undefined
    }).catch(() => {});
  }

  function speakText(txt) { if(currentAudio) currentAudio.pause(); playTTS(txt); }

  async function speakDialogue() {
    if (isSpeaking) {
      isSpeaking = false;
      if(currentAudio) currentAudio.pause();
      const icon = document.getElementById("btn-listen").querySelector(".ac-icon");
      if (icon) icon.textContent = "🔊";
      return;
    }
    if (!currentDialogue.length) { showToast(translations["cg.err_gen_first"] || "먼저 레슨을 생성해주세요."); return; }
    isSpeaking = true;
    const listenBtn = document.getElementById("btn-listen");
    const icon = listenBtn.querySelector(".ac-icon");
    if (icon) icon.textContent = "⏸️";

    const cards = [...document.querySelectorAll(".dialogue-card")];
    for (let i = 0; i < cards.length; i++) {
      if (!isSpeaking) break;
      cards.forEach(c => c.classList.remove("playing"));
      cards[i].classList.add("playing");
      cards[i].scrollIntoView({ behavior:"smooth", block:"nearest" });
      try {
        await playTTS(cards[i].dataset.text, {
          speaker: Number(cards[i].dataset.ttsSpeaker || 0),
          voice: cards[i].dataset.ttsVoice || undefined
        });
      } catch (_) {
        break;
      }
    }
    cards.forEach(c => c.classList.remove("playing"));
    isSpeaking = false;
    if (icon) icon.textContent = "🔊";
    showLevelUp();
  }

  // ── 레벨업 ──────────────────────────────────────────────────────
  function showLevelUp() {
    const b = document.getElementById("levelup-banner");
    const harder = document.getElementById("btn-harder");
    b.classList.add("show");
    harder.style.display = currentLevel === "고급" ? "none" : "";
  }
  function hideLevelUp() { document.getElementById("levelup-banner").classList.remove("show"); }
  function levelUpHarder() {
    const lvls = ["초급","중급","고급"];
    document.getElementById("level").value = lvls[Math.min(lvls.indexOf(currentLevel)+1, 2)];
    hideLevelUp(); generateContent();
  }
  function newTopic() { document.getElementById("topic").value = ""; document.getElementById("topic").focus(); hideLevelUp(); }

  // ── 이미지 생성 ─────────────────────────────────────────────────
  async function generateSceneImage() {
    if (!currentTopic) {
      showToast(translations["cg.err_gen_first"] || "먼저 레슨을 생성해주세요.");
      return;
    }
    const btn = document.getElementById("btn-image");
    const styleSelect = document.getElementById("image-style");
    const selectedStyle = styleSelect ? styleSelect.value : "illustration";
    const icon = btn.querySelector(".ac-icon");
    
    const wrap = document.getElementById("scene-image-wrap");
    setButtonLoading("btn-image", true);
    wrap.innerHTML = `<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:32px 0;"><div style="width:32px;height:32px;border-radius:50%;border:3px solid rgba(249,115,22,0.3);border-top-color:#f97316;animation:spin 0.8s linear infinite;"></div><span style="color:rgba(255,255,255,0.35);font-size:12px;font-weight:700;">${translations["cg.btn_image"] || "이미지 생성"} ...</span></div>`;
    wrap.classList.remove("hidden");
    try {
      const res = await fetch("/api/generate-image", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({situation:currentTopic, style:selectedStyle}) });
      const data = await readJsonResponse(res);
      if (data.success && data.image_url) {
        currentImageUrl = data.image_url;
        wrap.innerHTML = `<img src="${escapeAttr(data.image_url)}" alt="scene" />`;
        if (icon) icon.textContent = "🖼️";
        fetchCredits();
      } else {
        wrap.classList.add("hidden");
        showToast(data.message || translations["cg.err_image_failed"] || "이미지 생성에 실패했습니다.");
      }
    } catch(e) {
      wrap.classList.add("hidden");
      showToast(e.message || translations["cg.err_image_error"] || "이미지 생성 중 오류가 발생했습니다.");
    } finally {
      setButtonLoading("btn-image", false);
    }
  }

  function showToast(msg) {
    const t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:rgba(30,30,30,0.95);color:#fff;padding:10px 20px;border-radius:12px;font-size:13px;font-weight:700;z-index:9999;border:1px solid rgba(255,255,255,0.1);pointer-events:none;";
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3000);
  }

  // ── 퀴즈 ────────────────────────────────────────────────────────
  function toggleQuiz() {
    const wrap = document.getElementById("quiz-wrap");
    const isOpen = wrap.classList.contains("open");
    if (isOpen) { wrap.classList.remove("open"); return; }
    wrap.classList.add("open");
    if (!currentDialogue.length) { document.getElementById("quiz-questions").innerHTML = `<p style="color:rgba(255,255,255,0.3);font-size:12px;">${translations["cg.err_quiz_first"] || "먼저 교재를 생성해주세요."}</p>`; return; }
    if (currentQuizQuestions && currentQuizKey === getLessonKey()) {
      document.getElementById("quiz-score").style.display = "none";
      renderQuizQuestions(currentQuizQuestions);
      return;
    }
    loadQuiz();
  }
  function hideQuiz() { document.getElementById("quiz-wrap").classList.remove("open"); }

  async function loadQuiz() {
    const qDiv = document.getElementById("quiz-questions");
    document.getElementById("quiz-score").style.display = "none";
    qDiv.innerHTML = `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;color:rgba(255,255,255,0.3);font-size:12px;"><div style="width:16px;height:16px;border-radius:50%;border:2px solid #f97316;border-top-color:transparent;animation:spin 0.8s linear infinite;"></div>${translations["cg.quiz_loading"] || "퀴즈 생성 중..."}</div>`;
    setButtonLoading("btn-quiz", true);
    try {
      const res = await fetch("/api/textbook/quiz", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({dialogue:currentDialogue}) });
      const data = await readJsonResponse(res);
      fetchCredits();
      const qs = data.questions || [];
      if (!qs.length) { qDiv.innerHTML = `<p style="color:rgba(255,255,255,0.3);font-size:12px;">${translations["cg.err_quiz_failed"] || "퀴즈를 생성하지 못했습니다."}</p>`; return; }
      currentQuizQuestions = qs;
      currentQuizKey = getLessonKey();
      renderQuizQuestions(qs);
    } catch(e) {
      qDiv.innerHTML = `<p style="color:#f87171;font-size:12px;">${escapeHtml(e.message)}</p>`;
      showToast(e.message);
    } finally {
      setButtonLoading("btn-quiz", false);
    }
  }

  function checkAnswers() {
    let correct = 0;
    document.querySelectorAll(".quiz-blank").forEach(b => {
      b.classList.remove("correct","wrong");
      if (b.value.trim() === b.dataset.answer.trim()) { b.classList.add("correct"); correct++; }
      else { b.classList.add("wrong"); b.setAttribute("placeholder", b.dataset.answer); }
    });
    const total = document.querySelectorAll(".quiz-blank").length;
    const sc = document.getElementById("quiz-score");
    sc.style.display = "block";
    sc.innerHTML = `${correct===total?"🎉":correct>=total/2?"👍":"💪"} <span style="color:#f97316;">${correct}</span>/${total} ${translations["cg.quiz_correct_label"] || "정답"}`;
  }

  function renderLessonPackage(pkg) {
    const panel = document.getElementById("lesson-package-panel");
    if (!panel || !pkg) return;
    const expressions = (pkg.key_expressions || []).slice(0, 4).map((item) => {
      if (typeof item === "string") return `<li>${escapeHtml(item)}</li>`;
      const korean = item.korean || item.expression || item.text || "";
      const meaning = item.meaning || item.translation || item.note || "";
      return `<li><strong>${escapeHtml(korean)}</strong>${meaning ? ` <span style="color:rgba(255,255,255,0.42);">${escapeHtml(meaning)}</span>` : ""}</li>`;
    }).join("");
    const quiz = (pkg.quiz || []).slice(0, 2).map((q, i) => `<li>Q${i + 1}. ${escapeHtml(q.question || q)}</li>`).join("");
    const homework = Array.isArray(pkg.homework) ? pkg.homework.join(" · ") : (pkg.homework || "");
    panel.style.display = "block";
    panel.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px;">
        <strong style="color:#5eead4;font-size:13px;">${escapeHtml(pkg.title || "AI 수업 패키지")}</strong>
        <span style="color:rgba(255,255,255,0.34);font-size:11px;">${escapeHtml(pkg.level || currentLevel)}</span>
      </div>
      <div style="font-weight:800;color:rgba(255,255,255,0.55);margin-bottom:4px;">핵심 표현</div>
      <ul style="margin:0 0 8px 16px;padding:0;">${expressions || "<li>표현 없음</li>"}</ul>
      <div style="font-weight:800;color:rgba(255,255,255,0.55);margin-bottom:4px;">퀴즈</div>
      <ul style="margin:0 0 8px 16px;padding:0;">${quiz || "<li>퀴즈 없음</li>"}</ul>
      ${homework ? `<div style="color:rgba(255,255,255,0.48);"><strong>숙제:</strong> ${escapeHtml(homework)}</div>` : ""}
      <div style="margin-top:8px;color:rgba(255,255,255,0.3);font-size:11px;">AI 생성 수업안은 교사가 검토한 뒤 사용하는 것을 권장합니다.</div>`;
  }

  async function generateLessonPackage() {
    currentTopic = document.getElementById("topic").value.trim();
    currentLevel = document.getElementById("level").value;
    if (!currentTopic) {
      setTopicError(tr("cg.topic_required", "레슨 주제를 입력해주세요."));
      document.getElementById("topic").focus();
      showToast(tr("cg.topic_required", "레슨 주제를 입력해주세요."));
      return;
    }
    clearTopicError();
    setButtonLoading("btn-package", true, "⏳");
    const panel = document.getElementById("lesson-package-panel");
    if (panel) {
      panel.style.display = "block";
      panel.innerHTML = `<div style="display:flex;align-items:center;gap:8px;color:rgba(255,255,255,0.5);"><span style="width:14px;height:14px;border-radius:50%;border:2px solid #2dd4bf;border-top-color:transparent;animation:spin 0.8s linear infinite;"></span>수업 패키지를 생성하는 중...</div>`;
    }
    try {
      const res = await fetch("/api/lesson-packages/generate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({topic: currentTopic, level: currentLevel, use_ai: true})
      });
      const data = await readJsonResponse(res);
      renderLessonPackage(data.package);
      fetchCredits();
      showToast("수업 패키지를 생성했습니다.");
    } catch(e) {
      if (panel) panel.innerHTML = `<span style="color:#f87171;">${escapeHtml(e.message)}</span>`;
      showToast(e.message);
    } finally {
      setButtonLoading("btn-package", false);
    }
  }

  // ── 저장 및 서버 연동 ───────────────────────────────────────────
  let fetchedTextbooks = [];

  async function saveTextbook() {
    if (!currentDialogue.length) { showToast(translations["cg.err_gen_first"] || "먼저 레슨을 생성해주세요."); return; }
    
    const btn = document.getElementById("btn-save");
    const icon = btn.querySelector(".ac-icon");
    setButtonLoading("btn-save", true);

    try {
      const res = await fetch("/api/textbooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: currentTopic,
          level: currentLevel,
          dialogue: currentDialogue,
          vocabulary: currentVocabulary,
          imageUrl: currentImageUrl
        })
      });
      const data = await readJsonResponse(res);
      if (data.success) {
        if (icon) icon.textContent = "✅";
        loadSavedTextbooks(); // 목록 새로고침
        showToast(tr("cg.save_success", "교재를 저장했습니다."));
      } else {
        throw new Error(data.message || "저장 실패");
      }
    } catch(e) {
      if (icon) icon.textContent = "❌";
      showToast("서버 저장 실패: " + e.message);
    } finally {
      setTimeout(() => setButtonLoading("btn-save", false), 900);
    }
  }

  async function deleteSaved(id) {
    if (!confirm("이 교재를 정말 삭제할까요?")) return;
    try {
      const res = await fetch(`/api/textbooks/${id}`, { method: "DELETE" });
      const data = await res.json();
      if (data.success) loadSavedTextbooks();
      else showToast("삭제 실패: " + data.message);
    } catch(e) { showToast("삭제 중 오류 발생"); }
  }

  function restoreSaved(id) {
    const entry = fetchedTextbooks.find(s => s.id === id);
    if (!entry) return;
    
    document.getElementById("topic").value = entry.topic;
    document.getElementById("level").value = entry.level;
    currentTopic = entry.topic; currentLevel = entry.level;
    currentDialogue = entry.dialogue; currentVocabulary = entry.vocabulary || []; currentImageUrl = entry.imageUrl || null;
    resetQuizCache();
    hideLevelUp(); hideQuiz();

    document.getElementById("result-placeholder").style.display = "none";
    document.getElementById("result-content").style.display = "block";

    const wrap = document.getElementById("scene-image-wrap");
    if (entry.imageUrl) {
      wrap.innerHTML = `<img src="${escapeAttr(entry.imageUrl)}" alt="scene" />`;
      wrap.classList.remove("hidden");
    } else {
      wrap.innerHTML = ""; wrap.classList.add("hidden");
    }

    renderDialogue(entry.dialogue);
    renderVocabulary(entry.vocabulary || []);

    setActionBtnsEnabled(true);
    showToast("교재를 불러왔습니다.");
  }

  function toggleSavedList() {
    const wrap = document.getElementById("saved-list-wrap");
    const chevron = document.getElementById("saved-chevron");
    const isOpen = wrap.classList.contains("open");
    wrap.classList.toggle("open");
    chevron.textContent = isOpen ? "▲" : "▼";
  }

  async function loadSavedTextbooks() {
    try {
      const res = await fetch("/api/textbooks");
      const data = await res.json();
      if (!data.success) return;
      
      const saved = data.textbooks || [];
      fetchedTextbooks = saved;
      
      const toggleRow = document.getElementById("saved-toggle-row");
      if (!saved.length) { toggleRow.style.display = "none"; return; }
      toggleRow.style.display = "flex";
      document.getElementById("saved-count").textContent = `(${saved.length})`;
      
      const lv = {"초급":"🟢","중급":"🟡","고급":"🔴"};
      const lvLabel = {
        "초급": translations["cg.level_beginner"] || "초급",
        "중급": translations["cg.level_intermediate"] || "중급",
        "고급": translations["cg.level_advanced"] || "고급",
      };
      const lang = localStorage.getItem("app_lang") || "ko";
      
      document.getElementById("saved-list").innerHTML = saved.map(s => {
        const date = new Date(s.savedAt).toLocaleDateString(lang === "ko" ? "ko-KR" : lang, {month:"short",day:"numeric"});
        return `<div class="saved-item">
          <div class="saved-item-img">${s.imageUrl?`<img src="${escapeAttr(s.imageUrl)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;">`:"📖"}</div>
          <div class="saved-item-info"><div class="saved-item-topic">${escapeHtml(s.topic)}</div><div class="saved-item-meta">${escapeHtml(lv[s.level]||"")} ${escapeHtml(lvLabel[s.level]||s.level)} · ${escapeHtml(date)}</div></div>
          <button class="saved-load-btn" onclick="restoreSaved(${s.id})">${translations["cg.btn_load"] || "불러오기"}</button>
          <button class="saved-del-btn" onclick="deleteSaved(${s.id})">×</button>
        </div>`;
      }).join("");
    } catch(e) { console.error("Load textbooks failed", e); }
  }

  // ── AI 코치 ─────────────────────────────────────────────────────
  function appendBubble(role, html) {
    const msgs = document.getElementById("coach-messages");
    const div = document.createElement("div");
    if (role === "user") {
      div.className = "coach-bubble-user";
      div.innerHTML = `<div class="bubble-user-text">${escapeHtml(html)}</div>`;
    } else {
      div.className = "coach-bubble-ai";
      div.innerHTML = `<span style="font-size:18px;flex-shrink:0;">🤖</span><div class="bubble-ai-text">${html}</div>`;
    }
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
  }

  async function sendCoach() {
    const input = document.getElementById("coach-input");
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = "";
    appendBubble("user", prompt);
    coachHistory.push({role:"user", content:prompt});
    const typing = document.createElement("div");
    typing.className = "coach-bubble-ai"; typing.id = "coach-typing";
    typing.innerHTML = `<span style="font-size:20px;">🤖</span><div class="bubble-ai-text" style="color:rgba(255,255,255,0.3);">${translations["cg.coach_thinking"] || "생각중..."}</div>`;
    document.getElementById("coach-messages").appendChild(typing);
    document.getElementById("coach-messages").scrollTop = 9999;
    const ctx = currentDialogue.map(d=>d.text).join("\n");
    try {
      const res = await fetch("/api/chat/test", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({prompt, history:coachHistory.slice(-10), system_context:ctx}) });
      const data = await readJsonResponse(res);
      document.getElementById("coach-typing")?.remove();
      const reply = data.text || JSON.stringify(data);
      const safe = window.marked && window.DOMPurify ? DOMPurify.sanitize(marked.parse(reply)) : escapeHtml(reply);
      appendBubble("assistant", safe);
      coachHistory.push({role:"assistant", content:reply});
      fetchCredits();
    } catch(e) {
      document.getElementById("coach-typing")?.remove();
      appendBubble("assistant", (translations["cg.err_prefix"] || "오류") + ": " + e.message);
    }
  }

  // ── spin 애니메이션 ─────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
  document.head.appendChild(style);

  // ── 크레딧 ─────────────────────────────────────────────────────
  async function fetchCredits() {
    const token = localStorage.getItem("auth_token");
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    try {
      const res = await fetch("/api/credits", { headers });
      const data = await res.json();
      if (data.success) updateCreditBar(data.remaining, data.daily_limit);
      else setCreditUnavailable();
    } catch(e) {
      setCreditUnavailable();
    }
  }

  function setCreditUnavailable() {
    const remainingEl = document.getElementById("credit-remaining");
    const totalEl = document.getElementById("credit-total");
    const fill = document.getElementById("credit-bar-fill");
    if (remainingEl) remainingEl.textContent = "—";
    if (totalEl) totalEl.textContent = "—";
    if (fill) {
      fill.style.width = "0%";
      fill.className = "h-full rounded-full transition-all duration-500 bg-white/20";
    }
  }

  function updateCreditBar(remaining, total) {
    const el = document.getElementById("credit-remaining");
    const fill = document.getElementById("credit-bar-fill");
    const totalEl = document.getElementById("credit-total");
    if (!el) return;
    const safeRemaining = Number(remaining);
    const safeTotal = Number(total);
    if (!Number.isFinite(safeRemaining) || !Number.isFinite(safeTotal) || safeTotal <= 0) {
      setCreditUnavailable();
      return;
    }
    el.textContent = safeRemaining;
    if (totalEl) totalEl.textContent = safeTotal;
    const pct = Math.max(0, Math.min(100, (safeRemaining / safeTotal) * 100));
    if (fill) {
      fill.style.width = pct + "%";
      const color = pct > 50 ? "bg-orange-500" : pct > 20 ? "bg-yellow-500" : "bg-red-500";
      fill.className = "h-full rounded-full transition-all duration-500 " + color;
    }
  }

  function setActionBtnsEnabled(enabled) {
    ["btn-listen","btn-image","btn-quiz","btn-save"].forEach(id => {
      const btn = document.getElementById(id);
      if (!btn) return;
      const cost = btn.querySelector(".ac-cost");
      if (cost && !actionDefaultCosts[id]) actionDefaultCosts[id] = cost.textContent;
      btn.disabled = !enabled;
      btn.style.opacity = enabled ? "1" : "0.4";
      btn.style.pointerEvents = enabled ? "" : "none";
      btn.title = enabled ? "" : tr("cg.action_disabled", "먼저 레슨을 생성하세요.");
      if (cost) cost.textContent = enabled ? actionDefaultCosts[id] : tr("cg.action_disabled_short", "레슨 생성 후 사용");
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("topic")?.addEventListener("input", clearTopicError);
    loadSavedTextbooks();
    fetchCredits();
    setActionBtnsEnabled(false);
  });
