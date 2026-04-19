document.addEventListener('DOMContentLoaded', () => {
  // ── State ──────────────────────────────────────────────────────────────
  let scenarios = [];
  let currentScenario = null;
  let history = [];           // [{role:'assistant'|'user', content:'...'}]
  let isRecording = false;
  let mediaRecorder = null;
  let audioChunks = [];
  let timerInterval = null;
  let seconds = 0;
  let aiSpeaking = false;
  let currentAudio = null;

  const lobby      = document.getElementById('lobby');
  const callScreen = document.getElementById('call-screen');
  const chatLog    = document.getElementById('chat-log');
  const micBtn     = document.getElementById('mic-btn');
  const statusBadge = document.getElementById('status-badge');
  const recordLabel = document.getElementById('record-label');
  const recordWave  = document.getElementById('record-wave');
  const sttPreview  = document.getElementById('stt-preview');
  const sttText     = document.getElementById('stt-text');

  // ── Scenario loading ───────────────────────────────────────────────────
  async function loadScenarios() {
    try {
      const res = await fetch('/api/voice-call/scenarios');
      const data = await res.json();
      if (data.success) { scenarios = data.scenarios; renderScenarios(); }
    } catch (e) { console.error(e); }
  }

  function renderScenarios() {
    const list = document.getElementById('scenario-list');
    list.innerHTML = '';
    scenarios.forEach((s, idx) => {
      const btn = document.createElement('button');
      btn.className = 'scenario-card text-left';
      btn.innerHTML = `
        <div class="relative aspect-square overflow-hidden bg-white/5">
          <img src="${s.avatar_url}" onerror="this.src='/static/images/onui-pure-idol.png'"
               class="w-full h-full object-cover hover:scale-105 transition-all duration-500" />
          <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-center opacity-0 hover:opacity-100 transition-opacity pb-2">
            <span class="text-white text-xs font-black">▶ 시작</span>
          </div>
        </div>
        <div class="p-3">
          <h4 class="text-sm font-black text-white truncate">${s.title}</h4>
          <p class="text-orange-400 text-[10px] font-bold uppercase tracking-widest truncate mt-0.5">${s.tutor_name}</p>
        </div>`;
      btn.addEventListener('click', () => startCall(s));
      list.appendChild(btn);
    });
  }

  // ── Call lifecycle ─────────────────────────────────────────────────────
  async function startCall(scenario) {
    currentScenario = scenario;
    history = [];
    seconds = 0;
    lobby.classList.add('hidden');
    callScreen.classList.remove('hidden');
    document.getElementById('tutor-name').textContent = currentScenario.tutor_name;
    document.getElementById('tutor-avatar').src = currentScenario.avatar_url;
    setStatus('연결 중...');
    setMicEnabled(false);
    startTimer();

    // AI 첫 질문 생성
    await aiTurn('', true);
  };

  function startTimer() {
    timerInterval = setInterval(() => {
      seconds++;
      const m = String(Math.floor(seconds/60)).padStart(2,'0');
      const s = String(seconds%60).padStart(2,'0');
      document.getElementById('call-timer').textContent = `${m}:${s}`;
    }, 1000);
  }

  window.endCall = function() {
    clearInterval(timerInterval);
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    if (mediaRecorder && isRecording) stopRecording();

    const dur = document.getElementById('call-timer').textContent;
    showSummaryModal(dur);
  };

  function showSummaryModal(dur) {
    const modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.85);backdrop-filter:blur(8px);';
    const lines = [...chatLog.querySelectorAll('.bubble-ai,.bubble-user')].map(b => b.textContent);
    modal.innerHTML = `
      <div style="background:#1a1a1a;border:1px solid rgba(255,255,255,0.1);border-radius:24px;padding:32px;max-width:480px;width:90%;max-height:70vh;overflow-y:auto;">
        <h3 style="font-size:18px;font-weight:900;color:#fff;margin-bottom:4px;">통화 종료</h3>
        <p style="font-size:12px;color:rgba(255,255,255,0.4);margin-bottom:20px;">⏱ ${dur} · ${lines.length}개 발화</p>
        <div style="font-size:13px;color:rgba(255,255,255,0.7);line-height:1.7;">
          ${lines.slice(-8).map(l => `<p style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.05);">${l}</p>`).join('')}
        </div>
        <button onclick="this.closest('div[style]').parentElement.remove();location.reload();"
          style="margin-top:20px;width:100%;padding:14px;background:linear-gradient(to right,#f97316,#ec4899);color:#fff;font-weight:900;border-radius:14px;cursor:pointer;font-size:15px;">
          확인
        </button>
      </div>`;
    document.body.appendChild(modal);
  }

  // ── AI turn ────────────────────────────────────────────────────────────
  async function aiTurn(userText, isFirst = false) {
    setStatus('AI 생각 중...');
    setMicEnabled(false);
    if (isFirst) {
      document.getElementById('chat-placeholder')?.remove();
    }

    // Show thinking bubble
    const thinkId = 'think-' + Date.now();
    addThinkingBubble(thinkId);

    try {
      const res = await fetch('/api/voice-call/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: currentScenario.id,
          message: userText,
          history,
          is_first: isFirst,
        })
      });
      const data = await res.json();
      removeThinkingBubble(thinkId);

      if (!data.success) throw new Error(data.error || 'Chat failed');

      const reply = data.reply || '';
      const feedback = data.feedback || '';

      // Add to history
      history.push({ role: 'assistant', content: reply });

      // Show AI bubble
      appendBubble('ai', reply);

      // Show feedback chip if present
      if (feedback) appendFeedbackChip(feedback);

      // TTS play
      await speakText(reply);

    } catch (e) {
      removeThinkingBubble(thinkId);
      appendBubble('ai', '죄송해요, 연결에 문제가 생겼어요. 다시 시도해주세요.');
      console.error(e);
    }

    setStatus('녹음 준비');
    setMicEnabled(true);
  }

  // ── Recording ──────────────────────────────────────────────────────────
  window.toggleRecording = async function() {
    if (aiSpeaking) return;
    if (!isRecording) {
      await startRecording();
    } else {
      stopRecording();
    }
  };

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
      mediaRecorder.onstop = onRecordingStop;
      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add('recording');
      micBtn.textContent = '⏹';
      recordLabel.textContent = '녹음 중... (다시 눌러서 완료)';
      recordWave.classList.remove('hidden');
      sttPreview.classList.add('hidden');
      setStatus('녹음 중...');
    } catch (e) {
      alert('마이크 접근 오류: ' + e.message);
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    isRecording = false;
    micBtn.classList.remove('recording');
    micBtn.textContent = '🎙️';
    recordWave.classList.add('hidden');
    recordLabel.textContent = '분석 중...';
    setMicEnabled(false);
  }

  async function onRecordingStop() {
    const blob = new Blob(audioChunks, { type: 'audio/webm' });

    // STT
    setStatus('STT 변환 중...');
    let userText = '';
    try {
      const fd = new FormData();
      fd.append('file', blob, 'rec.webm');
      const res = await fetch('/api/voice-call/stt', { method: 'POST', body: fd });
      const data = await res.json();
      userText = data.text || '';
    } catch (e) {
      console.error('STT error', e);
    }

    if (!userText.trim()) {
      recordLabel.textContent = '음성을 인식하지 못했어요. 다시 시도해주세요.';
      setMicEnabled(true);
      setStatus('녹음 준비');
      return;
    }

    // Show STT result
    sttText.textContent = userText;
    sttPreview.classList.remove('hidden');

    // Show user bubble
    appendBubble('user', userText);
    history.push({ role: 'user', content: userText });

    recordLabel.textContent = '버튼을 눌러 한국어로 답하세요';

    // AI response
    await aiTurn(userText, false);
  }

  // ── TTS ────────────────────────────────────────────────────────────────
  async function speakText(text) {
    aiSpeaking = true;
    setStatus('AI 말하는 중...');
    document.getElementById('tutor-avatar').classList.add('speaking');
    try {
      const res = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      currentAudio = new Audio(url);
      await new Promise((resolve, reject) => {
        currentAudio.onended = resolve;
        currentAudio.onerror = reject;
        currentAudio.play();
      });
    } catch (e) {
      console.error('TTS error', e);
    }
    aiSpeaking = false;
    document.getElementById('tutor-avatar').classList.remove('speaking');
  }

  // ── UI helpers ─────────────────────────────────────────────────────────
  function appendBubble(role, text) {
    const div = document.createElement('div');
    div.className = role === 'ai' ? 'bubble-ai' : 'bubble-user';
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function appendFeedbackChip(text) {
    const div = document.createElement('div');
    div.className = 'feedback-chip';
    div.innerHTML = `💡 ${text}`;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function addThinkingBubble(id) {
    const div = document.createElement('div');
    div.id = id;
    div.className = 'bubble-ai flex items-center gap-2';
    div.innerHTML = `
      <div class="w-4 h-4 rounded-full border-2 border-orange-400/50 border-t-orange-400 spinner flex-shrink-0"></div>
      <span class="text-orange-300/60 text-xs">AI 응답 생성 중...</span>`;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function removeThinkingBubble(id) {
    document.getElementById(id)?.remove();
  }

  function setStatus(text) {
    statusBadge.textContent = text;
  }

  function setMicEnabled(enabled) {
    micBtn.disabled = !enabled;
    if (enabled) {
      recordLabel.textContent = '버튼을 눌러 한국어로 답하세요';
    }
  }

  loadScenarios();
});
