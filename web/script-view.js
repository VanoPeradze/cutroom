/* Script view: edit the video by editing its words. The edit's captions are
   shown as running text (edit time). Click a word to jump there; select
   words (drag, or click then Shift+click) and press Delete or Remove to cut
   that span from every track as one Undo step. The word being spoken is
   highlighted during playback. Find (Ctrl+F in the panel) highlights every
   place a phrase is said; Enter steps through them and Remove all cuts them
   in one Undo step. Hebrew and other right-to-left text flows in
   its own direction per paragraph. */

import { scriptParagraphs, selectionRange, findMatches, mergeRanges } from './transcript-search.js?v=20261128-find1';

export { scriptParagraphs, selectionRange, findMatches };

export function initScriptView(doc = document) {
  const button = doc.getElementById('scriptViewButton');
  if (!button || doc.getElementById('scriptView')) return null;
  const panel = doc.createElement('dialog');
  panel.id = 'scriptView';
  panel.className = 'script-view';
  panel.setAttribute('aria-labelledby', 'scriptViewTitle');
  panel.innerHTML = `
    <header><h2 id="scriptViewTitle">Script</h2><span class="script-hint">Click a word to jump. Select words and press Delete to cut them.</span><button type="button" class="script-close" aria-label="Close script">×</button></header>
    <div class="script-find" role="search"><input type="search" class="script-find-input" placeholder="Find in video" aria-label="Find words in the video" dir="auto"><span class="script-find-count" aria-live="polite"></span><button type="button" class="script-find-prev" aria-label="Previous match" disabled>↑</button><button type="button" class="script-find-next" aria-label="Next match" disabled>↓</button><button type="button" class="script-find-remove" hidden>Remove all</button></div>
    <div class="script-body" tabindex="0" role="textbox" aria-readonly="true" aria-multiline="true" aria-label="Edit script"></div>
    <footer><span class="script-status" aria-live="polite"></span><button type="button" class="script-undo" hidden>Undo</button><button type="button" class="script-remove" disabled>Remove selection</button></footer>`;
  doc.body.append(panel);
  const body = panel.querySelector('.script-body'), status = panel.querySelector('.script-status');
  const remove = panel.querySelector('.script-remove'), undo = panel.querySelector('.script-undo');
  const host = () => doc.defaultView.cutroomCleanupHost;
  const findInput = panel.querySelector('.script-find-input'), findCount = panel.querySelector('.script-find-count');
  const findPrev = panel.querySelector('.script-find-prev'), findNext = panel.querySelector('.script-find-next'), findRemove = panel.querySelector('.script-find-remove');
  let words = [], nodes = [], anchor = null, focus = null, raf = 0, active = -1, dragging = false, matches = [], matchAt = -1;

  const selected = () => (anchor === null || focus === null ? null : [Math.min(anchor, focus), Math.max(anchor, focus)]);
  const paintSelection = () => {
    const sel = selected();
    for (const node of nodes) node.classList.toggle('is-selected', Boolean(sel && node._i >= sel[0] && node._i <= sel[1]));
    const range = sel && selectionRange(words, sel[0], sel[1]);
    remove.disabled = !range;
    status.textContent = range ? `${sel[1] - sel[0] + 1} word${sel[1] === sel[0] ? '' : 's'} · ${(range.end - range.start).toFixed(1)} s` : '';
  };

  const showMatch = (k) => {
    if (!matches.length) return;
    matchAt = (k + matches.length) % matches.length;
    const [lo, hi] = matches[matchAt];
    anchor = lo; focus = hi;
    host()?.seek(words[lo].start);
    nodes[lo]?.scrollIntoView({ block: 'nearest' });
    paintSelection();
    findCount.textContent = `${matchAt + 1} of ${matches.length}`;
  };
  function runFind() {
    for (const node of nodes) node?.classList.remove('is-match');
    matches = findMatches(words, findInput.value); matchAt = -1;
    for (const [lo, hi] of matches) for (let i = lo; i <= hi; i++) nodes[i]?.classList.add('is-match');
    const query = findInput.value.trim();
    findCount.textContent = !query ? '' : matches.length ? `${matches.length} found` : 'Not found';
    findPrev.disabled = findNext.disabled = !matches.length;
    findRemove.hidden = !matches.length;
    findRemove.textContent = matches.length > 1 ? `Remove all ${matches.length}` : 'Remove';
  }
  const findRanges = () => mergeRanges(matches.map(([lo, hi]) => selectionRange(words, lo, hi)));

  let shown = null, shownKey = '';
  const captionKey = (project) => JSON.stringify((project?.editor_captions || []).map((c) => [c.hidden, c.words]));
  const render = () => {
    const project = host()?.project();
    shown = project; shownKey = captionKey(project);
    const paragraphs = scriptParagraphs(project?.editor_captions || []);
    words = paragraphs.flatMap((p) => p.words);
    anchor = focus = null; active = -1;
    if (!words.length) {
      body.textContent = 'No transcript yet. Transcribe the recording to edit by text.';
      nodes = []; paintSelection(); runFind(); return;
    }
    nodes = [];
    body.replaceChildren(...paragraphs.map((p) => {
      const para = doc.createElement('p'); para.dir = p.dir;
      if (p.estimated) para.title = 'Word timing here is estimated; cuts may be slightly off.';
      p.words.forEach((w, k) => {
        const span = doc.createElement('span'); span.className = 'script-word'; span.textContent = w.text; span._i = w.i;
        nodes[w.i] = span;
        para.append(span, k + 1 < p.words.length ? ' ' : '');
      });
      return para;
    }));
    paintSelection();
    runFind();
  };

  const wordAt = (target) => (target instanceof Element ? target.closest('.script-word')?._i ?? null : null);
  body.addEventListener('pointerdown', (e) => {
    const i = wordAt(e.target); if (i === null) return;
    if (e.shiftKey && anchor !== null) focus = i; else { anchor = focus = i; host()?.seek(words[i].start); }
    dragging = true; paintSelection(); body.focus({ preventScroll: true });
  });
  body.addEventListener('pointerover', (e) => { if (!dragging) return; const i = wordAt(e.target); if (i !== null && i !== focus) { focus = i; paintSelection(); } });
  doc.addEventListener('pointerup', () => { dragging = false; });

  const removeRanges = async (ranges, label) => {
    const h = host();
    if (!ranges.length || !h) return;
    const issue = h.issue?.(ranges);
    if (issue) { status.textContent = issue; return; }
    remove.disabled = findRemove.disabled = true;
    const result = await h.apply(ranges);
    findRemove.disabled = false;
    if (result) {
      render();
      status.textContent = `Removed ${label}.`;
      undo.hidden = false;
    } else paintSelection();
  };
  const cut = () => {
    const sel = selected(), range = sel && selectionRange(words, sel[0], sel[1]);
    if (!range) return;
    const text = words.slice(sel[0], sel[1] + 1).map((w) => w.text).join(' ');
    return removeRanges([range], `“${text.length > 60 ? text.slice(0, 57) + '…' : text}”`);
  };
  findInput.addEventListener('input', runFind);
  findInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); showMatch(matchAt < 0 && e.shiftKey ? -1 : matchAt + (e.shiftKey ? -1 : 1)); }
    else if (e.key === 'Escape' && findInput.value) { e.preventDefault(); e.stopPropagation(); findInput.value = ''; runFind(); }
  });
  findNext.addEventListener('click', () => showMatch(matchAt + 1));
  findPrev.addEventListener('click', () => showMatch(matchAt < 0 ? -1 : matchAt - 1));
  findRemove.addEventListener('click', () => {
    const n = matches.length, query = findInput.value.trim();
    return removeRanges(findRanges(), n > 1 ? `${n} × “${query}”` : `“${query}”`);
  });
  panel.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'f') { e.preventDefault(); e.stopPropagation(); findInput.focus(); findInput.select(); }
  });
  remove.addEventListener('click', cut);
  undo.addEventListener('click', async () => { undo.hidden = true; if (await host()?.undo?.()) { render(); status.textContent = 'Restored.'; } });
  body.addEventListener('keydown', (e) => {
    if ((e.key === 'Delete' || e.key === 'Backspace') && selected()) { e.preventDefault(); e.stopPropagation(); void cut(); }
    else if (e.key === 'Escape' && selected()) { e.stopPropagation(); anchor = focus = null; paintSelection(); }
    else if ((e.key === 'ArrowRight' || e.key === 'ArrowLeft') && words.length) {
      e.preventDefault(); e.stopPropagation();
      const rtl = doc.activeElement?.closest?.('[dir="rtl"]') || nodes[focus ?? 0]?.parentElement?.matches(':dir(rtl)');
      const step = (e.key === 'ArrowRight') !== Boolean(rtl) ? 1 : -1;
      const next = Math.max(0, Math.min(words.length - 1, (focus ?? -1) + step));
      if (e.shiftKey && anchor !== null) focus = next; else { anchor = focus = next; host()?.seek(words[next].start); }
      nodes[next]?.scrollIntoView({ block: 'nearest' }); paintSelection();
    }
  });

  const follow = () => {
    raf = 0;
    if (!panel.open) return;
    const now = host()?.project();
    if (now !== shown && !dragging) { if (captionKey(now) !== shownKey) render(); else shown = now; }
    const t = host()?.time?.();
    if (Number.isFinite(t) && words.length) {
      let lo = 0, hi = words.length - 1, found = -1;
      while (lo <= hi) { const mid = (lo + hi) >> 1; if (words[mid].start <= t) { found = mid; lo = mid + 1; } else hi = mid - 1; }
      if (found >= 0 && t > words[found].end + 0.6) found = -1;
      if (found !== active) {
        nodes[active]?.classList.remove('is-current');
        active = found;
        if (active >= 0) { nodes[active].classList.add('is-current'); if (!dragging && !selected()) nodes[active].scrollIntoView({ block: 'nearest' }); }
      }
    }
    raf = requestAnimationFrame(follow);
  };

  const open = () => { render(); panel.show(); body.focus({ preventScroll: true }); if (!raf) raf = requestAnimationFrame(follow); button.setAttribute('aria-expanded', 'true'); };
  panel.querySelector('.script-close').addEventListener('click', () => panel.close());
  panel.addEventListener('close', () => { cancelAnimationFrame(raf); raf = 0; button.setAttribute('aria-expanded', 'false'); button.focus({ preventScroll: true }); });
  button.setAttribute('aria-expanded', 'false');
  button.addEventListener('click', () => (panel.open ? panel.close() : open()));
  const find = (query) => { if (!panel.open) open(); findInput.value = String(query || ''); runFind(); showMatch(0); return matches.length; };
  const api = Object.freeze({ open, render, find });
  doc.defaultView.cutroomScriptView = api;
  return api;
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initScriptView(document), { once: true });
  else initScriptView(document);
}
