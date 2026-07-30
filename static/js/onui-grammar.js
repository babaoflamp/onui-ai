// OAI Grammar — chat UI with character selector and POST /api/messenger/chat.

const chatBody = document.getElementById("chat-body");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");

let currentCharacter = {
  id: "chaeon",
  name: "Chaewon",
  role: "Korean Grammar Teacher",
  avatar: "/static/images/onui-pure-idol.png",
};
const characterDropdown = document.getElementById("character-dropdown");
const correctionHint = {
  placeholder: "Type a Korean sentence and I will explain the correction in English.",
  starter: "Send me a Korean sentence and I will correct it and explain the grammar in English.",
};

let chatHistory = [
  { role: "assistant", content: correctionHint.starter },
];

document.getElementById("character-selector").addEventListener("click", (e) => {
  e.stopPropagation();
  characterDropdown.classList.toggle("hidden");
});
document.addEventListener("click", () => characterDropdown.classList.add("hidden"));

const charKeyMap = { chaeon: "msg.char_chaewon", teacher: "msg.char_youngja", barista: "msg.char_minsu", doctor: "msg.char_drpark" };
const t = (key, fallback) => (typeof translations !== "undefined" && translations[key]) || fallback;

function getStarterMessage() {
  return correctionHint.starter;
}

function updateInputPlaceholder() {
  userInput.placeholder = correctionHint.placeholder;
}

function resetConversation() {
  const starter = getStarterMessage();
  chatHistory = [{ role: "assistant", content: starter }];
  chatBody.innerHTML =
    `<div class="text-center text-xs font-bold text-white/30 uppercase tracking-widest my-4">${t("msg.today", "Today")}</div>`;
  addMessage("assistant", starter);
}

function selectCharacter(id, name, avatar, role) {
  currentCharacter = { id, name, role, avatar };
  document.getElementById("current-avatar").src = avatar;
  document.getElementById("current-name").textContent = (charKeyMap[id] && t(charKeyMap[id], name)) || name;
  characterDropdown.classList.add("hidden");
  resetConversation();
}

function addMessage(role, content) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${role === "assistant" ? "bubble-ai" : "bubble-user"}`;
  bubble.innerText = content;
  chatBody.appendChild(bubble);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function addCorrection(correction) {
  const original = correction.original || "";
  const corrected = correction.corrected || original;
  const unchanged = original.trim() === corrected.trim();
  const card = document.createElement("div");
  card.className = "correction-card";
  card.innerHTML = `
    <div class="flex items-center gap-2 mb-2">
      <span class="text-red-400 text-xs font-black uppercase tracking-widest">${t("msg.correction_label", "Grammar Correction")}</span>
    </div>
    ${unchanged
      ? `<p class="text-emerald-300 font-bold text-sm mb-1">${corrected}</p>`
      : `
        <p class="text-white/60 text-sm line-through decoration-red-500 mb-1">${original}</p>
        <p class="text-white font-bold text-sm">${corrected}</p>
      `
    }
  `;
  chatBody.appendChild(card);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function normalizeCorrectionPayload(result, originalText) {
  if (result && result.correction && typeof result.correction === "object") {
    return {
      original: result.correction.original || originalText,
      corrected: result.correction.corrected || result.correction.rewrite || originalText,
      reason: result.correction.reason || result.correction.feedback || result.reply || "",
    };
  }

  if (result && typeof result === "object") {
    const corrected = result.corrected || result.rewrite || originalText;
    const reason = result.reason || result.feedback || result.reply || "";
    return {
      original: result.original || originalText,
      corrected,
      reason,
    };
  }

  return {
    original: originalText,
    corrected: originalText,
    reason: "",
  };
}

function showTyping() {
  const indicator = document.createElement("div");
  indicator.className = "typing-indicator bubble-ai";
  indicator.id = "typing-indicator";
  indicator.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
  chatBody.appendChild(indicator);
  chatBody.scrollTop = chatBody.scrollHeight;
  return indicator;
}

updateInputPlaceholder();
addMessage("assistant", chatHistory[0].content);

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;

  userInput.value = "";
  addMessage("user", text);

  const typing = showTyping();

  try {
    const result = await APIClient.post("/api/messenger/chat", {
      message: text,
      history: chatHistory,
      character: currentCharacter.id,
      mode: "correction",
    });
    typing.remove();

    if (result?.success) {
      addCorrection(normalizeCorrectionPayload(result, text));
      addMessage("assistant", result.reply || t("toast.fetch_failed", "Failed to get response."));
      chatHistory.push({ role: "user", content: text });
      chatHistory.push({ role: "assistant", content: result.reply || "" });
    }
  } catch (err) {
    typing.remove();
    ToastManager.error(err?.message || t("toast.server_error", "Server connection failed."));
  }
});

window.selectCharacter = selectCharacter;
