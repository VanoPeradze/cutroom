/* Appearance only. No project state, media controls or network requests. */
(() => {
  "use strict";
  const root = document.documentElement;
  const storageKey = "cutroom-theme";
  const valid = (value) => value === "light" || value === "dark";
  let theme;
  try { theme = localStorage.getItem(storageKey); } catch {}
  if (!valid(theme)) theme = window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";

  function applyTheme(value) {
    theme = value;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#101516" : "#f6f5f1");
    const button = document.getElementById("themeToggle");
    if (button) {
      button.setAttribute("aria-pressed", String(theme === "dark"));
      button.title = theme === "dark" ? "Switch to day mode" : "Switch to night mode";
      document.getElementById("themeIcon").textContent = theme === "dark" ? "☾" : "☀";
      document.getElementById("themeLabel").textContent = theme === "dark" ? "Night" : "Day";
    }
  }
  applyTheme(theme);

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(theme);
    document.getElementById("themeToggle")?.addEventListener("click", () => {
      applyTheme(theme === "dark" ? "light" : "dark");
      try { localStorage.setItem(storageKey, theme); } catch {}
    });
    const chrome = document.getElementById("appChrome");
    if (!chrome) return;
    // One sticky stack. Its real height includes wrapped controls and job status.
    let previousHeight = 0;
    const measure = () => {
      const height = Math.ceil(chrome.getBoundingClientRect().height);
      if (height > 0 && height !== previousHeight) {
        previousHeight = height;
        root.style.setProperty("--app-chrome-height", `${height}px`);
      }
    };
    measure();
    if (window.ResizeObserver) new ResizeObserver(measure).observe(chrome);
    else {
      window.addEventListener("resize", measure);
      new MutationObserver(measure).observe(chrome, { subtree: true, attributes: true, childList: true, characterData: true });
    }
    document.fonts?.ready.then(measure);
  }, { once: true });
})();
