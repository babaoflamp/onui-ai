// Dashboard feed — loads recent pronunciation stats and track recommendations.
// Relies on global `translations` from i18n.js and /api/learning + /api/dashboard endpoints.

document.addEventListener("DOMContentLoaded", () => {
  loadSunoStyleDashboard();
});

async function loadSunoStyleDashboard() {
  const token = localStorage.getItem("auth_token");
  const feedContainer = document.getElementById("recent-evaluation-feed");
  const pronCountEl = document.getElementById("recent-pron-count");
  const tubeVocabFeed = document.getElementById("tube-vocab-feed");
  const tubeVocabCountEl = document.getElementById("tube-vocab-count");
  feedContainer.setAttribute("aria-busy", "true");
  tubeVocabFeed.setAttribute("aria-busy", "true");

  // 퀵 통계 로드
  if (token) {
    fetch("/api/dashboard/quick-stats", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((s) => {
        document.getElementById("qs-streak").textContent = s.consecutive_days ?? 0;
        document.getElementById("qs-score").textContent = (s.avg_score ?? 0) + "%";
        document.getElementById("qs-total").textContent = s.total_practices ?? 0;
        document.getElementById("quick-stats").classList.remove("hidden");
      })
      .catch(() => {});
  }

  try {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const [pronResp, vocabResp] = await Promise.all([
      fetch("/api/dashboard/recent-pronunciation", { headers }),
      fetch("/api/tube/vocab", { headers }),
    ]);
    const [pronData, vocabData] = await Promise.all([
      pronResp.json(),
      vocabResp.json(),
    ]);

    feedContainer.innerHTML = "";
    tubeVocabFeed.innerHTML = "";

    const pronunciationItems = Array.isArray(pronData?.recent_list) ? pronData.recent_list : [];
    pronCountEl.textContent = String(pronData?.total_count ?? pronunciationItems.length ?? 0);

    if (pronunciationItems.length > 0) {
      feedContainer.innerHTML = pronunciationItems.map((item) => createSunoCard(item)).join("");
    } else if (pronData?.recent && pronData.recent.score_latest > 0) {
      feedContainer.innerHTML = createSunoCard(pronData.recent);
    } else {
      // 데이터가 없을 때: empty-state + 샘플 카드 1장
      const noRecords = translations["dash.no_records"] || "No evaluation records yet";
      const diagnoseNow = translations["dash.diagnose_now"] || "Diagnose your first pronunciation now";
      const startLabel = translations["dash.start_now"] || "Start now";
      feedContainer.innerHTML = `
        <a href="/speechpro-practice" class="empty-state col-span-1 no-underline hover:bg-white/5 transition-colors">
          <div class="empty-state__icon" aria-hidden="true">🐯</div>
          <p class="empty-state__title">${noRecords}</p>
          <p class="empty-state__desc">${diagnoseNow}</p>
          <span class="empty-state__action btn btn-primary btn-sm">${startLabel}</span>
        </a>
        ${createSunoCard({
          sentence_text: "안녕하세요. 만나서 반가워요.",
          score_latest: 92,
          fluency_accuracy_latest: 95,
          is_sample: true,
        })}
      `;
    }

    const vocabItems = Array.isArray(vocabData?.vocab) ? vocabData.vocab : [];
    tubeVocabCountEl.textContent = String(vocabItems.length);
    if (vocabItems.length > 0) {
      tubeVocabFeed.innerHTML = vocabItems.map((item) => createVocabCard(item)).join("");
    } else {
      tubeVocabFeed.innerHTML = `
        <a href="/video-learning" class="empty-state col-span-1 no-underline hover:bg-white/5 transition-colors">
          <div class="empty-state__icon" aria-hidden="true">📚</div>
          <p class="empty-state__title">No saved OAITube words yet</p>
          <p class="empty-state__desc">Save words from video-learning and review them here.</p>
          <span class="empty-state__action btn btn-primary btn-sm">Go to OAITube</span>
        </a>
      `;
    }
  } catch (e) {
    console.error("Dashboard Load Error:", e);
    const errorLoading = translations["dash.error_loading"] || "An error occurred while loading data.";
    const errorTitle = translations["common.error_title"] || "Something went wrong";
    const retryLabel = translations["common.retry"] || "Retry";
    const offline = !navigator.onLine;
    const offlineNote = offline
      ? translations["common.offline"] || "You appear to be offline."
      : "";
    feedContainer.innerHTML = `
      <div class="error-state col-span-full" role="alert">
        <p class="error-state__title">${errorTitle}</p>
        <p class="error-state__desc">${offlineNote} ${errorLoading}</p>
        <button type="button" class="btn btn-primary btn-sm" onclick="loadSunoStyleDashboard()">${retryLabel}</button>
      </div>`;
    tubeVocabFeed.innerHTML = `
      <div class="error-state col-span-full" role="alert">
        <p class="error-state__title">${errorTitle}</p>
        <p class="error-state__desc">${offlineNote} ${errorLoading}</p>
        <button type="button" class="btn btn-primary btn-sm" onclick="loadSunoStyleDashboard()">${retryLabel}</button>
      </div>`;
  } finally {
    feedContainer.setAttribute("aria-busy", "false");
    tubeVocabFeed.setAttribute("aria-busy", "false");
  }
}

function createSunoCard(item) {
  const isSample = item.is_sample;
  const scoreUnit = translations["dash.score_unit"] || "pts";
  const fluencyLabel = translations["dash.fluency"] || "FLUENCY";
  const href = `/speechpro-practice?text=${encodeURIComponent(item.sentence_text)}`;
  return `
    <a href="${href}" class="suno-card group no-underline text-inherit">
      <div class="flex justify-between items-start mb-6">
        <div class="flex items-center gap-2">
          <span class="score-badge">${Math.round(item.score_latest)}${scoreUnit}</span>
          ${isSample ? '<span class="text-xs text-white font-black tracking-tighter">SAMPLE</span>' : ""}
        </div>
        <span class="text-xs text-white/85 font-bold uppercase tracking-wider">${item.last_attempted_at ? item.last_attempted_at.split(" ")[0] : "NEW"}</span>
      </div>
      <h3 class="text-2xl font-black text-white mb-6 line-clamp-2 leading-tight">${item.sentence_text}</h3>
      <div class="flex items-center gap-4 mt-auto">
        <div class="flex-1 bg-gray-800 h-2 rounded-full overflow-hidden" role="progressbar" aria-valuenow="${Math.round(item.fluency_accuracy_latest)}" aria-valuemin="0" aria-valuemax="100" aria-label="${fluencyLabel}">
          <div class="bg-gradient-to-r from-orange-500 to-red-500 h-full" style="width: ${item.fluency_accuracy_latest}%"></div>
        </div>
        <span class="text-sm font-bold text-white">${fluencyLabel} ${Math.round(item.fluency_accuracy_latest)}%</span>
      </div>
      <div class="play-overlay" aria-hidden="true">
        <div class="w-14 h-14 bg-orange-500 rounded-full flex items-center justify-center shadow-2xl scale-110">
          <span class="text-white text-xl ml-1">▶</span>
        </div>
      </div>
    </a>
  `;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function createVocabCard(item) {
  const label = escapeHtml(item.label || "");
  const pos = escapeHtml(item.pos || "");
  const meaning = escapeHtml(item.meaning || item.mean || "");
  const savedAt = item.savedAt ? String(item.savedAt).split(" ")[0] : "SAVED";

  return `
    <a href="/video-learning" class="suno-card group no-underline text-inherit">
      <div class="flex justify-between items-start mb-5 gap-3">
        <span class="score-badge">WORD</span>
        <span class="text-xs text-white/85 font-bold uppercase tracking-wider">${savedAt}</span>
      </div>
      <h3 class="text-3xl font-black text-white mb-2 leading-tight">${label}</h3>
      ${pos ? `<p class="text-xs font-black uppercase tracking-[0.25em] text-white mb-3">${pos}</p>` : ""}
      <p class="text-base text-white leading-relaxed line-clamp-3">${meaning || "Saved from OAITube vocabulary."}</p>
      <div class="mt-auto pt-6 text-sm font-bold text-white/85">Open in OAITube</div>
      <div class="play-overlay" aria-hidden="true">
        <div class="w-14 h-14 bg-orange-500 rounded-full flex items-center justify-center shadow-2xl scale-110">
          <span class="text-white text-xl">📚</span>
        </div>
      </div>
    </a>
  `;
}
