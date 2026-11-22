/* CUTROOM console. Presentation only; original controls retain their listeners,
   readiness, identity and save semantics. No project/API/media access here. */
export function initStudioConsole({ document: doc = document, window: win = window } = {}) {
  const panel = doc.getElementById('advancedPanel');
  const shelf = doc.getElementById('studioShelfMedia');
  const top = doc.querySelector('.topbar .top-actions');
  if (!panel?.workbenchController || !panel.workspaceController || !shelf?.dataset.studioScreens || !top) return null;
  if (panel.consoleController) return panel.consoleController;
  const make = (tag, className, text = '') => { const node = doc.createElement(tag); node.className = className; if (text) node.textContent = text; return node; };
  const listeners = [], observers = [], homes = [], compactHomes = [];
  const listen = (node, type, fn, options) => { node.addEventListener(type, fn, options); listeners.push(() => node.removeEventListener(type, fn, options)); };
  const menu = make('details', 'console-menu'); menu.id = 'consoleMenu';
  const trigger = make('summary', 'console-menu-trigger', 'Workspace'); trigger.setAttribute('aria-label', 'Workspace and help');
  const menuPanel = make('div', 'console-menu-panel'); menuPanel.setAttribute('aria-label', 'Workspace actions');
  menu.append(trigger, menuPanel); top.insertBefore(menu, doc.getElementById('projectsButton'));
  const headerIds = ['closeAdvanced', 'workspaceGuide', 'welcomeHelpButton', 'transcriptionButton', 'aiConnectionButton'];
  let mounted = false, compactMounted = false, disposed = false, frame = null, menuReturn = false;
  const restore = home => { const parent = home.marker.parentNode || home.parent; parent.insertBefore(home.node, home.marker.parentNode ? home.marker : null); };
  const syncChrome = () => {
    const active = doc.body.classList.contains('studio-open') && !panel.hidden;
    menu.hidden = !active;
    if (active && !mounted) {
      if (!homes.length) for (const id of headerIds) {
        const node = doc.getElementById(id); if (!node?.parentNode) continue;
        const marker = doc.createComment('CUTROOM console: ' + id), parent = node.parentNode;
        parent.insertBefore(marker, node); homes.push({ node, marker, parent });
      }
      homes.forEach(home => menuPanel.append(home.node));
    } else if (!active && mounted) {
      menu.open = false; homes.forEach(restore);
    }
    mounted = active;
    const compact = active && (win.innerWidth < 900 || win.innerHeight < 540);
    if (compact === compactMounted) return;
    const focused = doc.activeElement;
    if (compact) {
      if (!compactHomes.length) for (const node of [doc.getElementById('projectsButton'), top.querySelector('.manual-history-actions')]) {
        if (!node?.parentNode) continue;
        const marker = doc.createComment('CUTROOM console: compact action'), parent = node.parentNode;
        parent.insertBefore(marker, node); compactHomes.push({ node, marker, parent });
      }
      compactHomes.forEach(home => menuPanel.append(home.node));
    } else compactHomes.forEach(restore);
    compactMounted = compact;
    if (focused && compactHomes.some(home => home.node.contains(focused))) {
      if (compact) menu.open = true;
      focused.focus({ preventScroll: true });
    }
  };
  const closeMenu = (focus = false) => { if (!menu.open) return; menu.open = false; if (focus) trigger.focus(); };
  listen(doc, 'pointerdown', event => { if (!menu.contains(event.target)) closeMenu(); });
  listen(menu, 'keydown', event => { if (event.key === 'Escape' && menu.open) { event.preventDefault(); event.stopPropagation(); closeMenu(true); } });
  listen(menuPanel, 'click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    menuReturn = true;
    closeMenu(menu.contains(doc.activeElement));
  });
  // Original dialogs may return focus to their opener. Once its menu is closed,
  // the visible summary is the appropriate return point instead of a hidden node.
  listen(doc, 'close', event => {
    // Wait for the original dialog's own close handler before choosing a visible
    // return point. Browsers may leave focus on its now-hidden Close button.
    win.queueMicrotask(() => {
      if (disposed || !menuReturn || menu.open || panel.hidden || doc.querySelector('dialog[open]')) return;
      menuReturn = false;
      if (doc.activeElement === doc.body || menu.contains(doc.activeElement) || event.target.contains(doc.activeElement)) trigger.focus({ preventScroll: true });
    });
  }, true);
  listen(menu, 'focusout', event => { if (event.relatedTarget && !menu.contains(event.relatedTarget)) closeMenu(); });
  listen(win, 'resize', syncChrome);
  const chromeObserver = new win.MutationObserver(syncChrome);
  chromeObserver.observe(doc.body, { attributes: true, attributeFilter: ['class'] });
  chromeObserver.observe(panel, { attributes: true, attributeFilter: ['hidden'] }); observers.push(chromeObserver);

  // Move the native usage filter into a disclosure; search/type/view stay direct.
  const tools = shelf.querySelector('.library-tools'), usage = shelf.querySelector('.library-usage-label');
  let options = null, optionsHome = null;
  if (tools && usage) {
    options = make('details', 'console-library-options');
    const summary = make('summary', '', 'Filter'); summary.title = 'Filter imported media by timeline usage';
    options.append(summary);
    const marker = doc.createComment('CUTROOM console: usage filter'); usage.before(marker);
    optionsHome = { node: usage, marker, parent: usage.parentNode };
    tools.append(options); options.append(usage);
    listen(options, 'keydown', event => { if (event.key === 'Escape' && options.open) { event.preventDefault(); event.stopPropagation(); options.open = false; summary.focus(); } });
    listen(doc, 'pointerdown', event => { if (options.open && !options.contains(event.target)) options.open = false; });
    const select = usage.querySelector('select');
    const syncFilter = () => { const active = select && select.value !== 'all'; options.classList.toggle('has-filter', Boolean(active)); summary.textContent = active ? 'Filtered' : 'Filter'; };
    if (select) listen(select, 'change', syncFilter); syncFilter();
  }
  // Imported files are browseable rows. Placement and maintenance commands stay
  // attached to their exact file, behind a native keyboard/touch disclosure.
  const openAssets = new Set();
  const decorated = new Set();
  const decorateCards = () => {
    if (disposed) return;
    for (const card of shelf.querySelectorAll('.media-asset')) {
      if (card.querySelector('.console-asset-actions')) continue;
      const assetId = card.dataset.libraryAsset;
      const actions = [...card.children].filter(node => node.matches('button,a,.media-asset-usage,.media-preview-repair'));
      if (!actions.length) continue;
      const details = make('details', 'console-asset-actions');
      const summary = make('summary', ''); summary.append(make('span', '', 'Add / review'));
      const count = card.dataset.mediaUsageCount;
      if (card.dataset.mediaUsageValid === 'true' && /^\d+$/.test(count || '')) summary.append(make('small', '', `${count} ${count === '1' ? 'use' : 'uses'}`));
      const content = make('div', 'console-asset-action-body'); details.append(summary, content);
      details.open = openAssets.has(assetId);
      actions.forEach(node => content.append(node)); card.append(details); decorated.add(card);
      // A summary is a disclosure control, never an HTML drag origin.
      summary.addEventListener('dragstart', event => { event.preventDefault(); event.stopPropagation(); });
      details.addEventListener('toggle', () => { if (details.open) openAssets.add(assetId); else openAssets.delete(assetId); });
    }
    for (const card of decorated) if (!card.isConnected) decorated.delete(card);
  };
  const queueCards = () => { if (frame !== null || disposed) return; frame = win.requestAnimationFrame(() => { frame = null; decorateCards(); }); };
  const libraryObserver = new win.MutationObserver(queueCards);
  libraryObserver.observe(shelf, { childList: true, subtree: true }); observers.push(libraryObserver);
  syncChrome(); decorateCards(); panel.classList.add('console-ready'); doc.body.classList.add('console-shell');
  const controller = { sync: () => { syncChrome(); decorateCards(); }, destroy() {
    if (disposed) return; disposed = true;
    listeners.forEach(remove => remove()); observers.forEach(observer => observer.disconnect());
    if (frame !== null) win.cancelAnimationFrame(frame);
    if (menu.contains(doc.activeElement)) doc.getElementById('projectsButton')?.focus();
    [...homes, ...compactHomes].forEach(restore); [...homes, ...compactHomes].forEach(home => home.marker.remove()); menu.remove();
    if (optionsHome) { restore(optionsHome); optionsHome.marker.remove(); options.remove(); }
    for (const card of decorated) { const details = card.querySelector('.console-asset-actions'); const body = details?.querySelector('.console-asset-action-body'); if (body) [...body.children].forEach(node => card.insertBefore(node, details)); details?.remove(); }
    panel.classList.remove('console-ready'); doc.body.classList.remove('console-shell'); delete panel.consoleController;
  } };
  panel.consoleController = controller; return controller;
}
if (typeof document !== 'undefined') {
  const start = () => {
    if (initStudioConsole()) return;
    const panel = document.getElementById('advancedPanel'); if (!panel) return;
    const observer = new MutationObserver(() => { if (initStudioConsole()) observer.disconnect(); });
    observer.observe(panel, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();
}
