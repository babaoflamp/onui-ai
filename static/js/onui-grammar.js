// Onui Grammar — chat UI with character selector and POST /api/messenger/chat.

const chatBody = document.getElementById("chat-body");
const chatForm = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");

let currentCharacter = {
  id: "chaeon",
  name: "Chaewon",
  role: "Language Exchange Partner",
  avatar: "/static/images/onui-pure-idol.png",
};
let currentMode = "chat";
const characterDropdown = document.getElementById("character-dropdown");
const modeHints = {
  chat: {
    placeholder: "한국어로 대화해 보세요...",
    starter: "안녕하세요! 오늘 어떤 한국어 연습을 하고 싶으세요? 😊",
  },
  correction: {
    placeholder: "문장을 입력하면 문법과 자연스러운 표현으로 고쳐드려요.",
    starter: "문장을 보내주시면 문법, 조사, 어색한 표현을 자연스럽게 고쳐드릴게요.",
  },
};

let chatHistory = [
  { role: "assistant", content: modeHints.chat.starter },
];

document.getElementById("character-selector").addEventListener("click", (e) => {
  e.stopPropagation();
  characterDropdown.classList.toggle("hidden");
});
document.addEventListener("click", () => characterDropdown.classList.add("hidden"));

const charKeyMap = { chaeon: "msg.char_chaewon", teacher: "msg.char_youngja", barista: "msg.char_minsu", doctor: "msg.char_drpark" };
const t = (key, fallback) => (typeof translations !== "undefined" && translations[key]) || fallback;

function getStarterMessage() {
  if (currentMode === "correction") {
    return modeHints.correction.starter;
  }
  return `${currentCharacter.name}(이/가) 도와드릴게요! 무엇을 말씀해 주시겠어요? 😊`;
}

function updateInputPlaceholder() {
  userInput.placeholder = currentMode === "correction"
    ? modeHints.correction.placeholder
    : t("msg.input_placeholder", modeHints.chat.placeholder);
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

function setMode(mode) {
  currentMode = mode;
  document.getElementById("mode-chat-btn").className =
    mode === "chat"
      ? "px-3 py-1 bg-orange-500/20 text-orange-400 rounded-full text-xs font-bold"
      : "px-3 py-1 text-white/40 hover:text-white rounded-full text-xs font-bold";
  document.getElementById("mode-correction-btn").className =
    mode === "correction"
      ? "px-3 py-1 bg-orange-500/20 text-orange-400 rounded-full text-xs font-bold"
      : "px-3 py-1 text-white/40 hover:text-white rounded-full text-xs font-bold";
  updateInputPlaceholder();
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
  const card = document.createElement("div");
  card.className = "correction-card";
  card.innerHTML = `
    <div class="flex items-center gap-2 mb-2">
      <span class="text-red-400 text-xs font-black uppercase tracking-widest">${t("msg.correction_label", "Grammar Correction")}</span>
    </div>
    <p class="text-white/60 text-sm line-through decoration-red-500 mb-1">${correction.original}</p>
    <p class="text-white font-bold text-sm">${correction.corrected}</p>
    <p class="text-[10px] text-white/40 mt-1 italic">${correction.reason}</p>
  `;
  chatBody.appendChild(card);
  chatBody.scrollTop = chatBody.scrollHeight;
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
      mode: currentMode,
    });
    typing.remove();

    if (result?.success) {
      if (result.correction) {
        addCorrection(result.correction);
      }
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
window.setMode = setMode;
