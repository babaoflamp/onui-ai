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

  // ── 생성 ────────────────────────────────────────────────────────
  function toggleGeneration() { isGenerating ? stopGeneration() : generateContent(); }

  function stopGeneration() {
    if (abortController) { abortController.abort(); abortController = null; }
    isGenerating = false; setBtnState(false);
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
    if (!currentTopic) return;

    abortController = new AbortController();
    setBtnState(true);
    currentImageUrl = null;
    currentDialogue = []; currentVocabulary = [];
    hideLevelUp(); hideQuiz();

    document.getElementById("result-placeholder").style.display = "none";
    document.getElementById("result-content").style.display = "block";
    document.getElementById("scene-image-wrap").innerHTML = "";
    document.getElementById("scene-image-wrap").classList.add("hidden");
    document.getElementById("dialogue-area").innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:40px 0;justify-content:center;"><div style="width:24px;height:24px;border-radius:50%;border:2px solid #f97316;border-top-color:transparent;animation:spin 0.8s linear infinite;"></div><span style="color:rgba(255,255,255,0.4);font-size:13px;font-weight:700;">${translations["cg.loading"] || "AI가 교재를 만들고 있어요..."}</span></div>`;
    document.getElementById("vocab-area").innerHTML = "";

    const fd = new FormData();
    fd.append("topic", currentTopic); fd.append("level", currentLevel);
    fd.append("backend", "ollama"); fd.append("model", "exaone3.5:2.4b");

    try {
      const res = await fetch("/api/generate-content", { method:"POST", body:fd, signal:abortController.signal });
      const data = await res.json();

      let obj = data;
      if (data.text) {
        try { const m = data.text.match(/```(?:json)?\s*([\s\S]*?)\s*```/i); obj = JSON.parse(m ? m[1] : data.text); } catch(e) {}
      }

      if (!obj.dialogue) {
        document.getElementById("dialogue-area").innerHTML = `<pre style="font-size:11px;color:#f97316;padding:12px;">${translations["cg.err_prefix"] || "Error"}: ${JSON.stringify(data,null,2)}</pre>`;
        setBtnState(false); return;
      }

      currentDialogue = obj.dialogue;
      currentVocabulary = obj.vocabulary || [];

      // 대화 렌더링
      document.getElementById("dialogue-area").innerHTML = obj.dialogue.map((d, i) => `
        <div class="dialogue-card" data-text='${jsEsc(d.text)}'>
          <div style="display:flex;align-items:flex-start;gap:8px;">
            <span style="font-size:18px;flex-shrink:0;">${i%2===0?"👨‍🎓":"👩‍🏫"}</span>
            <div style="flex:1;">
              <div class="speaker">${d.speaker || (i%2===0 ? (translations["cg.speaker_student"] || "Student") : (translations["cg.speaker_teacher"] || "Teacher"))}</div>
              <div style="display:flex;align-items:center;gap:6px;margin-top:2px;">
                <button class="tts-btn" onclick="speakText('${jsEsc(d.text)}')">🔊</button>
                <span class="d-text">${d.text}</span>
              </div>
              ${d.pronunciation ? `<div class="d-pron">${d.pronunciation}</div>` : ""}
            </div>
          </div>
        </div>`).join("");

      // 어휘 렌더링
      document.getElementById("vocab-area").innerHTML = `
        <div style="font-size:10px;font-weight:900;color:rgba(255,255,255,0.25);text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;">${translations["cg.vocab_header"] || "Vocabulary"}</div>
        ${currentVocabulary.map(w=>`<span class="vocab-tag">${w}</span>`).join("")}`;

      setBtnState(false);
      loadSavedTextbooks();
    } catch(e) {
      if (e.name !== "AbortError") {
        document.getElementById("dialogue-area").innerHTML = `<div style="color:#f87171;font-size:13px;padding:12px;">${translations["cg.err_prefix"] || "오류"}: ${e.message}</div>`;
        setBtnState(false);
      }
    }
  }

  // ── TTS ─────────────────────────────────────────────────────────
  async function playTTS(text) {
    if (!text) return;
    try {
      const res = await fetch("/api/tts/generate", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({text, speaker:0}) });
      const blob = await res.blob();
      const audio = new Audio(URL.createObjectURL(blob));
      currentAudio = audio; await audio.play();
      return new Promise(r => { audio.onended = r; audio.onerror = r; });
    } catch(e) { console.error(e); }
  }

  function speakText(txt) { if(currentAudio) currentAudio.pause(); playTTS(txt); }

  async function speakDialogue() {
    if (isSpeaking) { isSpeaking = false; if(currentAudio) currentAudio.pause(); document.getElementById("btn-listen").querySelector("span:first-child").textContent="🔊"; return; }
    if (!currentDialogue.length) { showToast(translations["cg.err_gen_first"] || "먼저 레슨을 생성해주세요."); return; }
    isSpeaking = true;
    document.getElementById("btn-listen").querySelector("span:first-child").textContent="⏸️";
    const cards = [...document.querySelectorAll(".dialogue-card")];
    for (let i = 0; i < cards.length; i++) {
      if (!isSpeaking) break;
      cards.forEach(c => c.classList.remove("playing"));
      cards[i].classList.add("playing");
      cards[i].scrollIntoView({ behavior:"smooth", block:"nearest" });
      await playTTS(cards[i].dataset.text);
    }
    cards.forEach(c => c.classList.remove("playing"));
    isSpeaking = false;
    document.getElementById("btn-listen").querySelector("span:first-child").textContent="🔊";
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
    btn.disabled = true;
    btn.querySelector("span:first-child").textContent = "⏳";
    try {
      const res = await fetch("/api/generate-image", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({situation:currentTopic, style:"illustration"}) });
      const data = await res.json();
      if (data.success && data.image_url) {
        currentImageUrl = data.image_url;
        const wrap = document.getElementById("scene-image-wrap");
        wrap.innerHTML = `<img src="${data.image_url}" alt="scene" />`;
        wrap.classList.remove("hidden");
        btn.querySelector("span:first-child").textContent = "🖼️";
      } else {
        btn.querySelector("span:first-child").textContent = "❌";
        showToast(data.message || translations["cg.err_image_failed"] || "이미지 생성에 실패했습니다.");
      }
    } catch(e) {
      btn.querySelector("span:first-child").textContent = "❌";
      showToast(translations["cg.err_image_error"] || "이미지 생성 중 오류가 발생했습니다.");
    }
    btn.disabled = false;
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
    loadQuiz();
  }
  function hideQuiz() { document.getElementById("quiz-wrap").classList.remove("open"); }

  async function loadQuiz() {
    const qDiv = document.getElementById("quiz-questions");
    document.getElementById("quiz-score").style.display = "none";
    qDiv.innerHTML = `<div style="display:flex;align-items:center;gap:8px;padding:8px 0;color:rgba(255,255,255,0.3);font-size:12px;"><div style="width:16px;height:16px;border-radius:50%;border:2px solid #f97316;border-top-color:transparent;animation:spin 0.8s linear infinite;"></div>${translations["cg.quiz_loading"] || "퀴즈 생성 중..."}</div>`;
    try {
      const res = await fetch("/api/textbook/quiz", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({dialogue:currentDialogue}) });
      const data = await res.json();
      const qs = data.questions || [];
      if (!qs.length) { qDiv.innerHTML = `<p style="color:rgba(255,255,255,0.3);font-size:12px;">${translations["cg.err_quiz_failed"] || "퀴즈를 생성하지 못했습니다."}</p>`; return; }
      qDiv.innerHTML = qs.map((q,i) => {
        const parts = q.display.split("___");
        return `<div class="quiz-q">Q${i+1}. ${parts[0]}<input class="quiz-blank" data-answer="${jsEsc(q.blank_word)}" placeholder="  " />${parts[1]||""}<div class="quiz-hint">💡 ${q.hint||""}</div></div>`;
      }).join("");
    } catch(e) { qDiv.innerHTML = `<p style="color:#f87171;font-size:12px;">${e.message}</p>`; }
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

  // ── 저장 ────────────────────────────────────────────────────────
  function saveTextbook() {
    if (!currentDialogue.length) { showToast(translations["cg.err_gen_first"] || "먼저 레슨을 생성해주세요."); return; }
    const saved = JSON.parse(localStorage.getItem("saved_textbooks")||"[]");
    saved.unshift({ id:Date.now(), topic:currentTopic, level:currentLevel, dialogue:currentDialogue, vocabulary:currentVocabulary, imageUrl:currentImageUrl, savedAt:new Date().toISOString() });
    localStorage.setItem("saved_textbooks", JSON.stringify(saved.slice(0,20)));
    loadSavedTextbooks();
    document.getElementById("btn-save").querySelector("span:first-child").textContent = "✅";
    setTimeout(() => { document.getElementById("btn-save").querySelector("span:first-child").textContent = "💾"; }, 1500);
  }

  function deleteSaved(id) {
    const saved = JSON.parse(localStorage.getItem("saved_textbooks")||"[]").filter(s=>s.id!==id);
    localStorage.setItem("saved_textbooks", JSON.stringify(saved));
    loadSavedTextbooks();
  }

  function restoreSaved(id) {
    const entry = JSON.parse(localStorage.getItem("saved_textbooks")||"[]").find(s=>s.id===id);
    if (!entry) return;
    document.getElementById("topic").value = entry.topic;
    document.getElementById("level").value = entry.level;
    currentTopic = entry.topic; currentLevel = entry.level;
    currentDialogue = entry.dialogue; currentVocabulary = entry.vocabulary; currentImageUrl = entry.imageUrl;
    generateContent();
  }

  function toggleSavedList() {
    const wrap = document.getElementById("saved-list-wrap");
    const chevron = document.getElementById("saved-chevron");
    const isOpen = wrap.classList.contains("open");
    wrap.classList.toggle("open");
    chevron.textContent = isOpen ? "▲" : "▼";
  }

  function loadSavedTextbooks() {
    const saved = JSON.parse(localStorage.getItem("saved_textbooks")||"[]");
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
        <div class="saved-item-img">${s.imageUrl?`<img src="${s.imageUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;">`:"📖"}</div>
        <div class="saved-item-info"><div class="saved-item-topic">${s.topic}</div><div class="saved-item-meta">${lv[s.level]||""} ${lvLabel[s.level]||s.level} · ${date}</div></div>
        <button class="saved-load-btn" onclick="restoreSaved(${s.id})">${translations["cg.btn_load"] || "불러오기"}</button>
        <button class="saved-del-btn" onclick="deleteSaved(${s.id})">×</button>
      </div>`;
    }).join("");
  }

  // ── AI 코치 ─────────────────────────────────────────────────────
  function appendBubble(role, html) {
    const msgs = document.getElementById("coach-messages");
    const div = document.createElement("div");
    if (role === "user") {
      div.className = "coach-bubble-user";
      div.innerHTML = `<div class="bubble-user-text">${html}</div>`;
    } else {
      div.className = "coach-bubble-ai";
      div.innerHTML = `<span style="font-size:20px;flex-shrink:0;">🤖</span><div class="bubble-ai-text">${html}</div>`;
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
      const res = await fetch("/api/chat/test", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({prompt, backend:"ollama", model:"exaone3.5:2.4b", history:coachHistory.slice(-10), system_context:ctx}) });
      const data = await res.json();
      document.getElementById("coach-typing")?.remove();
      const reply = data.text || JSON.stringify(data);
      const safe = window.marked ? DOMPurify.sanitize(marked.parse(reply)) : reply;
      appendBubble("assistant", safe);
      coachHistory.push({role:"assistant", content:reply});
    } catch(e) {
      document.getElementById("coach-typing")?.remove();
      appendBubble("assistant", (translations["cg.err_prefix"] || "오류") + ": " + e.message);
    }
  }

  // ── spin 애니메이션 ─────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = "@keyframes spin{to{transform:rotate(360deg)}}";
  document.head.appendChild(style);

  document.addEventListener("DOMContentLoaded", loadSavedTextbooks);
