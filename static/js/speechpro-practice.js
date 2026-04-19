  const appState = {
    mode: 'guided',
    mediaRecorder: null,
    recordedChunks: [],
    recordedBlob: null,
    recordingStartTime: null,
    recordingTimer: null,
    selectedSentence: null,  // guided: {sentenceKr, fst, ...} | free: string
    sentenceAll: [],
    sentenceOffset: 0,
    sentenceLimit: 20,
    hasMoreSentences: true,
  };

  // ── Mode switching ──────────────────────────────────────
  function switchMode(mode) {
    appState.mode = mode;
    document.getElementById('tab-guided').classList.toggle('active', mode === 'guided');
    document.getElementById('tab-free').classList.toggle('active', mode === 'free');
    document.getElementById('panel-guided').classList.toggle('hidden', mode !== 'guided');
    document.getElementById('panel-free').classList.toggle('hidden', mode !== 'free');
    // reset recording state on mode switch
    appState.selectedSentence = null;
    document.getElementById('start-recording').disabled = true;
    document.getElementById('evaluate-button').disabled = true;
    document.getElementById('play-recording').disabled = true;
    document.getElementById('recording-timer-display').textContent = '00:00';
    document.getElementById('status-text').textContent = 'READY';
    if (mode === 'free') {
      setTimeout(() => document.getElementById('custom-sentence').focus(), 100);
    }
  }

  // ── Guided: sentence list ───────────────────────────────
  const LEVEL_KR = { A1:'초급1', A2:'초급2', B1:'중급1', B2:'중급2', C1:'고급1', C2:'고급2' };

  async function loadSentences(isMore = false) {
    if (!isMore) { appState.sentenceOffset = 0; appState.sentenceAll = []; }
    let url = `/api/speechpro/sentences?limit=${appState.sentenceLimit}&offset=${appState.sentenceOffset}`;
    const lvl = document.getElementById('level-filter').value;
    if (lvl) url += `&level=${lvl}`;
    const res = await fetch(url);
    const payload = await res.json();
    const newItems = payload.data || [];
    appState.sentenceAll = isMore ? [...appState.sentenceAll, ...newItems] : newItems;
    appState.sentenceOffset += newItems.length;
    appState.hasMoreSentences = newItems.length >= appState.sentenceLimit;
    renderSentenceList();
    document.getElementById('load-more-sentences').classList.toggle('hidden', !appState.hasMoreSentences);
  }

  function renderSentenceList() {
    document.getElementById('sentence-list').innerHTML = appState.sentenceAll.map((s, i) => `
      <button class="glass-sub-card w-full text-left p-4 rounded-2xl text-sm text-white/80 hover:text-white transition-all border border-white/5" onclick="selectSentence(${i})">
        <span class="text-[10px] font-black text-orange-500/60 mr-2">${LEVEL_KR[s.level] || s.level}</span>${s.sentenceKr || s.sentence}
      </button>
    `).join('');
  }

  function selectSentence(idx) {
    appState.selectedSentence = appState.sentenceAll[idx];
    document.getElementById('start-recording').disabled = false;
    document.querySelectorAll('#sentence-list button').forEach((b, i) => {
      b.style.borderColor = i === idx ? 'rgba(249,115,22,0.5)' : 'rgba(255,255,255,0.05)';
      b.style.background  = i === idx ? 'rgba(249,115,22,0.1)' : 'rgba(255,255,255,0.02)';
    });
  }

  // ── Free: custom input ──────────────────────────────────
  function setCustomSentence() {
    const val = document.getElementById('custom-sentence').value.trim();
    if (!val) return;
    appState.selectedSentence = val;
    document.getElementById('free-sentence-display').textContent = val;
    document.getElementById('free-sentence-display').style.color = 'white';
    document.getElementById('start-recording').disabled = false;
  }

  async function playTTS() {
    const text = typeof appState.selectedSentence === 'string' ? appState.selectedSentence : null;
    if (!text) return;
    try {
      const res = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const blob = await res.blob();
      new Audio(URL.createObjectURL(blob)).play();
    } catch (e) { console.error(e); }
  }

  // ── Recording ───────────────────────────────────────────
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      appState.mediaRecorder = new MediaRecorder(stream);
      appState.recordedChunks = [];
      appState.recordingStartTime = Date.now();
      appState.mediaRecorder.ondataavailable = e => appState.recordedChunks.push(e.data);
      appState.mediaRecorder.onstop = () => {
        appState.recordedBlob = new Blob(appState.recordedChunks, { type: 'audio/wav' });
        document.getElementById('audio-playback').src = URL.createObjectURL(appState.recordedBlob);
        document.getElementById('evaluate-button').disabled = false;
        document.getElementById('play-recording').disabled = false;
      };
      appState.mediaRecorder.start();
      document.getElementById('start-recording').classList.add('hidden');
      document.getElementById('stop-recording').classList.remove('hidden');
      document.getElementById('status-text').textContent = 'RECORDING';
      document.getElementById('status-dot').style.background = '#ef4444';
      document.getElementById('waveform').classList.remove('hidden');
      document.getElementById('waveform-right').classList.remove('hidden');
      startTimer();
    } catch (e) { alert('마이크 오류: ' + e.message); }
  }

  function stopRecording() {
    if (!appState.mediaRecorder) return;
    appState.mediaRecorder.stop();
    appState.mediaRecorder.stream.getTracks().forEach(t => t.stop());
    document.getElementById('stop-recording').classList.add('hidden');
    document.getElementById('start-recording').classList.remove('hidden');
    document.getElementById('status-text').textContent = 'DONE';
    document.getElementById('status-dot').style.background = '#22c55e';
    document.getElementById('waveform').classList.add('hidden');
    document.getElementById('waveform-right').classList.add('hidden');
    stopTimer();
  }

  function playRecording() {
    const audio = document.getElementById('audio-playback');
    if (audio.src) { audio.currentTime = 0; audio.play(); }
  }

  function startTimer() {
    appState.recordingTimer = setInterval(() => {
      const sec = Math.floor((Date.now() - appState.recordingStartTime) / 1000);
      document.getElementById('recording-timer-display').textContent =
        `${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;
    }, 1000);
  }
  function stopTimer() { clearInterval(appState.recordingTimer); }

  // ── Evaluate ────────────────────────────────────────────
  async function evaluatePronunciation() {
    if (!appState.recordedBlob) return;
    const btn = document.getElementById('evaluate-button');
    btn.disabled = true;
    btn.textContent = '분석 중...';
    document.getElementById('status-text').textContent = 'ANALYSING';

    const fd = new FormData();
    fd.append('audio', appState.recordedBlob, 'rec.wav');

    if (appState.mode === 'guided' && appState.selectedSentence) {
      const s = appState.selectedSentence;
      fd.append('text', s.sentenceKr || s.sentence);
      if (s.fst) {
        fd.append('syll_ltrs', s.syll_ltrs);
        fd.append('syll_phns', s.syll_phns);
        fd.append('fst', s.fst);
      }
    } else {
      const text = typeof appState.selectedSentence === 'string' ? appState.selectedSentence : '';
      fd.append('text', text);
    }

    let result;
    try {
      const res = await fetch('/api/speechpro/evaluate', { method: 'POST', body: fd });
      result = await res.json();
    } catch (e) {
      btn.disabled = false; btn.textContent = '🪄 AI 발음 평가';
      document.getElementById('status-text').textContent = 'DONE';
      alert('평가 요청 실패: ' + e.message);
      return;
    }

    btn.disabled = false; btn.textContent = '🪄 AI 발음 평가';
    document.getElementById('status-text').textContent = 'DONE';

    if (result.success) {
      showResults(result);
    } else {
      alert('평가 오류: ' + (result.error || result.message || '알 수 없는 오류'));
    }
  }

  // ── Results modal ───────────────────────────────────────
  function showResults(res) {
    const score = Math.round(res.overall_score || 0);
    document.getElementById('overall-score').textContent = score;
    document.getElementById('score-bar').style.width = score + '%';
    document.getElementById('score-feedback').textContent =
      score >= 80 ? 'Excellent! 🌟' : score >= 60 ? 'Good Effort! 👍' : 'Keep Practicing! 💪';

    // Analysis tab
    const analysisEl = document.getElementById('result-content-analysis');
    if (res.score && res.score.details) {
      const d = res.score.details;
      const accuracy = res.score.accuracy_percentage || 0;
      const fluency = d.fluency
        ? Math.round((d.fluency.correct_syllable_count / (d.fluency.total_syllable_count || 1)) * 100)
        : 0;
      const syllables = d.syllables || [];
      analysisEl.innerHTML = `
        <div class="grid grid-cols-2 gap-4 mb-6">
          <div class="glass-sub-card p-6 rounded-2xl text-center">
            <p class="text-[10px] font-black text-white/30 uppercase tracking-widest mb-2">정확도</p>
            <p class="text-3xl font-black text-white">${Math.round(accuracy)}%</p>
          </div>
          <div class="glass-sub-card p-6 rounded-2xl text-center">
            <p class="text-[10px] font-black text-white/30 uppercase tracking-widest mb-2">유창도</p>
            <p class="text-3xl font-black text-white">${fluency}%</p>
          </div>
        </div>
        ${syllables.length > 0 ? `
          <p class="text-xs font-black text-white/40 uppercase tracking-widest mb-4">음절 분석</p>
          <div class="flex flex-wrap gap-2">
            ${syllables.map(s => `
              <div class="px-3 py-2 rounded-xl text-center ${s.score >= 80 ? 'bg-green-500/20 border border-green-500/30' : 'bg-orange-500/20 border border-orange-500/30'}">
                <p class="text-lg font-black text-white">${s.syllable}</p>
                <p class="text-[10px] font-bold ${s.score >= 80 ? 'text-green-400' : 'text-orange-400'}">${Math.round(s.score)}%</p>
              </div>`).join('')}
          </div>` : '<p class="text-white/40 text-sm">음절 데이터가 없습니다.</p>'}
      `;
    } else {
      analysisEl.innerHTML = '<p class="text-white/40 text-sm p-4">분석 데이터가 없습니다.</p>';
    }

    // AI Coach tab: show immediately if available, else async fetch
    const aiWrap = document.getElementById('ai-coach-wrap');
    if (res.ai_feedback) {
      renderAiFeedback(res.ai_feedback);
    } else {
      aiWrap.innerHTML = `
        <div class="flex items-center justify-center gap-3 text-white/40">
          <div class="w-5 h-5 rounded-full border-2 border-white/30 border-t-white/80 spinner"></div>
          <span class="text-sm font-bold">AI 코치 분석 중...</span>
        </div>`;
      // async fetch feedback
      const evalText = appState.mode === 'guided' && appState.selectedSentence
        ? (appState.selectedSentence.sentenceKr || appState.selectedSentence.sentence)
        : (typeof appState.selectedSentence === 'string' ? appState.selectedSentence : '');
      fetch('/api/speechpro/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ score: res.overall_score, text: evalText, details: res.score })
      })
      .then(r => r.json())
      .then(fb => renderAiFeedback(fb.feedback || fb.message || '피드백을 불러올 수 없습니다.'))
      .catch(() => renderAiFeedback('AI 코치 연결에 실패했습니다.'));
    }

    switchTab('score');
    document.getElementById('results-modal').classList.remove('hidden');
  }

  function renderAiFeedback(text) {
    document.getElementById('ai-coach-wrap').innerHTML = `
      <p class="text-[10px] font-black text-orange-400 uppercase tracking-widest mb-4">AI Coach Feedback</p>
      <p class="text-lg text-white/90 font-medium leading-relaxed italic">"${text}"</p>
    `;
  }

  function switchTab(tabId) {
    document.querySelectorAll('.result-tab').forEach(t => {
      t.classList.remove('active', 'text-orange-500');
      t.classList.add('text-white/40');
    });
    document.querySelectorAll('.result-step').forEach(s => s.classList.add('hidden'));
    const activeTab = document.querySelector(`.result-tab[data-tab="${tabId}"]`);
    if (activeTab) {
      activeTab.classList.add('active', 'text-orange-500');
      activeTab.classList.remove('text-white/40');
    }
    document.getElementById(`result-content-${tabId}`).classList.remove('hidden');
  }

  function closeResults() { document.getElementById('results-modal').classList.add('hidden'); }

  // ── Init ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    loadSentences();
    document.getElementById('level-filter').addEventListener('change', () => loadSentences());
    document.getElementById('start-recording').addEventListener('click', startRecording);
    document.getElementById('stop-recording').addEventListener('click', stopRecording);
    document.getElementById('play-recording').addEventListener('click', playRecording);
    document.getElementById('evaluate-button').addEventListener('click', evaluatePronunciation);
    document.querySelectorAll('.result-tab').forEach(t =>
      t.addEventListener('click', () => switchTab(t.getAttribute('data-tab')))
    );
  });
