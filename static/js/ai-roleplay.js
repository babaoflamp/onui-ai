    const token = localStorage.getItem('auth_token');
    const nickname = localStorage.getItem('user_nickname');

    // Simple auth check
    if (!token) {
        window.location.href = '/login?redirect=/roleplay';
    }

    let scenarios = [];
    let currentScenario = null;
    let chatHistory = [];
    let isRecording = false;
    let recognition = null;

    // Initialize Speech Recognition
    if ('webkitSpeechRecognition' in window) {
        recognition = new webkitSpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'ko-KR';

        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById('user-input').value = text;
            stopMic();
            sendMessage();
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            stopMic();
        };

        recognition.onend = () => {
            stopMic();
        };
    }

    async function loadScenarios() {
        try {
            const resp = await fetch('/api/roleplay/scenarios');
            scenarios = await resp.json();
            renderScenarios();
        } catch (e) {
            console.error('Failed to load scenarios', e);
        }
    }

    function renderScenarios() {
        const container = document.getElementById('scenario-selection');
        container.innerHTML = scenarios.map((s, idx) => `
            <div onclick="startRoleplay('${s.id}')" class="scenario-card cursor-pointer group animate-in fade-in slide-in-from-bottom-4 duration-500 overflow-hidden" style="animation-delay: ${idx * 0.04}s">
                <div class="relative aspect-square overflow-hidden bg-white">
                    ${s.image
                        ? `<img src="${s.image}" alt="${s.title}" class="w-full h-full object-contain group-hover:scale-105 transition-all duration-500 p-2" style="mix-blend-mode:multiply;" loading="lazy">`
                        : `<div class="w-full h-full flex items-center justify-center text-5xl">${s.title.split(' ')[0]}</div>`
                    }
                    <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                        <div class="w-10 h-10 rounded-full bg-orange-500 flex items-center justify-center text-white text-lg shadow-lg">▶</div>
                    </div>
                    <span class="absolute top-2 left-2 px-2 py-0.5 bg-black/50 text-white/70 rounded-full text-[9px] font-black uppercase tracking-widest backdrop-blur-sm">${s.level}</span>
                </div>
                <div class="p-3">
                    <h3 class="text-sm font-black text-white truncate leading-tight">${s.title.substring(s.title.indexOf(' ') + 1)}</h3>
                    <p class="text-white/40 text-[10px] mt-0.5 truncate">${s.description}</p>
                </div>
            </div>
        `).join('');
    }

    let currentAvatarIcon = '/static/images/onui-sister-icon.png';

    function startRoleplay(id) {
        currentScenario = scenarios.find(s => s.id === id);
        if (!currentScenario) return;

        // --- 상하단 아바타 통합 의상 전환 ---
        if (window.AI_AVATAR && typeof AI_AVATAR.updateOutfit === 'function') {
            AI_AVATAR.updateOutfit(currentScenario.title, currentScenario.image || null);
        }
        
        // 채팅 프로필 경로 할당 (시나리오 image 필드 우선, 없으면 제목 기반 자동 선택)
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

        document.getElementById('scenario-selection').classList.add('hidden');
        document.getElementById('chat-interface').classList.remove('hidden');
        document.getElementById('current-scenario-title').textContent = currentScenario.title;
        document.getElementById('current-scenario-level').textContent = `Level: ${currentScenario.level}`;
        
        // Render goals
        document.getElementById('scenario-goals').innerHTML = currentScenario.goals.map(g => `
            <span onclick="promptGoal('${g}')" class="px-4 py-2 bg-white/5 text-white/70 rounded-2xl text-xs font-bold border border-white/5 cursor-pointer hover:bg-orange-500/20 hover:text-orange-400 transition-all" data-goal="${g}">✦ ${g}</span>
        `).join('');

        // Clear chat
        document.getElementById('chat-box').innerHTML = '';
        chatHistory = [];

        // Add initial message
        addMessage('ai', currentScenario.initial_message);
        chatHistory.push({role: 'assistant', content: currentScenario.initial_message});
        // TTS disabled as requested
    }

    function backToScenarios() {
        document.getElementById('chat-interface').classList.add('hidden');
        document.getElementById('eval-modal').classList.add('hidden');
        document.getElementById('scenario-selection').classList.remove('hidden');
        currentScenario = null;
    }

    function promptGoal(goal) {
        const input = document.getElementById('user-input');
        input.value = goal;
        sendMessage();
    }

    async function addMessage(role, text, isTyping = false) {
        const chatBox = document.getElementById('chat-box');
        const wrapper = document.createElement('div');
        wrapper.className = `flex w-full gap-3 ${role === 'user' ? 'justify-end' : 'justify-start'} animate-in slide-in-from-${role === 'user' ? 'right' : 'left'}-4 fade-in duration-300`;
        
        if (role === 'ai') {
            const avatar = document.createElement('div');
            avatar.className = "w-10 h-10 rounded-full overflow-hidden flex-shrink-0 border-2 border-pink-400/30 shadow-[0_5px_15px_rgba(255,182,193,0.2)] mt-1 bg-white";
            avatar.innerHTML = `<img src="${currentAvatarIcon}" onerror="this.src='/static/images/onui-pure-idol.webp'" class="w-full h-full object-cover">`;
            wrapper.appendChild(avatar);
        }

        const div = document.createElement('div');
        div.className = `max-w-[75%] p-5 font-medium leading-relaxed ${role === 'user' ? 'message-user' : 'message-ai'}`;
        
        wrapper.appendChild(div);
        chatBox.appendChild(wrapper);
        chatBox.scrollTop = chatBox.scrollHeight;

        if (isTyping) {
            for (let i = 0; i < text.length; i++) {
                div.textContent += text.charAt(i);
                chatBox.scrollTop = chatBox.scrollHeight;
                await new Promise(r => setTimeout(r, 30));
            }
        } else {
            div.textContent = text;
        }
    }

    async function sendMessage() {
        const input = document.getElementById('user-input');
        const text = input.value.trim();
        if (!text || !currentScenario) return;

        input.value = '';
        addMessage('user', text);
        chatHistory.push({role: 'user', content: text});

        if (window.AI_AVATAR) AI_AVATAR.setStatus('Thinking...');

        const typingId = 'typing-' + Date.now();
        const wrapper = document.createElement('div');
        wrapper.id = typingId;
        wrapper.className = 'flex w-full justify-start';
        const typingDiv = document.createElement('div');
        typingDiv.className = 'max-w-[80%] p-5 message-ai italic text-white/20';
        typingDiv.textContent = '...';
        wrapper.appendChild(typingDiv);
        document.getElementById('chat-box').appendChild(wrapper);
        document.getElementById('chat-box').scrollTop = document.getElementById('chat-box').scrollHeight;

        try {
            const resp = await fetch('/api/roleplay/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': token ? `Bearer ${token}` : ''
                },
                body: JSON.stringify({
                    scenario_id: currentScenario.id,
                    messages: chatHistory
                })
            });
            const data = await resp.json();
            
            document.getElementById(typingId).remove();
            if (window.AI_AVATAR) AI_AVATAR.setStatus(null);

            if (data.message) {
                addMessage('ai', data.message, true);
                chatHistory.push({role: 'assistant', content: data.message});
                // TTS disabled as requested
            }
        } catch (e) {
            console.error('Chat error', e);
            document.getElementById(typingId).textContent = 'Connection error.';
        }
    }

    function toggleMic() {
        if (!recognition) return alert('Voice recognition not supported.');
        isRecording ? stopMic() : startMic();
    }

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

    async function finishRoleplay() {
        if (!currentScenario || chatHistory.length < 3) {
            if (!confirm('End conversation now?')) return;
        }

        const btn = document.querySelector('[onclick="finishRoleplay()"]');
        const originalText = btn.textContent;
        btn.textContent = 'Analysing...';
        btn.disabled = true;

        try {
            const resp = await fetch('/api/roleplay/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scenario_id: currentScenario.id, messages: chatHistory })
            });
            const data = await resp.json();
            if (!resp.ok || data.error) {
                alert('Evaluation failed: ' + (data.error || resp.status));
                return;
            }
            showEvalModal(data.result);
        } catch (e) {
            alert('Evaluation failed: ' + e.message);
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
    window.onload = loadScenarios;
