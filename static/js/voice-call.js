/**
 * Voice Call Real-time (Gemini Live) Implementation
 */
document.addEventListener('DOMContentLoaded', () => {
  let scenarios = [];
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
  const tutorName = document.getElementById('tutor-name');
  const scenarioList = document.getElementById('scenario-list');
  const translateToggle = document.getElementById('translate-toggle');

  let isTranslationEnabled = true;

  if (translateToggle) {
    // Set initial visual state
    if (isTranslationEnabled) {
      translateToggle.classList.add('bg-orange-500/20', 'text-orange-400', 'border-orange-500/30');
      translateToggle.classList.remove('bg-white/5', 'text-white/50', 'border-white/10');
    }

    translateToggle.addEventListener('click', () => {
      isTranslationEnabled = !isTranslationEnabled;
      if (isTranslationEnabled) {
        translateToggle.classList.add('bg-orange-500/20', 'text-orange-400', 'border-orange-500/30');
        translateToggle.classList.remove('bg-white/5', 'text-white/50', 'border-white/10');
      } else {
        translateToggle.classList.remove('bg-orange-500/20', 'text-orange-400', 'border-orange-500/30');
        translateToggle.classList.add('bg-white/5', 'text-white/50', 'border-white/10');
      }
    });
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

  async function showSummaryModal(duration) {
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
    
    // Initial loading state
    const loadingState = document.createElement('div');
    loadingState.className = 'flex flex-col items-center justify-center py-8 text-white/50 animate-pulse';
    loadingState.innerHTML = '<span class="text-2xl mb-2">✨</span><p>AI 피드백 리포트를 생성 중입니다...</p>';
    contentArea.appendChild(loadingState);

    const footer = document.createElement('div');
    footer.className = 'p-6 bg-white/5 border-t border-white/10 shrink-0 flex gap-3';
    
    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.className = 'flex-1 rounded-[14px] bg-white/10 px-4 py-3 font-black text-white transition hover:bg-white/20';
    confirmBtn.textContent = '닫기 (대화 기록 보기)';
    confirmBtn.addEventListener('click', () => closeSummaryModal());
    
    const lobbyBtn = document.createElement('button');
    lobbyBtn.type = 'button';
    lobbyBtn.className = 'flex-1 rounded-[14px] bg-orange-500 px-4 py-3 font-black text-white transition hover:bg-orange-600';
    lobbyBtn.textContent = '로비로 돌아가기';
    lobbyBtn.addEventListener('click', () => returnToLobby());
    
    footer.append(confirmBtn, lobbyBtn);

    panel.append(header, contentArea, footer);
    summaryModal.appendChild(panel);
    document.body.appendChild(summaryModal);

    // Fetch AI Report
    if (bubbles.length > 0) {
      try {
        const response = await fetch('/api/voice-call/report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ transcript: bubbles })
        });
        const data = await response.json();
        
        loadingState.remove();
        
        if (data.report && typeof marked !== 'undefined') {
          const reportDiv = document.createElement('div');
          reportDiv.className = 'prose prose-invert prose-orange max-w-none';
          reportDiv.innerHTML = marked.parse(data.report);
          contentArea.appendChild(reportDiv);
        } else {
          // Fallback to basic transcript if API fails or marked is missing
          contentArea.innerHTML = '<p class="text-red-400 mb-4">리포트 생성에 실패했습니다. 대화 기록만 보여드립니다.</p>';
          bubbles.slice(-8).forEach((line) => {
            const row = document.createElement('p');
            row.className = 'border-b border-white/5 py-2';
            row.textContent = line;
            contentArea.appendChild(row);
          });
        }
      } catch (err) {
        console.error('Failed to generate report:', err);
        loadingState.remove();
        contentArea.innerHTML = '<p class="text-red-400">오류가 발생했습니다.</p>';
      }
    } else {
      loadingState.remove();
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
    if (!scenarioList) return;

    scenarioList.innerHTML = '';
    scenarios.forEach((scenario) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'scenario-card text-left';
      btn.setAttribute('aria-label', `${scenario.title} ${t('vc.select', 'Select')}`);
      btn.innerHTML = `
        <div class="relative aspect-square overflow-hidden bg-white/5">
          <img src="${scenario.avatar_url}" onerror="this.src='/static/images/onui-pure-idol.png'"
               alt="${scenario.tutor_name}"
               class="w-full h-full object-cover hover:scale-105 transition-all duration-500" />
          <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-center opacity-0 hover:opacity-100 transition-opacity pb-2">
            <span class="text-white text-xs font-black">▶ ${t('vc.select', 'Select')}</span>
          </div>
        </div>
        <div class="p-3">
          <h4 class="text-sm font-black text-white truncate">${scenario.title}</h4>
          <p class="text-orange-400 text-[10px] font-bold uppercase tracking-widest truncate mt-0.5">${scenario.tutor_name}</p>
        </div>`;
      btn.addEventListener('click', () => prepareCall(scenario));
      scenarioList.appendChild(btn);
    });
  }

  async function loadScenarios() {
    try {
      const response = await fetch('/api/voice-call/scenarios');
      const data = await response.json();
      if (data.success) {
        scenarios = data.scenarios;
        renderScenarios();
      } else {
        renderScenarioError();
      }
    } catch (error) {
      console.error(error);
      renderScenarioError();
    }
  }

  function prepareCall(scenario) {
    currentScenario = scenario;
    closeSummaryModal();
    lobby.classList.add('hidden');
    callScreen.classList.remove('hidden');
    tutorName.textContent = scenario.tutor_name;
    tutorAvatar.src = scenario.avatar_url;
    resetTimer();
    resetLivePreview();
    resetChatLog();
    resetControls('vc.waiting', 'vc.press_to_start');
  }

  async function setupAudioProcessing() {
    try {
      if (!audioContext || audioContext.state === 'closed' || audioContext.sampleRate !== 16000) {
        if (audioContext && audioContext.state !== 'closed') {
          await audioContext.close();
        }
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      }

      await audioContext.audioWorklet.addModule('/static/js/audio-processor.js');
      
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
      setStatus(t('vc.mic_error', 'Microphone access denied. Please allow mic access and refresh.'));
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
      stream.getTracks().forEach((track) => track.stop());
    }
    if (processor) {
      processor.disconnect();
    }
    try {
      if (typeof analyser !== 'undefined' && analyser) {
        analyser.disconnect();
      }
    } catch(e) {}
    
    if (mediaSourceNode) {
      mediaSourceNode.disconnect();
    }
    if (audioContext && audioContext.state !== 'closed') {
      audioContext.close();
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
      nextStartTime = currentTime + 0.05;
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
      recordLabel.textContent = t('vc.live_active', 'AI live conversation is active. Speak freely.');
      startTimer();
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
      console.log('AI signaled conversation end. Closing in 4s...');
      setTimeout(() => {
        if (isConnected) {
          endCall();
        }
      }, 4000); // 4 seconds delay to let audio finish playing
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
      if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      }
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      console.error('Mic access denied:', error);
      setStatus(t('vc.mic_error', 'Microphone access denied. Please allow mic access and refresh.'));
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
      cleanupAudio();
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
    cleanupAudio();

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
    showSummaryModal(duration);
  };

  document.addEventListener('app:translations-updated', () => {
    renderScenarios();
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
