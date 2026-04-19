  let audio = new Audio();
  let songs = [];
  let currentSong = null;
  let progressInterval = null;

  document.addEventListener("DOMContentLoaded", () => {
    const playBtn = document.getElementById('play-btn');
    const playIcon = document.getElementById('play-icon');
    const progressBar = document.getElementById('progress-bar');
    const progressContainer = document.getElementById('progress-container');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');
    const lyricsContainer = document.getElementById('lyrics-container');
    const lobbyScreen = document.getElementById('lobby-screen');
    const gameScreen = document.getElementById('game-screen');
    const songGrid = document.getElementById('song-grid');
    const accuracyDisplay = document.getElementById('accuracy-display');
    const playerVisual = document.getElementById('player-visual');

    const initialSongs = window.__INITIAL_SONGS || [];
    
    async function fetchSongs() {
      if (initialSongs && initialSongs.length > 0) {
        songs = initialSongs;
        renderLobby();
        return;
      }
      
      console.time('fetchSongs API call'); // Start timer for API call
      try {
        const resp = await fetch('/api/beats/songs');
        const data = await resp.json();
        if (data.success) {
          songs = data.songs;
          console.timeEnd('fetchSongs API call'); // End timer for API call

          console.time('renderLobby function'); // Start timer for rendering
          renderLobby();
          console.timeEnd('renderLobby function'); // End timer for rendering
          }
          } catch (err) {
          console.error('Failed to load songs', err);
          console.timeEnd('fetchSongs API call'); // Ensure timer ends on error
          }
          }

          function renderLobby() {
          songGrid.innerHTML = songs.map((s, idx) => `
        <div onclick="startSong(${idx})" class="song-card suno-card cursor-pointer group overflow-hidden" style="animation-delay:${idx*0.04}s">
          <div class="relative aspect-square overflow-hidden bg-white/5">
            <img src="${s.image_url}" onerror="this.src='/static/images/kpop-banner.svg'" class="w-full h-full object-cover group-hover:scale-105 transition-all duration-500" />
            <div class="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <div class="w-10 h-10 rounded-full bg-indigo-500 flex items-center justify-center text-white text-lg shadow-lg">▶</div>
            </div>
          </div>
          <div class="p-3">
            <h3 class="text-sm font-black text-white truncate leading-tight">${s.title}</h3>
            <p class="text-indigo-400 font-bold text-[10px] uppercase tracking-widest truncate mt-0.5">${s.artist}</p>
          </div>
        </div>
      `).join('');
    }

    window.startSong = (idx) => {
      currentSong = songs[idx];
      lobbyScreen.classList.add('hidden');
      gameScreen.classList.remove('hidden');
      
      document.getElementById('game-song-title').innerText = currentSong.title;
      document.getElementById('game-song-artist').innerText = currentSong.artist;
      const albumArt = document.getElementById('game-album-art');
      albumArt.src = currentSong.image_url;
      albumArt.onerror = () => { albumArt.src = '/static/images/kpop-banner.svg'; };
      
      audio.src = currentSong.audio_url;
      audio.play().catch(e => console.log("Autoplay blocked, waiting for user click"));
      
      accuracyDisplay.innerText = '0%';
      renderLyrics();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    };

    audio.onplay = () => {
      playIcon.innerHTML = '<path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/>';
      playerVisual.classList.add('playing');
      startProgressLoop();
    };

    audio.onpause = () => {
      playIcon.innerHTML = '<path d="M8 5v14l11-7z"/>';
      playerVisual.classList.remove('playing');
      stopProgressLoop();
    };

    function startProgressLoop() {
      stopProgressLoop();
      progressInterval = setInterval(() => {
        if (!audio.paused) {
          const curr = audio.currentTime;
          const dur = audio.duration;
          if (dur > 0) {
            const prog = (curr / dur) * 100;
            progressBar.style.width = prog + '%';
            timeCurrent.innerText = formatTime(curr);
            timeTotal.innerText = formatTime(dur);
          }
        }
      }, 500);
    }

    function stopProgressLoop() {
      if (progressInterval) clearInterval(progressInterval);
    }

    function renderLyrics() {
      lyricsContainer.innerHTML = '';
      if (!currentSong || !currentSong.lyrics) return;
      
      const answerLabel = translations['bt.answer'] || "Answer";
      const meaningLabel = translations['bt.meaning'] || "Meaning";

      currentSong.lyrics.forEach(line => {
        const p = document.createElement('p');
        p.className = 'lyric-line mb-4';
        if (line.blank) {
          const parts = line.text.split(line.blank);
          const firstPart = parts[0];
          const restPart = line.text.substring(firstPart.length + line.blank.length);
          
          const meaning = line.meaning || "Try again!";
          
          p.innerHTML = `${firstPart}<span class="relative inline-block">
              <input type="text" class="lyric-blank" data-answer="${line.blank}" placeholder="..." spellcheck="false" autocomplete="off" oninput="this.classList.remove('wrong')"/>
              <div class="feedback-tooltip">
                 ${answerLabel}: <span class="answer-highlight">${line.blank}</span><br/>
                 ${meaningLabel}: <span class="meaning-highlight">"${meaning}"</span>
              </div>
            </span>${restPart}`;
        } else {
          p.innerText = line.text;
        }
        lyricsContainer.appendChild(p);
      });
    }

    playBtn.onclick = () => {
      if (audio.paused) audio.play();
      else audio.pause();
    };

    progressContainer.onclick = (e) => {
       const rect = progressContainer.getBoundingClientRect();
       const pos = (e.clientX - rect.left) / rect.width;
       audio.currentTime = pos * audio.duration;
    };

    function formatTime(s) {
      if (isNaN(s)) return "0:00";
      const m = Math.floor(s / 60);
      const sec = Math.floor(s % 60);
      return `${m}:${sec.toString().padStart(2, '0')}`;
    }

    document.getElementById('hint-btn').onclick = () => {
      const inputs = document.querySelectorAll('.lyric-blank');
      let hinted = 0;
      inputs.forEach(input => {
        if (!input.classList.contains('correct') && !input.value) {
          const answer = input.dataset.answer || '';
          input.placeholder = answer.charAt(0) + '...';
          input.style.borderColor = 'rgba(251,191,36,0.6)';
          hinted++;
        }
      });
      if (hinted === 0 && window.ToastManager) {
        ToastManager.info(translations['bt.hint_none'] || '모든 빈칸을 이미 채웠습니다!');
      }
    };

    document.getElementById('check-ans-btn').onclick = () => {
      const inputs = document.querySelectorAll('.lyric-blank');
      let correct = 0;
      inputs.forEach(input => {
        if (input.value.trim().toLowerCase() === input.dataset.answer.toLowerCase()) {
          input.classList.add('correct');
          input.classList.remove('wrong');
          correct++;
        } else {
          input.classList.add('wrong');
          input.classList.remove('correct');
        }
      });

      const acc = Math.round((correct / inputs.length) * 100);
      animateAccuracy(acc);

      // 점수 학습 기록 저장
      const token = localStorage.getItem('auth_token');
      if (token) {
        fetch('/api/learning/pronunciation-completed', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
          body: JSON.stringify({ score: acc })
        }).catch(() => {});
      }

      if (acc === 100) {
        fireConfetti();
        if (window.ToastManager) {
            ToastManager.success(translations['bt.perfect'] || 'Perfect Score! You are a K-Pop Pro! 🌟');
        }
      }
    };
    
    function animateAccuracy(target) {
        let current = parseInt(accuracyDisplay.innerText) || 0;
        const step = target > current ? 1 : -1;
        
        clearInterval(window.accInterval);
        window.accInterval = setInterval(() => {
            if (current === target) {
                clearInterval(window.accInterval);
                return;
            }
            current += step;
            accuracyDisplay.innerText = current + '%';
            
            if (current === 100) accuracyDisplay.style.color = '#4ade80';
            else if (current > 50) accuracyDisplay.style.color = '#fb923c';
            else accuracyDisplay.style.color = 'white';
        }, 15);
    }
    
    function fireConfetti() {
        if (typeof confetti === 'function') {
            confetti({
                particleCount: 150,
                spread: 100,
                origin: { y: 0.6 },
                colors: ['#f97316', '#ec4899', '#3b82f6', '#10b981']
            });
        }
    }

    document.getElementById('btn-back-lobby').onclick = () => {
      audio.pause();
      gameScreen.classList.add('hidden');
      lobbyScreen.classList.remove('hidden');
    };

    fetchSongs();
  });
