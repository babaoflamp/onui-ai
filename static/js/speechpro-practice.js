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
    sentencePresetCache: {},
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

  function getSelectedSentenceText() {
    if (!appState.selectedSentence) return '';
    if (typeof appState.selectedSentence === 'string') return appState.selectedSentence;
    return appState.selectedSentence.sentenceKr || appState.selectedSentence.sentence || '';
  }

  async function fetchSentencePreset(text) {
    const normalized = (text || '').trim();
    if (!normalized) return null;
    if (appState.sentencePresetCache[normalized]) {
      return appState.sentencePresetCache[normalized];
    }

    const res = await fetch(`/api/speechpro/precomputed?text=${encodeURIComponent(normalized)}`);
    const payload = await res.json();
    if (!res.ok) {
      throw new Error(payload?.error || payload?.details || '문장 준비에 실패했습니다.');
    }
    if (!payload?.found || !payload?.fst) {
      throw new Error('문장 발음 정보를 준비하지 못했습니다.');
    }

    const preset = {
      sentenceKr: normalized,
      sentence: normalized,
      syll_ltrs: payload.syll_ltrs || '',
      syll_phns: payload.syll_phns || '',
      fst: payload.fst || '',
      source: payload.source || 'precomputed',
    };
    appState.sentencePresetCache[normalized] = preset;
    return preset;
  }

  async function ensureSentencePrepared(sentenceLike) {
    const text = typeof sentenceLike === 'string'
      ? sentenceLike
      : (sentenceLike?.sentenceKr || sentenceLike?.sentence || '');
    const normalized = (text || '').trim();
    if (!normalized) {
      throw new Error('연습 문장을 먼저 선택해주세요.');
    }

    if (
      sentenceLike &&
      typeof sentenceLike === 'object' &&
      sentenceLike.fst &&
      sentenceLike.syll_ltrs &&
      sentenceLike.syll_phns
    ) {
      return sentenceLike;
    }

    const preset = await fetchSentencePreset(normalized);
    return {
      ...(typeof sentenceLike === 'object' && sentenceLike ? sentenceLike : {}),
      ...preset,
      sentenceKr: normalized,
      sentence: normalized,
    };
  }

  async function prepareSelectedSentence(sentenceLike, displayText) {
    const startBtn = document.getElementById('start-recording');
    const statusText = document.getElementById('status-text');
    const targetText = (displayText || (typeof sentenceLike === 'string'
      ? sentenceLike
      : sentenceLike?.sentenceKr || sentenceLike?.sentence || '')).trim();

    startBtn.disabled = true;
    statusText.textContent = 'PREPARING';

    try {
      const prepared = await ensureSentencePrepared(sentenceLike);
      appState.selectedSentence = prepared;
      if (targetText) {
        appState.sentencePresetCache[targetText] = prepared;
      }
      startBtn.disabled = false;
      statusText.textContent = 'READY';
    } catch (e) {
      // Keep the text so TTS and display still work even without precomputed data
      appState.selectedSentence = targetText || null;
      startBtn.disabled = false;
      statusText.textContent = 'READY';
      alert('문장 준비 실패: ' + e.message);
    }
  }

  async function loadSentences(isMore = false) {
    appState.sentenceOffset = 0;
    appState.sentenceAll = [];
    let url = `/api/speechpro/sentences`;
    const lvl = document.getElementById('level-filter').value;
    if (lvl) url += `?level=${lvl}`;
    const res = await fetch(url);
    const payload = await res.json();
    appState.sentenceAll = Array.isArray(payload) ? payload : (payload.data || []);
    appState.sentenceOffset = appState.sentenceAll.length;
    appState.hasMoreSentences = false;
    renderSentenceList();
    document.getElementById('load-more-sentences').classList.add('hidden');
  }

  function renderSentenceList() {
    document.getElementById('sentence-list').innerHTML = appState.sentenceAll.map((s, i) => `
      <button class="glass-sub-card w-full text-left p-4 rounded-2xl text-sm text-white/80 hover:text-white transition-all border border-white/5" onclick="selectSentence(${i})">
        <span class="text-[10px] font-black text-orange-500/60 mr-2">${LEVEL_KR[s.level] || s.level}</span>${s.sentenceKr || s.sentence}
      </button>
    `).join('');
  }

  async function selectSentence(idx) {
    const sentence = appState.sentenceAll[idx];
    await prepareSelectedSentence(sentence, sentence?.sentenceKr || sentence?.sentence || '');
    document.querySelectorAll('#sentence-list button').forEach((b, i) => {
      b.style.borderColor = i === idx ? 'rgba(249,115,22,0.5)' : 'rgba(255,255,255,0.05)';
      b.style.background  = i === idx ? 'rgba(249,115,22,0.1)' : 'rgba(255,255,255,0.02)';
    });
  }

  // ── Free: custom input ──────────────────────────────────
  async function setCustomSentence() {
    const val = document.getElementById('custom-sentence').value.trim();
    if (!val) return;
    document.getElementById('free-sentence-display').textContent = val;
    document.getElementById('free-sentence-display').style.color = 'white';
    await prepareSelectedSentence(val, val);
  }

  async function playTTS() {
    let text = getSelectedSentenceText();
    // Fallback: read directly from the free-input display element
    if (!text && appState.mode === 'free') {
      const displayEl = document.getElementById('free-sentence-display');
      if (displayEl) {
        text = (displayEl.textContent || '').trim();
        // Don't use the placeholder text
        if (text === '문장을 입력해주세요 👆') text = '';
      }
    }
    if (!text) return;
    try {
      const res = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert('TTS 오류: ' + (err.message || err.details || `HTTP ${res.status}`));
        return;
      }
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
      appState.mediaRecorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) appState.recordedChunks.push(e.data);
      };
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
    fd.append('include_ai', 'false');

    try {
      appState.selectedSentence = await ensureSentencePrepared(appState.selectedSentence);
    } catch (e) {
      btn.disabled = false; btn.textContent = '🪄 AI 발음 평가';
      document.getElementById('status-text').textContent = 'DONE';
      alert('평가 준비 실패: ' + e.message);
      return;
    }

    const s = appState.selectedSentence;
    fd.append('text', s.sentenceKr || s.sentence || '');
    fd.append('syll_ltrs', s.syll_ltrs || '');
    fd.append('syll_phns', s.syll_phns || '');
    fd.append('fst', s.fst || '');

    let result;
    try {
      const res = await fetch('/api/speechpro/evaluate', { method: 'POST', body: fd });
      result = await res.json();
      if (!res.ok) {
        const serverMessage = result?.error || result?.message || `HTTP ${res.status}`;
        throw new Error(serverMessage);
      }
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
  function findDetailedSyllables(obj) {
    if (!obj || typeof obj !== 'object') return null;

    try {
      const quality = obj.score?.details?.quality || obj.details?.quality;
      if (quality && Array.isArray(quality.sentences)) {
        let allSyllables = [];
        quality.sentences.forEach(sentence => {
          if (sentence.text === '!SIL' || !sentence.words) return;
          sentence.words.forEach((word, wordIdx) => {
            if (wordIdx > 0 && allSyllables.length > 0) {
              allSyllables.push({ __word_break: true });
            }
            if (word.syll && Array.isArray(word.syll)) {
              allSyllables = allSyllables.concat(word.syll);
            }
          });
        });
        if (allSyllables.length > 0) return allSyllables;
      }
    } catch (_) {}

    if (Array.isArray(obj.syllables)) return obj.syllables;
    if (obj.score && Array.isArray(obj.score.syllables)) return obj.score.syllables;

    const phonemeScore = obj.phoneme_score || obj.score?.phoneme_score;
    if (phonemeScore && typeof phonemeScore === 'object') {
      return Object.entries(phonemeScore).map(([phn, score]) => ({ text: phn, score }));
    }

    return null;
  }

  function renderDetailedAnalysis(res) {
    const analysisEl = document.getElementById('result-content-analysis');
    if (!res.score || !res.score.details) {
      analysisEl.innerHTML = '<p class="text-white/40 text-sm p-4">분석 데이터가 없습니다.</p>';
      return;
    }

    const details = res.score.details;
    const syllables = findDetailedSyllables(res);

    let syllableHtml = "<p class='text-white/40 text-sm'>음절 데이터가 없습니다.</p>";
    if (syllables && Array.isArray(syllables) && syllables.length > 0) {
      syllableHtml = `
        <p class="text-xs font-black text-white/40 uppercase tracking-widest mb-4">음절 정밀 분석</p>
        <div class="flex flex-wrap gap-3">
          ${syllables.map(syl => {
            if (syl && syl.__word_break) {
              return '<div class="basis-full h-0"></div>';
            }

            const char = syl.syllable || syl.text || '?';
            if (char === '!SIL' || char === 'SIL') return '';

            const sylScore = Math.round(syl.accuracy_percentage || syl.score || 0);
            let colorClass = 'border-red-500/30 text-red-400';
            if (sylScore >= 80) colorClass = 'border-green-500/30 text-green-400';
            else if (sylScore >= 60) colorClass = 'border-orange-500/30 text-orange-400';

            let phonemesHtml = '';
            if (syl.phones && Array.isArray(syl.phones)) {
              phonemesHtml = `
                <div class="flex gap-1 mt-2 justify-center flex-wrap">
                  ${syl.phones.map(p => {
                    const symbol = p.symbol || p.text;
                    if (symbol === '!SIL' || symbol === 'SIL') return '';
                    const pScore = Math.round(p.score || 0);
                    let pColor = 'text-red-400/60';
                    if (pScore >= 80) pColor = 'text-green-400/60';
                    else if (pScore >= 60) pColor = 'text-orange-400/60';
                    return `
                      <div class="flex flex-col items-center min-w-[18px]">
                        <span class="text-[9px] font-black text-white/80">${symbol}</span>
                        <span class="text-[8px] font-bold ${pColor}">${pScore}</span>
                      </div>
                    `;
                  }).join('')}
                </div>
              `;
            }

            return `
              <div class="glass-sub-card flex flex-col items-center p-3 rounded-2xl border bg-white/5 min-w-[74px] ${colorClass}">
                <span class="text-2xl font-black text-white mb-0.5">${char}</span>
                <span class="text-[10px] font-bold opacity-70">${sylScore}%</span>
                ${phonemesHtml}
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    analysisEl.innerHTML = syllableHtml;
  }

  function showResults(res) {
    const score = Math.round(res.overall_score || 0);
    document.getElementById('overall-score').textContent = score;
    document.getElementById('score-bar').style.width = score + '%';
    document.getElementById('score-feedback').textContent =
      score >= 80 ? 'Excellent! 🌟' : score >= 60 ? 'Good Effort! 👍' : 'Keep Practicing! 💪';

    renderDetailedAnalysis(res);

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
      const evalText = getSelectedSentenceText();
      const currentLang = localStorage.getItem('app_lang') || 'ko';
      fetch('/api/speechpro/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: evalText,
          score: res.score || {
            score: res.overall_score || 0,
            details: {},
            error_code: 0,
          },
          ui_lang: currentLang,
        })
      })
      .then(r => r.json())
      .then(fb => {
        if (fb.success && fb.ai_feedback) {
          renderAiFeedback(fb.ai_feedback);
          return;
        }
        renderAiFeedback(fb.error || '피드백을 불러올 수 없습니다.');
      })
      .catch(() => renderAiFeedback('AI 코치 연결에 실패했습니다.'));
    }

    switchTab('score');
    document.getElementById('results-modal').classList.remove('hidden');
  }

  function renderAiFeedback(text) {
    document.getElementById('ai-coach-wrap').innerHTML = `
      <p class="text-[10px] font-black text-orange-400 uppercase tracking-widest mb-4">AI Coach Feedback</p>
      <p class="text-lg text-white/90 font-medium leading-relaxed whitespace-pre-line">${text}</p>
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
