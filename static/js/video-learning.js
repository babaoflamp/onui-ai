  document.addEventListener("DOMContentLoaded", () => {
    let ytPlayer = null;
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
    let timeUpdateInterval = null;

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

    // ── YouTube IFrame API ──────────────────────────────
    window.onYouTubeIframeAPIReady = () => {
      console.log("[OnuiTube] YouTube API Ready");
    };

    function initYouTubePlayer(videoId) {
      if (ytPlayer) {
        try { ytPlayer.destroy(); } catch(e) {}
      }
      
      const wrapper = document.getElementById('youtube-player-container');
      wrapper.innerHTML = '<div id="yt-player-target"></div>';
      
      const origin = window.location.origin;
      const referrer = window.location.href;

      ytPlayer = new YT.Player('yt-player-target', {
        height: '100%',
        width: '100%',
        videoId: videoId,
        host: 'https://www.youtube-nocookie.com',
        playerVars: {
          autoplay: 1,
          controls: 0, 
          modestbranding: 1,
          rel: 0,
          enablejsapi: 1,
          playsinline: 1,
          origin: origin,
          widget_referrer: referrer
        },
        events: {
          onReady: (event) => {
            console.log("[OnuiTube] YT Player Ready");
            startTimePolling();
          },
          onStateChange: (event) => {
            if (event.data === YT.PlayerState.PLAYING) {
              playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
            } else {
              playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
            }
          },
          onError: (event) => {
            console.error("[OnuiTube] YT Player Error:", event.data);
            showToast('영상을 불러오지 못했습니다. (Error: ' + event.data + ')', 'error');
          }
        }
      });
    }

    function startTimePolling() {
      if (timeUpdateInterval) clearInterval(timeUpdateInterval);
      timeUpdateInterval = setInterval(() => {
        if (ytPlayer && ytPlayer.getCurrentTime) {
          const cur = ytPlayer.getCurrentTime();
          const dur = ytPlayer.getDuration();
          updateProgressUI(cur, dur);
          handleTimeUpdate(cur);
        }
      }, 100); // 10fps for smooth subtitle sync
    }

    function updateProgressUI(cur, dur) {
      if (dur > 0) {
        progressFill.style.width = `${(cur / dur) * 100}%`;
        timeCurrent.innerText = formatTime(cur);
        timeTotal.innerText = formatTime(dur);
      }
    }

    // ── 토스트 알림 ─────────────────────────────────────
    function showToast(msg, type = 'info') {
      const toast = document.createElement('div');
      toast.className = `fixed bottom-8 left-1/2 -translate-x-1/2 z-[9999] px-5 py-2.5 rounded-2xl font-bold text-sm shadow-2xl transition-all duration-300 opacity-0 translate-y-3 bg-white/10 backdrop-blur-md border border-white/20 text-white`;
      toast.innerText = msg;
      document.body.appendChild(toast);
      requestAnimationFrame(() => toast.classList.remove('opacity-0', 'translate-y-3'));
      setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-3');
        setTimeout(() => toast.remove(), 300);
      }, 2500);
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderSavedVocab() {
      const vocabCount = savedVocab.length;
      vocabCountEl.innerText = `${vocabCount} word${vocabCount === 1 ? '' : 's'}`;

      if (!vocabCount) {
        vocabList.innerHTML = `
          <div id="vocab-empty" class="h-full flex flex-col items-center justify-center text-center opacity-50 py-8">
            <span class="text-3xl mb-2">📖</span>
            <p class="text-sm font-bold text-white">단어를 클릭해 저장하세요!</p>
            <p class="text-xs text-white/50 mt-1">저장한 단어가 여기 표시됩니다.</p>
          </div>
        `;
        return;
      }

      vocabList.innerHTML = savedVocab.map((item) => {
        const label = escapeHtml(item.label || '');
        const pos = escapeHtml(item.pos || '');
        const mean = escapeHtml(item.meaning || item.mean || '');
        return `
          <div class="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-black text-white leading-tight">${label}</div>
                ${pos ? `<div class="mt-1 text-[10px] uppercase tracking-widest text-orange-400 font-black">${pos}</div>` : ''}
                ${mean ? `<div class="mt-1.5 text-xs text-white/70 leading-relaxed">${mean}</div>` : ''}
              </div>
              <span class="shrink-0 rounded-full border border-orange-400/20 bg-orange-500/10 px-2 py-0.5 text-[10px] font-black text-orange-300">SAVED</span>
            </div>
          </div>
        `;
      }).join('');
    }

    async function loadSavedVocab() {
      try {
        const resp = await fetch('/api/tube/vocab');
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.success) {
          throw new Error(data.detail || data.error || '단어장을 불러오지 못했습니다.');
        }
        savedVocab = Array.isArray(data.vocab) ? data.vocab : [];
        renderSavedVocab();
      } catch (err) {
        console.error(err);
        showToast(err.message || '단어장을 불러오지 못했습니다.', 'error');
      }
    }

    // ── 자막 오프셋 조정 ────────────────────────────────
    function updateOffsetUI() {
      offsetLabel.innerText = (currentOffset >= 0 ? '+' : '') + currentOffset.toFixed(1) + 's';
      offsetLabel.parentElement.style.color = currentOffset !== 0 ? '#fb923c' : '';
    }
    btnOffsetMinus.onclick = () => {
      currentOffset = Math.round((currentOffset - 0.5) * 10) / 10;
      updateOffsetUI();
      if (ytPlayer) handleTimeUpdate(ytPlayer.getCurrentTime());
    };
    btnOffsetPlus.onclick = () => {
      currentOffset = Math.round((currentOffset + 0.5) * 10) / 10;
      updateOffsetUI();
      if (ytPlayer) handleTimeUpdate(ytPlayer.getCurrentTime());
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
      wordDetailMean.textContent = wordObj.mean || wordObj.meaning || '';
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
        showToast('발음 재생 실패', 'error');
      }
    }

    // ── 로비 로드 ────────────────────────────────────────
    async function loadLobby() {
      try {
        const resp = await fetch('/api/tube/videos');
        const data = await resp.json();
        if (data.success && data.videos) {
          allVideos = data.videos;
          renderGrid(allVideos);
        }
      } catch (err) {
        console.error(err);
      }
    }

    function renderGrid(videos) {
      videoGrid.innerHTML = '';
      videos.forEach((v, idx) => {
        const card = document.createElement('div');
        const hasTranscript = !!v.has_transcript;
        const isLearningReady = !!v.is_learning_ready;
        const catalogStatus = v.catalog_status || (isLearningReady ? 'ready' : (hasTranscript ? 'replacement_required' : 'transcript_missing'));
        const isPlayable = isLearningReady || catalogStatus === 'replacement_required';
        const coveragePct = Math.round((v.transcript_coverage || 0) * 100);
        let statusBadge = '';
        let statusLabel = '';

        if (catalogStatus === 'transcript_missing') {
          statusBadge = '<span class="px-2 py-0.5 bg-white/15 text-white/75 text-[9px] font-black rounded-full border border-white/15">자막 준비중</span>';
          statusLabel = 'SOON';
        } else if (catalogStatus === 'replacement_required') {
          statusBadge = `<span class="px-2 py-0.5 bg-rose-500/20 text-rose-200 text-[9px] font-black rounded-full border border-rose-300/20">교체 필요 ${coveragePct}%</span>`;
          statusLabel = '준비중';
        }

        card.className = `shorts-card group animate-in fade-in slide-in-from-bottom-4 duration-500 ${isPlayable ? '' : 'coming-soon'}`;
        card.style.animationDelay = `${idx * 0.04}s`;
        card.innerHTML = `
          <div class="card-content">
            <div class="shorts-thumb">
              <img src="${v.poster_url}" class="w-full h-full object-cover" alt="${v.title}" loading="lazy">
            </div>
            <div class="card-overlay-top">
              <span class="px-2 py-0.5 bg-orange-500 text-white text-[9px] font-black rounded-full shadow-sm">Lv.${v.level}</span>
              ${statusBadge}
            </div>
            <div class="card-overlay">
              <h3 class="text-xs font-black text-white leading-tight line-clamp-2 drop-shadow-md">${v.title}</h3>
            </div>
            <div class="absolute inset-0 flex items-center justify-center ${isPlayable ? 'opacity-0 group-hover:opacity-100' : 'opacity-100'} transition-all duration-300 z-10">
               <div class="w-11 h-11 bg-white/20 backdrop-blur-md rounded-full flex items-center justify-center border border-white/30 shadow-2xl scale-90 group-hover:scale-100 transition-transform">
                 ${isPlayable
                   ? '<svg class="w-6 h-6 text-white ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>'
                   : `<span class="text-[9px] font-black tracking-wide text-white/85">${statusLabel}</span>`}
               </div>
            </div>
          </div>
        `;
        card.onclick = () => {
          if (!isPlayable) {
            if (catalogStatus === 'transcript_missing') {
              showToast('이 영상은 자막 준비 후 열립니다.', 'info');
            } else {
              showToast(`현재 영상은 학습용 자막과 맞지 않아 교체 대상입니다. (${coveragePct}%)`, 'info');
            }
            return;
          }
          if (catalogStatus === 'replacement_required') {
            showToast(`자막 정합도가 낮아 추후 교체 예정이지만 현재는 열람 가능합니다. (${coveragePct}%)`, 'info');
          }
          initPlayer(v);
        };
        videoGrid.appendChild(card);
      });
    }

    // ── 플레이어 초기화 ──────────────────────────────────
    function initPlayer(v) {
      currentVideoId = v.id;
      currentOffset = v.transcript_offset || 0;
      document.getElementById('player-title').innerText = v.title;
      document.getElementById('player-desc').innerText = v.description || '';

      initYouTubePlayer(v.id);
      
      currentSpeed = 1.0;
      speedLabel.innerText = '1.0x';
      updateOffsetUI();

      transcripts = [];
      currentSubtitleIndex = -1;
      autoPauseFired = false;
      captionsContainer.innerHTML = '';

      // 자막 로드 (plural transcripts 키 사용 보장)
      fetch(`/api/tube/transcripts/${v.id}`)
        .then(r => r.json())
        .then(data => {
          if (data.success && data.transcripts) {
            transcripts = data.transcripts;
          }
        })
        .catch(console.error);

      lobby.classList.add('hidden');
      playerScreen.classList.remove('hidden');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── 컨트롤 이벤트 ──────────────────────────────────
    btnPlayPause.onclick = () => {
      if (!ytPlayer) return;
      const state = ytPlayer.getPlayerState();
      if (state === YT.PlayerState.PLAYING) ytPlayer.pauseVideo();
      else ytPlayer.playVideo();
    };

    btnRestart.onclick = () => {
      if (ytPlayer) ytPlayer.seekTo(0);
    };

    btnSpeed.onclick = () => {
      if (!ytPlayer) return;
      const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
      let nextIdx = speeds.indexOf(currentSpeed) + 1;
      if (nextIdx >= speeds.length) nextIdx = 0;
      currentSpeed = speeds[nextIdx];
      ytPlayer.setPlaybackRate(currentSpeed);
      speedLabel.innerText = `${currentSpeed}x`;
    };

    btnNext.onclick = () => {
      if (!transcripts.length || !ytPlayer) return;
      const idx = Math.min(currentSubtitleIndex + 1, transcripts.length - 1);
      ytPlayer.seekTo(transcripts[idx].start + currentOffset);
    };

    btnPrev.onclick = () => {
      if (!transcripts.length || !ytPlayer) return;
      const idx = Math.max(0, currentSubtitleIndex - 1);
      ytPlayer.seekTo(transcripts[idx].start + currentOffset);
    };

    function formatTime(sec) {
      const m = Math.floor(sec / 60);
      const s = Math.floor(sec % 60).toString().padStart(2, '0');
      return `${m}:${s}`;
    }

    function handleTimeUpdate(time) {
      if (!transcripts.length) return;

      const active = transcripts.findIndex(s => time >= (s.start + currentOffset) && time < (s.end + currentOffset));

      if (active !== currentSubtitleIndex) {
        currentSubtitleIndex = active;
        autoPauseFired = false;
        renderCaptions(active);
      }

      if (currentSubtitleIndex !== -1 && autoPauseToggle.checked && !autoPauseFired) {
        const cur = transcripts[currentSubtitleIndex];
        if (time >= (cur.end + currentOffset)) {
          autoPauseFired = true;
          ytPlayer.pauseVideo();
          ytPlayer.seekTo(cur.end + currentOffset);
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
        span.className = 'caption-word';
        span.innerText = wordObj.label;
        span.addEventListener('click', (e) => {
          e.stopPropagation();
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

      renderSubtitlePanel(line);
    }

    async function addToVocab(wordObj) {
      if (!wordObj?.label) return;
      const fd = new FormData();
      fd.append('label', wordObj.label);
      fd.append('pos', wordObj.pos || '');
      fd.append('meaning', wordObj.mean || wordObj.meaning || '');
      fd.append('source', 'tube');
      try {
        wordDetailSave.disabled = true;
        const resp = await fetch('/api/tube/vocab', { method: 'POST', body: fd });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || !data.success) {
          throw new Error(data.detail || data.error || '단어 저장에 실패했습니다.');
        }
        await loadSavedVocab();
        showToast(`'${wordObj.label}' 저장됨!`, 'success');
      } catch (err) {
        console.error(err);
        showToast(err.message || '단어 저장에 실패했습니다.', 'error');
      } finally {
        wordDetailSave.disabled = false;
      }
    }

    btnBack.onclick = () => {
      if (ytPlayer) ytPlayer.stopVideo();
      if (timeUpdateInterval) clearInterval(timeUpdateInterval);
      playerScreen.classList.add('hidden');
      lobby.classList.remove('hidden');
    };

    loadLobby();
    loadSavedVocab();
  });
