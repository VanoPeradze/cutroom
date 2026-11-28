/* One tooltip style for the whole app, shown on hover and on keyboard focus,
   with the shortcut of the active keyboard profile when a control has one.
   The control's own title stays the source of the text: while the tip is
   shown the title is parked in data-tip-title so the browser does not draw a
   second tooltip, and it is put back when the tip hides (unless the app set a
   new title meanwhile, which then wins). Shortcuts are also exposed through
   aria-keyshortcuts for assistive technology. */
import { shortcutRows } from './keyboard.js';

export const SHORTCUT_TARGETS = [
  ['[data-timeline-tool="select"]', 'tool_select'],
  ['[data-timeline-tool="range"]', 'tool_range'],
  ['[data-timeline-tool="blade"]', 'tool_blade'],
  ['[data-timeline-tool="remove_between"]', 'tool_remove_between'],
  ['#manualSplit', 'split'],
  ['#manualDelete', 'delete_selection'],
  ['#manualClear', 'clear_selection'],
  ['#manualRestore', 'restore_selection'],
  ['#manualUndo', 'undo'],
  ['#manualRedo', 'redo'],
  ['#timelineSnap', 'toggle_snapping'],
  ['#timelineZoomIn', 'zoom_in'],
  ['#timelineZoomOut', 'zoom_out'],
  ['#timelineFit', 'fit'],
  ['#timelinePreviousEdit', 'previous_edit'],
  ['#timelineNextEdit', 'next_edit'],
  ['#playButton', 'toggle_play'],
  ['#previewPlay', 'toggle_play'],
];

const DELAY = 450;

/* "Ctrl/Cmd+Shift+Z" → ARIA "Control+Shift+Z Meta+Shift+Z". */
export function ariaKeys(keys) {
  return keys.split(/\s+or\s+|\s+\/\s+/).flatMap((combo) => {
    combo = combo.trim();
    if (!combo || combo === 'Not assigned') return [];
    const parts = combo.split('+').map((p) => p.trim()).map((p) => ({ Esc: 'Escape', Left: 'ArrowLeft', Right: 'ArrowRight', Up: 'ArrowUp', Down: 'ArrowDown', '−': 'Minus' }[p] || p));
    if (parts[0] === 'Ctrl/Cmd') return [['Control', ...parts.slice(1)].join('+'), ['Meta', ...parts.slice(1)].join('+')];
    if (parts.some((p) => /\s/.test(p) || p.includes('/'))) return [];
    return [parts.map((p) => (p === 'Ctrl' ? 'Control' : p)).join('+')];
  }).join(' ');
}

export function shortcutMap(profile) {
  const rows = new Map(shortcutRows(profile).filter((r) => r.bound).map((r) => [r.action, r.keys]));
  const out = new Map();
  for (const [selector, action] of SHORTCUT_TARGETS) if (rows.has(action)) out.set(selector, rows.get(action));
  return out;
}

export function initTooltips(doc = document) {
  if (doc.getElementById('appTooltip')) return null;
  const tip = doc.createElement('div');
  tip.id = 'appTooltip';
  tip.className = 'app-tooltip';
  tip.setAttribute('role', 'tooltip');
  tip.hidden = true;
  const text = doc.createElement('span'), keys = doc.createElement('kbd');
  tip.append(text, keys);
  doc.body.append(tip);
  let current = null, timer = 0, parked = null;
  const profileSelect = () => doc.getElementById('keyboardProfile');
  let keyMap = new Map();

  const applyShortcuts = () => {
    const profile = profileSelect()?.value || 'cutroom';
    for (const [selector] of SHORTCUT_TARGETS) for (const el of doc.querySelectorAll(selector)) { delete el.dataset.shortcut; el.removeAttribute('aria-keyshortcuts'); }
    keyMap = shortcutMap(profile);
    for (const [selector, value] of keyMap) for (const el of doc.querySelectorAll(selector)) {
      el.dataset.shortcut = value;
      const aria = ariaKeys(value);
      if (aria) el.setAttribute('aria-keyshortcuts', aria);
    }
  };

  const restore = () => {
    if (!parked) return;
    const { el, title } = parked;
    if (!el.hasAttribute('title') && title) el.setAttribute('title', title);
    delete el.dataset.tipTitle;
    parked = null;
  };

  const hide = () => {
    clearTimeout(timer);
    tip.hidden = true;
    if (current?.dataset.tipDescribed) { current.removeAttribute('aria-describedby'); delete current.dataset.tipDescribed; }
    restore();
    current = null;
  };

  const place = (el) => {
    const r = el.getBoundingClientRect(), view = doc.defaultView;
    tip.style.left = '0px'; tip.style.top = '0px';
    const t = tip.getBoundingClientRect();
    let top = r.bottom + 8;
    if (top + t.height > view.innerHeight - 8) top = r.top - t.height - 8;
    const left = Math.max(8, Math.min(r.left + r.width / 2 - t.width / 2, view.innerWidth - t.width - 8));
    tip.style.left = left + 'px'; tip.style.top = Math.max(8, top) + 'px';
  };

  const show = (el) => {
    const title = el.getAttribute('title') || '';
    const label = el.getAttribute('aria-label') || '';
    const visibleText = (el.textContent || '').replace(/\s+/g, ' ').trim();
    const shortcut = el.dataset.shortcut || '';
    // Say something the button does not already say on screen.
    const body = title || (label && label !== visibleText ? label : '') || (shortcut && !visibleText ? label : '');
    if (!body && !shortcut) return;
    text.textContent = body || visibleText;
    keys.textContent = shortcut;
    keys.hidden = !shortcut;
    if (title) { parked = { el, title }; el.dataset.tipTitle = title; el.removeAttribute('title'); }
    tip.hidden = false;
    place(el);
    current = el;
    if (!el.hasAttribute('aria-describedby') && shortcut) { el.setAttribute('aria-describedby', tip.id); el.dataset.tipDescribed = '1'; }
  };

  const candidate = (node) => node instanceof Element ? node.closest('button, [role="tab"], a[href], summary, [data-shortcut]') : null;

  const enter = (el, delay) => {
    if (el === current) return;
    hide();
    if (!el || el.closest('#appTooltip, #appContextMenu, #commandPalette') || el.matches(':disabled') && !el.title) return;
    if (!el.title && !el.dataset.shortcut && !el.getAttribute('aria-label')) return;
    timer = setTimeout(() => show(el), delay);
    current = el;
  };

  doc.addEventListener('pointerover', (e) => { if (e.pointerType !== 'touch') enter(candidate(e.target), DELAY); });
  doc.addEventListener('pointerout', (e) => { const el = candidate(e.target); if (el && el === current && !el.contains(e.relatedTarget)) hide(); });
  doc.addEventListener('focusin', (e) => { const el = candidate(e.target); if (el && el.matches(':focus-visible')) enter(el, 150); });
  doc.addEventListener('focusout', (e) => { if (candidate(e.target) === current) hide(); });
  doc.addEventListener('pointerdown', hide, true);
  doc.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !tip.hidden) hide(); }, true);
  doc.addEventListener('scroll', hide, true);
  doc.addEventListener('change', (e) => { if (e.target?.id === 'keyboardProfile' || e.target?.id === 'keyboardHelpProfile') setTimeout(applyShortcuts, 0); });

  applyShortcuts();
  // Some targets (timeline navigation) are created after load.
  let queued = false;
  const check = () => { queued = false; if (SHORTCUT_TARGETS.some(([s]) => { const el = doc.querySelector(s); return el && !el.dataset.shortcut && keyMap.has(s); })) applyShortcuts(); };
  const again = new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(check); } });
  again.observe(doc.body, { childList: true, subtree: true });
  return { applyShortcuts, hide };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initTooltips(document), { once: true });
  else initTooltips(document);
}
