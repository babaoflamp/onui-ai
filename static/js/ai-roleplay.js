    function escapeHtml(str) {
        return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
                          .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
    }

    function scrollToBottom() {
        // 사용자가 위로 스크롤 중이면 강제 이동하지 않음
        if (document.body.scrollHeight - window.scrollY - window.innerHeight > 200) return;
        window.scrollTo({ top: document.body.scrollHeight, behavior: 'instant' });
    }

    // ── TTS ──────────────────────────────────────────────────────────────
    let audioCtx        = null;
    let currentSource   = null;   // Web Audio BufferSourceNode
    let currentAudio    = null;   // fallback (unused when AudioContext works)
    let ttsAborted      = false;
    let activeListenBtn = null;

    function ensureAudioCtx() {
        if (!audioCtx || audioCtx.state === 'closed') {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        if (audioCtx.state === 'suspended') audioCtx.resume();
        return audioCtx;
    }

    function stopCurrent() {
        if (currentSource) { try { currentSource.stop(); } catch(e) {} currentSource = null; }
        if (currentAudio)  { currentAudio.pause(); currentAudio = null; }
    }

    const SPEAKER_ICON = `<svg class="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.617.784L4.17 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.17l4.213-3.784a1 1 0 011 .076zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.414z" clip-rule="evenodd"/></svg>`;
    const STOP_ICON   = `<svg class="w-3 h-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clip-rule="evenodd"/></svg>`;
    const SPIN_ICON   = `<svg class="w-3 h-3 flex-shrink-0 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;

    const BTN_IDLE    = 'flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-orange-500/10 text-white/30 hover:text-orange-400 rounded-full text-[10px] font-bold border border-white/5 hover:border-orange-500/20 transition-all';
    const BTN_LOADING = 'flex items-center gap-1.5 px-3 py-1.5 bg-white/5 text-white/20 rounded-full text-[10px] font-bold border border-white/5 transition-all cursor-not-allowed';
    const BTN_PLAYING = 'flex items-center gap-1.5 px-3 py-1.5 bg-orange-500/15 text-orange-400 rounded-full text-[10px] font-bold border border-orange-500/30 transition-all';

    function setListenIdle(btn) {
        btn.disabled = false;
        btn.className = BTN_IDLE;
        btn.innerHTML = SPEAKER_ICON + '<span>듣기</span>';
        delete btn.dataset.playing;
    }
    function setListenLoading(btn) {
        btn.disabled = true;
        btn.className = BTN_LOADING;
        btn.innerHTML = SPIN_ICON + '<span>로딩 중</span>';
    }
    function setListenPlaying(btn) {
        btn.disabled = false;
        btn.className = BTN_PLAYING;
        btn.innerHTML = STOP_ICON + '<span>정지</span>';
        btn.dataset.playing = '1';
    }

    async function playTTS(text, voice, onEnd) {
        const t = localStorage.getItem('auth_token');
        ttsAborted = false;
        stopCurrent();

        try {
            const resp = await fetch('/api/tts/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + (t || '') },
                body: JSON.stringify({ text, voice })
            });
            if (!resp.ok || ttsAborted) return;

            const arrayBuffer = await resp.arrayBuffer();
            if (ttsAborted) return;

            const ctx = ensureAudioCtx();
            const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
            if (ttsAborted) return;

            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            currentSource = source;

            source.onended = () => {
                currentSource = null;
                if (!ttsAborted && onEnd) onEnd();
            };

            if (activeListenBtn) setListenPlaying(activeListenBtn);
            source.start(0);
        } catch (e) {
            console.error('TTS error', e);
        }
    }

    function handleListen(btn, text) {
        if (!currentScenario?.tts_voice) return;

        // 현재 버튼이 재생 중 → 정지
        if (activeListenBtn === btn) {
            ttsAborted = true;
            stopCurrent();
            setListenIdle(btn);
            activeListenBtn = null;
            return;
        }

        // 다른 버튼이 재생 중 → 그 버튼 초기화
        if (activeListenBtn) {
            ttsAborted = true;
            stopCurrent();
            setListenIdle(activeListenBtn);
        }

        activeListenBtn = btn;
        setListenLoading(btn);
        ensureAudioCtx(); // 클릭 컨텍스트에서 즉시 unlock → fetch 완료 후에도 재생 허용

        playTTS(text, currentScenario.tts_voice, () => {
            setListenIdle(btn);
            if (activeListenBtn === btn) activeListenBtn = null;
            refreshCredits();
        });
    }

    // ── 크레딧 갱신 ──────────────────────────────────────────────────────
    function refreshCredits() {
        const t = localStorage.getItem('auth_token');
        if (!t) return;
        fetch('/api/credits', { headers: { 'Authorization': 'Bearer ' + t } })
            .then(r => r.ok ? r.json() : null)
            .then(d => {
                if (!d || !d.success) return;
                const bar = document.getElementById('credits-bar');
                const lbl = document.getElementById('credits-label');
                const pct = Math.max(0, Math.min(100, d.remaining / d.daily_limit * 100));
                if (lbl) lbl.textContent = d.remaining + ' / ' + d.daily_limit;
                if (bar) {
                    bar.style.width = pct + '%';
                    bar.style.background = pct <= 20
                        ? 'linear-gradient(90deg,#ef4444,#f87171)'
                        : 'linear-gradient(90deg,#f97316,#fbbf24)';
                }
            })
            .catch(() => {});
    }

    // ── 인증 ─────────────────────────────────────────────────────────────
    const token = localStorage.getItem('auth_token');
    if (!token) { window.location.href = '/login?redirect=/roleplay'; }

    const MAX_HISTORY = 20;

    let scenarios = [];
    let currentScenario = null;
    let chatHistory = [];
    let isRecording = false;
    let isSending = false;
    let recognition = null;

    // ── 음성 인식 ─────────────────────────────────────────────────────────
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'ko-KR';
        recognition.onresult = (event) => {
            document.getElementById('user-input').value = event.results[0][0].transcript;
            stopMic();
            sendMessage();
        };
        recognition.onerror = (event) => { console.error('Speech recognition error:', event.error); stopMic(); };
        recognition.onend = () => stopMic();
    }

    if (!recognition) {
        const micBtn = document.getElementById('mic-btn');
        micBtn.disabled = true;
        micBtn.title = '이 브라우저는 음성 인식을 지원하지 않습니다. (Chrome 권장)';
        micBtn.classList.add('opacity-30', 'cursor-not-allowed');
    }

    // ── 시나리오 로드 ─────────────────────────────────────────────────────
    async function loadScenarios() {
        try {
            const resp = await fetch('/api/roleplay/scenarios');
            scenarios = await resp.json();
            renderScenarios();
        } catch (e) {
            console.error('Failed to load scenarios', e);
            document.getElementById('scenario-selection').innerHTML = `
                <div class="col-span-full flex flex-col items-center justify-center py-16 text-center gap-4">
                    <p class="text-4xl">⚠️</p>
                    <p class="text-white/50 text-sm">시나리오를 불러오지 못했습니다.</p>
                    <button id="retry-btn" class="px-5 py-2 bg-orange-500/20 text-orange-400 rounded-xl text-xs font-bold hover:bg-orange-500/30 transition-all">다시 시도</button>
                </div>`;
            document.getElementById('retry-btn').addEventListener('click', loadScenarios);
        }
    }

    function renderScenarios() {
        const container = document.getElementById('scenario-selection');
        container.innerHTML = scenarios.map((s, idx) => `
            <div data-id="${escapeHtml(s.id)}" class="scenario-card cursor-pointer group animate-in fade-in slide-in-from-bottom-4 duration-500 overflow-hidden" style="animation-delay: ${idx * 0.04}s">
                <div class="relative aspect-square overflow-hidden bg-white">
                    ${s.image
                        ? `<img src="${escapeHtml(s.image)}" alt="${escapeHtml(s.title)}" class="w-full h-full object-contain group-hover:scale-105 transition-all duration-500 p-2" style="mix-blend-mode:multiply;" loading="lazy">`
                        : `<div class="w-full h-full flex items-center justify-center text-5xl">${escapeHtml(s.title.split(' ')[0])}</div>`
                    }
                    <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <div class="w-10 h-10 rounded-full bg-orange-500 flex items-center justify-center text-white text-lg shadow-lg">▶</div>
                    </div>
                    <span class="absolute top-2 left-2 px-2 py-0.5 bg-black/50 text-white/70 rounded-full text-[9px] font-black uppercase tracking-widest backdrop-blur-sm">${escapeHtml(s.level)}</span>
                </div>
                <div class="p-3">
                    <h3 class="text-sm font-black text-white truncate leading-tight">${escapeHtml(s.title.substring(s.title.indexOf(' ') + 1))}</h3>
                    <p class="text-white/40 text-[10px] mt-0.5 truncate">${escapeHtml(s.description)}</p>
                </div>
            </div>
        `).join('');
        container.querySelectorAll('[data-id]').forEach(card => {
            card.addEventListener('click', () => startRoleplay(card.dataset.id));
        });
    }

    let currentAvatarIcon = '/static/images/onui-sister-icon.png';
    let cachedAvatarEl = null; // 시나리오당 한 번만 생성, 이후 cloneNode 재사용

    function buildAvatarEl(src) {
        const wrap = document.createElement('div');
        wrap.className = 'w-10 h-10 rounded-full overflow-hidden flex-shrink-0 border-2 border-pink-400/30 shadow-[0_5px_15px_rgba(255,182,193,0.2)] mt-1 bg-white';
        const img = new Image();
        img.src = src;
        img.className = 'w-full h-full object-cover';
        img.onerror = () => { img.src = '/static/images/onui-pure-idol.webp'; };
        wrap.appendChild(img);
        return wrap;
    }

    function startRoleplay(id) {
        currentScenario = scenarios.find(s => s.id === id);
        if (!currentScenario) return;

        if (window.AI_AVATAR && typeof AI_AVATAR.updateOutfit === 'function') {
            AI_AVATAR.updateOutfit(currentScenario.title, currentScenario.image || null);
        }

        if (currentScenario.image) {
            currentAvatarIcon = currentScenario.image;
        } else if (currentScenario.title.includes('카페') || currentScenario.title.includes('주문')) {
            currentAvatarIcon = '/static/images/onui-idol-barista.png';
        } else if (currentScenario.title.includes('공항') || currentScenario.title.includes('체크인')) {
            currentAvatarIcon = '/static/images/onui-idol-staff.png';
        } else if (currentScenario.title.includes('병원') || currentScenario.title.includes('증상')) {
            currentAvatarIcon = '/static/images/onui-idol-nurse.png';
        } else {
            currentAvatarIcon = '/static/images/onui-sister-icon.png';
        }
        cachedAvatarEl = buildAvatarEl(currentAvatarIcon);

        document.getElementById('scenario-selection').classList.add('hidden');
        document.getElementById('chat-interface').classList.remove('hidden');
        document.getElementById('current-scenario-title').textContent = currentScenario.title;
        document.getElementById('current-scenario-level').textContent = `Level: ${currentScenario.level}`;

        document.getElementById('scenario-goals').innerHTML = currentScenario.goals.map(g =>
            `<span data-goal="${escapeHtml(g)}" class="px-4 py-2 bg-white/5 text-white/70 rounded-2xl text-xs font-bold border border-white/5 cursor-pointer hover:bg-orange-500/20 hover:text-orange-400 transition-all">✦ ${escapeHtml(g)}</span>`
        ).join('');
        document.querySelectorAll('#scenario-goals [data-goal]').forEach(el => {
            el.addEventListener('click', () => promptGoal(el.dataset.goal));
        });

        document.getElementById('chat-box').innerHTML = '';
        chatHistory = [];

        addMessage('ai', currentScenario.initial_message);
        chatHistory.push({role: 'assistant', content: currentScenario.initial_message});
    }

    function backToScenarios() {
        // 재생 중인 TTS 중단
        ttsAborted = true;
        stopCurrent();
        if (activeListenBtn) { setListenIdle(activeListenBtn); activeListenBtn = null; }

        document.getElementById('chat-interface').classList.add('hidden');
        document.getElementById('eval-modal').classList.add('hidden');
        document.getElementById('scenario-selection').classList.remove('hidden');
        currentScenario = null;
    }

    function promptGoal(goal) {
        document.getElementById('user-input').value = goal;
        sendMessage();
    }

    // ── 메시지 렌더링 ─────────────────────────────────────────────────────
    async function addMessage(role, text, isTyping = false, romanized = null, vocab = []) {
        const chatBox = document.getElementById('chat-box');
        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full gap-3 ${role === 'user' ? 'justify-end' : 'justify-start'} animate-in slide-in-from-${role === 'user' ? 'right' : 'left'}-4 fade-in duration-300`;

        if (role === 'ai') {
            wrapper.appendChild((cachedAvatarEl || buildAvatarEl(currentAvatarIcon)).cloneNode(true));
        }

        // AI 메시지는 버블 + 발음 + 듣기/어휘 버튼을 세로로 묶는 컬럼
        const col = document.createElement('div');
        col.className = `flex flex-col gap-1.5 max-w-[75%]`;

        const div = document.createElement('div');
        div.className = `p-5 font-medium leading-relaxed ${role === 'user' ? 'message-user' : 'message-ai'}`;
        col.appendChild(div);

        let romanizedEl = null;
        let vocabPanel = null;

        if (role === 'ai') {
            // 발음 기호 (타이핑 완료 후 표시)
            if (romanized) {
                romanizedEl = document.createElement('div');
                romanizedEl.className = 'pl-5 text-[11px] text-white/25 font-mono italic leading-relaxed hidden';
                romanizedEl.textContent = romanized;
                col.appendChild(romanizedEl);
            }

            const actionRow = document.createElement('div');
            actionRow.className = 'flex items-center gap-2 pl-1 flex-wrap';

            const listenBtn = document.createElement('button');
            listenBtn.className = BTN_IDLE;
            listenBtn.innerHTML = SPEAKER_ICON + '<span>듣기</span>';
            listenBtn.title = '⚡ 문장당 1 크레딧';
            listenBtn.addEventListener('click', () => handleListen(listenBtn, text));

            const creditTag = document.createElement('span');
            creditTag.className = 'text-[9px] text-white/15 font-medium';
            creditTag.textContent = '⚡ 문장당 1 크레딧';

            actionRow.appendChild(listenBtn);
            actionRow.appendChild(creditTag);

            // 핵심 어휘 토글 (vocab이 있을 때만)
            if (vocab && vocab.length > 0) {
                const vocabToggle = document.createElement('button');
                vocabToggle.className = 'flex items-center gap-1 px-3 py-1.5 bg-white/3 hover:bg-white/8 text-white/25 hover:text-white/50 rounded-full text-[10px] font-bold border border-white/5 transition-all ml-1';
                vocabToggle.innerHTML = '💡 <span class="vocab-lbl">어휘 ▼</span>';

                vocabPanel = document.createElement('div');
                vocabPanel.className = 'hidden px-4 py-3 bg-white/3 border border-white/5 rounded-2xl';

                const vocabTitle = document.createElement('div');
                vocabTitle.className = 'text-[9px] font-black text-white/25 uppercase tracking-widest mb-2';
                vocabTitle.textContent = '핵심 어휘';
                vocabPanel.appendChild(vocabTitle);

                const ul = document.createElement('ul');
                ul.className = 'space-y-1.5 list-none p-0 m-0';
                vocab.forEach(v => {
                    const li = document.createElement('li');
                    li.className = 'text-xs text-white/50';
                    li.innerHTML = `<span class="text-white/70 font-semibold">${escapeHtml(v.word)}</span> — ${escapeHtml(v.meaning)}`;
                    ul.appendChild(li);
                });
                vocabPanel.appendChild(ul);

                vocabToggle.addEventListener('click', () => {
                    const closing = !vocabPanel.classList.contains('hidden');
                    vocabPanel.classList.toggle('hidden', closing);
                    vocabToggle.querySelector('.vocab-lbl').textContent = closing ? '어휘 ▼' : '어휘 ▲';
                });

                actionRow.appendChild(vocabToggle);
                col.appendChild(actionRow);
                col.appendChild(vocabPanel);
            } else {
                col.appendChild(actionRow);
            }
        }

        wrapper.appendChild(col);
        chatBox.appendChild(wrapper);
        scrollToBottom();

        if (isTyping) {
            let skipped = false;
            div.addEventListener('click', () => { skipped = true; }, { once: true });
            div.style.cursor = 'pointer';
            div.title = '클릭하여 건너뛰기';
            for (let i = 0; i < text.length; i++) {
                if (skipped) break;
                div.textContent += text.charAt(i);
                await new Promise(r => setTimeout(r, 10));
            }
            div.textContent = text;
            div.style.cursor = '';
            div.title = '';
        } else {
            div.textContent = text;
        }
        // 타이핑 완료 후 발음 기호 표시
        if (romanizedEl) romanizedEl.classList.remove('hidden');
    }

    // ── 메시지 전송 ───────────────────────────────────────────────────────
    async function sendMessage() {
        if (isSending) return;
        const input = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');
        const micBtn = document.getElementById('mic-btn');
        const text = input.value.trim();
        if (!text || !currentScenario) return;

        isSending = true;
        input.disabled = true;
        sendBtn.disabled = true;
        micBtn.disabled = true;
        input.value = '';

        addMessage('user', text);
        chatHistory.push({role: 'user', content: text});

        if (window.AI_AVATAR) AI_AVATAR.setStatus('Thinking...');

        const typingId = 'typing-' + Date.now();
        const typingWrapper = document.createElement('div');
        typingWrapper.id = typingId;
        typingWrapper.className = 'flex w-full justify-start';
        const typingDiv = document.createElement('div');
        typingDiv.className = 'max-w-[80%] p-5 message-ai italic text-white/20';
        typingDiv.textContent = '...';
        typingWrapper.appendChild(typingDiv);
        document.getElementById('chat-box').appendChild(typingWrapper);
        scrollToBottom();

        try {
            const resp = await fetch('/api/roleplay/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scenario_id: currentScenario.id,
                    messages: chatHistory.slice(-MAX_HISTORY)
                })
            });

            if (resp.status === 401) { window.location.href = '/login?redirect=/roleplay'; return; }

            const data = await resp.json();
            document.getElementById(typingId).remove();
            if (window.AI_AVATAR) AI_AVATAR.setStatus(null);

            if (resp.status === 429 || data.error) {
                addMessage('ai', data.error || '크레딧이 부족합니다.');
                return;
            }

            if (data.message) {
                await addMessage('ai', data.message, true, data.romanized || null, data.vocab || []);
                chatHistory.push({role: 'assistant', content: data.message});
                refreshCredits();
            }
        } catch (e) {
            console.error('Chat error', e);
            document.getElementById(typingId)?.remove();
            addMessage('ai', '연결 오류가 발생했습니다. 다시 시도해 주세요.');
        } finally {
            isSending = false;
            input.disabled = false;
            sendBtn.disabled = false;
            if (recognition) micBtn.disabled = false;
            input.focus();
        }
    }

    // ── 마이크 ────────────────────────────────────────────────────────────
    function toggleMic() { if (!recognition) return; isRecording ? stopMic() : startMic(); }
    function startMic() {
        isRecording = true;
        recognition.start();
        document.getElementById('mic-btn').classList.add('recording-pulse');
    }
    function stopMic() {
        isRecording = false;
        recognition.stop();
        document.getElementById('mic-btn').classList.remove('recording-pulse');
    }

    // ── 평가 ──────────────────────────────────────────────────────────────
    async function finishRoleplay() {
        if (!currentScenario) return;
        if (chatHistory.length < 3) {
            addMessage('ai', '평가를 받으려면 조금 더 대화해보세요! 최소 한 번 이상 대화가 필요합니다.');
            return;
        }

        const btn = document.getElementById('finish-btn');
        const originalText = btn.textContent;
        btn.textContent = '분석 중...';
        btn.disabled = true;

        try {
            const resp = await fetch('/api/roleplay/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scenario_id: currentScenario.id, messages: chatHistory })
            });

            if (resp.status === 401) { window.location.href = '/login?redirect=/roleplay'; return; }

            const data = await resp.json();
            if (resp.status === 429 || data.error) {
                addMessage('ai', data.error || '크레딧이 부족합니다. 잠시 후 다시 시도하세요.');
                return;
            }
            if (!resp.ok) { addMessage('ai', 'Evaluation failed: ' + resp.status); return; }
            showEvalModal(data.result);
            refreshCredits();
        } catch (e) {
            addMessage('ai', '평가 중 오류가 발생했습니다. 다시 시도해 주세요.');
            console.error('Evaluate error', e);
        } finally {
            btn.textContent = originalText;
            btn.disabled = false;
        }
    }

    function showEvalModal(result) {
        if (!result || typeof result !== 'object') return;
        document.getElementById('eval-score').textContent = result.score ?? '-';
        document.getElementById('eval-feedback').textContent = result.feedback ?? '';
        document.getElementById('eval-strengths').innerHTML = (result.strengths ?? []).map(s => `<li>${s}</li>`).join('');
        document.getElementById('eval-improvements').innerHTML = (result.improvements ?? []).map(i => `<li>${i}</li>`).join('');
        document.getElementById('eval-modal').classList.remove('hidden');
    }

    function closeEvalModal() { document.getElementById('eval-modal').classList.add('hidden'); }

    document.getElementById('send-btn').onclick = sendMessage;
    document.getElementById('mic-btn').onclick = toggleMic;
    document.getElementById('user-input').onkeypress = (e) => { if (e.key === 'Enter') sendMessage(); };
    loadScenarios();
