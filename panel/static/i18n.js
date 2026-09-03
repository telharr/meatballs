/** Bilingual UI (RU / EN) — Sprint 3 */
(function () {
  const STORAGE_KEY = "pz_lang";
  let lang = localStorage.getItem(STORAGE_KEY) || "ru";
  let dict = {};

  async function loadLocale(code) {
    const res = await fetch(`/static/locales/${code}.json?v=3.20.6`);
    if (!res.ok) throw new Error(`Locale ${code} missing`);
    dict = await res.json();
    lang = code;
    localStorage.setItem(STORAGE_KEY, code);
    document.documentElement.lang = code;
    applyI18n();
    document.dispatchEvent(new CustomEvent("i18n:change", { detail: { lang: code } }));
  }

  function t(key, vars) {
    let text = dict[key] || key;
    if (vars) {
      Object.entries(vars).forEach(([k, v]) => {
        text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
      });
    }
    return text;
  }

  function currentLang() {
    return lang;
  }

  function applyI18n(root) {
    const scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      if (key) el.textContent = t(key);
    });
    scope.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
    scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.dataset.i18nTitle);
    });
    scope.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.lang === lang);
    });
  }

  window.I18n = { loadLocale, t, applyI18n, currentLang };
})();
