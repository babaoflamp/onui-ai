/**
 * i18n.js - Onui Internationalization Helper
 */

let translations = {};

async function setAppLang(lang) {
    localStorage.setItem("app_lang", lang);
    await loadTranslations(lang);
    applyTranslations();

    // Update label
    const lbl = document.getElementById("current-lang-label");
    if (lbl) lbl.textContent = lang.toUpperCase();

    // Update flag/name (alternative selector pattern)
    const flagEl = document.getElementById("current-lang-flag");
    const nameEl = document.getElementById("current-lang-name");
    if (flagEl && nameEl) {
        const flagClasses = { ko: "fi-kr", en: "fi-us", ja: "fi-jp", zh: "fi-cn" };
        flagEl.className = "fi fis rounded-sm " + (flagClasses[lang] || "fi-un");
        nameEl.textContent = lang.toUpperCase();
    }

    // Update checkmarks in dropdown
    ["ko", "en", "ja", "zh"].forEach(l => {
        const el = document.getElementById("lang-check-" + l);
        if (el) el.classList.toggle("hidden", l !== lang);
    });
}

async function loadTranslations(lang) {
    try {
        const resp = await fetch(`/data/locales/${lang}.json`);
        if (resp.ok) {
            translations = await resp.json();
        }
    } catch (err) {
        console.error("Failed to load translations:", err);
    }
}

const _htmlTagPattern = /<[a-z][\s\S]*?>/i;

function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        const val = translations[key];
        if (!val) return;
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
            el.placeholder = val;
        } else if (_htmlTagPattern.test(val)) {
            // 번역값에 의도적인 HTML 마크업이 포함된 경우 (locale 파일 관리 대상)
            el.innerHTML = val;
        } else {
            el.textContent = val;
        }
    });
}

document.addEventListener("DOMContentLoaded", async () => {
    const lang = localStorage.getItem("app_lang") || "en";
    await loadTranslations(lang);
    applyTranslations();

    // FOUC 방지 해제: 번역 적용 완료 후 표시
    document.documentElement.style.visibility = "";

    // Sync header selector if it exists
    const flagEl = document.getElementById("current-lang-flag");
    const nameEl = document.getElementById("current-lang-name");
    if (flagEl && nameEl) {
        const flagClasses = { ko: "fi-kr", en: "fi-us", ja: "fi-jp", zh: "fi-cn" };
        flagEl.className = "fi fis rounded-sm " + (flagClasses[lang] || "fi-un");
        nameEl.textContent = lang.toUpperCase();
    }
});
