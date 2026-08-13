    function tr(key, fallback) {
        return (typeof translations !== 'undefined' && translations[key]) || fallback;
    }

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
        btn.innerHTML = SPEAKER_ICON + '<span>' + tr('rp.listen', 'Listen') + '</span>';
        delete btn.dataset.playing;
    }
    function setListenLoading(btn) {
        btn.disabled = true;
        btn.className = BTN_LOADING;
        btn.innerHTML = SPIN_ICON + '<span>' + tr('rp.loading', 'Loading') + '</span>';
    }
    function setListenPlaying(btn) {
        btn.disabled = false;
        btn.className = BTN_PLAYING;
        btn.innerHTML = STOP_ICON + '<span>' + tr('rp.stop', 'Stop') + '</span>';
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
    let draggedScenarioId = null;
    let editingScenarioId = null;
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
            if (resp.status === 401) { window.location.href = '/login?redirect=/roleplay'; return; }
            if (!resp.ok) throw new Error(`Scenario request failed: ${resp.status}`);
            scenarios = await resp.json();
            renderScenarios();
        } catch (e) {
            console.error('Failed to load scenarios', e);
            document.getElementById('scenario-selection').innerHTML = `
                <div class="col-span-full flex flex-col items-center justify-center py-16 text-center gap-4">
                    <p class="text-4xl">⚠️</p>
                    <p class="text-white/50 text-sm">${tr('rp.scenario_load_error', 'Could not load scenarios.')}</p>
                    <button id="retry-btn" class="px-5 py-2 bg-orange-500/20 text-orange-400 rounded-xl text-xs font-bold hover:bg-orange-500/30 transition-all">${tr('rp.retry', 'Retry')}</button>
                </div>`;
            document.getElementById('retry-btn').addEventListener('click', loadScenarios);
        }
    }

    function renderScenarios() {
        const container = document.getElementById('scenario-selection');
        container.innerHTML = scenarios.map((s, idx) => {
            const title = s.is_custom ? s.title : s.title.substring(s.title.indexOf(' ') + 1);
            const customActions = s.is_custom ? `
                <div class="absolute top-2 right-2 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity z-10">
                    <button type="button" data-edit-id="${escapeHtml(s.id)}" class="px-2 py-1 bg-black/70 text-white/80 rounded-lg text-[9px]" title="${tr('rp.edit_scenario', 'Edit')}">✎</button>
                    <button type="button" data-delete-id="${escapeHtml(s.id)}" class="px-2 py-1 bg-red-500/70 text-white rounded-lg text-[9px]" title="${tr('rp.delete_scenario', 'Delete')}">×</button>
                </div>` : '';
            return `
            <div data-id="${escapeHtml(s.id)}" draggable="${s.is_custom ? 'true' : 'false'}" class="scenario-card ${s.is_custom ? 'custom-scenario-card' : ''} cursor-pointer group animate-in fade-in slide-in-from-bottom-4 duration-500 overflow-hidden" style="animation-delay: ${idx * 0.04}s">
                <div class="relative aspect-square overflow-hidden bg-white">
                    ${s.image
                        ? `<img src="${escapeHtml(s.image)}" alt="${escapeHtml(s.title)}" class="w-full h-full object-contain group-hover:scale-105 transition-all duration-500 p-2" style="mix-blend-mode:multiply;" loading="lazy">`
                        : `<div class="w-full h-full flex items-center justify-center text-5xl">${escapeHtml(s.is_custom ? '✦' : s.title.split(' ')[0])}</div>`
                    }
                    ${customActions}
                    <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <div class="w-10 h-10 rounded-full bg-orange-500 flex items-center justify-center text-white text-lg shadow-lg">▶</div>
                    </div>
                    <span class="absolute top-2 left-2 px-2 py-0.5 bg-black/50 text-white/70 rounded-full text-[9px] font-black uppercase tracking-widest backdrop-blur-sm">${escapeHtml(s.level)}</span>
                </div>
                <div class="p-3">
                    <h3 class="text-sm font-black text-white truncate leading-tight">${escapeHtml(title)}</h3>
                    <p class="text-white/40 text-[10px] mt-0.5 truncate">${escapeHtml(s.description || '')}</p>
                </div>
            </div>`;
        }).join('');
        container.querySelectorAll('[data-id]').forEach(card => {
            card.addEventListener('click', () => startRoleplay(card.dataset.id));
        });
        container.querySelectorAll('[data-edit-id]').forEach(button => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                openScenarioEditor(scenarios.find(s => s.id === button.dataset.editId));
            });
        });
        container.querySelectorAll('[data-delete-id]').forEach(button => {
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                deleteCustomScenario(button.dataset.deleteId);
            });
        });
        container.querySelectorAll('.custom-scenario-card').forEach(card => {
            card.addEventListener('dragstart', (event) => {
                draggedScenarioId = card.dataset.id;
                card.classList.add('is-dragging');
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', draggedScenarioId);
            });
            card.addEventListener('dragend', () => {
                draggedScenarioId = null;
                card.classList.remove('is-dragging');
                container.querySelectorAll('.custom-scenario-card').forEach(item => item.classList.remove('drag-over'));
            });
            card.addEventListener('dragover', (event) => {
                event.preventDefault();
                if (draggedScenarioId && draggedScenarioId !== card.dataset.id) card.classList.add('drag-over');
            });
            card.addEventListener('dragleave', () => card.classList.remove('drag-over'));
            card.addEventListener('drop', async (event) => {
                event.preventDefault();
                card.classList.remove('drag-over');
                if (!draggedScenarioId || draggedScenarioId === card.dataset.id) return;
                await moveCustomScenario(draggedScenarioId, card.dataset.id);
            });
        });
    }

    async function moveCustomScenario(sourceId, targetId) {
        const custom = scenarios.filter(s => s.is_custom);
        const sourceIndex = custom.findIndex(s => s.id === sourceId);
        const targetIndex = custom.findIndex(s => s.id === targetId);
        if (sourceIndex < 0 || targetIndex < 0) return;
        const [moved] = custom.splice(sourceIndex, 1);
        custom.splice(targetIndex, 0, moved);
        scenarios = scenarios.filter(s => !s.is_custom).concat(custom);
        renderScenarios();
        try {
            const resp = await fetch('/api/roleplay/scenarios/custom/reorder', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scenario_ids: custom.map(s => s.id) }),
            });
            if (!resp.ok) throw new Error('reorder failed');
        } catch (error) {
            console.error('Failed to save roleplay order:', error);
            await loadScenarios();
        }
    }

    const CUSTOM_ROLEPLAY_EXAMPLES = {
        hanok: { title: '한옥에서 다도 배우기', description: '한옥의 다도 선생님과 차를 마시며 한국의 예절과 전통문화를 배웁니다.', level: 'A2-B1', initial_message: '어서 오세요. 오늘은 한옥에서 차를 마시는 예절을 배워 보겠습니다.', persona: '한옥 다도 선생님', era: '전통 한옥과 현대 서울', speaking_style: '차분하고 예의 바른 말투', topics: ['다도 예절', '전통 차', '한국의 손님맞이'], goals: ['차를 권하고 감사 인사를 할 수 있습니다.', '전통 예절에 대해 질문할 수 있습니다.', '존댓말로 자신의 느낌을 표현할 수 있습니다.'], keywords: ['다도', '예절', '차를 우려내다'], tts_voice: 'Kore' },
        pansori: { title: '판소리 명창에게 소리 배우기', description: '판소리 명창과 대화하며 한국 전통 음악의 표현과 이야기를 배웁니다.', level: 'B1-B2', initial_message: '얼씨구! 소리를 배우러 왔는가? 먼저 장단에 맞춰 인사를 해 보게.', persona: '판소리 명창', era: '조선의 판소리 마당', speaking_style: '흥겹고 해학적인 말투', topics: ['판소리', '장단과 추임새', '흥부와 놀부'], goals: ['판소리의 특징을 질문할 수 있습니다.', '감탄과 추임새를 사용할 수 있습니다.', '이야기의 줄거리를 설명할 수 있습니다.'], keywords: ['얼씨구', '추임새', '장단'], tts_voice: 'Orus' },
        market: { title: '전통시장에서 흥정하기', description: '전통시장 상인과 대화하며 물건을 고르고 자연스럽게 흥정합니다.', level: 'A2-B1', initial_message: '어서 와요! 오늘 싱싱한 나물이 들어왔는데, 뭐 찾으세요?', persona: '정이 많은 전통시장 상인', era: '서울의 전통시장', speaking_style: '활기차고 정겨운 사투리가 섞인 말투', topics: ['물건 고르기', '가격 묻기', '흥정과 덤'], goals: ['원하는 물건의 상태를 물을 수 있습니다.', '가격을 묻고 흥정할 수 있습니다.', '덤과 감사 표현을 이해할 수 있습니다.'], keywords: ['싱싱하다', '얼마예요?', '덤'], tts_voice: 'Aoede' },
        jeju: { title: '제주 해녀와 바다 이야기', description: '제주 해녀에게 바다와 공동체, 제주도의 삶에 대해 듣습니다.', level: 'B1-B2', initial_message: '혼저 옵서예. 제주 바다가 궁금해서 왔구나? 바당 이야기를 들려줄게.', persona: '제주 해녀', era: '오늘날의 제주 바다', speaking_style: '따뜻한 제주 방언이 섞인 말투', topics: ['제주 바다', '해녀 공동체', '섬의 생활'], goals: ['지역 문화에 대해 질문할 수 있습니다.', '경험과 추억을 들을 수 있습니다.', '표준어와 방언의 차이를 알아들을 수 있습니다.'], keywords: ['해녀', '바당', '혼저 옵서예'], tts_voice: 'Charon' },
        kpop: { title: 'K-pop 프로듀서와 데뷔 준비하기', description: 'K-pop 프로듀서와 연습생의 콘셉트와 무대 준비에 대해 이야기합니다.', level: 'B1-B2', initial_message: '이번 곡의 콘셉트를 정해 봅시다. 어떤 이미지와 메시지를 보여 주고 싶나요?', persona: 'K-pop 프로듀서', era: '현대의 서울 음악 기획사', speaking_style: '빠르고 전문적이지만 격려하는 말투', topics: ['K-pop 콘셉트', '연습과 무대', '팀워크'], goals: ['자신의 의견을 설득력 있게 말할 수 있습니다.', '콘셉트와 장단점을 설명할 수 있습니다.', '피드백을 듣고 개선 방향을 제안할 수 있습니다.'], keywords: ['콘셉트', '무대', '피드백'], tts_voice: 'Puck' },
        royal: { title: '조선의 궁중 학자와 토론하기', description: '조선시대 궁중 학자와 백성을 위한 교육과 책에 대해 토론합니다.', level: 'B2', initial_message: '그대는 어떤 책을 읽고 무엇을 배우고자 하는가? 함께 지혜를 나누어 보세.', persona: '조선의 궁중 학자', era: '조선시대 궁궐의 서재', speaking_style: '논리적이고 품위 있는 옛말투', topics: ['책과 교육', '백성을 위한 지식', '토론과 근거'], goals: ['자신의 의견과 근거를 말할 수 있습니다.', '상대의 의견에 정중하게 반박할 수 있습니다.', '어려운 주제를 요약할 수 있습니다.'], keywords: ['지혜', '근거', '논하다'], tts_voice: 'Charon' },
        temple: { title: '사찰에서 스님과 마음공부하기', description: '한국 사찰의 스님과 차분히 대화하며 마음과 일상의 균형을 생각합니다.', level: 'B1-B2', initial_message: '어서 오십시오. 이곳에 오신 마음의 짐은 무엇입니까?', persona: '산속 사찰의 스님', era: '한국의 전통 사찰', speaking_style: '차분하고 은유적인 말투', topics: ['마음과 감정', '명상과 쉼', '일상의 균형'], goals: ['자신의 감정을 설명할 수 있습니다.', '조언을 듣고 자신의 생각을 말할 수 있습니다.', '은유적인 표현을 이해할 수 있습니다.'], keywords: ['마음', '쉼', '깨닫다'], tts_voice: 'Kore' },
        webtoon: { title: '웹툰 작가와 다음 화 기획하기', description: 'K-웹툰 작가와 캐릭터와 줄거리를 만들며 창의적으로 대화합니다.', level: 'B1-B2', initial_message: '이번 화의 주인공에게 어떤 사건을 맡기면 독자들이 재미있어할까요?', persona: 'K-웹툰 작가', era: '현대의 서울 웹툰 작업실', speaking_style: '창의적이고 활발한 말투', topics: ['캐릭터 설정', '줄거리와 반전', '독자 반응'], goals: ['이야기의 아이디어를 제안할 수 있습니다.', '인물의 성격과 사건을 설명할 수 있습니다.', '다른 아이디어를 발전시킬 수 있습니다.'], keywords: ['주인공', '반전', '연재'], tts_voice: 'Aoede' },
        baseball: { title: '한국 야구 해설가와 경기 보기', description: '한국 야구 해설가와 경기 흐름과 응원 문화를 이야기합니다.', level: 'A2-B1', initial_message: '오늘 경기는 초반부터 팽팽합니다! 어느 팀을 응원하세요?', persona: '한국 프로야구 해설가', era: '현대의 야구 경기장', speaking_style: '열정적이고 생생한 해설 말투', topics: ['경기 흐름', '선수와 기록', '응원 문화'], goals: ['경기 상황을 설명할 수 있습니다.', '좋아하는 팀과 이유를 말할 수 있습니다.', '감탄과 응원 표현을 사용할 수 있습니다.'], keywords: ['응원하다', '홈런', '역전'], tts_voice: 'Orus' },
        snack: { title: '분식집에서 떡볶이 주문하기', description: '동네 분식집 사장님과 떡볶이와 한국의 간식 문화를 이야기합니다.', level: 'A1-A2', initial_message: '어서 와! 떡볶이 맵기는 어느 정도로 해 줄까?', persona: '동네 분식집 사장님', era: '현대의 서울 분식집', speaking_style: '친근하고 활기찬 반말 섞인 말투', topics: ['분식 주문', '매운맛 표현', '한국 간식'], goals: ['음식의 맛과 양을 말할 수 있습니다.', '주문 내용을 확인할 수 있습니다.', '한국 간식에 대해 질문할 수 있습니다.'], keywords: ['떡볶이', '맵다', '튀김'], tts_voice: 'Puck' },
    };

    function applyRoleplayExample(key) {
        const example = CUSTOM_ROLEPLAY_EXAMPLES[key];
        if (!example) return;
        const form = document.getElementById('custom-scenario-form');
        ['title', 'description', 'level', 'initial_message', 'persona', 'era', 'speaking_style', 'tts_voice'].forEach(field => {
            form.elements[field].value = example[field];
        });
        ['topics', 'goals', 'keywords'].forEach(field => {
            form.elements[field].value = example[field].join(', ');
        });
    }

    function splitFormList(value) {
        return value.split(',').map(item => item.trim()).filter(Boolean).slice(0, 8);
    }

    async function generateCustomCharacterImage(form) {
        const situation = [
            form.elements.persona.value.trim(), form.elements.era.value.trim(),
            form.elements.title.value.trim(), form.elements.description.value.trim(),
            form.elements.speaking_style.value.trim(),
        ].filter(Boolean).join(', ');
        if (!situation) {
            throw new Error(tr('rp.image_need_details', 'Enter a title or character first.'));
        }
        const resp = await fetch('/api/generate-image', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ situation, style: 'roleplay-card', quality: 'standard' }),
        });
        if (resp.status === 401) { window.location.href = '/login?redirect=/roleplay'; return null; }
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.success || !data.image_url) {
            throw new Error(data.message || tr('rp.image_error', 'Could not generate the image.'));
        }
        return data.image_url;
    }

    function openScenarioEditor(scenario = null) {
        editingScenarioId = scenario?.id || null;
        const editor = document.getElementById('custom-scenario-editor');
        const form = document.getElementById('custom-scenario-form');
        form.reset();
        document.getElementById('roleplay-example-select').value = '';
        form.elements.image.value = '';
        const defaults = { persona: '대화 상대', era: '현대', speaking_style: '친절하고 자연스러운 말투', level: 'B1', tts_voice: 'Kore' };
        Object.entries(defaults).forEach(([key, value]) => { form.elements[key].value = value; });
        if (scenario) {
            ['title', 'description', 'level', 'initial_message', 'persona', 'era', 'speaking_style', 'tts_voice'].forEach(key => {
                form.elements[key].value = scenario[key] || '';
            });
            ['topics', 'goals', 'keywords'].forEach(key => { form.elements[key].value = (scenario[key] || []).join(', '); });
            form.elements.image.value = scenario.image || '';
        }
        document.getElementById('custom-editor-title').textContent = scenario ? tr('rp.edit_scenario', 'Edit My Roleplay') : tr('rp.create_scenario', 'Create My Roleplay');
        document.getElementById('delete-scenario-btn').classList.toggle('hidden', !scenario);
        editor.classList.remove('hidden');
        editor.scrollIntoView({ behavior: 'smooth', block: 'start' });
        form.elements.title.focus();
    }

    function closeScenarioEditor() {
        editingScenarioId = null;
        document.getElementById('custom-scenario-editor').classList.add('hidden');
    }

    async function saveCustomScenario(event) {
        event.preventDefault();
        const form = event.currentTarget;
        const payload = {
            title: form.elements.title.value.trim(), description: form.elements.description.value.trim(),
            level: form.elements.level.value.trim(), initial_message: form.elements.initial_message.value.trim(),
            persona: form.elements.persona.value.trim(), era: form.elements.era.value.trim(),
            speaking_style: form.elements.speaking_style.value.trim(), tts_voice: form.elements.tts_voice.value,
            image: form.elements.image.value.trim() || null,
            topics: splitFormList(form.elements.topics.value), goals: splitFormList(form.elements.goals.value),
            keywords: splitFormList(form.elements.keywords.value),
        };
        const url = editingScenarioId ? `/api/roleplay/scenarios/custom/${encodeURIComponent(editingScenarioId)}` : '/api/roleplay/scenarios/custom';
        const submitButton = form.querySelector('button[type="submit"]');
        const originalSubmitText = submitButton.textContent;
        submitButton.disabled = true;
        try {
            if (!editingScenarioId && !payload.image) {
                submitButton.textContent = tr('rp.generating_and_saving', 'Generating image and saving...');
                payload.image = await generateCustomCharacterImage(form);
            }
            submitButton.textContent = tr('rp.saving_scenario', 'Saving...');
            const resp = await fetch(url, { method: editingScenarioId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            if (resp.status === 401) { window.location.href = '/login?redirect=/roleplay'; return; }
            if (!resp.ok) { const data = await resp.json().catch(() => ({})); throw new Error(data.detail || tr('rp.save_error', 'Could not save scenario.')); }
            closeScenarioEditor();
            await loadScenarios();
        } catch (error) { window.alert(error.message); }
        finally { submitButton.disabled = false; submitButton.textContent = originalSubmitText; }
    }

    async function deleteCustomScenario(id) {
        if (!window.confirm(tr('rp.confirm_delete', 'Delete this roleplay?'))) return;
        try {
            const resp = await fetch(`/api/roleplay/scenarios/custom/${encodeURIComponent(id)}`, { method: 'DELETE' });
            if (!resp.ok) throw new Error(tr('rp.delete_error', 'Could not delete scenario.'));
            if (editingScenarioId === id) closeScenarioEditor();
            await loadScenarios();
        } catch (error) { window.alert(error.message); }
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
        document.getElementById('current-scenario-level').textContent = `${tr('rp.level_label', 'Level')}: ${currentScenario.level}`;

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
            listenBtn.innerHTML = SPEAKER_ICON + '<span>' + tr('rp.listen', 'Listen') + '</span>';
            listenBtn.title = tr('rp.credit_sentence', '⚡ 1 credit per sentence');
            listenBtn.addEventListener('click', () => handleListen(listenBtn, text));

            const creditTag = document.createElement('span');
            creditTag.className = 'text-[9px] text-white/15 font-medium';
            creditTag.textContent = tr('rp.credit_sentence', '⚡ 1 credit per sentence');

            actionRow.appendChild(listenBtn);
            actionRow.appendChild(creditTag);

            // 핵심 어휘 토글 (vocab이 있을 때만)
            if (vocab && vocab.length > 0) {
                const vocabToggle = document.createElement('button');
                vocabToggle.className = 'flex items-center gap-1 px-3 py-1.5 bg-white/3 hover:bg-white/8 text-white/25 hover:text-white/50 rounded-full text-[10px] font-bold border border-white/5 transition-all ml-1';
                vocabToggle.innerHTML = '💡 <span class="vocab-lbl">' + tr('rp.vocab', 'Vocabulary') + ' ▼</span>';

                vocabPanel = document.createElement('div');
                vocabPanel.className = 'hidden px-4 py-3 bg-white/3 border border-white/5 rounded-2xl';

                const vocabTitle = document.createElement('div');
                vocabTitle.className = 'text-[9px] font-black text-white/25 uppercase tracking-widest mb-2';
                vocabTitle.textContent = tr('rp.vocab_title', 'Key vocabulary');
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
                    vocabToggle.querySelector('.vocab-lbl').textContent = tr('rp.vocab', 'Vocabulary') + (closing ? ' ▼' : ' ▲');
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

        if (window.AI_AVATAR) AI_AVATAR.setStatus(tr('rp.thinking', 'Thinking...'));

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
            addMessage('ai', tr('rp.connection_error', 'A connection error occurred. Please try again.'));
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
            addMessage('ai', tr('rp.need_more_chat', 'Please have at least one more exchange before requesting an evaluation.'));
            return;
        }

        const btn = document.getElementById('finish-btn');
        const originalText = btn.textContent;
        btn.textContent = tr('rp.evaluating', 'Analyzing...');
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
                addMessage('ai', data.error || tr('rp.credit_error', 'Not enough credits. Please try again later.'));
                return;
            }
            if (!resp.ok) { addMessage('ai', tr('rp.evaluation_failed', 'Evaluation failed') + ': ' + resp.status); return; }
            showEvalModal(data.result);
            refreshCredits();
        } catch (e) {
            addMessage('ai', tr('rp.evaluation_error', 'Evaluation failed. Please try again.'));
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
        const renderEvalItems = (items) => {
            const fragment = document.createDocumentFragment();
            (Array.isArray(items) ? items : []).forEach(item => {
                const li = document.createElement('li');
                li.textContent = String(item);
                fragment.appendChild(li);
            });
            return fragment;
        };
        const strengths = document.getElementById('eval-strengths');
        const improvements = document.getElementById('eval-improvements');
        strengths.replaceChildren(renderEvalItems(result.strengths));
        improvements.replaceChildren(renderEvalItems(result.improvements));
        document.getElementById('eval-modal').classList.remove('hidden');
    }

    function closeEvalModal() { document.getElementById('eval-modal').classList.add('hidden'); }

    document.getElementById('create-scenario-btn').onclick = () => {
        try {
            openScenarioEditor();
        } catch (error) {
            console.error('Failed to open custom roleplay editor:', error);
        }
    };
    document.getElementById('cancel-scenario-btn').onclick = closeScenarioEditor;
    document.getElementById('back-scenario-btn').onclick = () => {
        closeScenarioEditor();
        document.getElementById('scenario-selection').scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
    document.getElementById('cancel-scenario-btn-bottom').onclick = closeScenarioEditor;
    document.getElementById('custom-scenario-form').addEventListener('submit', saveCustomScenario);
    document.getElementById('roleplay-example-select').addEventListener('change', (event) => applyRoleplayExample(event.target.value));
    document.getElementById('delete-scenario-btn').onclick = () => deleteCustomScenario(editingScenarioId);
    document.getElementById('send-btn').onclick = sendMessage;
    document.getElementById('mic-btn').onclick = toggleMic;
    document.getElementById('user-input').onkeypress = (e) => { if (e.key === 'Enter') sendMessage(); };
    loadScenarios().catch(error => console.error('Roleplay initialization failed:', error));
