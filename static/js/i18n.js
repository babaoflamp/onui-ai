/**
 * i18n.js - Onui Internationalization Helper
 */

let translations = {};

async function setAppLang(lang) {
    localStorage.setItem("app_lang", lang);
    await loadTranslations(lang);
    applyTranslations();
    syncLangUI(lang);
}

function syncLangUI(lang) {
    const flagClasses = { ko: "fi-kr", en: "fi-us", ja: "fi-jp", zh: "fi-cn" };
    
    // Update all flags
    document.querySelectorAll("[id='current-lang-flag']").forEach(el => {
        el.className = "fi fis rounded-sm " + (flagClasses[lang] || "fi-un");
    });

    // Update all labels/names
    document.querySelectorAll("[id='current-lang-label'], [id='current-lang-name']").forEach(el => {
        el.textContent = lang.toUpperCase();
    });

    // Update checkmarks in dropdown
    ["ko", "en", "ja", "zh"].forEach(l => {
        document.querySelectorAll("[id='lang-check-" + l + "']").forEach(el => {
            el.classList.toggle("hidden", l !== lang);
        });
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

// 허용 태그/속성 화이트리스트 — 로케일 파일에서 실제로 사용되는 것만 포함
const _ALLOWED_TAGS = new Set(["span", "br", "strong", "em", "b", "i", "small", "mark", "wbr"]);
const _ALLOWED_ATTRS = new Set(["class", "style"]);

function _sanitizeI18nHtml(html) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    const walker = document.createTreeWalker(tpl.content, NodeFilter.SHOW_ELEMENT);
    const toRemove = [];
    let node;
    while ((node = walker.nextNode())) {
        if (!_ALLOWED_TAGS.has(node.tagName.toLowerCase())) {
            toRemove.push(node);
            continue;
        }
        for (const attr of [...node.attributes]) {
            if (!_ALLOWED_ATTRS.has(attr.name.toLowerCase())) {
                node.removeAttribute(attr.name);
            }
        }
    }
    toRemove.forEach(n => n.replaceWith(document.createTextNode(n.textContent)));
    const div = document.createElement("div");
    div.appendChild(tpl.content.cloneNode(true));
    return div.innerHTML;
}

function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        const val = translations[key];
        if (!val) return;
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
            el.placeholder = val;
        } else if (_htmlTagPattern.test(val)) {
            el.innerHTML = _sanitizeI18nHtml(val);
        } else {
            el.textContent = val;
        }
    });
}

// 브라우저 언어에서 지원 언어 코드 매핑
function _detectBrowserLang() {
    const supported = ["ko", "en", "ja", "zh"];
    const nav = (navigator.language || navigator.userLanguage || "en").toLowerCase();
    if (nav.startsWith("ko")) return "ko";
    if (nav.startsWith("ja")) return "ja";
    if (nav.startsWith("zh")) return "zh";
    return "en";
}

document.addEventListener("DOMContentLoaded", async () => {
    // 안전장치: i18n 로드 실패 시에도 2초 후 페이지 강제 표시
    const _fouc_guard = setTimeout(() => {
        document.documentElement.style.visibility = "";
    }, 2000);

    // 저장된 언어 없으면 브라우저 언어 자동 감지
    const lang = localStorage.getItem("app_lang") || _detectBrowserLang();
    if (!localStorage.getItem("app_lang")) {
        localStorage.setItem("app_lang", lang);
    }

    await loadTranslations(lang);
    applyTranslations();

    clearTimeout(_fouc_guard);
    document.documentElement.style.visibility = "";

    syncLangUI(lang);
});

// 탭 간 언어 동기화: 다른 탭에서 언어 변경 시 현재 탭도 갱신
window.addEventListener("storage", async (e) => {
    if (e.key === "app_lang" && e.newValue && e.newValue !== e.oldValue) {
        await loadTranslations(e.newValue);
        applyTranslations();
        syncLangUI(e.newValue);
    }
});
