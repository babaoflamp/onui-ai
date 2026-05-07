/**
 * Voice Call Real-time (Gemini Live) Implementation
 */
document.addEventListener('DOMContentLoaded', () => {
  let scenarios = []; // Loaded from server for background sync, but UI uses SSR
  let currentScenario = null;
  let socket = null;
  let audioContext = null;
  let mediaSourceNode = null;
  let processor = null;
  let analyser = null;
  let animationId = null;
  let dataArray = null;
  let stream = null;
  let isConnected = false;
  let isEndingCall = false;
  let seconds = 0;
  let timerInterval = null;
  let currentUserTranscript = '';
  let currentAiPreviewTranscript = '';
  let currentAiFinalTranscript = '';
  let nextStartTime = 0;
  let isWaitingForPlayback = false;
  let summaryModal = null;

  const lobby = document.getElementById('lobby');
  const callScreen = document.getElementById('call-screen');
  const chatLog = document.getElementById('chat-log');
  const statusBadge = document.getElementById('status-badge');
  const recordWave = document.getElementById('record-wave');
  const sttPreview = document.getElementById('stt-preview');
  const sttText = document.getElementById('stt-text');
  const startCallBtn = document.getElementById('start-call-btn');
  const endCallBtn = document.getElementById('end-call-btn');
  const recordLabel = document.getElementById('record-label');
  const endTip = document.getElementById('end-tip');
  const callTimer = document.getElementById('call-timer');
  const tutorAvatar = document.getElementById('tutor-avatar');
  const tutorName = null; // element removed from UI
  const scenarioList = document.getElementById('scenario-list');
  const creditNotice = document.getElementById('credit-notice');
  const creditRemainingBadge = document.getElementById('credit-remaining-badge');
  const headerAvatarImg = document.getElementById('header-avatar-img');

  let isTranslationEnabled = true;

  async function fetchAndUpdateCredits() {
    const token = localStorage.getItem('auth_token');
    if (!token) return null;
    try {
      const res = await fetch('/api/credits', { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (data.success) {
        if (creditRemainingBadge) creditRemainingBadge.textContent = data.remaining;
        // Also update sidebar credits bar if present
        const sidebarBar = document.getElementById('credits-bar');
        const sidebarLbl = document.getElementById('credits-label');
        if (sidebarLbl) sidebarLbl.textContent = `${data.remaining} / ${data.daily_limit}`;
        if (sidebarBar) {
          const pct = Math.max(0, Math.min(100, (data.remaining / data.daily_limit) * 100));
          sidebarBar.style.width = pct + '%';
        }
        return data.remaining;
      }
    } catch (e) {}
    return null;
  }

  function t(key, fallback) {
    if (typeof translations !== 'undefined' && translations && translations[key]) {
      return translations[key];
    }
    return fallback;
  }

  function currentLang() {
    return localStorage.getItem('app_lang') || 'en';
  }

  function formatUtteranceCount(count) {
    const lang = currentLang();
    if (lang === 'ko') return `${count}개 발화`;
    if (lang === 'ja') return `${count}件の発話`;
    if (lang === 'zh') return `${count} 条发话`;
    return `${count} utterances`;
  }

  function setStatus(text) {
    if (statusBadge) {
      statusBadge.textContent = text;
    }
  }

  function syncAccessibilityLabels() {
    startCallBtn.setAttribute('aria-label', t('vc.start_call', 'Start voice call'));
    endCallBtn.setAttribute('aria-label', t('vc.end_call', 'End voice call'));
    const tutorAlt = currentScenario
      ? `${currentScenario.tutor_name} ${t('vc.ai_tutor', 'AI Tutor')}`
      : t('vc.ai_tutor', 'AI Tutor');
    tutorAvatar.setAttribute('alt', tutorAlt);
  }

  function resetTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
    seconds = 0;
    if (callTimer) {
      callTimer.textContent = '00:00';
    }
  }

  function resetLivePreview() {
    currentUserTranscript = '';
    currentAiPreviewTranscript = '';
    currentAiFinalTranscript = '';
    sttText.textContent = '';
    sttPreview.classList.add('hidden');
  }

  function resetChatLog() {
    chatLog.innerHTML = '';
    const placeholder = document.createElement('div');
    placeholder.id = 'chat-placeholder';
    placeholder.className = 'text-center text-white/20 text-xs py-8';
    placeholder.textContent = t('vc.starting', 'Starting scenario...');
    chatLog.appendChild(placeholder);
  }

  function resetControls(statusKey = 'vc.ready', labelKey = 'vc.press_to_start') {
    isConnected = false;
    startCallBtn.disabled = false;
    startCallBtn.classList.remove('hidden', 'opacity-50');
    endCallBtn.classList.add('hidden');
    recordWave.classList.add('hidden');
    tutorAvatar.classList.remove('speaking');
    setStatus(t(statusKey, 'Ready...'));
    recordLabel.textContent = t(labelKey, 'Press the microphone button to start the live conversation');
    syncAccessibilityLabels();
  }

  async function appendBubble(role, text) {
    if (!text) return;

    const placeholder = document.getElementById('chat-placeholder');
    if (placeholder) {
      placeholder.remove();
    }

    const div = document.createElement('div');
    div.className = `bubble bubble-${role} animate-in fade-in zoom-in duration-300`;
    
    const textSpan = document.createElement('span');
    textSpan.textContent = text;
    textSpan.className = 'original-text';
    div.appendChild(textSpan);

    chatLog.appendChild(div);
    chatLog.scrollTo({ top: chatLog.scrollHeight, behavior: 'smooth' });

    if (role === 'ai' && isTranslationEnabled) {
      try {
        const targetLang = currentLang() === 'ko' ? 'en' : currentLang(); // Default to English if system is Korean
        const res = await fetch('/api/voice-call/translate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text, target: targetLang })
        });
        const data = await res.json();
        if (data.translation) {
          const transDiv = document.createElement('div');
          transDiv.className = 'mt-1 text-[11px] text-white/50 border-t border-white/5 pt-1';
          transDiv.textContent = data.translation;
          div.appendChild(transDiv);
          chatLog.scrollTo({ top: chatLog.scrollHeight, behavior: 'smooth' });
        }
      } catch (err) {
        console.error('Translation error:', err);
      }
    }
  }

  function renderPreview(text) {
    if (!text) return;
    sttPreview.classList.remove('hidden');
    sttText.textContent = text;
  }

  function mergeTranscript(existing, incoming) {
    const next = (incoming || '').trim();
    if (!next) return existing;
    if (!existing) return next;
    if (next.startsWith(existing)) return next;
    if (existing.includes(next)) return existing;
    return `${existing} ${next}`.trim();
  }

  function finalizeTurn() {
    const userTranscript = currentUserTranscript.trim();
    const aiTranscript = (currentAiFinalTranscript || currentAiPreviewTranscript).trim();

    if (userTranscript) appendBubble('user', userTranscript);
    if (aiTranscript) appendBubble('ai', aiTranscript);

    resetLivePreview();
  }

  window.returnToLobby = function() {
    if (isConnected) endCall();
    closeSummaryModal();
    callScreen.classList.add('hidden');
    lobby.classList.remove('hidden');
  };

  function closeSummaryModal() {
    if (summaryModal) {
      summaryModal.remove();
      summaryModal = null;
    }
  }

  function showSummaryModal(duration) {
    closeSummaryModal();

    summaryModal = document.createElement('div');
    summaryModal.className = 'fixed inset-0 z-[1000] flex items-center justify-center bg-black/85 backdrop-blur-md px-4';

    // Original text extraction
    const bubbles = [...chatLog.querySelectorAll('.bubble')]
      .map((bubble) => {
        const originalText = bubble.querySelector('.original-text');
        const role = bubble.classList.contains('bubble-user') ? 'User' : 'AI';
        return originalText ? `${role}: ${originalText.textContent}` : null;
      })
      .filter(Boolean);

    const panel = document.createElement('div');
    panel.className = 'w-full max-w-[540px] max-h-[80vh] flex flex-col rounded-[24px] border border-white/10 bg-[#1a1a1a] overflow-hidden';

    const header = document.createElement('div');
    header.className = 'p-6 border-b border-white/10 bg-white/5 shrink-0';
    const title = document.createElement('h3');
    title.className = 'mb-1 text-lg font-black text-white';
    title.textContent = t('vc.call_ended_title', 'Call Ended');
    const meta = document.createElement('p');
    meta.className = 'text-xs text-white/40';
    meta.textContent = `⏱ ${duration} · ${formatUtteranceCount(bubbles.length)}`;
    header.append(title, meta);

    const contentArea = document.createElement('div');
    contentArea.className = 'p-6 overflow-y-auto custom-scrollbar flex-1 text-[13px] leading-relaxed text-white/80';
    
    const footer = document.createElement('div');
    footer.className = 'p-6 bg-white/5 border-t border-white/10 shrink-0 flex gap-3';
    
    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'flex-1 rounded-[14px] bg-white/10 px-4 py-3 font-black text-white transition hover:bg-white/20';
    confirmBtn.textContent = t('vc.close_view_log', '닫기 (대화 기록 보기)');
    confirmBtn.addEventListener('click', () => closeSummaryModal());

    const lobbyBtn = document.createElement('button');
    lobbyBtn.type = 'button';
    lobbyBtn.className = 'flex-1 rounded-[14px] bg-orange-500 px-4 py-3 font-black text-white transition hover:bg-orange-600';
    lobbyBtn.textContent = t('vc.return_to_lobby', '로비로 돌아가기');
    lobbyBtn.addEventListener('click', () => returnToLobby());
    
    footer.append(confirmBtn, lobbyBtn);

    panel.append(header, contentArea, footer);
    summaryModal.appendChild(panel);
    document.body.appendChild(summaryModal);

    if (bubbles.length > 0) {
      bubbles.forEach((line) => {
        const row = document.createElement('p');
        row.className = 'border-b border-white/5 py-2';
        row.textContent = line;
        contentArea.appendChild(row);
      });
    } else {
      const empty = document.createElement('p');
      empty.className = 'text-center text-white/40 py-8';
      empty.textContent = t('vc.no_transcript', 'No transcript available.');
      contentArea.appendChild(empty);
    }
  }

  function renderScenarioError() {
    if (!scenarioList) return;
    scenarioList.innerHTML = '';

    const message = document.createElement('div');
    message.className = 'col-span-full py-16 text-center text-red-200/80 font-bold text-sm';
    message.textContent = t('vc.scenario_load_error', 'Unable to load scenarios.');
    scenarioList.appendChild(message);
  }

  function renderScenarios() {
    // SSR을 통해 서버에서 이미 렌더링되었으므로 JS에서는 DOM을 건드리지 않습니다.
    return;
  }

  async function loadScenarios() {
    // 배경 데이터 동기화만 수행 (추후 필요시 사용)
    try {
      const response = await fetch('/api/voice-call/scenarios');
      const data = await response.json();
      if (data.success) {
        scenarios = data.scenarios;
      }
    } catch (e) {}
  }

  window.prepareCall = function(scenario) {
    currentScenario = scenario;
    closeSummaryModal();
    lobby.classList.add('hidden');
    callScreen.classList.remove('hidden');
    tutorAvatar.src = scenario.avatar_url;
    if (headerAvatarImg) headerAvatarImg.src = scenario.avatar_url;
    resetTimer();
    resetLivePreview();
    resetChatLog();
    resetControls('vc.waiting', 'vc.press_to_start');
    if (creditNotice) creditNotice.classList.remove('hidden');
    fetchAndUpdateCredits();
  };

  async function setupAudioProcessing() {
    try {
      if (!audioContext || audioContext.state === 'closed' || audioContext.sampleRate !== 16000) {
        if (audioContext && audioContext.state !== 'closed') {
          await audioContext.close();
        }
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
          throw new Error('AudioContext not supported');
        }
        audioContext = new AudioContextClass({ sampleRate: 16000 });
      }

      if (!audioContext.audioWorklet) {
        throw new Error('AudioWorklet not supported');
      }

      await audioContext.audioWorklet.addModule('/static/js/audio-processor.js');
      
      // Ensure audioContext and stream still exist after await
      if (!audioContext || !stream) {
        console.warn('AudioContext or stream was cleaned up during setup');
        return;
      }

      mediaSourceNode = audioContext.createMediaStreamSource(stream);
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      const bufferLength = analyser.frequencyBinCount;
      dataArray = new Uint8Array(bufferLength);

      processor = new AudioWorkletNode(audioContext, 'audio-processor');

      processor.port.onmessage = (event) => {
        if (!isConnected || !socket || socket.readyState !== WebSocket.OPEN) return;
        socket.send(event.data);
      };

      mediaSourceNode.connect(analyser);
      analyser.connect(processor);
      processor.connect(audioContext.destination);

      visualizeVolume();
    } catch (error) {
      console.error('Audio setup failed:', error);
      const msg = error.message || 'Unknown error';
      setStatus(t('vc.audio_error', `Audio setup failed: ${msg}`));
      resetControls('vc.ready', 'vc.press_to_start');
    }
  }

  function visualizeVolume() {
    if (!analyser || !isConnected) return;
    
    animationId = requestAnimationFrame(visualizeVolume);
    analyser.getByteFrequencyData(dataArray);
    
    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const average = sum / dataArray.length;
    
    // Scale average to a height between 4px and 32px
    const minHeight = 4;
    const maxHeight = 32;
    const scaledHeight = minHeight + (average / 255) * (maxHeight - minHeight);
    
    const bars = recordWave.querySelectorAll('div');
    bars.forEach((bar, index) => {
      // Add some slight variation per bar for a dynamic look
      const variation = Math.sin((Date.now() / 100) + index) * 4;
      const finalHeight = Math.max(minHeight, Math.min(maxHeight, scaledHeight + variation));
      bar.style.height = `${finalHeight}px`;
    });
  }

  function cleanupAudio() {
    try {
      if (typeof animationId !== 'undefined' && animationId) {
        cancelAnimationFrame(animationId);
        animationId = null;
      }
    } catch(e) {}
    
    if (stream) {
      try {
        stream.getTracks().forEach((track) => track.stop());
      } catch(e) {}
    }
    if (processor) {
      try {
        processor.disconnect();
      } catch(e) {}
    }
    try {
      if (typeof analyser !== 'undefined' && analyser) {
        analyser.disconnect();
      }
    } catch(e) {}
    
    if (mediaSourceNode) {
      try {
        mediaSourceNode.disconnect();
      } catch(e) {}
    }
    if (audioContext && audioContext.state !== 'closed') {
      try {
        audioContext.close();
      } catch(e) {}
    }

    stream = null;
    processor = null;
    analyser = null;
    mediaSourceNode = null;
    audioContext = null;
    nextStartTime = 0;
    recordWave.classList.add('hidden');
    tutorAvatar.classList.remove('speaking');
  }

  function stopMicInput() {
    if (animationId) {
      cancelAnimationFrame(animationId);
      animationId = null;
    }
    if (processor) {
      try { processor.port.onmessage = null; } catch(e) {}
    }
    if (stream) {
      try { stream.getTracks().forEach(track => track.stop()); } catch(e) {}
      stream = null;
    }
    recordWave.classList.add('hidden');
  }

  function waitForPlaybackEnd(callback, maxMs) {
    maxMs = maxMs || 8000;
    isWaitingForPlayback = true;
    const deadline = performance.now() + maxMs;
    function check() {
      const audioGone = !audioContext || audioContext.state === 'closed';
      const playbackDone = audioGone || audioContext.currentTime >= nextStartTime - 0.05;
      if (playbackDone || performance.now() >= deadline) {
        isWaitingForPlayback = false;
        callback();
        return;
      }
      requestAnimationFrame(check);
    }
    requestAnimationFrame(check);
  }

  function handleIncomingAudio(arrayBuffer) {
    if (!audioContext || audioContext.state === 'closed') return;

    if (audioContext.state !== 'running') {
      audioContext.resume();
    }

    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }

    const audioBuffer = audioContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = audioContext.createBufferSource();
    const gainNode = audioContext.createGain();
    source.buffer = audioBuffer;
    gainNode.gain.value = 2.5;

    source.connect(gainNode);
    gainNode.connect(audioContext.destination);

    const currentTime = audioContext.currentTime;
    if (nextStartTime < currentTime) {
      nextStartTime = currentTime + 0.01;
    }

    source.start(nextStartTime);
    nextStartTime += audioBuffer.duration;
    tutorAvatar.classList.add('speaking');

    source.onended = () => {
      if (audioContext && audioContext.currentTime >= nextStartTime - 0.1) {
        tutorAvatar.classList.remove('speaking');
      }
    };
  }

  function startTimer() {
    clearInterval(timerInterval);
    timerInterval = setInterval(() => {
      seconds += 1;
      const minutes = String(Math.floor(seconds / 60)).padStart(2, '0');
      const secs = String(seconds % 60).padStart(2, '0');
      callTimer.textContent = `${minutes}:${secs}`;
    }, 1000);
  }

  function handleJsonMessage(data) {
    if (data.type === 'status' && data.text === 'connected') {
      isConnected = true;
      setStatus(t('vc.connected', 'Connected'));
      startCallBtn.classList.add('hidden');
      startCallBtn.disabled = false;
      startCallBtn.classList.remove('opacity-50');
      endCallBtn.classList.remove('hidden');
      recordWave.classList.remove('hidden');
      if (endTip) endTip.classList.remove('hidden');
      if (creditNotice) creditNotice.classList.add('hidden');
      recordLabel.textContent = data.user_speaks_first
        ? t('vc.say_hello_first', '💬 먼저 "안녕하세요"라고 말해보세요!')
        : t('vc.live_active', 'AI live conversation is active. Speak freely.');
      startTimer();
      fetchAndUpdateCredits();
      return;
    }

    if (data.type === 'user_transcript') {
      currentUserTranscript = data.text || '';
      renderPreview(currentUserTranscript);
      return;
    }

    if (data.type === 'ai_transcript_preview') {
      currentAiPreviewTranscript = data.text || '';
      if (!currentAiFinalTranscript) {
        renderPreview(currentAiPreviewTranscript);
      }
      return;
    }

    if (data.type === 'ai_transcript_final') {
      currentAiFinalTranscript = mergeTranscript(currentAiFinalTranscript, data.text);
      renderPreview(currentAiFinalTranscript);
      return;
    }

    if (data.type === 'turn_complete') {
      finalizeTurn();
      return;
    }

    if (data.type === 'call_concluded_by_ai') {
      stopMicInput();
      if (!isEndingCall) {
        // Brief pause lets any in-flight audio chunks arrive and get scheduled,
        // then endCall's waitForPlaybackEnd waits for actual playback to finish.
        setTimeout(() => { if (!isEndingCall) endCall(); }, 500);
      }
      return;
    }

    if (data.type === 'error') {
      console.error('Socket Error:', data.text);
      setStatus(data.text || t('vc.connection_error', 'Connection error'));
      cleanupAudio();
      resetControls('vc.ready', 'vc.press_to_start');
      if (socket && socket.readyState <= WebSocket.OPEN) {
        socket.close();
      }
    }
  }

  window.initiateLiveCall = async function() {
    if (isConnected || !currentScenario) return;

    isEndingCall = false;
    setStatus(t('vc.connecting', 'Connecting...'));
    startCallBtn.classList.add('opacity-50');
    startCallBtn.disabled = true;

    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        throw new Error('AudioContext not supported');
      }

      if (!audioContext) {
        audioContext = new AudioContextClass({ sampleRate: 16000 });
      }
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      
      if (!audioContext) return;

      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      if (!audioContext) return;
    } catch (error) {
      console.error('Initial audio/mic setup failed:', error);
      setStatus(t('vc.mic_error', 'Microphone access denied or audio not supported.'));
      resetControls('vc.ready', 'vc.press_to_start');
      return;
    }

    resetTimer();
    resetLivePreview();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/voice-call/${currentScenario.id}`;

    socket = new WebSocket(wsUrl);
    socket.binaryType = 'arraybuffer';

    socket.onopen = () => {
      setupAudioProcessing();
    };

    socket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        handleIncomingAudio(event.data);
        return;
      }

      try {
        const data = JSON.parse(event.data);
        handleJsonMessage(data);
      } catch (error) {
        console.error('Error parsing message:', error);
      }
    };

    socket.onclose = () => {
      if (!isWaitingForPlayback) cleanupAudio();
      clearInterval(timerInterval);
      isConnected = false;
      startCallBtn.disabled = false;
      startCallBtn.classList.remove('opacity-50');
      startCallBtn.classList.remove('hidden');
      endCallBtn.classList.add('hidden');
      recordWave.classList.add('hidden');
      if (endTip) endTip.classList.add('hidden');

      if (isEndingCall) {
        setStatus(t('vc.call_ended', 'Call ended'));
      } else {
        setStatus(t('vc.disconnected', 'Disconnected'));
        recordLabel.textContent = t('vc.press_to_start', 'Press the microphone button to start the live conversation');
      }

      isEndingCall = false;
    };

    socket.onerror = (error) => {
      console.error('WebSocket error:', error);
      setStatus(t('vc.connection_error', 'Connection error'));
    };
  };

  window.endCall = function() {
    if (isEndingCall) return;

    isEndingCall = true;
    const duration = callTimer ? callTimer.textContent : '00:00';

    clearInterval(timerInterval);
    stopMicInput();

    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'end_call' }));
      window.setTimeout(() => {
        if (socket && socket.readyState <= WebSocket.OPEN) {
          socket.close();
        }
      }, 300);
    }

    setStatus(t('vc.call_ended', 'Call ended'));
    resetControls('vc.call_ended', 'vc.press_to_start');

    // Wait for any remaining AI audio to finish before cleanup and summary modal
    waitForPlaybackEnd(() => {
      cleanupAudio();
      if (creditNotice) creditNotice.classList.remove('hidden');
      showSummaryModal(duration);
      fetchAndUpdateCredits().then(remaining => {
        if (remaining === null) return;
        const metaEl = summaryModal && summaryModal.querySelector('p.text-xs.text-white\\/40');
        if (metaEl) {
          metaEl.textContent += ` · ⚡${remaining} ${t('vc.credit_remaining_short', '남음')}`;
        }
      });
    });
  };

  document.addEventListener('app:translations-updated', () => {
    // renderScenarios(); // SSR 컨텐츠 보존을 위해 주석 처리
    syncAccessibilityLabels();
    if (!isConnected) {
      recordLabel.textContent = t('vc.press_to_start', 'Press the microphone button to start the live conversation');
      if (currentScenario) {
        setStatus(t('vc.waiting', 'Waiting'));
      }
    }
  });

  resetChatLog();
  resetTimer();
  resetControls();
  loadScenarios();
});
