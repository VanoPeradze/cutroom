/* B-roll ideas. Reads the edit's own transcript (edit time) and suggests
   where a cutaway would help: sentences that name things, numbers, places or
   say "look", "imagine", "for example". Each idea lists what to show. When an
   imported image or video's file name matches what is said, it is offered as
   the shot and can be placed full frame for a few seconds in one Undo step.
   Everything runs on this computer; nothing is searched online. */
import { normalizeWord } from './transcript-search.js?v=20261128-find1';

const STOP = new Set(`about above after again against also always another because been before being below between both
could didn't doesn't doing don't down during each even every everything few from further going gonna have having here
into just know like little make many more most much must need never nothing only other over really right same should
something still such than that their them then there these they thing things think this those through today together
under until very want wanted were what when where which while will with without would your you're yours actually
basically literally probably maybe kind sort okay yeah well also gets got getting people because said says say tell
told talk talking look looking see seeing time times year years way ways lot lots imagine picture example check show here best made part good great done went come came take took give gave back first last next works work`.split(/\s+/));
const HE_STOP = new Set('אני אתה את אתם הוא היא הם הן זה זאת זו של על עם אבל גם כי אם או לא כן מה מי איך למה כמו יש אין היה היו הייתי עוד כל רק אז פה שם הזה הזאת אותו אותה שלי שלך שלנו שלהם בעצם כאילו ממש מאוד'.split(' '));
const CUE = /\b(?:look(?: at)?|see|imagine|picture|for example|example|here's|here is|this is|check out|show you|like this)\b|תראו|תסתכלו|דמיינו|לדוגמה|למשל|הנה|ככה/i;
const round = (n) => Math.round(n * 1000) / 1000;

/** Content words worth showing, in spoken order, without repeats. */
export function visualTerms(words, limit = 4) {
  const seen = new Set(), out = [];
  for (const raw of words) {
    const word = normalizeWord(raw);
    if (!word || seen.has(word)) continue;
    const number = /\p{N}/u.test(word);
    const hebrew = /\p{Script=Hebrew}/u.test(word);
    const content = hebrew ? word.length >= 3 && !HE_STOP.has(word) : word.length >= 4 && !STOP.has(word) && !/'/.test(word);
    if (!number && !content) continue;
    seen.add(word);
    out.push(String(raw).trim().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ''));
    if (out.length >= limit) break;
  }
  return out;
}

const nameTokens = (name) => String(name || '').replace(/\.[a-z0-9]{2,5}$/i, '').split(/[^\p{L}\p{N}]+/u).map(normalizeWord).filter((t) => t.length >= 3);

/** The imported image or video whose file name best matches the spoken words. */
export function matchAsset(words, assets) {
  const spoken = words.map(normalizeWord).filter((w) => w.length >= 3);
  let best = null;
  for (const asset of assets || []) {
    const tokens = nameTokens(asset.name).filter((t) => !STOP.has(t) && !HE_STOP.has(t));
    const score = tokens.filter((t) => spoken.some((w) => w === t || (t.length >= 4 && (w.startsWith(t) || t.startsWith(w)) && Math.min(w.length, t.length) >= 4))).length;
    if (score > 0 && (!best || score > best.score)) best = { id: asset.id, name: asset.name, kind: asset.kind, score };
  }
  return best;
}

/**
 * Ideas in edit time, in order: [{start, end, text, terms, reasons, match}].
 * At most one idea every `gap` seconds; the very start is left to the speaker.
 */
export function suggestBroll(captions, assets = [], { limit = 12, gap = 6, hold = 3, lead = 1.5 } = {}) {
  const rows = [];
  for (const c of captions || []) {
    if (c.hidden || !Array.isArray(c.words) || !c.words.length) continue;
    const words = c.words.map(([s, e, w]) => ({ start: Number(s), end: Number(e), word: String(w).trim() }))
      .filter((w) => w.word && Number.isFinite(w.start) && Number.isFinite(w.end));
    if (words.length < 3 || words[0].start < lead) continue;
    const text = words.map((w) => w.word).join(' ');
    const terms = visualTerms(words.map((w) => w.word));
    const match = matchAsset(words.map((w) => w.word), assets);
    const reasons = [];
    let score = 0;
    if (match) { score += 4; reasons.push(`matches “${match.name}”`); }
    if (CUE.test(text)) { score += 2; reasons.push('points at something'); }
    if (/\p{N}/u.test(text)) { score += 1; reasons.push('a number'); }
    if (terms.length >= 2) { score += 1; reasons.push('names things'); }
    if (!score) continue;
    const start = round(words[0].start);
    const end = round(Math.min(words.at(-1).end + 0.3, start + Math.max(hold, 1)));
    rows.push({ start, end, text, terms, reasons, match, score });
  }
  // Best ideas first, then keep them apart so the speaker is still seen.
  const chosen = [];
  for (const row of rows.sort((a, b) => b.score - a.score || a.start - b.start)) {
    if (chosen.every((c) => Math.abs(c.start - row.start) >= gap)) chosen.push(row);
    if (chosen.length >= limit) break;
  }
  return chosen.sort((a, b) => a.start - b.start).map(({ score, ...row }) => row);
}

const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;

export function initBroll(doc = document) {
  const button = doc.getElementById('brollButton');
  if (!button || doc.getElementById('brollDialog')) return null;
  const dialog = doc.createElement('dialog');
  dialog.id = 'brollDialog';
  dialog.className = 'cleanup-dialog broll-dialog';
  dialog.setAttribute('aria-labelledby', 'brollTitle');
  dialog.innerHTML = `
    <header><h2 id="brollTitle">B-roll ideas</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <p class="cleanup-intro" id="brollIntro"></p>
    <ul class="cleanup-list broll-list" aria-label="B-roll ideas"></ul>
    <footer><span class="cleanup-total broll-status" aria-live="polite"></span><button type="button" class="cleanup-cancel">Close</button></footer>`;
  doc.body.append(dialog);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const intro = dialog.querySelector('#brollIntro'), list = dialog.querySelector('.broll-list'), status = dialog.querySelector('.broll-status');

  const shots = (project) => Object.entries(project?.assets || {})
    .filter(([, a]) => (a?.kind === 'image' || a?.kind === 'video') && a.status === 'ready')
    .map(([id, a]) => ({ id, name: a.name || id, kind: a.kind, duration: Number(a.duration) || 0 }));

  const open = () => {
    const project = host()?.project();
    if (!project) return;
    const media = shots(project);
    const ideas = suggestBroll(project.editor_captions || [], media);
    const hasWords = (project.editor_captions || []).some((c) => !c.hidden && c.words?.length);
    intro.textContent = !hasWords ? 'B-roll ideas need a transcript with word timing. Transcribe the recording first.'
      : !ideas.length ? 'No clear places for B-roll were found in what is said.'
      : media.length ? 'Places where a cutaway would help, and what to show. Choose a shot from your imported media to place it full frame.'
      : 'Places where a cutaway would help, and what to show. Import images or clips (names that match what is said are suggested first) to place them here.';
    status.textContent = ideas.length ? `${ideas.length} idea${ideas.length === 1 ? '' : 's'}` : '';
    list.replaceChildren(...ideas.map((idea) => {
      const li = doc.createElement('li');
      const label = doc.createElement('div'); label.className = 'broll-text';
      const time = doc.createElement('time'); time.textContent = fmt(idea.start);
      const text = doc.createElement('span'); text.textContent = idea.text; text.dir = 'auto';
      const show = doc.createElement('small'); show.dir = 'auto';
      show.textContent = `Show: ${idea.terms.join(', ') || 'what is described'} · ${idea.reasons.join(' · ')}`;
      label.append(time, text, show);
      const go = doc.createElement('button'); go.type = 'button'; go.textContent = 'Go to';
      go.addEventListener('click', () => host()?.seek(Math.max(0, idea.start - 0.5)));
      li.append(label, go);
      if (media.length) {
        const pick = doc.createElement('select'); pick.setAttribute('aria-label', `Shot for ${fmt(idea.start)}`);
        pick.append(Object.assign(doc.createElement('option'), { value: '', textContent: 'Choose a shot…' }));
        for (const shot of media) pick.append(Object.assign(doc.createElement('option'), { value: shot.id, textContent: shot.name, selected: idea.match?.id === shot.id }));
        const place = doc.createElement('button'); place.type = 'button'; place.className = 'cleanup-apply'; place.textContent = 'Place';
        place.disabled = !pick.value;
        pick.addEventListener('change', () => { place.disabled = !pick.value; });
        place.addEventListener('click', async () => {
          const h = host(), shot = media.find((m) => m.id === pick.value);
          if (!h || !shot) return;
          const duration = Number(h.project()?.editor_sequence?.duration) || idea.end;
          let end = Math.min(idea.end, duration);
          if (shot.kind === 'video' && shot.duration > 0) end = Math.min(end, idea.start + shot.duration);
          place.disabled = true;
          const result = await h.edit?.('media_add', { asset_id: shot.id, start: idea.start, end: round(end), x: 0, y: 0, w: 1, h: 1, fit: 'cover', audio_enabled: false });
          status.textContent = result ? `Placed “${shot.name}” at ${fmt(idea.start)}.` : 'The shot could not be placed.';
          place.textContent = result ? 'Placed' : 'Place';
          place.disabled = Boolean(result);
        });
        li.append(pick, place);
      }
      return li;
    }));
    dialog.showModal();
    (list.querySelector('button') || dialog.querySelector('.cleanup-cancel')).focus();
  };
  dialog.querySelector('.cleanup-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', open);
  return { open };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initBroll(document), { once: true });
  else initBroll(document);
}
