// Learning Progress — fetches /api/learning/user-stats/me and renders weekly trends,
// activity focus, fluency metrics, coverage bars, and recent activity logs.

const ACHIEVEMENTS = {
  first_learning: { emoji: "🌟", title: "Beginner" },
  consecutive_3days: { emoji: "🔥", title: "3 Days" },
  score_80plus: { emoji: "⭐", title: "Expert" },
  five_practices: { emoji: "💪", title: "Worker" },
};

async function loadProgressData() {
  const token = localStorage.getItem("auth_token");
  const nickname = localStorage.getItem("user_nickname") || "Learner";
  if (!token) {
    location.href = "/login";
    return;
  }

  document.getElementById("userGreeting").textContent = nickname;

  try {
    const resp = await fetch(`/api/learning/user-stats/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) throw new Error("Failed to fetch stats");
    const statsData = await resp.json();

    updateUI(statsData);
    renderWeeklyGraph(statsData.daily_log);

    const fluencyGrade =
      statsData.avg_score >= 90
        ? "A+"
        : statsData.avg_score >= 80
          ? "A"
          : statsData.avg_score >= 70
            ? "B"
            : "C";
    renderFluencyMetrics({
      fluency_grade: fluencyGrade,
      best_fluency_score: statsData.best_score,
      speech_rate_average: 3.2,
      practice_frequency: statsData.learning_days > 5 ? "High" : "Normal",
    });
  } catch (err) {
    console.error("Failed to load real stats, using fallback", err);
  } finally {
    document.getElementById("loadingState").style.display = "none";
    document.getElementById("progressContent").classList.remove("hidden");
  }
}

function updateUI(data) {
  document.getElementById("consecutiveDays").textContent = data.consecutive_days || 0;

  const todayLog =
    data.daily_log && data.daily_log.length > 0
      ? data.daily_log[data.daily_log.length - 1]
      : { practices: 0, duration: 0 };
  document.getElementById("todayPractices").textContent = todayLog.practices || 0;
  document.getElementById("todayAvgScore").textContent = Math.round(data.avg_score || 0) + "%";
  document.getElementById("todayDuration").textContent = todayLog.duration || 0;

  document.getElementById("totalPractices").textContent = data.total_practices || 0;
  document.getElementById("bestScore").textContent = (data.best_score || 0) + "%";

  const wordsPercent =
    data.words_total > 0 ? Math.round((data.words_learned / data.words_total) * 100) : 0;
  const sentencesPercent =
    data.sentences_total > 0
      ? Math.round((data.sentences_learned / data.sentences_total) * 100)
      : 0;
  const contentPercent =
    data.content_total > 0 ? Math.round((data.content_completed / data.content_total) * 100) : 0;

  document.getElementById("coverageWordsPercent").textContent = wordsPercent + "%";
  document.getElementById("coverageWordsBar").style.width = wordsPercent + "%";
  document.getElementById("coverageWordsText").textContent = `${data.words_learned} / ${data.words_total}`;

  document.getElementById("coverageSentencesPercent").textContent = sentencesPercent + "%";
  document.getElementById("coverageSentencesBar").style.width = sentencesPercent + "%";
  document.getElementById("coverageSentencesText").textContent = `${data.sentences_learned} / ${data.sentences_total}`;

  const contentPctEl = document.getElementById("coverageContentPercent");
  if (contentPctEl) {
    contentPctEl.textContent = contentPercent + "%";
    document.getElementById("coverageContentBar").style.width = contentPercent + "%";
    document.getElementById("coverageContentText").textContent = `${data.content_completed} / ${data.content_total}`;
  }

  const dist = data.accuracy_distribution || { excellent: 0, good: 0, fair: 0, need_improvement: 0 };
  document.getElementById("accuracyExcellentCount").textContent = dist.excellent;
  document.getElementById("accuracyGoodCount").textContent = dist.good;

  renderActivityFocus(data.activity_breakdown);

  const achCont = document.getElementById("achievementsContainer");
  if (data.achievements && data.achievements.length > 0) {
    achCont.innerHTML = data.achievements
      .map(
        (a) => `
      <div class="flex flex-col items-center p-4 glass-card rounded-2xl group">
        <div class="text-3xl mb-2 group-hover:scale-110 transition-transform badge-glow">${a.icon || "⭐"}</div>
        <p class="text-[9px] font-black text-white/40 uppercase text-center">${a.name}</p>
      </div>`,
      )
      .join("");
  } else {
    achCont.innerHTML = '<p class="col-span-3 text-center text-xs text-white/20 py-4">No achievements yet</p>';
  }

  const logCont = document.getElementById("dailyLog");
  if (data.daily_log && data.daily_log.length > 0) {
    logCont.innerHTML = [...data.daily_log]
      .reverse()
      .map(
        (l) => `
      <div class="flex items-center justify-between p-5 glass-card rounded-[24px] mb-3 group hover:bg-white/5 transition-all">
        <div class="flex items-center gap-5">
          <div class="w-12 h-12 rounded-2xl bg-white/5 flex items-center justify-center text-white/40 font-black">${new Date(l.date).getDate()}</div>
          <div>
            <p class="font-black text-white">${new Date(l.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</p>
            <p class="text-[10px] text-white/30 font-bold uppercase">${l.practices} Eval • ${l.duration} Min</p>
          </div>
        </div>
        <div class="text-right">
          <p class="text-xl font-black text-blue-400">${Math.round(l.avg_score)}%</p>
        </div>
      </div>`,
      )
      .join("");
  } else {
    logCont.innerHTML = '<p class="text-center text-xs text-white/20 py-10">No activity logs found</p>';
  }
}

function renderActivityFocus(breakdown) {
  const cont = document.getElementById("activityFocusContainer");
  if (!cont) return;
  if (!breakdown || breakdown.length === 0) {
    cont.innerHTML = '<p class="text-xs text-white/20 text-center py-6">아직 활동 데이터가 없습니다.</p>';
    return;
  }
  const colors = ["blue", "emerald", "orange", "purple", "teal"];
  cont.innerHTML = breakdown
    .map((a, i) => {
      const color = colors[i % colors.length];
      return `
      <div class="space-y-2">
        <div class="flex justify-between items-center">
          <span class="text-sm font-bold text-white/80">${a.icon} ${a.name}</span>
          <span class="text-xs font-black text-white/40">${a.count}회 · ${a.pct}%</span>
        </div>
        <div class="w-full bg-white/5 rounded-full h-2">
          <div class="bg-${color}-500 h-full rounded-full shadow-[0_0_8px_rgba(59,130,246,0.4)] transition-all duration-1000" style="width:${a.pct}%"></div>
        </div>
      </div>`;
    })
    .join("");
}

function renderWeeklyGraph(log) {
  const host = document.getElementById("weeklyGraph");
  if (!log || log.length === 0) {
    host.innerHTML = '<p class="text-white/20 text-xs">Insufficient data for graph</p>';
    return;
  }

  const points = log
    .slice(-10)
    .map((l, i) => `${i * 70 + 50},${180 - l.avg_score * 1.5}`)
    .join(" ");

  host.innerHTML = `
    <svg viewBox="0 0 700 200" width="100%" class="drop-shadow-[0_0_15px_rgba(59,130,246,0.3)]">
      <defs>
        <linearGradient id="grad" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" style="stop-color:rgba(59,130,246,0.2);stop-opacity:1" />
          <stop offset="100%" style="stop-color:rgba(59,130,246,0);stop-opacity:0" />
        </linearGradient>
      </defs>
      <polyline points="${points}" fill="none" stroke="#3b82f6" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />
      <path d="M50,200 L${points} L${(log.slice(-10).length - 1) * 70 + 50},200 Z" fill="url(#grad)" />
    </svg>`;
}

function renderFluencyMetrics(data) {
  document.getElementById("fluencyMetricsContainer").innerHTML = `
    <div class="p-6 glass-card rounded-[28px] border-emerald-500/20 flex justify-between items-center">
      <div>
        <p class="text-[9px] font-black text-emerald-500 uppercase tracking-[0.2em] mb-1">AI Grade</p>
        <p class="text-4xl font-black text-white">${data.fluency_grade}</p>
      </div>
      <div class="text-4xl opacity-40">🏆</div>
    </div>
  `;
}

document.addEventListener("DOMContentLoaded", loadProgressData);
