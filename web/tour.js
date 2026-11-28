/* Quick tour: five short stops the first time an edit is open, ending at
   Export. Each stop points at a real control; Skip or Escape ends it, and it
   can be started again from the Script… area with window.cutroomTour.start()
   or the "Quick tour" button in the keyboard help. Shown once per browser. */

export const STEPS = [
  { target: '#scriptViewButton', title: 'Edit by text', text: 'Open the script, select words and press Delete. The video is cut in the same place.' },
  { target: '#cleanupButton', title: 'Clean up in one go', text: 'Find long pauses, “um”s and repeated takes, then choose what to remove.' },
  { target: '#promptEditButton', title: 'Or just type it', text: 'Write “remove the long pauses” or “keep only the parts about pricing” and check the plan first.' },
  { target: '#clipBoardButton', title: 'Find the best moments', text: 'Clips ranks moments in the recording and exports the ones you pick as shorts.' },
  { target: '#studioRenderButton, #renderButton', title: 'Export', text: 'When it looks right, export the video, its subtitles, or a file for another editor.' },
];
const KEY = 'cutroom-tour-done';

const visible = (el) => {
  if (!el) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && el.offsetParent !== null;
};

/** The first visible element for a step, or null. */
export function findTarget(doc, selector) {
  for (const el of doc.querySelectorAll(selector)) if (visible(el)) return el;
  return null;
}

/** Bubble position next to a target rect, kept inside the viewport. */
export function place(rect, box, viewport, gap = 12) {
  const below = rect.bottom + gap + box.height <= viewport.height;
  const top = below ? rect.bottom + gap : Math.max(gap, rect.top - gap - box.height);
  const left = Math.min(Math.max(gap, rect.left + rect.width / 2 - box.width / 2), viewport.width - box.width - gap);
  return { top: Math.round(top), left: Math.round(left), below };
}

export function initTour(doc = document) {
  const win = doc.defaultView;
  if (!win || doc.getElementById('cutroomTour')) return null;
  const layer = doc.createElement('div');
  layer.id = 'cutroomTour';
  layer.className = 'tour-layer';
  layer.hidden = true;
  layer.innerHTML = `<div class="tour-ring" aria-hidden="true"></div>
    <div class="tour-bubble" role="dialog" aria-modal="false" aria-labelledby="tourTitle" aria-describedby="tourText">
      <p class="tour-count"></p><h2 id="tourTitle"></h2><p id="tourText"></p>
      <div class="tour-actions"><button type="button" class="tour-skip">Skip tour</button><span></span><button type="button" class="tour-back">Back</button><button type="button" class="tour-next button primary compact">Next</button></div>
    </div>`;
  doc.body.append(layer);
  const ring = layer.querySelector('.tour-ring'), bubble = layer.querySelector('.tour-bubble');
  const count = layer.querySelector('.tour-count'), title = layer.querySelector('#tourTitle'), text = layer.querySelector('#tourText');
  const back = layer.querySelector('.tour-back'), next = layer.querySelector('.tour-next');
  let steps = [], at = 0, target = null;

  const remember = () => { try { win.localStorage.setItem(KEY, '1'); } catch { /* private window */ } };
  const done = () => { try { return win.localStorage.getItem(KEY) === '1'; } catch { return true; } };
  const position = () => {
    if (!target) return;
    const r = target.getBoundingClientRect();
    Object.assign(ring.style, { top: `${r.top - 4}px`, left: `${r.left - 4}px`, width: `${r.width + 8}px`, height: `${r.height + 8}px` });
    const p = place(r, bubble.getBoundingClientRect(), { width: win.innerWidth, height: win.innerHeight });
    Object.assign(bubble.style, { top: `${p.top}px`, left: `${p.left}px` });
  };
  const show = (k) => {
    at = k;
    const step = steps[at];
    target = findTarget(doc, step.target);
    target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    count.textContent = `${at + 1} of ${steps.length}`;
    title.textContent = step.title; text.textContent = step.text;
    back.hidden = at === 0;
    next.textContent = at === steps.length - 1 ? 'Done' : 'Next';
    position();
    next.focus({ preventScroll: true });
  };
  const end = () => {
    layer.hidden = true; target = null; remember();
    win.removeEventListener('resize', position); win.removeEventListener('scroll', position, true);
    doc.removeEventListener('keydown', onKey, true);
  };
  const onKey = (e) => {
    if (layer.hidden) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); end(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); next.click(); }
    else if (e.key === 'ArrowLeft' && at > 0) { e.preventDefault(); show(at - 1); }
  };
  const start = () => {
    steps = STEPS.filter((s) => findTarget(doc, s.target));
    if (!steps.length || doc.querySelector('dialog[open]')) return false;
    layer.hidden = false;
    win.addEventListener('resize', position); win.addEventListener('scroll', position, true);
    doc.addEventListener('keydown', onKey, true);
    show(0);
    return true;
  };
  next.addEventListener('click', () => (at + 1 < steps.length ? show(at + 1) : end()));
  back.addEventListener('click', () => at > 0 && show(at - 1));
  layer.querySelector('.tour-skip').addEventListener('click', end);

  // First time an edit is on screen with its tools, offer the tour once.
  // Automated browsers (tests) never get the tour by itself.
  if (!done() && !win.navigator?.webdriver) {
    let tries = 0;
    const timer = win.setInterval(() => {
      tries += 1;
      const ready = findTarget(doc, '#scriptViewButton') && doc.querySelector('#previewStage video')?.readyState >= 2;
      if (ready && start()) win.clearInterval(timer);
      else if (tries > 600 || done()) win.clearInterval(timer);
    }, 1500);
  }
  const help = doc.querySelector('.shortcut-profile-picker');
  if (help) {
    const again = doc.createElement('button');
    again.type = 'button'; again.className = 'button ghost compact tour-again'; again.textContent = 'Quick tour';
    again.addEventListener('click', () => { help.closest('dialog')?.close?.(); win.setTimeout(start, 50); });
    help.append(again);
  }
  return (win.cutroomTour = { start, end });
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initTour(document), { once: true });
  else initTour(document);
}
