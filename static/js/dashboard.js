// Dashboard command center: combines learning activity, AI coach, missions, and recent study signals.

document.addEventListener("DOMContentLoaded", () => {
  loadSunoStyleDashboard();
});

async function loadSunoStyleDashboard() {
  const token = localStorage.getItem("auth_token");
  const nickname = localStorage.getItem("user_nickname") || "Learner";
  setText("dashboard-nickname", nickname);
  setText("dashboard-date", formatToday());

  if (!token) {
    renderSignedOutDashboard();
    return;
  }

  const headers = { Authorization: `Bearer ${token}` };
  setBusy("ai-coach-routine", true);
  setBusy("recent-evaluation-feed", true);
  setBusy("tube-vocab-feed", true);

  const [statsResult, coachResult, weaknessResult, missionResult, reportResult, pronResult, vocabResult] = await Promise.allSettled([
    fetchJson("/api/dashboard/quick-stats", headers),
    fetchJson("/api/coach/today", headers),
    fetchJson("/api/coach/weakness-map", headers),
    fetchJson("/api/speaking-missions", headers),
    fetchJson("/api/ai-feedback/session-report/recent?limit=2", headers),
    fetchJson("/api/dashboard/recent-pronunciation", headers),
    fetchJson("/api/tube/vocab", headers),
  ]);

  const stats = valueOf(statsResult, {});
  const coach = valueOf(coachResult, {});
  const weakness = valueOf(weaknessResult, {});
  const missions = valueOf(missionResult, {});
  const reports = valueOf(reportResult, {});
  const pronunciation = valueOf(pronResult, {});
  const vocab = valueOf(vocabResult, {});

  renderQuickStats(stats);
  renderCoach(coach);
  renderWeakness(weakness);
  renderMissions(missions);
  renderFeedback(reports);
  renderPronunciation(pronunciation);
  renderVocabulary(vocab);

  setBusy("ai-coach-routine", false);
  setBusy("recent-evaluation-feed", false);
  setBusy("tube-vocab-feed", false);
}

async function fetchJson(url, headers = {}) {
  const res = await fetch(url, { headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.message || data.detail || `${url} failed`);
  return data;
}

function valueOf(result, fallback) {
  return result.status === "fulfilled" ? result.value : fallback;
}

function renderSignedOutDashboard() {
  setText("hero-next-action-title", "로그인 후 개인 루틴을 확인하세요");
  setText("hero-next-action-desc", "AI 코치가 발음, 어휘, 듣기, 말하기 기록을 기반으로 오늘의 학습 순서를 추천합니다.");
  setHref("hero-primary-cta", "/login");
  setText("hero-primary-cta", "로그인하기");
  setHref("hero-secondary-cta", "/signup");
  setText("hero-secondary-cta", "무료 시작");
  const routineEl = byId("ai-coach-routine");
  if (routineEl) {
    routineEl.innerHTML = renderEmptyCard("로그인이 필요합니다", "개인 맞춤 루틴과 학습 리포트를 보려면 로그인해주세요.", "/login", "로그인");
  }
}

function renderQuickStats(stats) {
  setText("qs-streak", stats.consecutive_days ?? 0);
  setText("qs-score", `${Math.round(Number(stats.avg_score || 0))}%`);
  setText("qs-total", stats.total_practices ?? 0);
  byId("quick-stats")?.classList.remove("hidden");
}

function renderCoach(data) {
  const routine = Array.isArray(data.routine) ? data.routine : [];
  const firstPending = routine.find((step) => step.status !== "completed") || routine[0];
  if (firstPending) {
    setText("hero-next-action-title", firstPending.title || "오늘의 루틴");
    setText("hero-next-action-desc", firstPending.action || "추천 활동을 완료하세요.");
    setText("hero-next-minutes", firstPending.duration_min ? `${firstPending.duration_min} min` : "AI 추천");
    setHref("hero-primary-cta", firstPending.url || "/speechpro-practice");
    setText("hero-next-action-meta", firstPending.reason || "AI/자동 추천은 학습 참고용입니다.");
  }

  const routineEl = byId("ai-coach-routine");
  if (!routineEl) return;
  if (!routine.length) {
    routineEl.innerHTML = onboardingRoutine().map(renderCoachStep).join("");
    return;
  }
  routineEl.innerHTML = routine.map(renderCoachStep).join("");
}

function onboardingRoutine() {
  return [
    { id: "first-pron", title: "첫 발음 진단", duration_min: 4, action: "짧은 문장을 녹음해 현재 발음 기준점을 만드세요.", reason: "루틴 추천을 시작하기 위한 첫 데이터입니다.", url: "/speechpro-practice" },
    { id: "first-video", title: "영상 단어 저장", duration_min: 5, action: "OnuiTube에서 단어 3개를 저장하세요.", reason: "어휘와 듣기 데이터를 함께 쌓습니다.", url: "/video-learning" },
    { id: "first-speak", title: "짧은 대화", duration_min: 5, action: "AI 음성 통화로 3분 대화를 진행하세요.", reason: "말하기 유창성 데이터를 만듭니다.", url: "/voice-call" },
  ];
}

function renderCoachStep(step) {
  const done = step.status === "completed";
  return `
    <a href="${escapeAttr(step.url || "/learning-progress")}" class="dash-action-card ${done ? "dash-action-card--done" : ""}">
      <div class="dash-action-card__top">
        <span class="score-badge">${done ? "DONE" : `${Number(step.duration_min || 0)}M`}</span>
        <span class="dash-muted">AI</span>
      </div>
      <h3>${escapeHtml(step.title || "학습 단계")}</h3>
      <p>${escapeHtml(step.action || "추천 활동을 완료하세요.")}</p>
      <div class="dash-action-card__footer">${escapeHtml(step.reason || "학습 데이터를 기반으로 추천되었습니다.")}</div>
    </a>`;
}

function renderWeakness(data) {
  const map = data.weakness_map || {};
  const primary = map.primary || {};
  const categories = Array.isArray(map.categories) ? map.categories.slice(0, 4) : [];
  setText("weakness-primary", primary.label || "분석할 학습 데이터가 더 필요합니다");
  setText("weakness-summary", map.summary || primary.reason || "발음 평가, 영상 학습, 말하기 활동을 시작하면 우선 보강 영역을 추천합니다.");
  const el = byId("weakness-categories");
  if (!el) return;
  if (!categories.length) {
    el.innerHTML = `<div class="dash-mini-row"><span class="dash-mini-row__label">Start data collection</span><span class="dash-mini-row__action">발음 진단과 OnuiTube 학습을 먼저 진행하세요.</span></div>`;
    return;
  }
  el.innerHTML = categories.map((item) => {
    const score = clamp(Number(item.score || 0), 0, 100);
    return `
      <a href="${escapeAttr(item.url || "/learning-progress")}" class="dash-mini-row no-underline">
        <span class="dash-mini-row__label">${escapeHtml(item.label || item.key)}</span>
        <span class="dash-mini-row__bar"><span class="dash-mini-row__fill" style="width:${score}%"></span></span>
        <span class="dash-mini-row__action">${escapeHtml(item.next_action || "다음 연습을 진행하세요.")}</span>
      </a>`;
  }).join("");
}

function renderMissions(data) {
  const missions = Array.isArray(data.missions) ? data.missions.slice(0, 2) : [];
  setText("speaking-mission-count", missions.length);
  const el = byId("speaking-mission-feed");
  if (!el) return;
  if (!missions.length) {
    el.innerHTML = renderEmptyCard("말하기 미션 준비 중", "상황 미션을 불러오지 못했습니다. 역할극에서 바로 연습할 수 있습니다.", "/roleplay", "역할극 열기");
    return;
  }
  el.innerHTML = missions.map((mission) => `
    <a href="${escapeAttr(mission.next_url || "/roleplay")}" class="dash-action-card dash-action-card--compact">
      <div class="dash-action-card__top"><span class="score-badge">${escapeHtml(mission.level || "MISSION")}</span></div>
      <h3>${escapeHtml(mission.title || "말하기 미션")}</h3>
      <p>${escapeHtml(mission.scenario || "실전 상황을 연습하세요.")}</p>
    </a>`).join("");
}

function renderFeedback(data) {
  const reports = Array.isArray(data.reports) ? data.reports.slice(0, 2) : [];
  const el = byId("ai-feedback-feed");
  if (!el) return;
  if (!reports.length) {
    el.innerHTML = renderEmptyCard("AI 피드백 대기 중", "연습 후 세션 리포트를 생성하면 다음 연습이 여기에 표시됩니다.", "/speechpro-practice", "첫 리포트 만들기");
    return;
  }
  el.innerHTML = reports.map((item) => {
    const report = item.report || {};
    const next = Array.isArray(report.next_practice) ? report.next_practice[0] : report.next_practice;
    return `
      <div class="dash-action-card dash-action-card--compact">
        <div class="dash-action-card__top"><span class="score-badge">${escapeHtml(report.level_estimate || "피드백")}</span><span class="dash-muted">${escapeHtml(item.source_type || "practice")}</span></div>
        <h3>다음 연습</h3>
        <p>${escapeHtml(next || "짧은 문장을 다시 연습하세요.")}</p>
      </div>`;
  }).join("");
}

function renderPronunciation(data) {
  const el = byId("recent-evaluation-feed");
  const countEl = byId("recent-pron-count");
  if (!el) return;
  const items = Array.isArray(data.recent_list) ? data.recent_list.slice(0, 2) : [];
  if (countEl) countEl.textContent = String(data.total_count ?? items.length ?? 0);
  if (items.length) {
    el.innerHTML = items.map(createSunoCard).join("");
  } else if (data.recent && data.recent.score_latest > 0) {
    el.innerHTML = createSunoCard(data.recent);
  } else {
    el.innerHTML = `
      ${renderEmptyCard("첫 발음 기록이 없습니다", "짧은 문장 하나를 녹음하면 대시보드가 개인화됩니다.", "/speechpro-practice", "발음 진단 시작")}
      ${createSunoCard({ sentence_text: "안녕하세요. 만나서 반가워요.", score_latest: 92, fluency_accuracy_latest: 95, is_sample: true })}`;
  }
}

function createSunoCard(item) {
  const score = Math.round(Number(item.score_latest || 0));
  const fluency = Math.round(Number(item.fluency_accuracy_latest || item.accuracy_latest || 0));
  const href = `/speechpro-practice?text=${encodeURIComponent(item.sentence_text || "")}`;
  return `
    <a href="${escapeAttr(href)}" class="suno-card">
      <div class="dash-action-card__top"><span class="score-badge">${score}pts</span><span class="dash-muted">${item.is_sample ? "SAMPLE" : escapeHtml(String(item.last_attempted_at || "NEW").split(" ")[0])}</span></div>
      <h3>${escapeHtml(item.sentence_text || "연습 문장")}</h3>
      <p>Fluency ${fluency}%</p>
      <div class="dash-mini-row__bar" aria-hidden="true"><span class="dash-mini-row__fill" style="width:${clamp(fluency, 0, 100)}%"></span></div>
    </a>`;
}

function renderVocabulary(data) {
  const el = byId("tube-vocab-feed");
  const countEl = byId("tube-vocab-count");
  if (!el) return;
  const items = Array.isArray(data.vocab) ? data.vocab.slice(0, 2) : [];
  if (countEl) countEl.textContent = String(Array.isArray(data.vocab) ? data.vocab.length : 0);
  if (!items.length) {
    el.innerHTML = renderEmptyCard("저장한 단어가 없습니다", "OnuiTube 영상 자막에서 단어를 클릭해 저장해보세요.", "/video-learning", "OnuiTube 열기");
    return;
  }
  el.innerHTML = items.map(createVocabCard).join("");
}

function createVocabCard(item) {
  return `
    <a href="/video-learning" class="suno-card">
      <div class="dash-action-card__top"><span class="score-badge">WORD</span><span class="dash-muted">${escapeHtml(String(item.savedAt || "SAVED").split(" ")[0])}</span></div>
      <h3>${escapeHtml(item.label || "단어")}</h3>
      <p>${escapeHtml(item.meaning || item.mean || "저장한 OnuiTube 단어")}</p>
      ${item.pos ? `<div class="dash-action-card__footer">${escapeHtml(item.pos)}</div>` : ""}
    </a>`;
}

function renderEmptyCard(title, desc, href, action) {
  return `
    <a href="${escapeAttr(href)}" class="empty-state no-underline">
      <h3 class="empty-state__title">${escapeHtml(title)}</h3>
      <p class="empty-state__desc">${escapeHtml(desc)}</p>
      <div class="dash-action-card__footer">${escapeHtml(action)} →</div>
    </a>`;
}

function formatToday() {
  try {
    return new Intl.DateTimeFormat(localStorage.getItem("app_lang") || "ko", {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(new Date());
  } catch (_) {
    return new Date().toLocaleDateString();
  }
}

function byId(id) { return document.getElementById(id); }
function setText(id, value) { const el = byId(id); if (el) el.textContent = value; }
function setHref(id, value) { const el = byId(id); if (el) el.setAttribute("href", value); }
function setBusy(id, busy) { const el = byId(id); if (el) el.setAttribute("aria-busy", String(busy)); }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}
