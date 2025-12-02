// 발음 연습 - Pronunciation Practice JavaScript (ELSA Speak Style)

(function() {
  'use strict';

  // State
  let allWords = [];
  let filteredWords = [];
  let currentWord = null;
  let currentLevel = 'all';
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  // DOM Elements
  const searchInput = document.getElementById('searchInput');
  const wordButtons = document.getElementById('wordButtons');
  const mainWord = document.getElementById('mainWord');
  const romanText = document.getElementById('romanText');
  const meaningKo = document.getElementById('meaningKo');
  const meaningEn = document.getElementById('meaningEn');
  const levelBadge = document.getElementById('levelBadge');
  const phonemeBreakdown = document.getElementById('phonemeBreakdown');
  const tipsText = document.getElementById('tipsText');
  const bubbleWord = document.getElementById('bubbleWord');
  const listenBtn = document.getElementById('listenBtn');
  const recordBtn = document.getElementById('recordBtn');
  const stopBtn = document.getElementById('stopBtn');
  const scoreResult = document.getElementById('scoreResult');

  // Load pronunciation words from API
  async function loadWords() {
    try {
      const response = await fetch('/api/pronunciation-words');
      const data = await response.json();
      allWords = data.words || [];
      filteredWords = [...allWords];
      renderWordButtons();

      // Auto-select first word
      if (allWords.length > 0) {
        selectWord(allWords[0]);
      }
    } catch (error) {
      console.error('Error loading pronunciation words:', error);
      wordButtons.innerHTML = '<p class="text-red-500 text-sm">단어를 불러오는 중 오류가 발생했습니다.</p>';
    }
  }

  // Filter words by level
  window.filterByLevel = function(level) {
    currentLevel = level;

    // Update active button
    document.querySelectorAll('.level-filter-btn').forEach(btn => {
      btn.classList.remove('active');
    });
    document.querySelector(`[data-level="${level}"]`).classList.add('active');

    // Filter words
    if (level === 'all') {
      filteredWords = [...allWords];
    } else {
      filteredWords = allWords.filter(w => w.level === level);
    }

    renderWordButtons();
  };

  // Search functionality
  searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();

    if (!query) {
      filteredWords = currentLevel === 'all' ? [...allWords] : allWords.filter(w => w.level === currentLevel);
    } else {
      const baseFiltered = currentLevel === 'all' ? allWords : allWords.filter(w => w.level === currentLevel);
      filteredWords = baseFiltered.filter(w =>
        w.word.includes(query) ||
        w.roman.toLowerCase().includes(query) ||
        w.meaningKo.includes(query) ||
        w.meaningEn.toLowerCase().includes(query)
      );
    }

    renderWordButtons();
  });

  // Render word selection buttons
  function renderWordButtons() {
    if (filteredWords.length === 0) {
      wordButtons.innerHTML = '<p class="text-gray-500 text-sm">검색 결과가 없습니다.</p>';
      return;
    }

    wordButtons.innerHTML = '';
    filteredWords.forEach(word => {
      const btn = document.createElement('button');
      btn.className = 'word-btn';
      btn.innerHTML = `
        ${word.word}
        <span class="level-tag">${word.level}</span>
      `;

      if (currentWord && currentWord.id === word.id) {
        btn.classList.add('selected');
      }

      btn.addEventListener('click', () => {
        selectWord(word);
        // Update selected state
        document.querySelectorAll('.word-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
      });

      wordButtons.appendChild(btn);
    });
  }

  // Select a word for practice
  function selectWord(word) {
    currentWord = word;

    // Update Step 1 (Listen panel)
    mainWord.textContent = word.word;
    romanText.textContent = `[ ${word.roman} ]`;
    meaningKo.textContent = word.meaningKo;
    meaningEn.textContent = word.meaningEn;
    levelBadge.textContent = word.level;

    // Update phoneme breakdown
    phonemeBreakdown.innerHTML = '';
    if (word.phonemes && word.phonemes.length > 0) {
      word.phonemes.forEach(phoneme => {
        const box = document.createElement('div');
        box.className = 'phoneme-box';
        box.textContent = phoneme;
        phonemeBreakdown.appendChild(box);
      });
    } else {
      phonemeBreakdown.innerHTML = '<p class="text-gray-500 text-xs">음소 정보 없음</p>';
    }

    // Update tips
    tipsText.textContent = word.tips || '발음 팁이 제공되지 않습니다.';

    // Update Step 2 (Speak panel)
    bubbleWord.textContent = word.word;

    // Hide previous score
    scoreResult.classList.add('hidden');

    // Auto-play audio
    playAudio();
  }

  // Play audio using MzTTS API
  window.playAudio = async function() {
    if (!currentWord) {
      alert('먼저 단어를 선택하세요.');
      return;
    }

    // Visual feedback
    listenBtn.style.transform = 'scale(0.95)';
    listenBtn.disabled = true;

    try {
      // Create JSON payload
      const payload = {
        text: currentWord.word,
        speaker: 0, // Hanna (female voice)
        tempo: 0.9, // Slightly slower for learning
        pitch: 1.0,
        gain: 1.2 // Slightly louder
      };

      // Call MzTTS API
      const response = await fetch('/api/tts/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('TTS generation failed');
      }

      // Get audio blob and play
      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);

      audio.onended = () => {
        URL.revokeObjectURL(audioUrl); // Clean up
      };

      await audio.play();

    } catch (error) {
      console.error('Error playing audio:', error);
      alert('음성 재생 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.');
    } finally {
      // Reset button state
      setTimeout(() => {
        listenBtn.style.transform = 'scale(1)';
        listenBtn.disabled = false;
      }, 200);
    }
  };

  // Start recording
  window.startRecording = async function() {
    if (!currentWord) {
      alert('먼저 단어를 선택하세요.');
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        await analyzePronunciation();
      };

      mediaRecorder.start();
      isRecording = true;

      // Update UI
      recordBtn.disabled = true;
      recordBtn.classList.add('recording');
      stopBtn.disabled = false;
      stopBtn.style.opacity = '1';
      scoreResult.classList.add('hidden');

    } catch (error) {
      console.error('Error starting recording:', error);
      alert('마이크 접근 권한을 허용해주세요.');
    }
  };

  // Stop recording and analyze
  window.stopRecording = function() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;

      // Update UI
      recordBtn.disabled = false;
      recordBtn.classList.remove('recording');
      stopBtn.disabled = true;
      stopBtn.style.opacity = '0.5';
    }
  };

  // Analyze pronunciation using existing API
  async function analyzePronunciation() {
    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('file', audioBlob, 'recording.webm');
    formData.append('target_text', currentWord.word);

    // Show loading state
    scoreResult.classList.remove('hidden');
    scoreResult.innerHTML = `
      <div class="flex items-center justify-center gap-3 p-4">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-pink-600"></div>
        <span class="text-sm text-gray-600">AI가 분석 중입니다...</span>
      </div>
    `;

    try {
      const response = await fetch('/api/pronunciation-check', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      if (data.error) {
        scoreResult.innerHTML = `
          <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-700 font-semibold text-sm">⚠️ 오류</p>
            <p class="text-red-600 text-xs mt-1">${data.error}</p>
            ${data.details ? '<p class="text-gray-600 text-xs mt-1">' + data.details + '</p>' : ''}
          </div>
        `;
      } else {
        displayScore(data);
      }
    } catch (error) {
      console.error('Error analyzing pronunciation:', error);
      scoreResult.innerHTML = `
        <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
          <p class="text-red-700 font-semibold text-sm">⚠️ 오류</p>
          <p class="text-red-600 text-xs mt-1">발음 분석 중 문제가 발생했습니다.</p>
        </div>
      `;
    }
  }

  // Display pronunciation score
  function displayScore(data) {
    const score = data.score || 0;
    let scoreClass = 'needs-improvement';
    let emoji = '😢';
    let message = '다시 연습해보세요!';

    if (score >= 80) {
      scoreClass = 'excellent';
      emoji = '🎉';
      message = '완벽해요!';
    } else if (score >= 60) {
      scoreClass = 'good';
      emoji = '😊';
      message = '좋아요! 조금만 더!';
    }

    scoreResult.innerHTML = `
      <div class="score-display">
        <div class="score-number ${scoreClass}">${score}점</div>
        <div class="score-label">${emoji} ${message}</div>
      </div>
      ${data.user_said ? `
        <div class="feedback-text">
          <p class="text-xs font-semibold text-gray-700 mb-1">인식된 발음:</p>
          <p class="text-sm font-medium text-gray-900">${data.user_said}</p>
        </div>
      ` : ''}
      ${data.feedback ? `
        <div class="feedback-text mt-2">
          <p class="text-xs font-semibold text-gray-700 mb-1">피드백:</p>
          <p class="text-sm text-gray-800">${data.feedback}</p>
        </div>
      ` : ''}
      <div class="mt-3 flex gap-2">
        <button onclick="playAudio()" class="flex-1 px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 text-sm font-medium">
          🔊 다시 듣기
        </button>
        <button onclick="startRecording()" class="flex-1 px-4 py-2 bg-pink-500 text-white rounded-lg hover:bg-pink-600 text-sm font-medium">
          🎤 다시 녹음
        </button>
      </div>
    `;
  }

  // Initialize
  loadWords();
})();
