/**
 * i18n.js - OAI Internationalization Helper
 *
 * Hybrid strategy:
 * - STATIC_LOCALES: load curated data/locales/{lang}.json (data-i18n)
 * - GOOGLE_UI_LANGS: render English UI then apply Google Website Translator
 *
 * Korean learning content should use class="notranslate" / translate="no".
 */

let translations = {};

/** Curated locale JSON files — high quality, no Google widget */
const STATIC_LOCALES = new Set(["ko", "en", "ja", "zh", "vi", "ne"]);

/** App lang codes that use Google Website Translate on top of English UI */
const GOOGLE_UI_LANGS = new Set(["id", "mn", "lo"]);

/** All languages shown in the picker */
const SUPPORTED_LANGS = ["ko", "en", "ja", "zh", "vi", "ne", "id", "mn", "lo"];

/** App code → Google Translate combo value */
const GOOGLE_LANG_MAP = {
    id: "id",
    mn: "mn",
    lo: "lo",
    zh: "zh-CN",
    // extend freely when adding more Google-only langs
};

const LANG_FLAG_CLASSES = {
    ko: "fi-kr",
    en: "fi-us",
    ja: "fi-jp",
    zh: "fi-cn",
    vi: "fi-vn",
    ne: "fi-np",
    id: "fi-id",
    mn: "fi-mn",
    lo: "fi-la",
};

/** Pending Google target while Element script loads */
let _pendingGoogleLang = null;
let _googleElementReady = false;

function notifyTranslationsUpdated() {
    document.dispatchEvent(new CustomEvent("app:translations-updated"));
}

function usesGoogleTranslate(lang) {
    return GOOGLE_UI_LANGS.has(lang) || (!STATIC_LOCALES.has(lang) && lang !== "en");
}

function isGoogleTranslateActive() {
    const m = document.cookie.match(/(?:^|;\s*)googtrans=([^;]+)/);
    if (!m || !m[1]) return false;
    const val = decodeURIComponent(m[1]);
    // "/en/id" or "/auto/id"
    return /\/[a-zA-Z-]+\/[a-zA-Z-]+/.test(val) && !/\/(en|auto)\/(en)$/.test(val);
}

function _setCookie(name, value, days) {
    let expires = "";
    if (days) {
        const d = new Date();
        d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
        expires = "; expires=" + d.toUTCString();
    }
    document.cookie = name + "=" + (value || "") + expires + "; path=/";
}

function clearGoogleTranslateCookies() {
    const host = window.location.hostname;
    const expire = "Thu, 01 Jan 1970 00:00:00 GMT";
    const variants = [
        "googtrans=; expires=" + expire + "; path=/",
        "googtrans=; expires=" + expire + "; path=/; domain=" + host,
        "googtrans=; expires=" + expire + "; path=/; domain=." + host,
    ];
    variants.forEach((c) => {
        document.cookie = c;
    });
    // Reset hidden combo if present
    const select = document.querySelector(".goog-te-combo");
    if (select) {
        select.value = "";
        try {
            select.dispatchEvent(new Event("change"));
        } catch (_) { /* ignore */ }
    }
    document.body.classList.remove("gt-active");
}

/**
 * Called from googleTranslateElementInit when the Element is ready.
 */
function onGoogleTranslateReady() {
    _googleElementReady = true;
    if (_pendingGoogleLang) {
        const code = _pendingGoogleLang;
        _pendingGoogleLang = null;
        _applyGoogleCombo(code);
    }
}

function _applyGoogleCombo(googleCode) {
    const select = document.querySelector(".goog-te-combo");
    if (!select) {
        // Cookie alone often enough after reload; Element may still be mounting
        _setCookie("googtrans", "/en/" + googleCode, 1);
        document.body.classList.add("gt-active");
        return false;
    }
    _setCookie("googtrans", "/en/" + googleCode, 1);
    if (select.value !== googleCode) {
        select.value = googleCode;
        select.dispatchEvent(new Event("change"));
    }
    document.body.classList.add("gt-active");
    return true;
}

function triggerGoogleTranslate(appLang) {
    // Some pages intentionally run without the third-party Google widget.
    // Keep their UI in English instead of creating blocked third-party requests.
    if (window.DISABLE_GOOGLE_TRANSLATE) return;
    const googleCode = GOOGLE_LANG_MAP[appLang] || appLang;
    _pendingGoogleLang = googleCode;
    _setCookie("googtrans", "/en/" + googleCode, 1);

    if (_googleElementReady || document.querySelector(".goog-te-combo")) {
        _pendingGoogleLang = null;
        _applyGoogleCombo(googleCode);
        return;
    }

    // Wait briefly for Element script
    let attempts = 0;
    const timer = setInterval(() => {
        attempts += 1;
        if (document.querySelector(".goog-te-combo") || _googleElementReady) {
            clearInterval(timer);
            _pendingGoogleLang = null;
            _applyGoogleCombo(googleCode);
        } else if (attempts >= 40) {
            clearInterval(timer);
            console.warn("[i18n] Google Translate Element not ready; UI stays English.");
            document.body.classList.add("gt-active");
        }
    }, 100);
}

/**
 * Leaving Google mode mutates the DOM — force a clean reload after clearing cookies.
 */
function exitGoogleTranslateAndReload(nextLang) {
    clearGoogleTranslateCookies();
    localStorage.setItem("app_lang", nextLang);
    // Avoid loop: mark that we intentionally reset
    sessionStorage.setItem("i18n_gt_reset", "1");
    window.location.reload();
}

async function setAppLang(lang) {
    if (!lang) return;
    const prev = localStorage.getItem("app_lang");
    const wasGoogle = usesGoogleTranslate(prev) || isGoogleTranslateActive();
    const willGoogle = usesGoogleTranslate(lang);

    localStorage.setItem("app_lang", lang);

    if (window.DISABLE_GOOGLE_TRANSLATE && willGoogle) {
        clearGoogleTranslateCookies();
        await loadTranslations("en");
        applyTranslations();
        syncLangUI(lang);
        notifyTranslationsUpdated();
        return;
    }

    // Switching away from Google → reload clean page (DOM is polluted by font tags)
    if (wasGoogle && !willGoogle) {
        exitGoogleTranslateAndReload(lang);
        return;
    }

    // Switching between Google langs or first enter Google: may need reload for cookie apply
    if (willGoogle) {
        await loadTranslations("en");
        applyTranslations();
        syncLangUI(lang);
        notifyTranslationsUpdated();

        if (wasGoogle && prev !== lang) {
            // Change target language via cookie + reload for reliable re-translation
            clearGoogleTranslateCookies();
            _setCookie("googtrans", "/en/" + (GOOGLE_LANG_MAP[lang] || lang), 1);
            window.location.reload();
            return;
        }

        triggerGoogleTranslate(lang);
        return;
    }

    // Static locale path
    clearGoogleTranslateCookies();
    await loadTranslations(lang);
    applyTranslations();
    syncLangUI(lang);
    notifyTranslationsUpdated();
}

function syncLangUI(lang) {
    document.querySelectorAll("[id^='current-lang-flag']").forEach((el) => {
        el.className = "fi rounded-sm " + (LANG_FLAG_CLASSES[lang] || "fi-un");
        el.style.fontSize = "1.4rem";
    });

    document.querySelectorAll("[id='current-lang-label'], [id='current-lang-name']").forEach((el) => {
        el.textContent = (lang || "en").toUpperCase();
    });

    SUPPORTED_LANGS.forEach((l) => {
        document.querySelectorAll("[id='lang-check-" + l + "']").forEach((el) => {
            el.classList.toggle("hidden", l !== lang);
        });
    });

    // Sidebar active flags (base.html also toggles; keep in sync)
    SUPPORTED_LANGS.forEach((l) => {
        document.querySelectorAll("#lang-btn-" + l).forEach((btn) => {
            btn.classList.toggle("lang-active", l === lang);
        });
    });
}

async function loadTranslations(lang) {
    try {
        const resp = await fetch(`/data/locales/${lang}.json?v=${new Date().getTime()}`);
        if (resp.ok) {
            translations = await resp.json();
        } else if (lang !== "en") {
            // Fallback to English
            const fallback = await fetch(`/data/locales/en.json?v=${new Date().getTime()}`);
            if (fallback.ok) translations = await fallback.json();
        }
    } catch (err) {
        console.error("Failed to load translations:", err);
    }
}

const _htmlTagPattern = /<[a-z][\s\S]*?>/i;

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
    toRemove.forEach((n) => n.replaceWith(document.createTextNode(n.textContent)));
    const div = document.createElement("div");
    div.appendChild(tpl.content.cloneNode(true));
    return div.innerHTML;
}

function applyTranslations() {
    document.querySelectorAll("[data-i18n]").forEach((el) => {
        // Never overwrite protected Korean content via i18n keys incorrectly
        if (el.classList.contains("notranslate") && el.hasAttribute("data-i18n-skip-google")) {
            /* still apply locale string for static mode */
        }
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

function _detectBrowserLang() {
    const nav = (navigator.language || navigator.userLanguage || "en").toLowerCase();
    if (nav.startsWith("ko")) return "ko";
    if (nav.startsWith("ja")) return "ja";
    if (nav.startsWith("zh")) return "zh";
    if (nav.startsWith("vi")) return "vi";
    if (nav.startsWith("ne")) return "ne";
    if (nav.startsWith("id") || nav.includes("indonesia")) return "id";
    if (nav.startsWith("mn")) return "mn";
    if (nav.startsWith("lo")) return "lo";
    return "en";
}

/**
 * Early cookie hygiene before Element script: if user wants static locale, drop googtrans.
 * Call from inline head or DOMContentLoaded start.
 */
function ensureTranslateCookieMatchesAppLang(lang) {
    if (window.DISABLE_GOOGLE_TRANSLATE) {
        clearGoogleTranslateCookies();
        return;
    }
    if (usesGoogleTranslate(lang)) {
        const code = GOOGLE_LANG_MAP[lang] || lang;
        _setCookie("googtrans", "/en/" + code, 1);
    } else {
        clearGoogleTranslateCookies();
    }
}

document.addEventListener("DOMContentLoaded", async () => {
    const _fouc_guard = setTimeout(() => {
        document.documentElement.style.visibility = "";
    }, 2000);

    const lang = localStorage.getItem("app_lang") || _detectBrowserLang();
    if (!localStorage.getItem("app_lang")) {
        localStorage.setItem("app_lang", lang);
    }

    ensureTranslateCookieMatchesAppLang(lang);

    if (usesGoogleTranslate(lang)) {
        await loadTranslations("en");
        applyTranslations();
        // Element init (async) will pick up cookie; also try combo when ready
        triggerGoogleTranslate(lang);
    } else {
        await loadTranslations(lang);
        applyTranslations();
    }

    notifyTranslationsUpdated();
    clearTimeout(_fouc_guard);
    document.documentElement.style.visibility = "";
    syncLangUI(lang);
    sessionStorage.removeItem("i18n_gt_reset");
});

window.addEventListener("storage", async (e) => {
    if (e.key === "app_lang" && e.newValue && e.newValue !== e.oldValue) {
        await setAppLang(e.newValue);
    }
});

// Expose for base.html Google init callback
window.onGoogleTranslateReady = onGoogleTranslateReady;
window.usesGoogleTranslate = usesGoogleTranslate;
window.SUPPORTED_LANGS = SUPPORTED_LANGS;
window.STATIC_LOCALES = STATIC_LOCALES;
window.GOOGLE_UI_LANGS = GOOGLE_UI_LANGS;
