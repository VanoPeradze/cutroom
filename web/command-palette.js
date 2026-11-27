/* Command palette (Ctrl/Cmd+Shift+P, or the "Commands" button in the top bar).
   It lists the commands that are on screen right now: every visible, enabled
   button and tab, named by its own label. Choosing one clicks that very
   button, so each command keeps its existing handler, checks and undo.
   Ctrl/Cmd+K stays the Split shortcut. */

const SKIP = '#commandPalette, #commandPaletteButton, [aria-hidden="true"], [inert]';

function labelOf(el) {
  let text = el.getAttribute('aria-label') || '';
  if (!text) {
    const parts = [], walk = el.ownerDocument.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    while (walk.nextNode()) if (!walk.currentNode.parentElement.closest('[aria-hidden="true"], .sr-only')) parts.push(walk.currentNode.nodeValue.trim());
    const [name, ...rest] = parts.filter(Boolean);
    text = name ? (rest.length ? name + ' · ' + rest.join(' ') : name) : (el.title || '');
  }
  text = text.replace(/\s+/g, ' ').trim();
  return text.length > 70 ? text.slice(0, 67) + '…' : text;
}

function areaOf(el) {
  const region = el.closest('[role="tabpanel"], [role="dialog"], dialog, section[aria-label], nav[aria-label], [role="group"][aria-label], .topbar');
  if (!region) return '';
  if (region.classList.contains('topbar')) return 'Top bar';
  const by = region.getAttribute('aria-labelledby');
  const named = by && region.ownerDocument.getElementById(by.split(' ')[0]);
  return (region.getAttribute('aria-label') || named?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
}

function shortcutOf(el) {
  const m = /\(([^()]*(?:Ctrl|Cmd|Shift|Alt|⌘|[A-Z]\b)[^()]*)\)\s*$/.exec(el.title || '');
  return m ? m[1] : (el.getAttribute('aria-keyshortcuts') || '');
}

function visible(el) {
  if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.closest(SKIP)) return false;
  if (!el.getClientRects().length) return false;
  const style = getComputedStyle(el);
  return style.visibility !== 'hidden' && style.display !== 'none';
}

export function collectCommands(doc) {
  const seen = new Set(), list = [];
  for (const el of doc.querySelectorAll('button, [role="tab"], [role="menuitem"], a[href]:not([href="#"])')) {
    if (!visible(el)) continue;
    const label = labelOf(el);
    if (!label || label.length < 2) continue;
    const area = areaOf(el), key = label + '|' + area;
    if (seen.has(key)) continue;
    seen.add(key);
    list.push({ el, label, area, shortcut: shortcutOf(el) });
  }
  return list;
}

/* Every typed word must appear in the label or area; whole-word and
   start-of-label matches rank first. */
export function rankCommands(list, query) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return list.slice();
  const scored = [];
  for (const item of list) {
    const label = item.label.toLowerCase(), hay = label + ' ' + item.area.toLowerCase();
    if (!words.every((w) => hay.includes(w))) continue;
    let score = 0;
    for (const w of words) {
      if (label.startsWith(w)) score += 4;
      else if (new RegExp('(^|\\W)' + w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).test(label)) score += 2;
      else if (label.includes(w)) score += 1;
    }
    if (item.el.getAttribute?.('role') === 'tab') score += 1;
    scored.push([score, item]);
  }
  return scored.sort((a, b) => b[0] - a[0]).map(([, item]) => item);
}

export function initCommandPalette(doc = document) {
  if (doc.getElementById('commandPalette')) return;
  const dialog = doc.createElement('dialog');
  dialog.id = 'commandPalette';
  dialog.className = 'command-palette';
  dialog.setAttribute('aria-label', 'Commands');
  if (typeof dialog.showModal !== 'function') return;
  dialog.innerHTML = `
    <div class="palette-field">
      <input id="commandPaletteInput" type="text" role="combobox" aria-expanded="true" aria-controls="commandPaletteList"
        aria-autocomplete="list" autocomplete="off" spellcheck="false" dir="auto" placeholder="Type a command…" aria-label="Search commands">
      <kbd>Esc</kbd>
    </div>
    <ul id="commandPaletteList" role="listbox" aria-label="Commands"></ul>
    <p class="palette-empty" id="commandPaletteEmpty" hidden>No command on this screen matches.</p>
    <p class="palette-foot"><span><kbd>↑</kbd><kbd>↓</kbd> choose</span><span><kbd>Enter</kbd> run</span><span><kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>P</kbd> open</span></p>`;
  doc.body.append(dialog);
  const input = dialog.querySelector('input'), listEl = dialog.querySelector('ul'), empty = dialog.querySelector('.palette-empty');
  let all = [], shown = [], active = 0, opener = null;

  const render = () => {
    shown = rankCommands(all, input.value).slice(0, 60);
    active = Math.min(active, Math.max(0, shown.length - 1));
    listEl.replaceChildren(...shown.map((item, i) => {
      const li = doc.createElement('li');
      li.id = 'commandPaletteItem' + i;
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(i === active));
      li.dataset.index = String(i);
      const name = doc.createElement('span'); name.className = 'palette-label'; name.textContent = item.label; name.dir = 'auto';
      li.append(name);
      if (item.area) { const a = doc.createElement('span'); a.className = 'palette-area'; a.textContent = item.area; li.append(a); }
      if (item.shortcut) { const k = doc.createElement('kbd'); k.textContent = item.shortcut; li.append(k); }
      return li;
    }));
    empty.hidden = shown.length > 0;
    if (shown.length) input.setAttribute('aria-activedescendant', 'commandPaletteItem' + active);
    else input.removeAttribute('aria-activedescendant');
    listEl.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' });
  };

  const run = (item) => {
    if (!item) return;
    dialog.close();
    if (item.el.isConnected && !item.el.disabled) { item.el.focus({ preventScroll: true }); item.el.click(); }
  };

  const open = () => {
    if (dialog.open) return;
    opener = doc.activeElement;
    all = collectCommands(doc);
    input.value = ''; active = 0;
    render();
    dialog.showModal();
    input.focus();
  };

  input.addEventListener('input', () => { active = 0; render(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { active = (active + 1) % Math.max(1, shown.length); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { active = (active - 1 + shown.length) % Math.max(1, shown.length); render(); e.preventDefault(); }
    else if (e.key === 'Enter') { run(shown[active]); e.preventDefault(); }
  });
  listEl.addEventListener('click', (e) => { const li = e.target.closest('li'); if (li) run(shown[Number(li.dataset.index)]); });
  listEl.addEventListener('pointermove', (e) => {
    const li = e.target.closest('li'); if (!li || Number(li.dataset.index) === active) return;
    active = Number(li.dataset.index); render();
  });
  dialog.addEventListener('click', (e) => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => { if (opener?.isConnected && doc.activeElement === doc.body) opener.focus({ preventScroll: true }); });

  doc.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && e.code === 'KeyP') { e.preventDefault(); e.stopPropagation(); open(); }
  }, true);

  const nav = doc.querySelector('.topbar .top-actions');
  if (nav) {
    const b = doc.createElement('button');
    b.type = 'button'; b.id = 'commandPaletteButton'; b.className = 'button ghost compact command-palette-button';
    b.setAttribute('aria-haspopup', 'dialog'); b.setAttribute('aria-keyshortcuts', 'Control+Shift+P');
    b.title = 'Search every command on this screen (Ctrl+Shift+P)';
    b.innerHTML = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="6"/><path d="m20 20-4.2-4.2"/></svg><span>Commands</span>';
    b.addEventListener('click', open);
    nav.prepend(b);
  }
  return { open };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initCommandPalette(document), { once: true });
  else initCommandPalette(document);
}
