  document.addEventListener("DOMContentLoaded", () => {
    let videoEl = document.getElementById('video-player');
    let transcripts = [];
    let currentSubtitleIndex = -1;
    let autoPauseFired = false;
    let savedVocab = [];
    let allVideos = [];
    let currentSpeed = 1.0;
    let currentVideoId = null;
    let currentOffset = 0;
    let activeLevel = 'all';
    let saveProgressTimer = null;
    let ttsAudio = null;

    const lobby             = document.getElementById('tube-lobby');
    const playerScreen      = document.getElementById('player-screen');
    const videoGrid         = document.getElementById('video-grid');
    const captionsContainer = document.getElementById('captions-container');
    const vocabList         = document.getElementById('vocab-list');
    const vocabEmpty        = document.getElementById('vocab-empty');
    const vocabCountEl      = document.getElementById('vocab-count');
    const subtitlePanelWords = document.getElementById('subtitle-panel-words');
    const subtitlePanelTrans = document.getElementById('subtitle-panel-trans');
    const wordDetail        = document.getElementById('word-detail');
    const wordDetailPos     = document.getElementById('word-detail-pos');
    const wordDetailLabel   = document.getElementById('word-detail-label');
    const wordDetailMean    = document.getElementById('word-detail-mean');
    const wordDetailTts     = document.getElementById('word-detail-tts');
    const wordDetailSave    = document.getElementById('word-detail-save');
    const autoPauseToggle   = document.getElementById('auto-pause-toggle');
    const btnBack           = document.getElementById('btn-back-lobby');
    const btnSpeed          = document.getElementById('btn-playback-speed');
    const speedLabel        = document.getElementById('speed-label');
    const btnPlayPause      = document.getElementById('btn-play-pause');
    const playIcon          = document.getElementById('play-icon');
    const progressFill      = document.getElementById('progress-fill');
    const progressWrapper   = document.getElementById('progress-wrapper');
    const timeCurrent       = document.getElementById('time-current');
    const timeTotal         = document.getElementById('time-total');
    const btnRewind         = document.getElementById('btn-rewind-sentence');
    const btnPrev           = document.getElementById('btn-prev-sentence');
    const btnNext           = document.getElementById('btn-next-sentence');
    const btnRestart        = document.getElementById('btn-restart');
    const searchInput       = document.getElementById('search-input');
    const searchBtn         = document.getElementById('search-btn');
    const showAllBtn        = document.getElementById('show-all-btn');
    const btnExport         = document.getElementById('btn-export-vocab');
    const btnOffsetMinus    = document.getElementById('btn-offset-minus');
    const btnOffsetPlus     = document.getElementById('btn-offset-plus');
    const offsetLabel       = document.getElementById('offset-label');

    // ── 토스트 알림 ─────────────────────────────────────
    function showToast(msg, type = 'info') {
      const colors = {
        success: 'bg-green-500 text-white',
        error:   'bg-red-500 text-white',
        warn:    'bg-orange-500 text-white',
        info:    'bg-white/10 backdrop-blur-md border border-white/20 text-white',
      };
      const toast = document.createElement('div');
      toast.className = `fixed bottom-8 left-1/2 -translate-x-1/2 z-[9999] px-5 py-2.5 rounded-2xl font-bold text-sm shadow-2xl transition-all duration-300 opacity-0 translate-y-3 ${colors[type] || colors.info}`;
      toast.innerText = msg;
      document.body.appendChild(toast);
      requestAnimationFrame(() => toast.classList.remove('opacity-0', 'translate-y-3'));
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-3');
        setTimeout(() => toast.remove(), 300);
      }, 2500);
    }

    // ── 자막 오프셋 조정 ────────────────────────────────
    function updateOffsetUI() {
      offsetLabel.innerText = (currentOffset >= 0 ? '+' : '') + currentOffset.toFixed(1) + 's';
      offsetLabel.parentElement.style.color = currentOffset !== 0 ? '#fb923c' : '';
    }
    btnOffsetMinus.onclick = () => {
      currentOffset = Math.round((currentOffset - 0.5) * 10) / 10;
      updateOffsetUI();
      handleTimeUpdate(videoEl.currentTime);
      console.log(`[OnuiTube] transcript_offset: ${currentOffset}`);
    };
    btnOffsetPlus.onclick = () => {
      currentOffset = Math.round((currentOffset + 0.5) * 10) / 10;
      updateOffsetUI();
      handleTimeUpdate(videoEl.currentTime);
      console.log(`[OnuiTube] transcript_offset: ${currentOffset}`);
    };

    // ── 우측 패널 자막 + 단어 상세 ──────────────────────
    function renderSubtitlePanel(line) {
      subtitlePanelWords.innerHTML = '';
      subtitlePanelTrans.textContent = line ? line.trans : '';
      wordDetail.classList.add('hidden');
      if (!line) return;
      line.words.forEach((wordObj) => {
        const span = document.createElement('span');
        span.className = 'panel-word';
        span.textContent = wordObj.label;
        span.addEventListener('click', () => {
          document.querySelectorAll('.panel-word.active').forEach(el => el.classList.remove('active'));
          span.classList.add('active');
          showWordDetail(wordObj);
        });
        subtitlePanelWords.appendChild(span);
      });
      // 첫 번째 단어 자동 선택
      const first = subtitlePanelWords.querySelector('.panel-word');
      if (first) { first.classList.add('active'); showWordDetail(line.words[0]); }
    }

    function showWordDetail(wordObj) {
      wordDetailPos.textContent = wordObj.pos || '';
      wordDetailLabel.textContent = wordObj.label;
      wordDetailMean.textContent = wordObj.mean || '';
      wordDetailTts.onclick = () => playWordTTS(wordObj.label);
      wordDetailSave.onclick = () => { addToVocab(wordObj); };
      wordDetail.classList.remove('hidden');
    }

    // ── TTS 발음 재생 ────────────────────────────────────
    async function playWordTTS(word) {
      try {
        if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
        const resp = await fetch('/api/tts/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: word }),
        });
        if (!resp.ok) throw new Error('TTS error');
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        ttsAudio = new Audio(url);
        ttsAudio.play();
        ttsAudio.onended = () => URL.revokeObjectURL(url);
      } catch {
        showToast(translations['yt.tts_failed'] || '발음 재생 실패', 'error');
      }
    }

    // ── 어휘 CSV 내보내기 ────────────────────────────────
    btnExport.onclick = async () => {
      try {
        const resp = await fetch('/api/tube/vocab/export');
        if (resp.status === 401) {
          showToast(translations['yt.login_required'] || '로그인 후 이용하세요.', 'warn');
          return;
        }
        if (!resp.ok) throw new Error('export failed');
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'onui-vocab.csv';
        a.click();
        URL.revokeObjectURL(url);
      } catch {
        showToast(translations['yt.export_failed'] || '내보내기 실패', 'error');
      }
    };

    // ── 로비 로드 ────────────────────────────────────────
    const initialVideos = window.__INITIAL_VIDEOS || [];

    async function loadLobby() {
      if (initialVideos && initialVideos.length > 0) {
        allVideos = initialVideos;
      } else {
        try {
          const resp = await fetch('/api/tube/videos');
          const data = await resp.json();
          if (data.success && data.videos && data.videos.length > 0) {
            allVideos = data.videos;
          } else {
            videoGrid.innerHTML = `<div class="col-span-full py-20 text-center text-white/50 font-black uppercase">${translations['yt.no_videos'] || '영상이 없습니다.'}</div>`;
            return;
          }
        } catch {
          videoGrid.innerHTML = `<div class="col-span-full py-20 text-center text-red-400 font-bold uppercase">${translations['yt.server_error'] || '서버 연결 오류.'}</div>`;
          return;
        }
      }
      // 저장된 검색어 복원
      const savedSearch = sessionStorage.getItem('tube_search');
      const savedLevel  = sessionStorage.getItem('tube_level');
      if (savedLevel) {
        activeLevel = savedLevel;
        document.querySelectorAll('.level-filter-btn').forEach(b => {
          b.classList.toggle('active', b.dataset.level === activeLevel);
        });
      }
      if (savedSearch) {
        searchInput.value = savedSearch;
      }
      applyFilters();
    }

    function renderGrid(videos) {
      videoGrid.innerHTML = '';
      if (videos.length === 0) {
        videoGrid.innerHTML = `<div class="col-span-full py-20 text-center text-white/40 font-black uppercase">${translations['yt.no_results'] || '검색 결과가 없습니다.'}</div>`;
        return;
      }
      const levelColors = { '1': 'bg-green-500 text-white', '2': 'bg-blue-500 text-white', '3': 'bg-purple-500 text-white' };
      videos.forEach((v, idx) => {
        const hasVideo = v.video_url && v.video_url.trim() !== '';
        const card = document.createElement('div');
        card.className = `shorts-card group ${hasVideo ? '' : 'coming-soon'} animate-in fade-in slide-in-from-bottom-4 duration-500`;
        card.style.animationDelay = `${idx * 0.04}s`;

        const posterHtml = v.poster_url
          ? `<img src="${v.poster_url}" class="w-full h-full object-cover" alt="${v.title}" loading="lazy">`
          : `<div class="w-full h-full flex items-center justify-center text-4xl bg-white/5">📱</div>`;

        const levelColor = levelColors[v.level] || 'bg-white/10 text-white/40';
        const savedPos = localStorage.getItem(`tube_pos_${v.id}`);

        card.innerHTML = `
          <div class="card-content">
            <div class="shorts-thumb">${posterHtml}</div>
            
            <!-- 상단 오버레이 (레벨 & 진행도) -->
            <div class="card-overlay-top">
              <span class="px-2 py-0.5 ${levelColor} text-[9px] font-black rounded-full shadow-sm">Lv.${v.level}</span>
              ${savedPos ? `<span class="text-[9px] font-black text-orange-400 drop-shadow-lg">▶ ${formatTime(parseFloat(savedPos))}</span>` : ''}
            </div>

            <!-- 하단 오버레이 (제목) -->
            <div class="card-overlay">
              <h3 class="text-xs font-black text-white leading-tight line-clamp-2 drop-shadow-md">${v.title}</h3>
            </div>

            <!-- 재생 아이콘 (호버 시) -->
            ${hasVideo
              ? `<div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all duration-300 z-10">
                   <div class="w-11 h-11 bg-white/20 backdrop-blur-md rounded-full flex items-center justify-center border border-white/30 shadow-2xl scale-90 group-hover:scale-100 transition-transform">
                     <svg class="w-6 h-6 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                   </div>
                 </div>`
              : `<div class="absolute inset-0 flex items-center justify-center z-10">
                   <span class="px-2 py-1 bg-black/60 backdrop-blur text-[10px] font-black text-white/60 rounded-full uppercase tracking-widest">준비 중</span>
                 </div>`}
          </div>
        `;
        if (hasVideo) card.onclick = () => initPlayer(v);
        videoGrid.appendChild(card);
      });
    }

    // ── 검색 + 레벨 필터 ────────────────────────────────
    function applyFilters() {
      const q = searchInput.value.trim().toLowerCase();
      let filtered = allVideos;
      if (activeLevel !== 'all') filtered = filtered.filter(v => v.level === activeLevel);
      if (q) filtered = filtered.filter(v =>
        (v.title && v.title.toLowerCase().includes(q)) ||
        (v.description && v.description.toLowerCase().includes(q))
      );
      renderGrid(filtered);
    }

    function doSearch() { applyFilters(); }

    searchBtn.onclick = doSearch;
    showAllBtn.onclick = () => {
      searchInput.value = '';
      activeLevel = 'all';
      document.querySelectorAll('.level-filter-btn').forEach(b => b.classList.toggle('active', b.dataset.level === 'all'));
      sessionStorage.removeItem('tube_search');
      sessionStorage.removeItem('tube_level');
      renderGrid(allVideos);
    };
    searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });

    document.querySelectorAll('.level-filter-btn').forEach(btn => {
      btn.onclick = () => {
        activeLevel = btn.dataset.level;
        document.querySelectorAll('.level-filter-btn').forEach(b => b.classList.toggle('active', b === btn));
        sessionStorage.setItem('tube_level', activeLevel);
        applyFilters();
      };
    });

    // ── 플레이어 초기화 ──────────────────────────────────
    function initPlayer(v) {
      currentVideoId = v.id;
      currentOffset = typeof v.transcript_offset === 'number' ? v.transcript_offset : 0;
      document.getElementById('player-title').innerText = v.title;
      document.getElementById('player-desc').innerText = v.description || '';

      videoEl.src = v.video_url;
      if (v.poster_url) {
        videoEl.poster = v.poster_url;
      } else {
        videoEl.removeAttribute('poster');
      }
      videoEl.load();
      currentSpeed = 1.0;
      speedLabel.innerText = '1.0x';
      videoEl.playbackRate = 1.0;
      updateOffsetUI();

      transcripts = [];
      currentSubtitleIndex = -1;
      autoPauseFired = false;
      captionsContainer.innerHTML = '';

      // 재생 위치 복원 (loadedmetadata 후)
      videoEl.addEventListener('loadedmetadata', () => {
        const saved = localStorage.getItem(`tube_pos_${currentVideoId}`);
        if (saved) {
          const pos = parseFloat(saved);
          if (pos > 3 && pos < videoEl.duration - 3) {
            videoEl.currentTime = pos;
            showToast(`${translations['yt.resume_at'] || '이어서 재생:'} ${formatTime(pos)}`, 'info');
          }
        }
        videoEl.play().catch(() => {});
      }, { once: true });

      // 자막 로드
      fetch(`/api/tube/transcripts/${v.id}`)
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json();
        })
        .then(data => {
          if (data.success && data.transcripts) {
            transcripts = data.transcripts;
            handleTimeUpdate(videoEl.currentTime);
          } else {
            showToast(translations['yt.captions_failed'] || '자막을 불러오지 못했어요.', 'warn');
          }
        })
        .catch(() => showToast(translations['yt.captions_failed'] || '자막을 불러오지 못했어요.', 'warn'));

      lobby.classList.add('hidden');
      playerScreen.classList.remove('hidden');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── 비디오 이벤트 ──────────────────────────────────
    videoEl.addEventListener('play', () => {
      playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
    });
    videoEl.addEventListener('pause', () => {
      playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
    });
    videoEl.addEventListener('ended', () => {
      if (currentVideoId) localStorage.removeItem(`tube_pos_${currentVideoId}`);
    });
    videoEl.addEventListener('timeupdate', () => {
      const cur = videoEl.currentTime;
      const dur = videoEl.duration || 0;
      if (dur > 0) {
        progressFill.style.width = `${(cur / dur) * 100}%`;
        timeCurrent.innerText = formatTime(cur);
        timeTotal.innerText = formatTime(dur);
      }
      // 재생 위치 주기적 저장 (2초 디바운스)
      if (currentVideoId && !videoEl.paused && dur > 0) {
        clearTimeout(saveProgressTimer);
        saveProgressTimer = setTimeout(() => {
          localStorage.setItem(`tube_pos_${currentVideoId}`, cur.toFixed(1));
        }, 2000);
      }
      handleTimeUpdate(cur);
    });

    btnPlayPause.onclick = () => {
      if (videoEl.paused) videoEl.play();
      else videoEl.pause();
    };

    progressWrapper.addEventListener('click', e => {
      const rect = progressWrapper.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      videoEl.currentTime = ratio * (videoEl.duration || 0);
    });

    btnSpeed.onclick = () => {
      const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
      let nextIdx = speeds.indexOf(currentSpeed) + 1;
      if (nextIdx >= speeds.length) nextIdx = 0;
      currentSpeed = speeds[nextIdx];
      videoEl.playbackRate = currentSpeed;
      speedLabel.innerText = `${currentSpeed}x`;
    };

    btnRestart.onclick = () => {
      videoEl.currentTime = 0;
      videoEl.play();
    };

    btnRewind.onclick = () => {
      if (!transcripts.length) return;
      const cur = videoEl.currentTime;
      let target = null;
      for (const t of transcripts) { if ((t.end + currentOffset) + 1 >= cur) { target = t; break; } }
      if (target) { videoEl.currentTime = target.start + currentOffset; videoEl.play(); }
    };

    btnPrev.onclick = () => {
      if (!transcripts.length) return;
      const idx = currentSubtitleIndex > 0 ? currentSubtitleIndex - 1 : 0;
      videoEl.currentTime = (transcripts[idx]?.start ?? 0) + currentOffset;
      videoEl.play();
    };

    btnNext.onclick = () => {
      if (!transcripts.length) return;
      const idx = Math.min(currentSubtitleIndex + 1, transcripts.length - 1);
      videoEl.currentTime = (transcripts[idx]?.start ?? 0) + currentOffset;
      videoEl.play();
    };

    function formatTime(sec) {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60).toString().padStart(2, '0');
      return `${m}:${s}`;
    }

    // ── 자막 처리 (auto-pause 버그 수정) ────────────────
    function handleTimeUpdate(time) {
      if (!transcripts.length) return;

      const active = transcripts.findIndex(s => time >= (s.start + currentOffset) && time < (s.end + currentOffset));

      if (active !== currentSubtitleIndex) {
        currentSubtitleIndex = active;
        autoPauseFired = false;
        document.querySelectorAll('.caption-word.active').forEach(el => el.classList.remove('active'));
        renderCaptions(active);
      }

      if (currentSubtitleIndex !== -1 && autoPauseToggle.checked && !autoPauseFired) {
        const cur = transcripts[currentSubtitleIndex];
        if (time >= (cur.end + currentOffset)) {
          autoPauseFired = true;
          videoEl.pause();
          videoEl.currentTime = cur.end + currentOffset;
        }
      }
    }

    function renderCaptions(index) {
      captionsContainer.innerHTML = '';
      if (index === -1) return;
      const line = transcripts[index];
      if (!line) return;
      const box = document.createElement('div');
      box.className = 'caption-box';
      const lineWrapper = document.createElement('div');

      line.words.forEach((wordObj) => {
        const span = document.createElement('span');
        span.className = 'caption-word relative';
        span.innerText = wordObj.label;

        span.addEventListener('click', (e) => {
          e.stopPropagation();
          // 패널에서 해당 단어 선택
          const panelSpan = Array.from(subtitlePanelWords.querySelectorAll('.panel-word'))
            .find(s => s.textContent === wordObj.label);
          if (panelSpan) {
            document.querySelectorAll('.panel-word.active').forEach(el => el.classList.remove('active'));
            panelSpan.classList.add('active');
          }
          showWordDetail(wordObj);
        });

        lineWrapper.appendChild(span);
        lineWrapper.appendChild(document.createTextNode(' '));
      });

      const transEl = document.createElement('div');
      transEl.className = 'caption-translation';
      transEl.innerText = line.trans;
      box.appendChild(lineWrapper);
      box.appendChild(transEl);
      captionsContainer.appendChild(box);

      // 패널 업데이트
      renderSubtitlePanel(line);
    }

    // ── 어휘 저장 ──────────────────────────────────────
    function renderVocabCard(wordObj) {
      vocabEmpty.style.display = 'none';
      const card = document.createElement('div');
      card.className = 'bg-white/5 border border-white/10 rounded-xl p-3 flex justify-between items-start hover:bg-white/10 transition-colors group';
      card.innerHTML = `
        <div class="flex-1 min-w-0 mr-2">
          <h4 class="text-sm font-black text-white mb-0.5 group-hover:text-orange-400 transition-colors">${wordObj.label}</h4>
          <p class="text-xs text-white/50">${wordObj.mean || wordObj.meaning || ''}</p>
        </div>
        <button class="tts-word-btn p-1.5 rounded-lg bg-white/10 hover:bg-orange-500/30 text-white/40 hover:text-orange-400 transition-all text-sm flex-shrink-0" title="발음 듣기">🔊</button>
      `;
      card.querySelector('.tts-word-btn').onclick = () => playWordTTS(wordObj.label);
      if (vocabList.firstChild && vocabList.firstChild !== vocabEmpty) {
        vocabList.insertBefore(card, vocabList.firstChild);
      } else {
        vocabList.insertBefore(card, vocabEmpty);
      }
      const wordsLabel = translations['yt.words_count'] || 'words';
      vocabCountEl.innerText = `${savedVocab.length} ${wordsLabel}`;
    }

    function addToVocab(wordObj) {
      if (savedVocab.find(w => w.label === wordObj.label)) {
        showToast(translations['yt.already_saved'] || '이미 저장된 단어예요.', 'warn');
        return;
      }
      savedVocab.push(wordObj);
      renderVocabCard(wordObj);
      showToast(`'${wordObj.label}' ${translations['yt.word_saved'] || '저장됨!'}`, 'success');
      const fd = new FormData();
      fd.append('label', wordObj.label);
      fd.append('pos', wordObj.pos || '');
      fd.append('meaning', wordObj.mean || '');
      fd.append('source', 'tube');
      fetch('/api/tube/vocab', { method: 'POST', body: fd })
        .catch(() => showToast(translations['yt.save_failed'] || '저장 오류', 'error'));
    }

    async function loadSavedVocab() {
      try {
        const resp = await fetch('/api/tube/vocab');
        const data = await resp.json();
        if (data.success && data.vocab.length > 0) {
          data.vocab.forEach(w => {
            if (!savedVocab.find(v => v.label === w.label)) {
              savedVocab.push(w);
              renderVocabCard(w);
            }
          });
        }
      } catch {}
    }

    // ── 뒤로 가기 ──────────────────────────────────────
    btnBack.onclick = () => {
      videoEl.pause();
      videoEl.src = '';
      captionsContainer.innerHTML = '';
      transcripts = [];
      currentSubtitleIndex = -1;
      autoPauseFired = false;
      // 검색/필터 상태 세션에 저장
      sessionStorage.setItem('tube_search', searchInput.value);
      sessionStorage.setItem('tube_level', activeLevel);
      playerScreen.classList.add('hidden');
      lobby.classList.remove('hidden');
    };

    // 초기 로드
    loadSavedVocab();
    loadLobby();
  });
