// Studio screens: presents existing editor controls in the approved concept
// layout. Every generated control proxies an original control (same handler,
// same saved setting), so the editor keeps one source of truth. Display only.
(() => {
  "use strict";
  const doc = document;
  const $ = (selector, root = doc) => root.querySelector(selector);
  const $$ = (selector, root = doc) => [...root.querySelectorAll(selector)];
  const make = (tag, className = "", text = "") => {
    const element = doc.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  const fire = (element, type) => element.dispatchEvent(new Event(type, { bubbles: true }));
  const syncers = new Set();
  setInterval(() => { if (!doc.hidden) syncers.forEach((sync) => sync()); }, 600);
  const observe = (target, callback, options = { attributes: true, childList: true, subtree: true, characterData: true }) => {
    if (!target) return;
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      requestAnimationFrame(() => { queued = false; callback(); });
    }).observe(target, options);
  };

  // A select shown as a row of buttons. The select stays in the DOM (hidden)
  // and remains the control that saves the setting.
  function segmented(select, labels = {}) {
    if (!select || select.dataset.segmented) return null;
    select.dataset.segmented = "true";
    const group = make("div", "studio-segmented");
    group.setAttribute("role", "radiogroup");
    const label = select.closest("label")?.querySelector("span")?.textContent || select.getAttribute("aria-label") || "";
    if (label) group.setAttribute("aria-label", label);
    const buttons = [...select.options].map((option) => {
      const button = make("button", "", labels[option.value] || option.textContent.replace(/\s+·.*$/, "").trim());
      button.type = "button";
      button.setAttribute("role", "radio");
      button.dataset.value = option.value;
      button.addEventListener("click", () => {
        if (select.disabled || select.value === option.value) return;
        select.value = option.value;
        fire(select, "input");
        fire(select, "change");
        sync();
      });
      group.append(button);
      return button;
    });
    const sync = () => {
      for (const button of buttons) {
        const checked = button.dataset.value === select.value;
        button.setAttribute("aria-checked", String(checked));
        button.tabIndex = checked ? 0 : -1;
        button.disabled = select.disabled;
      }
    };
    group.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      const rtl = doc.documentElement.dir === "rtl" && event.key.startsWith("Arrow") && ["ArrowLeft", "ArrowRight"].includes(event.key) ? -1 : 1;
      const index = buttons.findIndex((button) => button.dataset.value === select.value);
      const next = buttons[(index + step * rtl + buttons.length) % buttons.length];
      next.click(); next.focus();
    });
    select.classList.add("studio-segmented-source");
    select.after(group);
    select.addEventListener("change", sync);
    observe(select, sync, { attributes: true, childList: true });
    syncers.add(sync);
    sync();
    return group;
  }

  // A range input with a live value readout.
  function rangeValue(input, format) {
    if (!input || input.dataset.rangeValue) return;
    input.dataset.rangeValue = "true";
    const out = make("output", "studio-range-value");
    out.setAttribute("aria-hidden", "true");
    const update = () => { out.textContent = format(Number(input.value), input); };
    input.after(out);
    input.addEventListener("input", update);
    input.addEventListener("change", update);
    observe(input, update, { attributes: true });
    setInterval(update, 1000);
    update();
  }

  // ---------- Output ----------
  function initOutput() {
    const shelf = $("#studioShelfOutput"), aspect = $("#aspectSelect"), panel = $("#studioPanelSettings");
    if (!shelf || !aspect || !panel || shelf.dataset.studioScreens) return;
    shelf.dataset.studioScreens = "true";
    $("h3", shelf).textContent = "Output presets";
    const presets = make("div", "output-presets");
    presets.setAttribute("role", "radiogroup");
    presets.setAttribute("aria-label", "Video shape");
    const names = { "16:9": ["Landscape", "16:9"], "9:16": ["Vertical", "9:16"], "1:1": ["Square", "1:1"], "4:5": ["Portrait", "4:5"], source: ["Source", "Same as project"] };
    const order = ["16:9", "9:16", "1:1", "4:5", "source"];
    const options = [...aspect.options].sort((a, b) => order.indexOf(a.value) - order.indexOf(b.value));
    const tiles = options.map((option) => {
      const value = option.value || option.textContent;
      const [title, detail] = names[value] || [option.textContent, ""];
      const tile = make("button", "output-preset");
      tile.type = "button";
      tile.setAttribute("role", "radio");
      tile.dataset.aspect = value;
      tile.append(make("span", "output-preset-shape"), make("b", "", title), make("small", "", detail));
      tile.addEventListener("click", () => {
        if (aspect.disabled || aspect.value === value) return;
        aspect.value = value; fire(aspect, "input"); fire(aspect, "change"); sync();
      });
      presets.append(tile);
      return tile;
    });
    const sync = () => tiles.forEach((tile) => {
      const checked = tile.dataset.aspect === aspect.value;
      tile.setAttribute("aria-checked", String(checked));
      tile.disabled = aspect.disabled;
    });
    aspect.addEventListener("change", sync);
    observe(aspect, sync, { attributes: true });
    syncers.add(sync);
    sync();
    $(".shelf-help", shelf)?.remove();
    shelf.append(presets);

    segmented($("#resolutionSelect"), { 1440: "1440p", 2160: "2160p" });
    segmented($("#fpsSelect"), { 24: "24", 25: "25", 30: "30", 50: "50", 60: "60 FPS" });
    segmented($("#qualitySelect"), { quality: "High" });

    // Summary and the main Export action at the end of the tools.
    const summary = make("div", "export-summary");
    const size = make("div"), length = make("div");
    size.append(make("small", "", "Summary"), make("b"));
    length.append(make("small", "", "Duration"), make("b"));
    summary.append(size, length);
    const exportButton = make("button", "button render export-video", "Export video");
    exportButton.type = "button";
    const render = $("#renderButton");
    exportButton.addEventListener("click", () => render?.click());
    const note = make("p", "export-local-note", "Rendered locally on this computer");
    const anchor = $(".output-format-section", panel);
    anchor?.after(summary);
    const tail = make("div", "export-tail");
    tail.append(exportButton, note);
    panel.append(tail);
    const resolutionHeights = { 720: [1280, 720], 1080: [1920, 1080], 1440: [2560, 1440], 2160: [3840, 2160] };
    const updateSummary = () => {
      const height = Number($("#resolutionSelect")?.value || 1080);
      const [wide, tall] = resolutionHeights[height] || [Math.round(height * 16 / 9), height];
      const ratio = aspect.value;
      const dims = ratio === "9:16" ? [tall, wide] : ratio === "1:1" ? [tall, tall] : ratio === "4:5" ? [Math.round(tall * .8), tall] : [wide, tall];
      $("b", size).textContent = `${dims[0]} × ${dims[1]} · ${$("#fpsSelect")?.value || 30} FPS`;
      $("b", length).textContent = ($("#previewTime")?.textContent || "").split("/")[1]?.trim() || "--:--";
      exportButton.disabled = Boolean(render?.disabled);
    };
    ["#resolutionSelect", "#fpsSelect", "#aspectSelect"].forEach((id) => $(id)?.addEventListener("change", updateSummary));
    observe($("#previewTime"), updateSummary, { childList: true, characterData: true, subtree: true });
    observe(render, updateSummary, { attributes: true });
    syncers.add(updateSummary);
    updateSummary();
  }

  // ---------- Media library ----------
  function initMedia() {
    const shelf = $("#studioShelfMedia");
    if (!shelf || shelf.dataset.studioScreens) return;
    shelf.dataset.studioScreens = "true";
    const heading = $(".shelf-heading", shelf);
    if (heading) {
      $("h3", heading).textContent = "Media";
      const add = make("button", "shelf-add", "Import");
      add.type = "button";
      add.setAttribute("aria-label", "Import media");
      add.addEventListener("click", () => ($(".media-import", shelf) || $(".media-import"))?.click());
      heading.append(add);
    }
    const tools = make("div", "library-tools");
    const search = make("input", "library-search");
    search.type = "search";
    search.placeholder = "Search media...";
    search.setAttribute("aria-label", "Search media");
    const tabs = make("div", "library-filter");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Media type");
    let kind = "all";
    const filters = [["all", "All media"], ["video", "Video"], ["audio", "Audio"], ["image", "Images"]].map(([value, text]) => {
      const tab = make("button", "", text);
      tab.type = "button";
      tab.setAttribute("role", "tab");
      tab.addEventListener("click", () => { kind = value; apply(); });
      tab.dataset.value = value;
      tabs.append(tab);
      return tab;
    });
    tools.append(search, tabs);
    heading?.after(tools);
    const apply = () => {
      const query = search.value.trim().toLowerCase();
      filters.forEach((tab) => tab.setAttribute("aria-selected", String(tab.dataset.value === kind)));
      for (const item of $$(".source-library-card, .media-asset", shelf)) {
        const matchesKind = kind === "all" || item.dataset.kind === kind;
        const matchesText = !query || item.textContent.toLowerCase().includes(query);
        item.hidden = !(matchesKind && matchesText);
      }
    };
    search.addEventListener("input", apply);
    // One list for everything: keep the imported-files section open.
    const keepOpen = () => { const files = $(".media-library-section", shelf); if (files && !files.open) files.open = true; };
    syncers.add(keepOpen); keepOpen();
    observe(shelf, () => apply(), { childList: true, subtree: true });
    apply();
  }

  // ---------- Layout ----------
  function initLayout() {
    const shelf = $("#studioShelfLayout"), choices = $("#sourceLayoutChoices");
    if (!shelf || !choices || shelf.dataset.studioScreens) return;
    shelf.dataset.studioScreens = "true";
    const section = make("section", "composition-tiles");
    section.append(make("h3", "shelf-title", "Composition"));
    const grid = make("div", "composition-grid");
    grid.setAttribute("role", "radiogroup");
    grid.setAttribute("aria-label", "Composition");
    const names = { stacked: "Stacked", screen: "Screen only", camera: "Camera only", side_by_side: "Side by side", pip: "Picture in picture", auto: "Style default" };
    const tiles = Object.entries(names).map(([layout, title]) => {
      const tile = make("button", "composition-tile");
      tile.type = "button";
      tile.setAttribute("role", "radio");
      tile.dataset.layout = layout;
      tile.append(make("span", "composition-shape"), make("b", "", title));
      tile.addEventListener("click", () => { $(`[data-layout="${layout}"]`, choices)?.click(); sync(); });
      grid.append(tile);
      return tile;
    });
    const note = make("p", "composition-note", "Add a second recording to combine camera and screen.");
    const sync = () => {
      const available = !$("#sourceMixerBody")?.hidden && !$("#sourceMixerBody")?.closest("[hidden]");
      section.classList.toggle("unavailable", !available);
      note.hidden = available;
      for (const tile of tiles) {
        const original = $(`[data-layout="${tile.dataset.layout}"]`, choices);
        tile.setAttribute("aria-checked", String(Boolean(original?.classList.contains("active") || original?.getAttribute("aria-pressed") === "true")));
        tile.disabled = !available || !original || original.disabled;
      }
    };
    section.append(grid, note);
    shelf.prepend(section);
    observe(choices, sync);
    syncers.add(sync);
    observe($("#sourceMixer"), sync, { attributes: true, subtree: true, attributeFilter: ["hidden", "class", "disabled"] });
    sync();

    // The framing tools are the panel itself, not a collapsible section.
    const framing = $("#studioPanelFraming .framing-layout");
    const keepFramingOpen = () => { if (framing && !framing.open) framing.open = true; };
    syncers.add(keepFramingOpen); keepFramingOpen();
    // Framing sliders read as label · slider · value rows.
    rangeValue($("#cropX"), (value) => `${Math.round(value)}%`);
    rangeValue($("#cropY"), (value) => `${Math.round(value)}%`);
    rangeValue($("#cropZoom"), (value, input) => `${Math.round(Number(input.max) > 10 ? value : value * 100)}%`);
  }

  // ---------- Captions ----------
  function initCaptions() {
    const shelf = $("#studioShelfCaptions"), transcript = $("#transcriptSection");
    if (!shelf || shelf.dataset.studioScreens) return;
    shelf.dataset.studioScreens = "true";
    const heading = $(".shelf-heading", shelf);
    if (heading) $("h3", heading).textContent = "Captions";
    const tabs = make("div", "library-filter caption-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Captions view");
    const segments = make("button", "", "Segments"), words = make("button", "", "Transcript");
    [segments, words].forEach((tab) => { tab.type = "button"; tab.setAttribute("role", "tab"); tabs.append(tab); });
    const select = (showTranscript) => {
      segments.setAttribute("aria-selected", String(!showTranscript));
      words.setAttribute("aria-selected", String(showTranscript));
      if (showTranscript && transcript) {
        transcript.open = true;
        transcript.scrollIntoView({ block: "start", behavior: "smooth" });
      }
    };
    segments.addEventListener("click", () => select(false));
    words.addEventListener("click", () => select(true));
    heading?.after(tabs);
    select(false);
  }

  // ---------- Edit ----------
  function initEdit() {
    const panel = $("#studioPanelTimeline");
    if (!panel || panel.dataset.studioScreens) return;
    panel.dataset.studioScreens = "true";
    const title = make("h3", "panel-title", "Edit");
    panel.prepend(title);
  }

  // ---------- Audio ----------
  function initAudio() {
    const panel = $("#studioPanelAudio");
    if (!panel || panel.dataset.studioScreens) return;
    const mixer = $(".audio-mixer", panel);
    if (!mixer) return;
    panel.dataset.studioScreens = "true";
    const title = make("h3", "panel-title", "Audio");
    const sub = make("p", "panel-subtitle", "Track mixer");
    panel.prepend(title, sub);
    const foot = make("p", "mixer-footnote", "Mute: preview + export  |  Solo: preview only");
    mixer.append(foot);
  }

  // ---------- Captions inspector ----------
  function initCaptionStyle() {
    const panel = $("#studioPanelTranscript");
    if (!panel || panel.dataset.studioScreens) return;
    panel.dataset.studioScreens = "true";
    const style = $(".caption-settings-disclosure", panel);
    if (style) style.open = true;
    segmented($("#captionStyleSelect"));
    segmented($("#captionPositionSelect"), { auto: "Auto" });
    const importer = $("#studioShelfCaptions details");
    if (importer) importer.classList.add("caption-import");
  }

  // ---------- Director progress ----------
  function initDirector() {
    const panel = $("#analysisPanel"), detail = $("#analysisPanel .analysis-detail"), message = $("#jobMessage"), track = $("#analysisPanel .progress-track");
    if (!panel || !detail || !message || !track || panel.dataset.studioScreens) return;
    panel.dataset.studioScreens = "true";
    const subtitle = make("p", "director-subtitle", "Building an editable first draft from your recording.");
    message.after(subtitle);
    const head = make("div", "director-progress-head");
    const stage = make("b"), percent = make("strong"), eta = make("small", "director-eta");
    eta.setAttribute("aria-live", "polite");
    head.append(stage, percent);
    detail.prepend(head);
    head.after(eta);
    // Remaining-time estimate from the observed progress rate; shown only once
    // the rate is meaningful, and cleared whenever progress restarts.
    let first = null, lastText = "";
    const sync = () => {
      stage.textContent = message.textContent.trim();
      const value = Number(track.getAttribute("aria-valuenow"));
      percent.textContent = Number.isFinite(value) ? `${Math.round(value)}%` : "";
      const now = performance.now();
      if (panel.hidden || !Number.isFinite(value) || value <= 0 || (first && value < first.value)) first = null;
      if (!first && Number.isFinite(value) && value > 0 && !panel.hidden) first = { time: now, value };
      let text = "";
      if (first && value < 99 && value - first.value >= 3 && now - first.time > 8000) {
        const rate = (value - first.value) / (now - first.time);
        const seconds = (100 - value) / rate / 1000;
        text = seconds < 60 ? "Less than a minute left" : `About ${Math.round(seconds / 60)} min left`;
      }
      if (text !== lastText) { eta.textContent = text; lastText = text; }
    };
    observe(message, sync, { childList: true, characterData: true, subtree: true });
    observe(track, sync, { attributes: true });
    syncers.add(sync);
    sync();
  }

  // ---------- Shared inspector headers ----------
  function initHeaders() {
    const titles = { studioPanelTimeline: "Edit", studioPanelFraming: "Clip framing", studioPanelTranscript: "Caption style", studioPanelSettings: "Export settings" };
    for (const [id, title] of Object.entries(titles)) {
      const heading = $(`#${id} .studio-tool-intro h3`);
      if (heading) heading.textContent = title;
    }
    const mixer = $("#studioPanelAudio .audio-mixer h3, #studioPanelAudio h3");
    if (mixer && !mixer.dataset.studioScreens) { mixer.dataset.studioScreens = "true"; mixer.textContent = "Audio"; }
  }

  function init() {
    if (!$("#advancedPanel") && !$("#analysisPanel")) return;
    initHeaders();
    initOutput();
    initMedia();
    initLayout();
    initCaptions();
    initEdit();
    initAudio();
    initCaptionStyle();
    initDirector();
  }
  // The editor builds parts of its panels after start-up; initialise when they exist.
  const start = () => { init(); observe($("#advancedPanel"), init, { attributes: true, attributeFilter: ["hidden"] }); };
  if (doc.readyState === "loading") doc.addEventListener("DOMContentLoaded", start); else start();
  window.addEventListener("load", init);
})();
