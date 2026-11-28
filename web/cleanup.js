/* One-click cleanup. Finds long pauses, hesitation sounds, optional filler
   words and repeated takes in the edit's own captions (edit time), lists them
   for approval, and removes the approved ones from every track in one Undo
   step. Nothing is removed before the user presses Remove. */

const HESITATION = /^(?:u+m+|u+h+|e+r+m+|h+m+|e+h+|e+m+|e+u+h+|א+מ+|א+ה+|א+ממ+|ה+מ+|ا+م+|آه+|э+м*)$/;
// Words that often carry meaning: listed, but left unticked.
const SOFT_FILLERS = new Set(['like', 'basically', 'actually', 'literally', 'כאילו', 'בעצם', 'יעני', 'אז']);
const MIN_RANGE = 0.08;

const clean = (word) => String(word || '').trim().replace(/^[\s,.!?…؟;:"'()-]+|[\s,.!?…؟;:"'()-]+$/g, '').toLowerCase();
const round = (n) => Math.round(n * 1000) / 1000;

export const DEFAULTS = Object.freeze({ pause: 0.8, keepPause: 0.25, edgePause: 1.0 });

/** Candidates from editor captions: [{kind, start, end, text, checked}]. */
export function findCleanup(captions, duration, options = {}) {
  const opts = { ...DEFAULTS, ...options };
  const items = (captions || []).filter((c) => !c.hidden && Array.isArray(c.words) && c.words.length && !c.estimated_words)
    .map((c) => ({ ...c, words: c.words.map(([s, e, w]) => ({ start: Number(s), end: Number(e), word: String(w) })) }))
    .sort((a, b) => a.start - b.start);
  const words = items.flatMap((c) => c.words).filter((w) => Number.isFinite(w.start) && Number.isFinite(w.end) && w.end > w.start)
    .sort((a, b) => a.start - b.start);
  const out = [];
  if (!words.length) return out;
  const half = opts.keepPause / 2;

  // Long pauses: keep a short natural breath on each side.
  const gap = (start, end, where) => {
    const s = where === 'lead' ? Math.max(0, end - opts.keepPause) : start + half;
    const e = where === 'lead' ? end - opts.keepPause : where === 'tail' ? end : end - half;
    const from = where === 'lead' ? 0 : s, to = e;
    if (to - from >= MIN_RANGE) out.push({ kind: 'pause', start: round(from), end: round(to), text: `${(end - start).toFixed(1)} s pause`, checked: true });
  };
  if (words[0].start >= opts.edgePause) gap(0, words[0].start, 'lead');
  for (let i = 1; i < words.length; i++) {
    const pause = words[i].start - words[i - 1].end;
    if (pause >= opts.pause) gap(words[i - 1].end, words[i].start, 'mid');
  }
  const last = words.at(-1).end;
  if (Number.isFinite(duration) && duration - last >= opts.edgePause) out.push({ kind: 'pause', start: round(last + opts.keepPause), end: round(duration), text: `${(duration - last).toFixed(1)} s at the end`, checked: true });

  // Hesitations and fillers: only when a measured pause separates them from
  // their neighbours, so a cut never clips a real word.
  for (let i = 0; i < words.length; i++) {
    const w = words[i], label = clean(w.word);
    const hesitation = HESITATION.test(label), soft = SOFT_FILLERS.has(label);
    if (!hesitation && !soft) continue;
    const prev = words[i - 1], next = words[i + 1];
    if (prev && w.start - prev.end < 0.05 || next && next.start - w.end < 0.05) continue;
    const start = Math.max(prev ? prev.end + 0.03 : 0, w.start - 0.02), end = Math.min(next ? next.start - 0.03 : w.end + 0.08, w.end + 0.06);
    if (end - start >= MIN_RANGE) out.push({ kind: hesitation ? 'hesitation' : 'filler', start: round(start), end: round(end), text: `“${w.word.trim()}”`, checked: hesitation });
  }

  // Repeated takes: a caption whose opening words are said again by the next
  // one, which is at least as long. The earlier attempt goes.
  for (let i = 0; i + 1 < items.length; i++) {
    const a = items[i].words.map((w) => clean(w.word)).filter(Boolean), b = items[i + 1].words.map((w) => clean(w.word)).filter(Boolean);
    const n = Math.min(3, a.length);
    if (a.length < 2 || b.length < n || b.length + 1 < a.length) continue;
    if (!a.slice(0, n).every((w, k) => w === b[k])) continue;
    const start = items[i].words[0].start, end = items[i + 1].words[0].start - 0.05;
    if (end - start >= MIN_RANGE) out.push({ kind: 'retake', start: round(start), end: round(end), text: items[i].words.map((w) => w.word.trim()).join(' '), checked: true });
  }
  return out.sort((x, y) => x.start - y.start || y.end - x.end);
}

/** Approved candidates as non-overlapping removal ranges. */
export function removalRanges(candidates) {
  const rows = candidates.filter((c) => c.checked).map((c) => ({ start: c.start, end: c.end })).sort((a, b) => a.start - b.start);
  const merged = [];
  for (const row of rows) {
    const last = merged.at(-1);
    if (last && row.start <= last.end + 0.02) last.end = Math.max(last.end, row.end);
    else merged.push({ ...row });
  }
  return merged.filter((r) => r.end - r.start >= MIN_RANGE).map((r) => ({ start: round(r.start), end: round(r.end) }));
}

const LABELS = { pause: 'Pauses', hesitation: 'Hesitations', filler: 'Filler words', retake: 'Repeated takes' };
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

export function initCleanup(doc = document) {
  const button = doc.getElementById('cleanupButton');
  if (!button || doc.getElementById('cleanupDialog')) return null;
  const dialog = doc.createElement('dialog');
  dialog.id = 'cleanupDialog';
  dialog.className = 'cleanup-dialog';
  dialog.setAttribute('aria-labelledby', 'cleanupTitle');
  dialog.innerHTML = `
    <header><h2 id="cleanupTitle">Clean up</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <p class="cleanup-intro" id="cleanupIntro"></p>
    <div class="cleanup-kinds" role="group" aria-label="What to remove"></div>
    <ul class="cleanup-list" aria-label="Places to remove"></ul>
    <footer><span class="cleanup-total" aria-live="polite"></span><button type="button" class="cleanup-cancel">Cancel</button><button type="button" class="cleanup-apply">Remove</button></footer>`;
  doc.body.append(dialog);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const intro = dialog.querySelector('.cleanup-intro'), kinds = dialog.querySelector('.cleanup-kinds'), list = dialog.querySelector('.cleanup-list');
  const total = dialog.querySelector('.cleanup-total'), apply = dialog.querySelector('.cleanup-apply');
  let candidates = [];

  const sync = () => {
    const ranges = removalRanges(candidates), seconds = ranges.reduce((s, r) => s + r.end - r.start, 0);
    total.textContent = ranges.length ? `${ranges.length} cuts · ${seconds.toFixed(1)} s shorter` : 'Nothing selected';
    apply.disabled = !ranges.length;
    apply.textContent = ranges.length ? `Remove ${ranges.length}` : 'Remove';
    for (const box of kinds.querySelectorAll('input')) {
      const rows = candidates.filter((c) => c.kind === box.value), on = rows.filter((c) => c.checked).length;
      box.checked = on > 0 && on === rows.length; box.indeterminate = on > 0 && on < rows.length;
    }
  };

  const render = () => {
    kinds.replaceChildren(...Object.keys(LABELS).filter((k) => candidates.some((c) => c.kind === k)).map((k) => {
      const label = doc.createElement('label'), box = doc.createElement('input');
      box.type = 'checkbox'; box.value = k;
      box.addEventListener('change', () => { for (const c of candidates) if (c.kind === k) c.checked = box.checked; render(); });
      label.append(box, ` ${LABELS[k]} (${candidates.filter((c) => c.kind === k).length})`);
      return label;
    }));
    list.replaceChildren(...candidates.map((c, i) => {
      const li = doc.createElement('li'), box = doc.createElement('input'), id = `cleanupItem${i}`;
      li.dataset.kind = c.kind;
      box.type = 'checkbox'; box.id = id; box.checked = c.checked;
      box.addEventListener('change', () => { c.checked = box.checked; sync(); });
      const label = doc.createElement('label'); label.htmlFor = id;
      const time = doc.createElement('time'); time.textContent = fmt(c.start);
      const kind = doc.createElement('b'); kind.textContent = LABELS[c.kind].replace(/s$/, '');
      const text = doc.createElement('span'); text.textContent = c.text; text.dir = 'auto';
      label.append(time, kind, text);
      const play = doc.createElement('button'); play.type = 'button'; play.className = 'cleanup-play';
      play.textContent = 'Go to'; play.setAttribute('aria-label', `Go to ${fmt(c.start)}`);
      play.addEventListener('click', () => host()?.seek(Math.max(0, c.start - 0.5)));
      li.append(box, label, play);
      return li;
    }));
    sync();
  };

  const open = () => {
    const h = host(), project = h?.project();
    if (!project) return;
    const duration = Number(project.editor_sequence?.duration);
    candidates = findCleanup(project.editor_captions || [], duration);
    const hasWords = (project.editor_captions || []).some((c) => !c.hidden && c.words?.length && !c.estimated_words);
    intro.textContent = !hasWords
      ? 'Cleanup needs a transcript with word timing. Transcribe the recording first.'
      : candidates.length ? 'Review what will be removed. Unticked items stay. Everything is one Undo step.' : 'Nothing to clean up: no long pauses, hesitations or repeated takes were found.';
    render();
    dialog.showModal();
    (candidates.length ? apply : dialog.querySelector('.cleanup-cancel')).focus();
  };

  apply.addEventListener('click', async () => {
    const ranges = removalRanges(candidates), h = host();
    if (!ranges.length || !h) return;
    const issue = h.issue?.(ranges);
    if (issue) { intro.textContent = issue; return; }
    apply.disabled = true;
    const result = await h.apply(ranges);
    if (result) dialog.close(); else { apply.disabled = false; }
  });
  dialog.querySelector('.cleanup-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', open);
  return { open };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initCleanup(document), { once: true });
  else initCleanup(document);
}
