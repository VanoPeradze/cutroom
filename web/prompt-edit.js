/* Edit by prompt. The user types what they want in plain English or Hebrew
   ("remove the pauses", "cut from 0:10 to 0:14", "delete every 'basically'",
   "find pricing", "add an opener"). The request is understood here, on this
   computer, by matching known edit phrases; nothing is sent anywhere. Before
   anything changes the dialog says exactly what will happen, and removals are
   one Undo step. */
import { findCleanup, removalRanges } from './cleanup.js?v=20261128-cleanup1';
import { rankHooks } from './hook.js?v=20261128-hook1';
import { autoZoomKeyframes } from './color-motion.js?v=20261128-autozoom1';
import { scriptParagraphs, selectionRange, findMatches, mergeRanges, parseTime } from './transcript-search.js?v=20261128-find1';

const REMOVE = /(?:^|\s)(?:remove|delete|cut|trim|drop|get rid of|take out|clean(?: up)?|הסר|תסיר|תסירי|להסיר|מחק|תמחק|תמחקי|למחוק|חתוך|תחתוך|תחתכי|לחתוך|הורד|תוריד|תורידי|להוריד|נקה|תנקה|תנקי|לנקות)(?=\s|$)/i;
const FIND = /^(?:find|search(?: for)?|where (?:do i|did i|is|are)(?: say)?|show me|go to|jump to|חפש|תחפש|תחפשי|מצא|תמצא|תמצאי|איפה(?: אמרתי)?|עבור ל-?|תעבור ל-?|קפוץ ל-?|תקפוץ ל-?|לך ל-?)\s*/i;
const TIME = String.raw`(\d+(?::\d{1,2})*(?:\.\d+)?)\s*(?:s|sec|secs|seconds|שניות)?`;
const RANGE = new RegExp(String.raw`(?:from|between|מ-?|בין)\s*${TIME}\s*(?:to|until|and|-|–|עד|ל-?|ו-?)\s*${TIME}`, 'i');
const KINDS = [
  ['pause', /pause|silence|quiet|gap|dead air|שקט|שתיק|הפסק|רווח/i],
  ['hesitation', /\bums?\b|\buhs?\b|\berm\b|hesitat|stutter|אממ|אהה|גמגו|היסוס/i],
  ['filler', /filler|מילות מילוי|מילי מילוי/i],
  ['retake', /retake|repeat|second take|false start|חזרות|טייק|חזרה/i],
];
const EVERYTHING = /^(?:clean(?: it)? up|clean everything|tidy(?: up)?|נקה(?: הכל| את הכל)?|תנקה(?: הכל| את הכל)?|ניקוי)$/i;
const OPENER = /opener|hook|cold open|start with|פתיח|הוק|תפתח/i;
const ZOOM = /zoom|punch.?in|זום/i;
const QUOTE = /^["“”'‘’״׳](.+)["“”'‘’״׳]$/;
const fmt = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(1).padStart(4, '0')}`;
const total = (ranges) => ranges.reduce((s, r) => s + r.end - r.start, 0);
const phraseOf = (text) => {
  const bare = text.replace(/^(?:the words?|every|all(?: the)?|each|את המילים|את המילה|המילה|כל ה-?|את כל ה-?|את)\s+/i, '').replace(/\s+(?:everywhere|from the video|מהסרטון|מכל הסרטון)$/i, '').trim();
  return (bare.match(QUOTE)?.[1] ?? bare).trim();
};

/**
 * What a prompt asks for, as a plan that has not been applied yet:
 * {kind: 'remove'|'seek'|'find'|'opener'|'zoom'|'none', summary, ranges?, time?, query?, hook?, keyframes?}
 */
export function planPrompt(prompt, project) {
  const text = String(prompt ?? '').trim().replace(/[.!؟?]+$/, '').replace(/\s+/g, ' ');
  const captions = project?.editor_captions || [];
  const duration = Number(project?.editor_sequence?.duration);
  if (!text) return { kind: 'none', summary: '' };
  const removing = REMOVE.test(text);

  const range = text.match(RANGE);
  if (range && removing) {
    const start = parseTime(range[1]), end = parseTime(range[2]);
    if (start === null || end === null || end - start < 0.08) return { kind: 'none', summary: 'The end time has to come after the start time.' };
    if (Number.isFinite(duration) && end > duration + 0.001) return { kind: 'none', summary: `The edit is only ${fmt(duration)} long.` };
    return { kind: 'remove', ranges: [{ start, end }], summary: `Remove ${fmt(start)} to ${fmt(end)} (${(end - start).toFixed(1)} s).` };
  }

  const find = text.match(FIND);
  if (find && !removing) {
    const rest = text.slice(find[0].length).trim();
    const time = parseTime(rest);
    if (time !== null) {
      if (Number.isFinite(duration) && time > duration) return { kind: 'none', summary: `The edit is only ${fmt(duration)} long.` };
      return { kind: 'seek', time, summary: `Go to ${fmt(time)}.` };
    }
    const query = phraseOf(rest);
    if (!query) return { kind: 'none', summary: 'Say what to find, for example: find pricing.' };
    const words = scriptParagraphs(captions).flatMap((p) => p.words);
    const matches = findMatches(words, query);
    return matches.length
      ? { kind: 'find', query, time: words[matches[0][0]].start, summary: `“${query}” is said ${matches.length === 1 ? 'once' : `${matches.length} times`}, first at ${fmt(words[matches[0][0]].start)}. Opens the script on it.` }
      : { kind: 'none', summary: `“${query}” isn't in the transcript.` };
  }

  const kinds = KINDS.filter(([, pattern]) => pattern.test(text)).map(([kind]) => kind);
  if ((removing && kinds.length) || EVERYTHING.test(text)) {
    const all = findCleanup(captions, duration);
    const chosen = kinds.length ? all.filter((c) => kinds.includes(c.kind)).map((c) => ({ ...c, checked: true })) : all;
    const ranges = removalRanges(chosen);
    const what = kinds.length ? kinds.map((k) => ({ pause: 'long pauses', hesitation: 'hesitations', filler: 'filler words', retake: 'repeated takes' })[k]).join(' and ') : 'long pauses, hesitations and repeated takes';
    if (!captions.some((c) => !c.hidden && c.words?.length && !c.estimated_words)) return { kind: 'none', summary: 'This needs a transcript with word timing. Transcribe the recording first.' };
    return ranges.length
      ? { kind: 'remove', ranges, summary: `Remove ${what}: ${ranges.length} cut${ranges.length === 1 ? '' : 's'}, ${total(ranges).toFixed(1)} s shorter.` }
      : { kind: 'none', summary: `No ${what} were found.` };
  }

  if (OPENER.test(text) && !removing) {
    const hook = rankHooks(captions)[0];
    return hook
      ? { kind: 'opener', hook, summary: `Copy “${hook.text}” (${fmt(hook.start)}) to the start as the opener.` }
      : { kind: 'none', summary: 'No strong opener was found. This needs a transcript with word timing.' };
  }

  if (ZOOM.test(text) && !removing) {
    const existing = project?.manual?.keyframes || [];
    const keyframes = autoZoomKeyframes(captions, existing);
    const added = (keyframes.length - existing.length) / 4;
    return added > 0
      ? { kind: 'zoom', keyframes, summary: `Add ${added} short zoom${added === 1 ? '' : 's'} on numbers and key words.` }
      : { kind: 'none', summary: 'No new key words to zoom on.' };
  }

  if (removing) {
    const query = phraseOf(text.replace(REMOVE, ' ').trim());
    if (query) {
      const words = scriptParagraphs(captions).flatMap((p) => p.words);
      const matches = findMatches(words, query, { prefix: false });
      const ranges = mergeRanges(matches.map(([lo, hi]) => selectionRange(words, lo, hi)));
      return ranges.length
        ? { kind: 'remove', ranges, query, summary: `Remove “${query}” ${matches.length === 1 ? 'once' : `in ${matches.length} places`} (${total(ranges).toFixed(1)} s).` }
        : { kind: 'none', summary: `“${query}” isn't in the transcript.` };
    }
  }
  return { kind: 'none', summary: "Not sure what to do. Try one of the examples below." };
}

const EXAMPLES = ['Remove the long pauses', 'Remove um and uh', 'Cut from 0:05 to 0:08', 'Delete every “basically”', 'Find pricing', 'Add an opener', 'Zoom on key words', 'תסיר את השתיקות'];

export function initPromptEdit(doc = document) {
  const button = doc.getElementById('promptEditButton');
  if (!button || doc.getElementById('promptEditDialog')) return null;
  const dialog = doc.createElement('dialog');
  dialog.id = 'promptEditDialog';
  dialog.className = 'cleanup-dialog prompt-edit-dialog';
  dialog.setAttribute('aria-labelledby', 'promptEditTitle');
  dialog.innerHTML = `
    <header><h2 id="promptEditTitle">What should change?</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <form class="prompt-edit-form" method="dialog">
      <input type="text" class="prompt-edit-input" dir="auto" autocomplete="off" aria-describedby="promptEditPlan" placeholder="Remove the long pauses">
      <p class="prompt-edit-plan" id="promptEditPlan" aria-live="polite"></p>
      <div class="prompt-edit-examples" role="group" aria-label="Examples"></div>
    </form>
    <footer><span class="cleanup-total">Understood on this computer. Removals are one Undo step.</span><button type="button" class="cleanup-cancel">Close</button><button type="button" class="cleanup-apply" disabled>Do it</button></footer>`;
  doc.body.append(dialog);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const input = dialog.querySelector('.prompt-edit-input'), planText = dialog.querySelector('.prompt-edit-plan');
  const apply = dialog.querySelector('.cleanup-apply'), examples = dialog.querySelector('.prompt-edit-examples');
  let plan = { kind: 'none' };

  const refresh = () => {
    plan = planPrompt(input.value, host()?.project());
    planText.textContent = plan.summary;
    planText.dataset.ready = String(plan.kind !== 'none');
    apply.disabled = plan.kind === 'none';
    apply.textContent = plan.kind === 'remove' ? 'Remove' : plan.kind === 'seek' || plan.kind === 'find' ? 'Go' : 'Do it';
  };
  examples.replaceChildren(...EXAMPLES.map((example) => {
    const chip = doc.createElement('button'); chip.type = 'button'; chip.textContent = example; chip.dir = 'auto';
    chip.addEventListener('click', () => { input.value = example.replace(/[“”]/g, '"'); refresh(); input.focus(); });
    return chip;
  }));

  const run = async () => {
    const h = host();
    if (!h || plan.kind === 'none') return;
    if (plan.kind === 'seek') { h.seek(plan.time); dialog.close(); return; }
    if (plan.kind === 'find') { dialog.close(); const view = doc.defaultView.cutroomScriptView; if (view) view.find(plan.query); else h.seek(plan.time); return; }
    if (plan.kind === 'zoom') { h.saveManual({ keyframes: plan.keyframes }); h.refreshMotion?.(); dialog.close(); return; }
    apply.disabled = true;
    if (plan.kind === 'opener') {
      const result = await h.opener(plan.hook.start, plan.hook.end);
      if (result) { dialog.close(); h.seek(0); } else refresh();
      return;
    }
    const issue = h.issue?.(plan.ranges);
    if (issue) { planText.textContent = issue; planText.dataset.ready = 'false'; return; }
    const result = await h.apply(plan.ranges);
    if (result) dialog.close(); else refresh();
  };

  input.addEventListener('input', refresh);
  dialog.querySelector('form').addEventListener('submit', (e) => { e.preventDefault(); void run(); });
  apply.addEventListener('click', () => void run());
  dialog.querySelector('.cleanup-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', () => { if (!host()?.project()) return; refresh(); dialog.showModal(); input.focus(); input.select(); });
  return { refresh };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initPromptEdit(document), { once: true });
  else initPromptEdit(document);
}
