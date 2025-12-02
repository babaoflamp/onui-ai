// 오늘의 표현 - Daily Expression Card Slider JavaScript

(function() {
  'use strict';

  let expressions = [];
  let currentIndex = 0;

  const card = document.getElementById("expressionCard");
  const sentenceKrEl = document.getElementById("sentenceKr");
  const sentenceEnEl = document.getElementById("sentenceEn");
  const cultureNoteEl = document.getElementById("cultureNote");
  const levelChipEl = document.getElementById("levelChip");
  const situationLabelEl = document.getElementById("situationLabel");
  const tagLabelEl = document.getElementById("tagLabel");
  const sliderCaptionEl = document.getElementById("sliderCaption");
  const dotsContainer = document.getElementById("dots");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");

  // Load expressions from API
  async function loadExpressions() {
    try {
      const response = await fetch('/api/expressions');
      const data = await response.json();
      expressions = data.expressions || [];

      if (expressions.length > 0) {
        createDots();
        renderCard();
      } else {
        card.innerHTML = '<p class="text-gray-500">표현 데이터가 없습니다.</p>';
      }
    } catch (error) {
      console.error('Error loading expressions:', error);
      card.innerHTML = '<p class="text-red-500">데이터를 불러오는 중 오류가 발생했습니다.</p>';
    }
  }

  // Create navigation dots
  function createDots() {
    dotsContainer.innerHTML = '';
    expressions.forEach((_, idx) => {
      const dot = document.createElement("div");
      dot.className = "dot";
      dot.dataset.index = idx;
      dot.addEventListener("click", () => {
        currentIndex = idx;
        renderCard();
      });
      dotsContainer.appendChild(dot);
    });
  }

  // Render current card
  function renderCard() {
    if (!expressions.length) return;

    const data = expressions[currentIndex];

    sentenceKrEl.textContent = data.sentenceKr;
    sentenceEnEl.textContent = data.sentenceEn;
    cultureNoteEl.textContent = data.cultureNote;
    levelChipEl.textContent = "CEFR " + data.level;
    situationLabelEl.textContent = data.situation;
    tagLabelEl.textContent = data.tag;

    sliderCaptionEl.textContent = `${currentIndex + 1} / ${expressions.length}`;

    // Update dots
    document.querySelectorAll(".dot").forEach((d, idx) => {
      d.classList.toggle("active", idx === currentIndex);
    });

    // Animation effect
    card.style.opacity = "0";
    card.style.transform = "translateY(8px)";
    requestAnimationFrame(() => {
      setTimeout(() => {
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";
      }, 30);
    });
  }

  // Navigation buttons
  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      currentIndex = (currentIndex - 1 + expressions.length) % expressions.length;
      renderCard();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      currentIndex = (currentIndex + 1) % expressions.length;
      renderCard();
    });
  }

  // Initialize
  loadExpressions();
})();
