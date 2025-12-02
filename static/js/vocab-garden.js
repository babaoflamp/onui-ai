// 단어 꽃밭 - Vocabulary Flower Garden JavaScript

(function() {
  'use strict';

  let vocabList = [];
  const flowerGrid = document.getElementById("flowerGrid");
  const detailsBox = document.getElementById("details");
  const infoCaption = document.getElementById("infoCaption");

  // Load vocabulary from API
  async function loadVocabulary() {
    try {
      const response = await fetch('/api/vocabulary');
      const data = await response.json();
      vocabList = data.vocabulary || [];

      if (vocabList.length > 0) {
        renderFlowers();
      } else {
        flowerGrid.innerHTML = '<p class="text-gray-500">단어 데이터가 없습니다.</p>';
      }
    } catch (error) {
      console.error('Error loading vocabulary:', error);
      flowerGrid.innerHTML = '<p class="text-red-500">데이터를 불러오는 중 오류가 발생했습니다.</p>';
    }
  }

  // Render flower buttons
  function renderFlowers() {
    flowerGrid.innerHTML = '';

    vocabList.forEach((item, index) => {
      const card = document.createElement("div");
      card.className = "flower-card";
      card.dataset.id = item.id;
      card.dataset.level = item.level;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "flower-btn";
      btn.setAttribute("aria-label", item.word + " 선택");
      btn.textContent = item.emoji || "🌸";

      const wordLabel = document.createElement("div");
      wordLabel.className = "flower-word";
      wordLabel.textContent = item.word;

      const cefr = document.createElement("div");
      cefr.className = "cefr-pill";
      cefr.innerHTML = `<span class="cefr-dot"></span> CEFR ${item.level}`;

      card.appendChild(btn);
      card.appendChild(wordLabel);
      card.appendChild(cefr);

      flowerGrid.appendChild(card);

      // Auto-select first word
      if (index === 0) {
        card.classList.add("active");
        showDetails(item);
      }

      card.addEventListener("click", () => {
        document.querySelectorAll(".flower-card").forEach(c => c.classList.remove("active"));
        card.classList.add("active");
        showDetails(item);
      });
    });
  }

  // Show word details in right panel
  function showDetails(item) {
    if (!detailsBox) return;

    const mainWord = detailsBox.querySelector(".main-word");
    const roman = detailsBox.querySelector(".roman");
    const meaning = detailsBox.querySelector(".meaning");
    const tagWrap = detailsBox.querySelector(".tag-wrap");
    const sentKr = detailsBox.querySelector(".sentence-kr");
    const sentEn = detailsBox.querySelector(".sentence-en");

    if (mainWord) mainWord.textContent = item.word;
    if (roman) roman.textContent = item.roman ? `발음 (romanization): ${item.roman}` : "";
    if (meaning) meaning.textContent = `뜻: ${item.meaningKo} (${item.meaningEn})`;

    // Tags
    if (tagWrap) {
      tagWrap.innerHTML = "";
      const levelTag = document.createElement("span");
      levelTag.className = "tag level";
      levelTag.textContent = `CEFR ${item.level}`;
      tagWrap.appendChild(levelTag);

      if (item.tags && item.tags.length > 0) {
        item.tags.forEach(t => {
          const tag = document.createElement("span");
          tag.className = "tag";
          tag.textContent = t;
          tagWrap.appendChild(tag);
        });
      }
    }

    if (sentKr) sentKr.textContent = item.sentenceKr || "";
    if (sentEn) sentEn.textContent = item.sentenceEn || "";

    if (infoCaption) infoCaption.textContent = `"${item.word}" 단어가 선택되었습니다.`;
  }

  // Initialize
  loadVocabulary();
})();
