// 발음 연습 - Pronunciation Practice JavaScript (ELSA Speak Style)

(function () {
  "use strict";

  // State
  let allWords = [];
  let filteredWords = [];
  let currentWord = null;
  let currentLevel = "all";
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  // DOM Elements
  let searchInput = null;
  let wordButtons = null;
  let mainWord = null;
  let romanText = null;
  let meaningKo = null;
  let meaningEn = null;
  let levelBadge = null;
  let phonemeBreakdown = null;
  let tipsText = null;
  let bubbleWord = null;
  let listenBtn = null;
  let recordBtn = null;
  let stopBtn = null;
  let scoreResult = null;

  // Initialize DOM references
  function initializeDOMElements() {
    searchInput = document.getElementById("searchInput");
    wordButtons = document.getElementById("wordButtons");
    mainWord = document.getElementById("mainWord");
    romanText = document.getElementById("romanText");
    meaningKo = document.getElementById("meaningKo");
    meaningEn = document.getElementById("meaningEn");
    levelBadge = document.getElementById("levelBadge");
    phonemeBreakdown = document.getElementById("phonemeBreakdown");
    tipsText = document.getElementById("tipsText");
    bubbleWord = document.getElementById("bubbleWord");
    listenBtn = document.getElementById("listenBtn");
    recordBtn = document.getElementById("recordBtn");
    stopBtn = document.getElementById("stopBtn");
    scoreResult = document.getElementById("scoreResult");

    console.log("DOM Elements initialized:", {
      searchInput: !!searchInput,
      wordButtons: !!wordButtons,
      mainWord: !!mainWord,
    });

    // Add search input listener if element exists
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase().trim();

        if (!query) {
          filteredWords =
            currentLevel === "all"
              ? [...allWords]
              : allWords.filter((w) => w.level === currentLevel);
        } else {
          const baseFiltered =
            currentLevel === "all"
              ? allWords
              : allWords.filter((w) => w.level === currentLevel);
          filteredWords = baseFiltered.filter(
            (w) =>
              w.word.includes(query) ||
              w.roman.toLowerCase().includes(query) ||
              w.meaningKo.includes(query) ||
              w.meaningEn.toLowerCase().includes(query)
          );
        }

        renderWordButtons();
      });
    }
  }

  // Load pronunciation words from API
  async function loadWords() {
    console.log("loadWords() called");
    try {
      // Initialize DOM elements if not already done
      if (!wordButtons) {
        console.log("Initializing DOM elements...");
        initializeDOMElements();
      }

      console.log("Fetching pronunciation words from API...");
      const response = await fetch("/api/pronunciation-words");
      const data = await response.json();
      allWords = data.words || [];
      filteredWords = [...allWords];

      console.log(`Loaded ${allWords.length} words`);

      // Ensure wordButtons element exists before rendering
      if (wordButtons) {
        console.log("Rendering word buttons...");
        renderWordButtons();
      } else {
        console.error("wordButtons element not found!");
      }

      // Don't auto-select any word on page load
      // User should manually select a word to practice
    } catch (error) {
      console.error("Error loading pronunciation words:", error);
      if (wordButtons) {
        wordButtons.innerHTML =
          '<p class="text-red-500 text-sm">단어를 불러오는 중 오류가 발생했습니다. 콘솔을 확인하세요.</p>';
      }
    }
  }

  // Filter words by level
  window.filterByLevel = function (level) {
    currentLevel = level;

    // Initialize DOM elements if needed
    if (!wordButtons) {
      initializeDOMElements();
    }

    // Update active button
    document.querySelectorAll(".level-filter-btn").forEach((btn) => {
      btn.classList.remove("active");
    });
    const activeBtn = document.querySelector(`[data-level="${level}"]`);
    if (activeBtn) {
      activeBtn.classList.add("active");
    }

    // Filter words
    if (level === "all") {
      filteredWords = [...allWords];
    } else {
      filteredWords = allWords.filter((w) => w.level === level);
    }

    renderWordButtons();
  };

  // Render word selection buttons
  function renderWordButtons() {
    if (!wordButtons) {
      console.warn("wordButtons element not found, skipping render");
      return;
    }

    if (filteredWords.length === 0) {
      wordButtons.innerHTML =
        '<p class="text-gray-500 text-sm">검색 결과가 없습니다.</p>';
      return;
    }

    wordButtons.innerHTML = "";
    filteredWords.forEach((word) => {
      const btn = document.createElement("button");
      btn.className = "word-btn";
      btn.innerHTML = `
        ${word.word}
        <span class="level-tag">${word.level}</span>
      `;

      if (currentWord && currentWord.id === word.id) {
        btn.classList.add("selected");
      }

      btn.addEventListener("click", () => {
        selectWord(word);
        // Update selected state
        document
          .querySelectorAll(".word-btn")
          .forEach((b) => b.classList.remove("selected"));
        btn.classList.add("selected");
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
    phonemeBreakdown.innerHTML = "";
    if (word.phonemes && word.phonemes.length > 0) {
      word.phonemes.forEach((phoneme) => {
        const box = document.createElement("div");
        box.className = "phoneme-box";
        box.textContent = phoneme;
        phonemeBreakdown.appendChild(box);
      });
    } else {
      phonemeBreakdown.innerHTML =
        '<p class="text-gray-500 text-xs">음소 정보 없음</p>';
    }

    // Update tips
    tipsText.textContent = word.tips || "발음 팁이 제공되지 않습니다.";

    // Update Step 2 (Speak panel)
    bubbleWord.textContent = word.word;

    // Hide previous score
    scoreResult.classList.add("hidden");

    // Don't auto-play audio - let user click "다시 듣기" button
    // playAudio();
  }

  // Play audio using MzTTS API
  window.playAudio = async function () {
    if (!currentWord) {
      alert("먼저 단어를 선택하세요.");
      return;
    }

    // Visual feedback
    listenBtn.style.transform = "scale(0.95)";
    listenBtn.disabled = true;

    try {
      // Create JSON payload
      const payload = {
        text: currentWord.word,
        speaker: 0, // Hanna (female voice)
        tempo: 0.9, // Slightly slower for learning
        pitch: 1.0,
        gain: 1.2, // Slightly louder
      };

      // Call MzTTS API
      const response = await fetch("/api/tts/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error("TTS generation failed");
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
      console.error("Error playing audio:", error);
      alert("음성 재생 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      // Reset button state
      setTimeout(() => {
        listenBtn.style.transform = "scale(1)";
        listenBtn.disabled = false;
      }, 200);
    }
  };

  // Start recording
  window.startRecording = async function () {
    if (!currentWord) {
      alert("먼저 단어를 선택하세요.");
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
      recordBtn.classList.add("recording");
      stopBtn.disabled = false;
      stopBtn.style.opacity = "1";
      scoreResult.classList.add("hidden");
    } catch (error) {
      console.error("Error starting recording:", error);
      alert("마이크 접근 권한을 허용해주세요.");
    }
  };

  // Stop recording and analyze
  window.stopRecording = function () {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;

      // Update UI
      recordBtn.disabled = false;
      recordBtn.classList.remove("recording");
      stopBtn.disabled = true;
      stopBtn.style.opacity = "0.5";
    }
  };

  // Analyze pronunciation using existing API
  async function analyzePronunciation() {
    const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
    const formData = new FormData();
    formData.append("file", audioBlob, "recording.webm");
    formData.append("target_text", currentWord.word);

    // Show loading state
    scoreResult.classList.remove("hidden");
    scoreResult.innerHTML = `
      <div class="flex items-center justify-center gap-3 p-4">
        <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-pink-600"></div>
        <span class="text-sm text-gray-600">AI가 분석 중입니다...</span>
      </div>
    `;

    try {
      const response = await fetch("/api/pronunciation-check", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        scoreResult.innerHTML = `
          <div class="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p class="text-red-700 font-semibold text-sm">⚠️ 오류</p>
            <p class="text-red-600 text-xs mt-1">${data.error}</p>
            ${
              data.details
                ? '<p class="text-gray-600 text-xs mt-1">' +
                  data.details +
                  "</p>"
                : ""
            }
          </div>
        `;
      } else {
        displayScore(data);
      }
    } catch (error) {
      console.error("Error analyzing pronunciation:", error);
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
    let scoreClass = "needs-improvement";
    let emoji = "😢";
    let message = "다시 연습해보세요!";

    if (score >= 80) {
      scoreClass = "excellent";
      emoji = "🎉";
      message = "완벽해요!";
    } else if (score >= 60) {
      scoreClass = "good";
      emoji = "😊";
      message = "좋아요! 조금만 더!";
    }

    scoreResult.innerHTML = `
      <div class="score-display">
        <div class="score-number ${scoreClass}">${score}점</div>
        <div class="score-label">${emoji} ${message}</div>
      </div>
      ${
        data.user_said
          ? `
        <div class="feedback-text">
          <p class="text-xs font-semibold text-gray-700 mb-1">인식된 발음:</p>
          <p class="text-sm font-medium text-gray-900">${data.user_said}</p>
        </div>
      `
          : ""
      }
      ${
        data.feedback
          ? `
        <div class="feedback-text mt-2">
          <p class="text-xs font-semibold text-gray-700 mb-1">피드백:</p>
          <p class="text-sm text-gray-800">${data.feedback}</p>
        </div>
      `
          : ""
      }
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

  // Tab switching function
  window.switchTab = function (tabName) {
    console.log("switchTab() called with tabName:", tabName);

    // Get elements
    const wordTabContent = document.getElementById("wordTabContent");
    const sentenceTabContent = document.getElementById("sentenceTabContent");
    const wordTab = document.getElementById("wordTab");
    const sentenceTab = document.getElementById("sentenceTab");

    console.log("Elements found:", {
      wordTabContent: !!wordTabContent,
      sentenceTabContent: !!sentenceTabContent,
      wordTab: !!wordTab,
      sentenceTab: !!sentenceTab,
    });

    // Hide all tab contents
    if (wordTabContent) {
      wordTabContent.classList.add("hidden");
      wordTabContent.style.display = "none";
    }
    if (sentenceTabContent) {
      sentenceTabContent.classList.add("hidden");
      sentenceTabContent.style.display = "none";
    }

    // Remove active class from all tabs
    if (wordTab) wordTab.classList.remove("tab-active");
    if (sentenceTab) sentenceTab.classList.remove("tab-active");

    // Show selected tab
    if (tabName === "word") {
      console.log("Switching to word tab");
      if (wordTabContent) {
        wordTabContent.classList.remove("hidden");
        wordTabContent.style.display = "block";
      }
      if (wordTab) wordTab.classList.add("tab-active");
    } else if (tabName === "sentence") {
      console.log("Switching to sentence tab");
      if (sentenceTabContent) {
        sentenceTabContent.classList.remove("hidden");
        sentenceTabContent.style.display = "block";
        console.log("sentenceTabContent hidden class removed");
      } else {
        console.error("sentenceTabContent not found!");
      }
      if (sentenceTab) sentenceTab.classList.add("tab-active");
      console.log("Calling loadSentencesData()...");
      loadSentencesData();
    }
  };

  // Sentence evaluation functions
  let sentenceMediaRecorder = null;
  let sentenceRecordedChunks = [];
  let recordingStartTime = null;
  let recordingTimer = null;
  let selectedSentence = null;

  window.startSentenceRecording = async function () {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      sentenceMediaRecorder = new MediaRecorder(stream);
      sentenceRecordedChunks = [];
      recordingStartTime = Date.now();

      sentenceMediaRecorder.ondataavailable = (event) => {
        sentenceRecordedChunks.push(event.data);
      };

      sentenceMediaRecorder.onstop = () => {
        const audioBlob = new Blob(sentenceRecordedChunks, {
          type: "audio/wav",
        });
        const audioUrl = URL.createObjectURL(audioBlob);
        document.getElementById("sentence-audio-playback").src = audioUrl;
        document
          .getElementById("sentence-playback-section")
          .classList.remove("hidden");
        document.getElementById("sentence-evaluate-button").disabled = false;
      };

      sentenceMediaRecorder.start();

      // UI update
      document.getElementById("sentence-record-btn").disabled = true;
      document.getElementById("sentence-stop-btn").disabled = false;
      document.getElementById("recording-status").innerHTML =
        '<div class="text-6xl mb-4">🔴</div><p class="text-red-600 font-semibold">녹음 중...</p>';
      document
        .getElementById("sentence-recording-progress")
        .classList.remove("hidden");

      startSentenceTimer();
    } catch (error) {
      alert(`마이크 접근 실패: ${error.message}`);
    }
  };

  window.stopSentenceRecording = function () {
    if (sentenceMediaRecorder && sentenceMediaRecorder.state !== "inactive") {
      sentenceMediaRecorder.stop();
      sentenceMediaRecorder.stream.getTracks().forEach((track) => track.stop());

      // UI update
      document.getElementById("sentence-record-btn").disabled = false;
      document.getElementById("sentence-stop-btn").disabled = true;
      document.getElementById("recording-status").innerHTML =
        '<div class="text-6xl mb-4">✅</div><p class="text-green-600 font-semibold">녹음 완료</p>';
      document
        .getElementById("sentence-recording-progress")
        .classList.add("hidden");

      stopSentenceTimer();
    }
  };

  function startSentenceTimer() {
    recordingTimer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
      const minutes = Math.floor(elapsed / 60);
      const seconds = elapsed % 60;
      document.getElementById("recording-timer").textContent = `${String(
        minutes
      ).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    }, 100);
  }

  function stopSentenceTimer() {
    if (recordingTimer) {
      clearInterval(recordingTimer);
    }
  }

  window.evaluateSentencePronunciation = async function () {
    const text = document.getElementById("evaluation-text").value.trim();

    if (!text) {
      alert("평가할 문장을 입력하세요");
      return;
    }

    if (sentenceRecordedChunks.length === 0) {
      alert("음성을 녹음하세요");
      return;
    }

    // Show loading
    document
      .getElementById("sentence-recording-progress")
      .classList.remove("hidden");
    document.getElementById("sentence-recording-progress").innerHTML =
      '<div class="inline-block"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-2"></div><p class="text-sm text-gray-600">분석 중...</p></div>';

    const controller = new AbortController();
    const timeoutMs = 25000;
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const audioBlob = new Blob(sentenceRecordedChunks, { type: "audio/wav" });

      const formData = new FormData();
      formData.append("text", text);
      formData.append("audio", audioBlob, "recording.wav");

      if (
        selectedSentence &&
        selectedSentence.syll_ltrs &&
        selectedSentence.syll_phns &&
        selectedSentence.fst
      ) {
        formData.append("syll_ltrs", selectedSentence.syll_ltrs);
        formData.append("syll_phns", selectedSentence.syll_phns);
        formData.append("fst", selectedSentence.fst);
      }

      const response = await fetch("/api/speechpro/evaluate", {
        method: "POST",
        body: formData,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || "평가 실패");
      }

      const result = await response.json();
      document
        .getElementById("sentence-recording-progress")
        .classList.add("hidden");

      if (result.success) {
        displaySentenceResults(result);
      } else {
        alert(result.error || "평가에 실패했습니다");
      }
    } catch (error) {
      document
        .getElementById("sentence-recording-progress")
        .classList.add("hidden");
      if (error.name === "AbortError") {
        alert("요청이 지연되고 있습니다. 다시 시도해주세요.");
      } else {
        alert(`평가 중 오류: ${error.message}`);
      }
    } finally {
      clearTimeout(timeoutId);
    }
  };

  function displaySentenceResults(result) {
    const score = Math.round(result.overall_score || 0);

    let feedback = "";
    if (score >= 90) feedback = "완벽한 발음입니다! 🌟";
    else if (score >= 80) feedback = "매우 좋은 발음입니다! 👍";
    else if (score >= 70)
      feedback = "좋은 발음입니다. 조금 더 연습하면 더 좋아질 거예요 💪";
    else if (score >= 60)
      feedback = "더 연습이 필요합니다. 계속해서 노력해보세요 📚";
    else feedback = "많은 연습이 필요합니다. 천천히 따라해보세요 🎯";

    let resultHtml = `
      <div class="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-6 mb-6">
        <div class="text-center mb-4">
          <div class="text-5xl font-bold text-blue-600 mb-2">${score}점</div>
          <p class="text-lg font-semibold text-gray-800">${feedback}</p>
        </div>
        <div class="w-full bg-gray-300 rounded-full h-3">
          <div class="bg-blue-500 h-3 rounded-full" style="width: ${score}%"></div>
        </div>
      </div>
    `;

    if (result.ai_feedback) {
      resultHtml += `
        <div class="bg-white rounded-lg p-4 border border-gray-200">
          <h3 class="font-bold text-gray-900 mb-2">💡 AI 피드백</h3>
          <p class="text-gray-700 whitespace-pre-wrap">${result.ai_feedback}</p>
        </div>
      `;
    }

    document.getElementById("sentence-score-result").innerHTML = resultHtml;
    document.getElementById("sentence-score-result").classList.remove("hidden");
  }

  window.loadSentencesData = async function () {
    try {
      console.log(
        "loadSentencesData() called - fetching from /api/speechpro/sentences"
      );
      const response = await fetch("/api/speechpro/sentences");
      console.log("Response received:", response);

      if (!response.ok) {
        throw new Error("문장 데이터를 불러올 수 없습니다");
      }

      const sentences = await response.json();
      console.log("Sentences loaded:", sentences.length, "sentences");
      const select = document.getElementById("sentence-select");

      if (!select) {
        console.error("sentence-select element not found");
        return;
      }

      // Always refresh the list
      select.innerHTML = '<option value="">-- 문장 선택 --</option>';

      if (Array.isArray(sentences)) {
        sentences.forEach((sentence) => {
          const option = document.createElement("option");
          option.value = JSON.stringify(sentence);
          const sourceLabel =
            sentence.source === "precomputed" ? "[프리셋] " : "";
          option.textContent = `${sourceLabel}[${sentence.level}] ${sentence.sentenceKr}`;
          select.appendChild(option);
        });
      }
      console.log(
        "loadSentencesData() completed - loaded",
        select.options.length - 1,
        "sentences"
      );
    } catch (error) {
      console.error("문장 로드 실패:", error);
      const select = document.getElementById("sentence-select");
      if (select) {
        select.innerHTML =
          '<option value="">-- 문장 데이터를 불러올 수 없습니다 --</option>';
      }
    }
  };

  window.selectSentence = function () {
    const select = document.getElementById("sentence-select");

    if (!select.value) {
      selectedSentence = null;
      document.getElementById("sentence-level").textContent = "";
      document.getElementById("sentence-difficulty").textContent = "";
      document.getElementById("sentence-category").textContent = "";
      document.getElementById("sentence-en").textContent = "";
      document.getElementById("sentence-tips").textContent = "";
      document.getElementById("sentence-info-section").classList.add("hidden");
      return;
    }

    try {
      const sentence = JSON.parse(select.value);
      selectedSentence = sentence;

      document.getElementById("evaluation-text").value = sentence.sentenceKr;
      document.getElementById("sentence-level").textContent =
        sentence.level || "";
      document.getElementById("sentence-difficulty").textContent =
        sentence.difficulty || "";
      document.getElementById("sentence-category").textContent =
        sentence.category || "";
      document.getElementById("sentence-en").textContent =
        sentence.sentenceEn || "";
      document.getElementById("sentence-tips").textContent =
        sentence.tips || "";
      document
        .getElementById("sentence-info-section")
        .classList.remove("hidden");
    } catch (error) {
      console.error("문장 선택 중 오류:", error);
    }
  };

  // Initialize
  console.log(
    "Script loaded, current document.readyState:",
    document.readyState
  );

  // Always wait for DOMContentLoaded to ensure all elements are present
  function doInitialize() {
    console.log("Starting initialization...");
    initializeDOMElements();
    loadWords();
  }

  if (document.readyState === "loading") {
    // DOM이 아직 로드 중이면 DOMContentLoaded 대기
    console.log("DOM still loading, waiting for DOMContentLoaded...");
    document.addEventListener("DOMContentLoaded", doInitialize);
  } else {
    // DOM이 이미 로드됨
    console.log("DOM already loaded, initializing immediately...");
    // 약간의 딜레이를 주어 모든 DOM 요소가 준비되도록 함
    setTimeout(doInitialize, 100);
  }
})();
