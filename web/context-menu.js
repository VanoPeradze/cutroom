/* Right-click menus for the edit timeline, track headers and the media shelf.
   Every item stands for a button that already exists in the app; choosing it
   clicks that button, so the action keeps its own checks, saving and undo.
   An item is disabled while its button is. Text fields keep the browser's
   menu, and Shift+right-click always gives the browser's menu. */

const TIMELINE_ITEMS = [
  ['manualSplit', 'Split at playhead', 'Ctrl+K'],
  ['clipDuplicate', 'Duplicate'],
  ['manualDelete', 'Remove', 'Delete'],
  null,
  ['manualRestore', 'Add to edit'],
  ['manualLayout', 'Layout…'],
  null,
  ['timelineZoomSelection', 'Zoom to selection'],
  ['manualClear', 'Clear selection'],
  ['closeTimelineGaps', 'Close gaps'],
];

const isShown = (el) => el && !el.hidden && el.getClientRects().length > 0 && !el.closest('[hidden], [inert]');
const isUsable = (el) => el && !el.disabled && el.getAttribute('aria-disabled') !== 'true';

function nameOf(button) {
  const text = button.getAttribute('aria-label') || button.textContent || button.title || '';
  return text.replace(/\s+/g, ' ').trim().slice(0, 60);
}

export function timelineEntries(doc) {
  return TIMELINE_ITEMS.map((row) => {
    if (!row) return null;
    const [id, label, shortcut] = row, button = doc.getElementById(id);
    if (!button || button.hidden) return undefined;
    return { button, label, shortcut, disabled: !isUsable(button) };
  }).filter((entry) => entry !== undefined);
}

export function containerEntries(container) {
  return [...container.querySelectorAll('button')]
    .filter((b) => isShown(b) && nameOf(b))
    .map((button) => ({ button, label: nameOf(button), disabled: !isUsable(button) }));
}

/* Separators only between two items. */
export function tidy(entries) {
  const out = [];
  for (const entry of entries) {
    if (!entry) { if (out.length && out.at(-1) !== null) out.push(null); continue; }
    out.push(entry);
  }
  while (out.length && out.at(-1) === null) out.pop();
  return out;
}

export function initContextMenu(doc = document) {
  if (doc.getElementById('appContextMenu')) return null;
  const menu = doc.createElement('div');
  menu.id = 'appContextMenu';
  menu.className = 'app-context-menu';
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  doc.body.append(menu);
  let opener = null;

  const close = (restore = true) => {
    if (menu.hidden) return;
    menu.hidden = true;
    menu.replaceChildren();
    if (restore && opener?.isConnected) opener.focus({ preventScroll: true });
  };

  const items = () => [...menu.querySelectorAll('[role="menuitem"]:not([aria-disabled="true"])')];

  const open = (entries, x, y, title) => {
    entries = tidy(entries);
    if (!entries.some((e) => e)) return false;
    opener = doc.activeElement;
    menu.replaceChildren();
    menu.setAttribute('aria-label', title);
    for (const entry of entries) {
      if (!entry) { const hr = doc.createElement('div'); hr.setAttribute('role', 'separator'); menu.append(hr); continue; }
      const item = doc.createElement('button');
      item.type = 'button';
      item.setAttribute('role', 'menuitem');
      item.tabIndex = -1;
      const name = doc.createElement('span'); name.textContent = entry.label; name.dir = 'auto'; item.append(name);
      if (entry.shortcut) { const k = doc.createElement('kbd'); k.textContent = entry.shortcut; item.append(k); }
      if (entry.disabled) item.setAttribute('aria-disabled', 'true');
      item.addEventListener('click', () => {
        if (item.getAttribute('aria-disabled') === 'true') return;
        close(false);
        const target = entry.button;
        if (target.isConnected && isUsable(target)) target.click();
        if (opener?.isConnected) opener.focus({ preventScroll: true });
      });
      menu.append(item);
    }
    menu.hidden = false;
    const view = doc.defaultView, rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(x, view.innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, view.innerHeight - rect.height - 8)) + 'px';
    (items()[0] || menu.querySelector('[role="menuitem"]'))?.focus({ preventScroll: true });
    return true;
  };

  menu.addEventListener('keydown', (e) => {
    const list = items(), at = list.indexOf(doc.activeElement);
    if (e.key === 'Escape') { close(); e.preventDefault(); e.stopPropagation(); }
    else if (e.key === 'ArrowDown') { list[(at + 1) % list.length]?.focus(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { list[(at - 1 + list.length) % list.length]?.focus(); e.preventDefault(); }
    else if (e.key === 'Home') { list[0]?.focus(); e.preventDefault(); }
    else if (e.key === 'End') { list.at(-1)?.focus(); e.preventDefault(); }
    else if (e.key === 'Tab') { close(); }
  });
  doc.addEventListener('pointerdown', (e) => { if (!menu.hidden && !menu.contains(e.target)) close(false); }, true);
  doc.defaultView?.addEventListener('blur', () => close(false));
  doc.defaultView?.addEventListener('resize', () => close(false));
  doc.addEventListener('scroll', () => close(false), true);

  /* With Select or Move active, a right-click first selects what is under the
     pointer, the same way a left click would. Other tools (Blade, Slip…)
     would edit on click, so the menu then acts on the current selection. */
  const selectUnder = (canvas, e) => {
    const tool = doc.querySelector('.timeline-tools [data-timeline-tool][aria-pressed="true"]')?.dataset.timelineTool;
    if (!['select', 'move'].includes(tool)) return;
    const init = { bubbles: true, cancelable: true, clientX: e.clientX, clientY: e.clientY, button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse', isPrimary: true };
    canvas.dispatchEvent(new PointerEvent('pointerdown', init));
    canvas.dispatchEvent(new PointerEvent('pointerup', { ...init, buttons: 0 }));
  };

  doc.addEventListener('contextmenu', (e) => {
    if (e.shiftKey || e.defaultPrevented) return;
    const t = e.target;
    if (!(t instanceof Element) || t.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"], #appContextMenu')) return;
    let shown = false;
    const canvas = t.closest('#timelineCanvas');
    if (canvas) {
      selectUnder(canvas, e);
      shown = open(timelineEntries(doc), e.clientX, e.clientY, 'Clip actions');
    } else {
      const row = t.closest('.timeline-track-headers .layer-track-row, .timeline-track-headers [data-track-id], .timeline-track-rows > *');
      const card = !row && t.closest('#studioShelf li, #studioShelf [role="listitem"], #studioShelf article, #studioShelf [data-media-id], #studioShelf [data-asset-id]');
      const box = row || card;
      if (box) shown = open(containerEntries(box), e.clientX, e.clientY, row ? 'Track actions' : 'Media actions');
    }
    if (shown) e.preventDefault();
  });

  return { open, close };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initContextMenu(document), { once: true });
  else initContextMenu(document);
}
