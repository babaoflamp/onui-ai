  document.addEventListener("DOMContentLoaded", () => {
    const AUTO_PAUSE_GRACE_SECONDS = 0.15;

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
    let pendingResumeTime = 0;
    let progressByVideo = {};
    let videoProgressFailureCount = 0;
    let videoProgressRetryAt = 0;
    let ttsAudio = null;
    let timeUpdateInterval = null;
    let vocabularyLookup = null;
    let isYouTubeApiReady = !!(window.YT && window.YT.Player);
    let youtubeReadyResolvers = [];

    const lobby             = document.getElementById('tube-lobby');
    const playerScreen      = document.getElementById('player-screen');
    const videoGrid         = document.getElementById('video-grid');
    const videoPlayer       = document.getElementById('video-player');
    const youtubeContainer  = document.getElementById('youtube-player-container');
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

    function getCookie(name) {
      const encodedName = encodeURIComponent(name) + '=';
      return document.cookie
        .split(';')
        .map((item) => item.trim())
        .find((item) => item.startsWith(encodedName))
        ?.slice(encodedName.length) || '';
    }

    function getCurrentUserId() {
      return getCookie('user_id');
    }

    function getAuthHeaders(extra = {}) {
      const token = localStorage.getItem('auth_token');
      return token ? { ...extra, Authorization: `Bearer ${token}` } : extra;
    }

    function getInitialVideos() {
      return Array.isArray(window.__INITIAL_VIDEOS) ? window.__INITIAL_VIDEOS : [];
    }

    function renderLobbyError(message) {
      videoGrid.innerHTML = `
        <div class="col-span-full py-20 text-center text-white/35 font-black uppercase tracking-widest">
          ${escapeHtml(message)}
        </div>
      `;
    }

    // ── YouTube IFrame API ──────────────────────────────
    window.onYouTubeIframeAPIReady = () => {
      console.log("[OnuiTube] YouTube API Ready");
      isYouTubeApiReady = true;
      youtubeReadyResolvers.forEach((resolve) => resolve());
      youtubeReadyResolvers = [];
    };

    function waitForYouTubeApi() {
      if (window.YT && window.YT.Player) {
        isYouTubeApiReady = true;
        return Promise.resolve();
      }

      return new Promise((resolve, reject) => {
        youtubeReadyResolvers.push(resolve);
        window.setTimeout(() => {
          if (isYouTubeApiReady || (window.YT && window.YT.Player)) {
            resolve();
            return;
          }
          reject(new Error('YouTube player API did not load.'));
        }, 8000);
      });
    }

    function extractYouTubeVideoId(video) {
      const rawUrl = String(video.video_url || '').trim();
      const rawId = String(video.id || '').trim();

      if (/^[a-zA-Z0-9_-]{11}$/.test(rawId)) return rawId;
      if (!rawUrl) return rawId;

      try {
        const url = new URL(rawUrl, window.location.origin);
        const queryId = url.searchParams.get('v');
        if (queryId) return queryId;

        const parts = url.pathname.split('/').filter(Boolean);
        const embedIndex = parts.findIndex((part) => part === 'embed' || part === 'shorts');
        if (embedIndex !== -1 && parts[embedIndex + 1]) return parts[embedIndex + 1];
        if (url.hostname.includes('youtu.be') && parts[0]) return parts[0];
      } catch (error) {
        console.warn('[OnuiTube] Unable to parse YouTube URL:', rawUrl, error);
      }

      return rawId;
    }

    async function initYouTubePlayer(video) {
      const videoId = extractYouTubeVideoId(video);
      if (!videoId) {
        showToast('YouTube 영상 ID를 찾지 못했습니다.', 'error');
        return false;
      }

      try {
        await waitForYouTubeApi();
      } catch (error) {
        console.error('[OnuiTube] YouTube API unavailable:', error);
        showToast('YouTube 플레이어를 불러오지 못했습니다.', 'error');
        return false;
      }

      if (ytPlayer) {
        try { ytPlayer.destroy(); } catch(e) {}
        ytPlayer = null;
      }
      videoPlayer.classList.add('hidden');
      videoPlayer.pause();
      youtubeContainer.classList.remove('hidden');
      
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
            applyPendingResume();
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
      return true;
    }

    function initLocalPlayer(videoUrl) {
      if (ytPlayer) {
        try { ytPlayer.destroy(); } catch(e) {}
        ytPlayer = null;
      }
      youtubeContainer.classList.add('hidden');
      videoPlayer.classList.remove('hidden');
      videoPlayer.src = videoUrl;
      videoPlayer.load();
      videoPlayer.onloadedmetadata = () => {
        applyPendingResume();
      };
      videoPlayer.play().catch(console.warn);

      videoPlayer.onplay = () => {
        playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
      };
      videoPlayer.onpause = () => {
        playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
      };
      videoPlayer.onended = () => {
        playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
      };

      startTimePolling();
    }

    function startTimePolling() {
      if (timeUpdateInterval) clearInterval(timeUpdateInterval);
      timeUpdateInterval = setInterval(() => {
        let cur = 0;
        let dur = 0;

        if (ytPlayer && ytPlayer.getCurrentTime) {
          cur = ytPlayer.getCurrentTime();
          dur = ytPlayer.getDuration();
        } else if (videoPlayer && !videoPlayer.classList.contains('hidden')) {
          cur = videoPlayer.currentTime;
          dur = videoPlayer.duration;
        }

        if (dur > 0) {
          updateProgressUI(cur, dur);
          handleTimeUpdate(cur);
          scheduleProgressSave(cur, dur);
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

    function getPlaybackState() {
      if (ytPlayer && ytPlayer.getCurrentTime) {
        return {
          currentTime: ytPlayer.getCurrentTime() || 0,
          duration: ytPlayer.getDuration() || 0,
          isPlaying: ytPlayer.getPlayerState && ytPlayer.getPlayerState() === YT.PlayerState.PLAYING,
        };
      }

      if (videoPlayer && !videoPlayer.classList.contains('hidden')) {
        return {
          currentTime: videoPlayer.currentTime || 0,
          duration: videoPlayer.duration || 0,
          isPlaying: !videoPlayer.paused,
        };
      }

      return { currentTime: 0, duration: 0, isPlaying: false };
    }

    function seekPlayback(time, shouldPlay = false) {
      const targetTime = Math.max(0, Number(time) || 0);
      if (ytPlayer && ytPlayer.seekTo) {
        ytPlayer.seekTo(targetTime, true);
        if (shouldPlay && ytPlayer.playVideo) ytPlayer.playVideo();
      } else if (videoPlayer && !videoPlayer.classList.contains('hidden')) {
        videoPlayer.currentTime = targetTime;
        if (shouldPlay) videoPlayer.play().catch(console.warn);
      }
      handleTimeUpdate(targetTime);
    }

    function applyPendingResume() {
      if (!pendingResumeTime || pendingResumeTime < 2) return;
      const { duration } = getPlaybackState();
      const targetTime = duration > 0 ? Math.min(pendingResumeTime, Math.max(0, duration - 1)) : pendingResumeTime;
      pendingResumeTime = 0;
      seekPlayback(targetTime, true);
    }

    async function loadVideoProgress() {
      const userId = getCurrentUserId();
      if (!userId) return;

      try {
        const resp = await fetch(`/api/video-progress/${encodeURIComponent(userId)}`, {
          headers: getAuthHeaders(),
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.ok && data.progress && typeof data.progress === 'object') {
          progressByVideo = data.progress;
        }
      } catch (error) {
        console.warn('[OnuiTube] Failed to load video progress:', error);
      }
    }

    async function saveCurrentProgress(cur, dur) {
      if (!currentVideoId || !dur) return;
      if (Date.now() < videoProgressRetryAt) return;

      const watchedSeconds = Math.max(0, Math.floor(cur || 0));
      const durationSeconds = Math.max(0, Math.floor(dur || 0));
      const completed = durationSeconds > 0 && watchedSeconds >= Math.max(1, durationSeconds - 2);
      const lastPosition = completed ? 0 : watchedSeconds;

      try {
        const resp = await fetch('/api/video-progress', {
          method: 'POST',
          headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            video_id: currentVideoId,
            watched_seconds: watchedSeconds,
            duration_seconds: durationSeconds,
            last_position: lastPosition,
            completed,
          }),
        });
        if (!resp.ok) {
          videoProgressFailureCount += 1;
          const backoffMs = resp.status === 503
            ? Math.min(300000, 30000 * videoProgressFailureCount)
            : Math.min(60000, 5000 * videoProgressFailureCount);
          videoProgressRetryAt = Date.now() + backoffMs;
          if (resp.status !== 503) {
            console.warn(`[OnuiTube] Video progress save failed (${resp.status}); retrying in ${Math.round(backoffMs / 1000)}s.`);
          }
          return;
        }
        videoProgressFailureCount = 0;
        videoProgressRetryAt = 0;
        progressByVideo[currentVideoId] = {
          watched_seconds: watchedSeconds,
          duration_seconds: durationSeconds,
          last_position: lastPosition,
          completed,
        };
      } catch (error) {
        console.warn('[OnuiTube] Failed to save video progress:', error);
      }
    }

    function scheduleProgressSave(cur, dur) {
      if (!currentVideoId || saveProgressTimer || !dur) return;
      saveProgressTimer = window.setTimeout(() => {
        saveProgressTimer = null;
        const state = getPlaybackState();
        saveCurrentProgress(state.currentTime || cur, state.duration || dur);
      }, 5000);
    }

    function flushProgressSave() {
      if (saveProgressTimer) {
        clearTimeout(saveProgressTimer);
        saveProgressTimer = null;
      }
      const { currentTime, duration } = getPlaybackState();
      return saveCurrentProgress(currentTime, duration);
    }

    function getSentenceIndexForTime(time) {
      if (!transcripts.length) return -1;
      const active = transcripts.findIndex(s => time >= (s.start + currentOffset) && time < (s.end + currentOffset));
      if (active !== -1) return active;
      const next = transcripts.findIndex(s => time < (s.end + currentOffset));
      return next !== -1 ? next : transcripts.length - 1;
    }

    function normalizeVocabLabel(value) {
      let text = String(value ?? '').trim();
      text = text.replace(/[.,!?;:，。！？、]/g, '').trim();
      text = text.replace(/\s+/g, ' ');
      return text;
    }

    function getVocabCandidates(value) {
      const normalized = normalizeVocabLabel(value);
      const candidates = new Set([normalized]);
      const particles = [
        '에서는', '에게도', '들과', '으로', '에서', '에게', '에도', '까지', '부터',
        '에는', '은', '는', '이', '가', '을', '를', '의', '에', '와', '과', '도', '로'
      ];

      particles.forEach((particle) => {
        if (normalized.length > particle.length + 1 && normalized.endsWith(particle)) {
          candidates.add(normalized.slice(0, -particle.length));
        }
      });

      return [...candidates].filter(Boolean);
    }

    function findMeaningForLabel(label) {
      if (!vocabularyLookup) return '';
      for (const candidate of getVocabCandidates(label)) {
        const meaning = vocabularyLookup.get(candidate);
        if (meaning) return meaning;
      }
      return '';
    }

    async function loadVocabularyLookup() {
      if (vocabularyLookup) return vocabularyLookup;

      vocabularyLookup = new Map();
      try {
        const resp = await fetch('/api/tube/vocab/export');
        const data = await resp.json().catch(() => ({}));
        const vocabulary = Array.isArray(data.vocabulary) ? data.vocabulary : [];

        vocabulary.forEach((item) => {
          const word = normalizeVocabLabel(item.word || item.label || '');
          const meaning = item.meaningEn || item.meaning || item.mean || item.translation || '';
          if (word && meaning && !vocabularyLookup.has(word)) {
            vocabularyLookup.set(word, meaning);
          }
        });
      } catch (err) {
        console.warn('[OnuiTube] Failed to load vocabulary lookup:', err);
      }

      return vocabularyLookup;
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
      const fallbackMeaning = findMeaningForLabel(wordObj.label);
      wordDetailPos.textContent = wordObj.pos || '';
      wordDetailLabel.textContent = wordObj.label;
      wordDetailMean.textContent = wordObj.mean || wordObj.meaning || fallbackMeaning || '';
      wordDetailTts.onclick = () => playWordTTS(wordObj.label);
      wordDetailSave.onclick = () => { addToVocab({ ...wordObj, meaning: wordObj.meaning || wordObj.mean || fallbackMeaning }); };
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
        const resp = await fetch('/api/tube/videos', { headers: getAuthHeaders() });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(data.detail || data.error || '영상 목록을 불러오지 못했습니다.');
        }
        if (data.success && data.videos) {
          allVideos = data.videos;
          renderGrid(allVideos);
          return;
        }
        throw new Error('영상 목록을 불러오지 못했습니다.');
      } catch (err) {
        console.error(err);
        if (!allVideos.length) {
          renderLobbyError(err.message || '영상 목록을 불러오지 못했습니다.');
        } else {
          showToast('최신 영상 목록을 불러오지 못해 저장된 목록을 표시합니다.', 'info');
        }
      }
    }

    function renderGrid(videos) {
      videoGrid.innerHTML = '';
      if (!videos.length) {
        videoGrid.innerHTML = `
          <div class="col-span-full py-20 text-center text-white/30 font-black uppercase tracking-widest">
            검색 결과가 없습니다
          </div>
        `;
        return;
      }

      videos.forEach((v, idx) => {
        const card = document.createElement('div');
        const title = escapeHtml(v.title || '');
        const posterUrl = escapeHtml(v.poster_url || '');
        const loadingMode = idx < 5 ? 'eager' : 'lazy';
        const fetchPriority = idx === 0 ? 'high' : 'auto';
        const level = escapeHtml(v.level || '');
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
              <img src="${posterUrl}" class="w-full h-full object-cover" alt="${title}" loading="${loadingMode}" decoding="async" fetchpriority="${fetchPriority}">
            </div>
            <div class="card-overlay-top">
              <span class="px-2 py-0.5 bg-orange-500 text-white text-[9px] font-black rounded-full shadow-sm">Lv.${level}</span>
              ${statusBadge}
            </div>
            <div class="card-overlay">
              <h3 class="text-xs font-black text-white leading-tight line-clamp-2 drop-shadow-md">${title}</h3>
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

    function applyLobbyFilters() {
      const query = (searchInput?.value || '').trim().toLowerCase();
      const filtered = allVideos.filter((video) => {
        const levelMatches = activeLevel === 'all' || String(video.level || '') === activeLevel;
        const searchable = [
          video.title,
          video.description,
          video.level ? `level ${video.level}` : '',
          video.level ? `lv.${video.level}` : '',
          video.level ? `lv${video.level}` : '',
        ].join(' ').toLowerCase();
        return levelMatches && (!query || searchable.includes(query));
      });
      renderGrid(filtered);
    }

    function resetLobbyFilters() {
      activeLevel = 'all';
      if (searchInput) searchInput.value = '';
      document.querySelectorAll('.level-filter-btn').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.level === 'all');
      });
      renderGrid(allVideos);
    }

    // ── 플레이어 초기화 ──────────────────────────────────
    async function initPlayer(v) {
      await flushProgressSave();
      currentVideoId = v.id;
      currentOffset = v.transcript_offset || 0;
      const progress = progressByVideo[currentVideoId] || {};
      pendingResumeTime = Number(progress.completed ? 0 : progress.last_position || 0) || 0;
      document.getElementById('player-title').innerText = v.title;
      document.getElementById('player-desc').innerText = v.description || '';

      if (v.source_type === 'local' || v.local_video_url) {
        if (!v.local_video_url) {
          showToast('로컬 영상 경로가 없습니다.', 'error');
          return;
        }
        initLocalPlayer(v.local_video_url);
      } else {
        const initialized = await initYouTubePlayer(v);
        if (!initialized) return;
      }
      
      currentSpeed = 1.0;
      speedLabel.innerText = '1.0x';
      updateOffsetUI();

      transcripts = [];
      currentSubtitleIndex = -1;
      autoPauseFired = false;
      captionsContainer.innerHTML = '';

      // 자막 로드 (plural transcripts 키 사용 보장)
      fetch(`/api/tube/transcripts/${v.id}`, { headers: getAuthHeaders() })
        .then(r => r.ok ? r.json() : Promise.reject(new Error('자막을 불러오지 못했습니다.')))
        .then(data => {
          if (data.success && data.transcripts) {
            transcripts = data.transcripts;
          } else {
            throw new Error('자막을 불러오지 못했습니다.');
          }
        })
        .catch((error) => {
          console.error(error);
          showToast(error.message || '자막을 불러오지 못했습니다.', 'error');
        });

      lobby.classList.add('hidden');
      playerScreen.classList.remove('hidden');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // ── 컨트롤 이벤트 ──────────────────────────────────
    btnPlayPause.onclick = () => {
      if (ytPlayer) {
        const state = ytPlayer.getPlayerState();
        if (state === YT.PlayerState.PLAYING) ytPlayer.pauseVideo();
        else ytPlayer.playVideo();
      } else if (!videoPlayer.classList.contains('hidden')) {
        if (videoPlayer.paused) videoPlayer.play();
        else videoPlayer.pause();
      }
    };

    btnRestart.onclick = () => {
      const { isPlaying } = getPlaybackState();
      seekPlayback(0, isPlaying);
    };

    btnSpeed.onclick = () => {
      const speeds = [0.5, 0.75, 1.0, 1.25, 1.5];
      let nextIdx = speeds.indexOf(currentSpeed) + 1;
      if (nextIdx >= speeds.length) nextIdx = 0;
      currentSpeed = speeds[nextIdx];
      
      if (ytPlayer) {
        ytPlayer.setPlaybackRate(currentSpeed);
      } else if (!videoPlayer.classList.contains('hidden')) {
        videoPlayer.playbackRate = currentSpeed;
      }
      
      speedLabel.innerText = `${currentSpeed}x`;
    };

    btnNext.onclick = () => {
      if (!transcripts.length) return;
      const { currentTime, isPlaying } = getPlaybackState();
      const baseIndex = currentSubtitleIndex !== -1 ? currentSubtitleIndex : getSentenceIndexForTime(currentTime);
      const idx = Math.min(baseIndex + 1, transcripts.length - 1);
      const targetTime = transcripts[idx].start + currentOffset;
      seekPlayback(targetTime, isPlaying);
    };

    btnPrev.onclick = () => {
      if (!transcripts.length) return;
      const { currentTime, isPlaying } = getPlaybackState();
      const baseIndex = currentSubtitleIndex !== -1 ? currentSubtitleIndex : getSentenceIndexForTime(currentTime);
      const idx = Math.max(0, baseIndex - 1);
      const targetTime = transcripts[idx].start + currentOffset;
      seekPlayback(targetTime, isPlaying);
    };

    btnRewind.onclick = () => {
      if (!transcripts.length) return;
      const { currentTime } = getPlaybackState();
      const idx = currentSubtitleIndex !== -1 ? currentSubtitleIndex : getSentenceIndexForTime(currentTime);
      if (idx === -1) return;
      seekPlayback(transcripts[idx].start + currentOffset, true);
    };

    progressWrapper.onclick = (event) => {
      const { duration, isPlaying } = getPlaybackState();
      if (!duration) return;
      const rect = progressWrapper.getBoundingClientRect();
      const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      seekPlayback(duration * ratio, isPlaying);
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
        if (active !== -1) {
          currentSubtitleIndex = active;
          autoPauseFired = false;
          renderCaptions(active);
        } else if (currentSubtitleIndex !== -1) {
          const current = transcripts[currentSubtitleIndex];
          const currentEnd = current.end + currentOffset;
          const pauseAt = currentEnd + AUTO_PAUSE_GRACE_SECONDS;
          const beforeNextSentence = currentSubtitleIndex >= transcripts.length - 1 || time < (transcripts[currentSubtitleIndex + 1].start + currentOffset);
          if (!autoPauseToggle.checked || time < pauseAt || !beforeNextSentence) {
            currentSubtitleIndex = -1;
            autoPauseFired = false;
            renderCaptions(-1);
          }
        }
      }

      if (currentSubtitleIndex !== -1 && autoPauseToggle.checked && !autoPauseFired) {
        const cur = transcripts[currentSubtitleIndex];
        const pauseAt = cur.end + currentOffset + AUTO_PAUSE_GRACE_SECONDS;
        if (time >= pauseAt) {
          autoPauseFired = true;
          if (ytPlayer) ytPlayer.pauseVideo();
          else if (!videoPlayer.classList.contains('hidden')) videoPlayer.pause();
          seekPlayback(pauseAt, false);
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
      const meaning = wordObj.mean || wordObj.meaning || findMeaningForLabel(wordObj.label);
      const fd = new FormData();
      fd.append('label', wordObj.label);
      fd.append('pos', wordObj.pos || '');
      fd.append('meaning', meaning || '');
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

    btnBack.onclick = async () => {
      await flushProgressSave();
      if (ytPlayer) ytPlayer.stopVideo();
      if (videoPlayer) {
        videoPlayer.pause();
        videoPlayer.src = "";
      }
      if (timeUpdateInterval) clearInterval(timeUpdateInterval);
      currentVideoId = null;
      pendingResumeTime = 0;
      playerScreen.classList.add('hidden');
      lobby.classList.remove('hidden');
    };

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) flushProgressSave();
    });

    searchBtn.onclick = applyLobbyFilters;
    searchInput.addEventListener('input', applyLobbyFilters);
    searchInput.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') applyLobbyFilters();
    });
    showAllBtn.onclick = resetLobbyFilters;
    document.querySelectorAll('.level-filter-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeLevel = btn.dataset.level || 'all';
        document.querySelectorAll('.level-filter-btn').forEach(el => el.classList.remove('active'));
        btn.classList.add('active');
        applyLobbyFilters();
      });
    });

    btnExport.onclick = async () => {
      if (!savedVocab.length) {
        showToast('내보낼 단어가 없습니다.', 'info');
        return;
      }
      await loadVocabularyLookup();

      const headers = ['label', 'pos', 'meaning', 'source', 'savedAt'];
      const formatSavedAtForCsv = (value) => {
        const raw = String(value ?? '').trim();
        if (!raw) return '';

        const isoLike = raw.includes('T') ? raw : raw.replace(' ', 'T');
        const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(isoLike);
        const date = new Date(hasTimezone ? isoLike : `${isoLike}Z`);
        if (Number.isNaN(date.getTime())) return raw;

        const pad = (num) => String(num).padStart(2, '0');
        return [
          date.getFullYear(),
          pad(date.getMonth() + 1),
          pad(date.getDate()),
        ].join('-') + ' ' + [
          pad(date.getHours()),
          pad(date.getMinutes()),
          pad(date.getSeconds()),
        ].join(':');
      };
      const escapeCsv = (value) => {
        const text = String(value ?? '');
        return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
      };
      const rows = savedVocab.map((item) => headers.map((key) => {
        let value = key === 'savedAt' ? formatSavedAtForCsv(item[key]) : item[key];
        if (key === 'meaning' && !value) value = findMeaningForLabel(item.label);
        return escapeCsv(value || '');
      }).join(','));
      const csv = `\uFEFF${[headers.join(','), ...rows].join('\r\n')}`;
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'onuitube-vocab.csv';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    };

    allVideos = getInitialVideos();
    if (allVideos.length) {
      renderGrid(allVideos);
    }

    loadVocabularyLookup();
    loadVideoProgress();
    loadLobby();
    loadSavedVocab();
  });
