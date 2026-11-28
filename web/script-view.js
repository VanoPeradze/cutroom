/* Script view: edit the video by editing its words. The edit's captions are
   shown as running text (edit time). Click a word to jump there; select
   words (drag, or click then Shift+click) and press Delete or Remove to cut
   that span from every track as one Undo step. The word being spoken is
   highlighted during playback. Hebrew and other right-to-left text flows in
   its own direction per paragraph. */

const PAD = 0.04;

/** Paragraphs of words in edit time: [{id, dir, words:[{i,start,end,text}]}] */
export function scriptParagraphs(captions) {
  let i = 0;
  return (captions || []).filter((c) => !c.hidden && Array.isArray(c.words) && c.words.length)
    .sort((a, b) => a.start - b.start)
    .map((c) => ({ id: c.id, dir: c.direction === 'rtl' ? 'rtl' : 'auto', estimated: Boolean(c.estimated_words),
      words: c.words.map(([start, end, text]) => ({ start: Number(start), end: Number(end), text: String(text).trim() }))
        .filter((w) => w.text && Number.isFinite(w.start) && Number.isFinite(w.end)).map((w) => ({ i: i++, ...w })) }))
    .filter((p) => p.words.length);
}

/** The edit-time range covering words a..b, reaching into the pauses around them. */
export function selectionRange(words, a, b) {
  const lo = Math.min(a, b), hi = Math.max(a, b);
  const first = words[lo], last = words[hi];
  if (!first || !last) return null;
  const before = words[lo - 1], after = words[hi + 1];
  const start = before ? Math.max(before.end, first.start - PAD) : Math.max(0, first.start - PAD);
  const end = after ? Math.min(after.start, last.end + PAD) : last.end + PAD;
  return end - start >= 0.08 ? { start: Math.round(start * 1000) / 1000, end: Math.round(end * 1000) / 1000 } : null;
}

export function initScriptView(doc = document) {
  const button = doc.getElementById('scriptViewButton');
  if (!button || doc.getElementById('scriptView')) return null;
  const panel = doc.createElement('dialog');
  panel.id = 'scriptView';
  panel.className = 'script-view';
  panel.setAttribute('aria-labelledby', 'scriptViewTitle');
  panel.innerHTML = `
    <header><h2 id="scriptViewTitle">Script</h2><span class="script-hint">Click a word to jump. Select words and press Delete to cut them.</span><button type="button" class="script-close" aria-label="Close script">×</button></header>
    <div class="script-body" tabindex="0" role="textbox" aria-readonly="true" aria-multiline="true" aria-label="Edit script"></div>
    <footer><span class="script-status" aria-live="polite"></span><button type="button" class="script-undo" hidden>Undo</button><button type="button" class="script-remove" disabled>Remove selection</button></footer>`;
  doc.body.append(panel);
  const body = panel.querySelector('.script-body'), status = panel.querySelector('.script-status');
  const remove = panel.querySelector('.script-remove'), undo = panel.querySelector('.script-undo');
  const host = () => doc.defaultView.cutroomCleanupHost;
  let words = [], nodes = [], anchor = null, focus = null, raf = 0, active = -1, dragging = false;

  const selected = () => (anchor === null || focus === null ? null : [Math.min(anchor, focus), Math.max(anchor, focus)]);
  const paintSelection = () => {
    const sel = selected();
    for (const node of nodes) node.classList.toggle('is-selected', Boolean(sel && node._i >= sel[0] && node._i <= sel[1]));
    const range = sel && selectionRange(words, sel[0], sel[1]);
    remove.disabled = !range;
    status.textContent = range ? `${sel[1] - sel[0] + 1} word${sel[1] === sel[0] ? '' : 's'} · ${(range.end - range.start).toFixed(1)} s` : '';
  };

  const render = () => {
    const project = host()?.project();
    const paragraphs = scriptParagraphs(project?.editor_captions || []);
    words = paragraphs.flatMap((p) => p.words);
    anchor = focus = null; active = -1;
    if (!words.length) {
      body.textContent = 'No transcript yet. Transcribe the recording to edit by text.';
      nodes = []; paintSelection(); return;
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
  };

  const wordAt = (target) => (target instanceof Element ? target.closest('.script-word')?._i ?? null : null);
  body.addEventListener('pointerdown', (e) => {
    const i = wordAt(e.target); if (i === null) return;
    if (e.shiftKey && anchor !== null) focus = i; else { anchor = focus = i; host()?.seek(words[i].start); }
    dragging = true; paintSelection(); body.focus({ preventScroll: true });
  });
  body.addEventListener('pointerover', (e) => { if (!dragging) return; const i = wordAt(e.target); if (i !== null && i !== focus) { focus = i; paintSelection(); } });
  doc.addEventListener('pointerup', () => { dragging = false; });

  const cut = async () => {
    const sel = selected(), range = sel && selectionRange(words, sel[0], sel[1]), h = host();
    if (!range || !h) return;
    const issue = h.issue?.([range]);
    if (issue) { status.textContent = issue; return; }
    remove.disabled = true;
    const text = words.slice(sel[0], sel[1] + 1).map((w) => w.text).join(' ');
    const result = await h.apply([range]);
    if (result) {
      render();
      status.textContent = `Removed “${text.length > 60 ? text.slice(0, 57) + '…' : text}”.`;
      undo.hidden = false;
    } else paintSelection();
  };
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
  return { open, render };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initScriptView(document), { once: true });
  else initScriptView(document);
}
