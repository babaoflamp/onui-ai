// 단어 순서 맞추기 - Word Order Puzzle JavaScript

(function() {
  'use strict';

  let sentences = [];
  let currentIndex = 0;
  let draggedCard = null;
  let selectedCard = null;

  const wordsRow = document.getElementById("wordsRow");
  const puzzleTitle = document.getElementById("puzzleTitle");
  const puzzleMeta = document.getElementById("puzzleMeta");
  const sentenceHint = document.getElementById("sentenceHint");
  const translationText = document.getElementById("translationText");
  const feedback = document.getElementById("feedback");

  const shuffleBtn = document.getElementById("shuffleBtn");
  const checkBtn = document.getElementById("checkBtn");
  const nextBtn = document.getElementById("nextBtn");

  // Timer elements
  const timerProgress = document.getElementById("timerProgress");
  const timerSun = document.getElementById("timerSun");
  const timerMoon = document.getElementById("timerMoon");
  const timerText = document.getElementById("timerText");

  const TIMER_TOTAL = 30000; // 30 seconds
  let timerStart = Date.now();

  // Load sentences from API
  async function loadSentences() {
    try {
      const response = await fetch('/api/puzzle/sentences');
      const data = await response.json();
      sentences = data.sentences || [];

      if (sentences.length > 0) {
        renderSentence();
        resetTimer();
        requestAnimationFrame(updateTimer);
      } else {
        wordsRow.innerHTML = '<p class="text-gray-500">문장 데이터가 없습니다.</p>';
      }
    } catch (error) {
      console.error('Error loading sentences:', error);
      wordsRow.innerHTML = '<p class="text-red-500">데이터를 불러오는 중 오류가 발생했습니다.</p>';
    }
  }

  // Shuffle array utility
  function shuffleArray(array) {
    const arr = [...array];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    // Ensure shuffled array is different from original
    if (arr.join(" ") === array.join(" ")) {
      return shuffleArray(array);
    }
    return arr;
  }

  // Render current sentence
  function renderSentence() {
    if (!sentences.length) return;

    const data = sentences[currentIndex];
    puzzleTitle.textContent = `문장 ${currentIndex + 1} / ${sentences.length}`;
    puzzleMeta.textContent = `레벨: ${data.level} · 어순 연습`;
    sentenceHint.textContent = `${data.situation} — ${data.hint}`;
    translationText.textContent = data.translation;

    feedback.textContent = "카드를 드래그하거나 클릭해서 순서를 바꿔 보세요.";
    feedback.className = "feedback";
    wordsRow.classList.remove("correct", "incorrect");
    selectedCard = null;

    wordsRow.innerHTML = "";
    const shuffled = shuffleArray(data.words);
    shuffled.forEach((w) => {
      const card = document.createElement("div");
      card.className = "word-card";
      card.draggable = true;
      card.innerHTML = `<span class="word-text">${w}</span>`;
      addCardEvents(card);
      wordsRow.appendChild(card);
    });

    resetTimer();
  }

  // Add drag and click events to word cards
  function addCardEvents(card) {
    // Drag events
    card.addEventListener("dragstart", (e) => {
      draggedCard = card;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });

    card.addEventListener("dragend", () => {
      if (draggedCard) {
        draggedCard.classList.remove("dragging");
        draggedCard = null;
      }
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      const targetCard = card;
      if (!draggedCard || draggedCard === targetCard) return;
      swapCardTexts(draggedCard, targetCard);
    });

    // Click events for mobile/alternative interaction
    card.addEventListener("click", () => {
      if (!selectedCard) {
        selectedCard = card;
        card.classList.add("selected");
        return;
      }

      if (selectedCard === card) {
        card.classList.remove("selected");
        selectedCard = null;
        return;
      }

      swapCardTexts(selectedCard, card);
      selectedCard.classList.remove("selected");
      selectedCard = null;
    });
  }

  // Swap text content between two cards
  function swapCardTexts(cardA, cardB) {
    const spanA = cardA.querySelector(".word-text");
    const spanB = cardB.querySelector(".word-text");
    const tmp = spanA.textContent;
    spanA.textContent = spanB.textContent;
    spanB.textContent = tmp;
  }

  // Get current word order
  function getCurrentOrder() {
    return Array.from(wordsRow.querySelectorAll(".word-card .word-text")).map(
      (span) => span.textContent
    );
  }

  // Check answer
  function checkAnswer() {
    if (!sentences.length) return;

    const data = sentences[currentIndex];
    const current = getCurrentOrder();
    const correct = data.words;

    if (current.join(" ") === correct.join(" ")) {
      wordsRow.classList.remove("incorrect");
      wordsRow.classList.add("correct");
      feedback.textContent = "정답입니다! 아주 잘하셨어요. 👏";
      feedback.className = "feedback good";
    } else {
      wordsRow.classList.remove("correct");
      wordsRow.classList.add("incorrect");
      feedback.textContent = "조금 더 생각해 보세요. 어순을 다시 한 번 확인해 보세요.";
      feedback.className = "feedback bad";
      setTimeout(() => {
        wordsRow.classList.remove("incorrect");
      }, 220);
    }
  }

  // Event listeners for buttons
  if (shuffleBtn) {
    shuffleBtn.addEventListener("click", () => {
      if (!sentences.length) return;

      const data = sentences[currentIndex];
      const shuffled = shuffleArray(data.words);
      const cards = wordsRow.querySelectorAll(".word-card .word-text");
      shuffled.forEach((w, i) => {
        if (cards[i]) cards[i].textContent = w;
      });
      feedback.textContent = "다시 섞었습니다. 올바른 순서를 맞춰 보세요.";
      feedback.className = "feedback";
      wordsRow.classList.remove("correct", "incorrect");
      selectedCard = null;
      resetTimer();
    });
  }

  if (checkBtn) {
    checkBtn.addEventListener("click", () => {
      checkAnswer();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      currentIndex = (currentIndex + 1) % sentences.length;
      renderSentence();
    });
  }

  // Timer functions
  function resetTimer() {
    timerStart = Date.now();
  }

  function updateTimer() {
    const now = Date.now();
    let elapsed = now - timerStart;
    if (elapsed > TIMER_TOTAL) {
      elapsed = elapsed % TIMER_TOTAL;
      timerStart = now - elapsed;
    }
    const progress = elapsed / TIMER_TOTAL;

    if (timerProgress) timerProgress.style.width = `${progress * 100}%`;

    const sunPos = 5 + progress * 70;
    const moonPos = 25 + progress * 70;

    if (timerSun) {
      timerSun.style.left = sunPos + "%";
      timerSun.style.opacity = String(1 - progress);
    }
    if (timerMoon) {
      timerMoon.style.left = moonPos + "%";
      timerMoon.style.opacity = String(progress);
    }

    const seconds = Math.floor(elapsed / 1000);
    const secStr = seconds.toString().padStart(2, "0");
    if (timerText) timerText.textContent = `00:${secStr}`;

    requestAnimationFrame(updateTimer);
  }

  // Initialize
  loadSentences();
})();
