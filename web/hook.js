/* Opener (hook). Ranks the edit's own sentences by how well they grab
   attention (numbers, key words, questions, exclamations, talking to the
   viewer) and copies the chosen one to the start of the edit as a cold open.
   The original stays where it was; the copy is one Undo step. */
import { isEmphasisWord } from './color-motion.js?v=20261128-autozoom1';

const VIEWER = new Set(['you', "you're", 'your', 'אתם', 'אתה', 'את', 'שלכם', 'שלך']);
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

/** Sentence candidates in edit time, best first: [{start, end, text, score, reasons}] */
export function rankHooks(captions, { minWords = 3, maxWords = 24, minSeconds = 1.2, maxSeconds = 9, limit = 5 } = {}) {
  const rows = [];
  for (const c of captions || []) {
    if (c.hidden || !Array.isArray(c.words) || !c.words.length) continue;
    const words = c.words.map(([s, e, w]) => ({ start: Number(s), end: Number(e), word: String(w).trim() })).filter((w) => w.word);
    if (words.length < minWords || words.length > maxWords) continue;
    const start = words[0].start, end = words.at(-1).end;
    if (!(end - start >= minSeconds && end - start <= maxSeconds) || start < 0.5) continue;
    const text = words.map((w) => w.word).join(' ');
    const reasons = [];
    let score = 0;
    const key = words.filter((w) => isEmphasisWord(w.word)).length;
    if (key) { score += Math.min(3, key) * 1.5; reasons.push(`${key} key word${key === 1 ? '' : 's'}`); }
    if (/\d/.test(text)) { score += 1.5; reasons.push('a number'); }
    if (/[?؟]\s*$/.test(text)) { score += 2; reasons.push('a question'); }
    if (/!\s*$/.test(text)) { score += 1.5; reasons.push('an exclamation'); }
    if (words.some((w) => VIEWER.has(w.word.toLowerCase().replace(/[^\p{L}']/gu, '')))) { score += 1; reasons.push('talks to the viewer'); }
    if (end - start <= 5) score += 0.5;
    if (reasons.length) rows.push({ start: Math.round(start * 1000) / 1000, end: Math.round(Math.min(end + 0.15, (c.end ?? end + 0.15)) * 1000) / 1000, text, score, reasons });
  }
  return rows.sort((a, b) => b.score - a.score || a.start - b.start).slice(0, limit);
}

export function initHook(doc = document) {
  const button = doc.getElementById('hookButton');
  if (!button || doc.getElementById('hookDialog')) return null;
  const dialog = doc.createElement('dialog');
  dialog.id = 'hookDialog';
  dialog.className = 'cleanup-dialog hook-dialog';
  dialog.setAttribute('aria-labelledby', 'hookTitle');
  dialog.innerHTML = `
    <header><h2 id="hookTitle">Opener</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <p class="cleanup-intro" id="hookIntro"></p>
    <ul class="cleanup-list hook-list" aria-label="Opener candidates"></ul>
    <footer><span class="cleanup-total">The sentence is copied to the start. It also stays in place.</span><button type="button" class="cleanup-cancel">Close</button></footer>`;
  doc.body.append(dialog);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const intro = dialog.querySelector('#hookIntro'), list = dialog.querySelector('.hook-list');

  const open = () => {
    const project = host()?.project();
    if (!project) return;
    const rows = rankHooks(project.editor_captions || []);
    intro.textContent = rows.length ? 'The strongest sentences to open with. Go to one to hear it, then use it as the opener.'
      : 'No strong opener was found. Opener needs a transcript with word timing.';
    list.replaceChildren(...rows.map((row) => {
      const li = doc.createElement('li');
      const label = doc.createElement('div'); label.className = 'hook-text';
      const time = doc.createElement('time'); time.textContent = fmt(row.start);
      const text = doc.createElement('span'); text.textContent = row.text; text.dir = 'auto';
      const why = doc.createElement('small'); why.textContent = row.reasons.join(' · ');
      label.append(time, text, why);
      const go = doc.createElement('button'); go.type = 'button'; go.textContent = 'Go to';
      go.addEventListener('click', () => host()?.seek(row.start));
      const use = doc.createElement('button'); use.type = 'button'; use.className = 'cleanup-apply'; use.textContent = 'Use as opener';
      use.addEventListener('click', async () => {
        use.disabled = true;
        const result = await host()?.opener(row.start, row.end);
        if (result) { dialog.close(); host()?.seek(0); } else use.disabled = false;
      });
      li.append(label, go, use);
      return li;
    }));
    dialog.showModal();
    (list.querySelector('.cleanup-apply') || dialog.querySelector('.cleanup-cancel')).focus();
  };
  dialog.querySelector('.cleanup-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', open);
  return { open };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initHook(document), { once: true });
  else initHook(document);
}
