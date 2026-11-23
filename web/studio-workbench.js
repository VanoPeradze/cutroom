/* Workbench presentation and navigation only. Existing editor controls remain
   the only owners of project data, AI requests, export and playback. */
export function initWorkbench({ document: doc = document, window: win = window } = {}) {
  const byId = id => doc.getElementById(id);
  const panel = byId('advancedPanel');
  const inspector = byId('studioInspector');
  const shelf = byId('studioShelf');
  const header = panel?.querySelector('.studio-header');
  const suggestions = panel?.querySelector('.editor-ai-suggestions');
  if (!panel || !inspector || !shelf || !header || !suggestions || !byId('workspaceToolsToggle')) return null;
  if (panel.workbenchController) return panel.workbenchController;
  const listeners = [], observers = [];
  const listen = (el, type, callback) => {
    el.addEventListener(type, callback);
    listeners.push(() => el.removeEventListener(type, callback));
  };
  const make = (tag, className, text = '') => {
    const node = doc.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    return node;
  };
  const button = (id, text, className = '') => {
    const node = make('button', className, text);
    node.id = id; node.type = 'button';
    return node;
  };
  const original = { parent: suggestions.parentNode, next: suggestions.nextSibling, open: suggestions.open };
  const preferenceKey = 'cutroom-media-pool-visible-v1';
  let mediaPoolVisible = true;
  try { mediaPoolVisible = win.localStorage.getItem(preferenceKey) !== 'false'; } catch {}
  let pane = 'inspector', previousScroll = 0, savedInert = new Map();

  const poolToggle = button('workbenchMediaToggle', 'Media pool', 'workbench-pool-toggle');
  poolToggle.setAttribute('aria-controls', 'studioShelf');
  poolToggle.title = 'Show or hide the media pool. Does not change your edit.';
  header.insertBefore(poolToggle, header.firstChild);

  const switcher = make('div', 'workbench-inspector-switch');
  switcher.setAttribute('role', 'group');
  switcher.setAttribute('aria-label', 'Inspector view');
  const inspectButton = button('workbenchInspectorButton', 'Inspector');
  const aiButton = button('workbenchAIButton', 'AI Director');
  inspectButton.setAttribute('aria-controls', 'studioPanelMedia studioPanelTimeline studioPanelFraming studioPanelAudio studioPanelTranscript studioPanelSettings');
  aiButton.setAttribute('aria-controls', 'workbenchAIPanel');
  switcher.append(inspectButton, aiButton);
  inspector.insertBefore(switcher, inspector.firstChild);

  const aiPanel = make('section', 'workbench-ai-panel');
  aiPanel.id = 'workbenchAIPanel'; aiPanel.hidden = true;
  aiPanel.setAttribute('aria-labelledby', 'workbenchAITitle');
  const intro = make('header', 'workbench-ai-intro');
  const heading = make('h3', '', 'AI Director'); heading.id = 'workbenchAITitle';
  intro.append(heading, make('p', '', 'Describe a request alongside your edit. Generation starts only after you review it.'));
  aiPanel.append(intro);
  const brief = make('section', 'workbench-ai-brief'); brief.id = 'workbenchAIBrief';
  brief.setAttribute('aria-label', 'Editing request');
  const requestStatus = make('p', 'workbench-ai-request-status'); requestStatus.id = 'workbenchAIRequestStatus';
  requestStatus.setAttribute('role', 'status'); requestStatus.setAttribute('aria-live', 'polite'); requestStatus.setAttribute('aria-atomic', 'true');
  const requestOptions = make('details', 'workbench-ai-request-options inspector-section');
  requestOptions.id = 'workbenchAIRequestOptions'; requestOptions.append(make('summary', '', 'Draft length & fallback'));
  const progress = make('details', 'workbench-ai-progress inspector-section'); progress.id = 'workbenchAIProgress';
  progress.hidden = true; progress.append(make('summary', '', 'Generation progress'));
  brief.append(requestStatus, requestOptions, progress); aiPanel.append(brief);
  // Only move complete original groups. Their listeners, values, host-owned
  // visibility and accessible descriptions remain the authoritative controls.
  const instruction = byId('directorInstruction')?.closest?.('.instruction-group');
  const duration = byId('durationGroup');
  const fallback = byId('allowExtractiveRoughCut')?.closest?.('label');
  const action = byId('generateButton')?.closest?.('.director-action');
  const analysis = byId('analysisPanel');
  const canDock = Boolean(instruction && duration && fallback && action);
  brief.hidden = !canDock;
  const homes = [];
  let mounted = false, progressVisible = false;
  const restoreHome = home => {
    const parent = home.marker.parentNode || home.parent;
    const next = home.marker.parentNode === parent ? home.marker : home.next?.parentNode === parent ? home.next : null;
    parent.insertBefore(home.node, next);
  };
  const syncProgress = () => {
    const visible = Boolean(analysis && !analysis.hidden);
    progress.hidden = !visible;
    if (visible && !progressVisible) progress.open = true;
    progressVisible = visible;
  };
  const dockControls = active => {
    active = Boolean(active && canDock);
    if (active === mounted) return;
    if (active) {
      if (!homes.length) for (const [node, key] of [[instruction, 'instruction'], [duration, 'duration'], [fallback, 'fallback'], [action, 'action'], [analysis, 'progress']]) {
        if (!node?.parentNode) continue;
        const marker = doc.createComment(`CUTROOM AI pane: ${key}`), parent = node.parentNode, next = node.nextSibling;
        parent.insertBefore(marker, node); homes.push({ node, marker, parent, next });
      }
      brief.insertBefore(instruction, requestOptions);
      requestOptions.append(duration, fallback);
      brief.insertBefore(action, progress);
      if (analysis) progress.append(analysis);
      panel.dataset.aiRequestContext = 'editor';
    } else {
      homes.forEach(restoreHome);
      delete panel.dataset.aiRequestContext;
    }
    mounted = active; syncProgress();
    // The host owns Manual-vs-AI intent, readiness and generation. Relocation
    // never starts a request or rewrites workflow/settings itself.
    panel.dispatchEvent(new win.Event('workbench-ai-context', { bubbles: true }));
  };
  if (analysis && canDock) {
    const progressObserver = new win.MutationObserver(syncProgress);
    progressObserver.observe(analysis, { attributes: true, attributeFilter: ['hidden'] });
    observers.push(progressObserver);
  }
  const connections = make('details', 'workbench-ai-connections inspector-section');
  connections.id = 'workbenchAIConnections'; connections.append(make('summary', '', 'AI connection & speech'));
  const setup = make('div', 'workbench-ai-setup');
  // These open the original dialogs. No model starts, downloads or network
  // requests are introduced by showing or switching this panel.
  for (const [id, title, description, targetId] of [
    ['workbenchAIConnection', 'AI connection', 'Choose local or cloud Story AI', 'aiConnectionButton'],
    ['workbenchTranscription', 'Transcription', 'Speech engine and language options', 'transcriptionButton'],
  ]) {
    const control = button(id, '', 'workbench-ai-entry');
    control.append(make('strong', '', title), make('span', '', description));
    listen(control, 'click', () => {
      const target = byId(targetId);
      if (target && !target.disabled) target.click();
    });
    const target = byId(targetId);
    const sync = () => { control.disabled = !target || target.disabled; };
    sync();
    if (target) {
      const availability = new win.MutationObserver(sync);
      availability.observe(target, { attributes: true, attributeFilter: ['disabled'] });
      observers.push(availability);
    }
    setup.append(control);
  }
  connections.append(setup, make('p', 'workbench-ai-note', 'AI is optional. These tools use your configured providers. Editing and export stay local.'));
  aiPanel.append(connections);
  suggestions.open = true;
  aiPanel.append(suggestions);
  inspector.append(aiPanel);

  const setPane = (next, { focus = false, restoreScroll = true } = {}) => {
    if (!['inspector', 'ai'].includes(next)) return;
    const changed = next !== pane;
    if (changed) {
      if (next === 'ai') {
        previousScroll = inspector.scrollTop;
        savedInert = new Map([...inspector.querySelectorAll(':scope > .tab-panel')].map(node => [node, node.inert]));
        savedInert.forEach((_, node) => { node.inert = true; });
      } else {
        savedInert.forEach((value, node) => { node.inert = value; });
        savedInert.clear();
      }
      pane = next;
      // Focus may be inside the region that is about to become hidden.
      if (pane === 'ai' && [...inspector.querySelectorAll(':scope > .tab-panel')].some(node => node.contains(doc.activeElement))) aiButton.focus();
      if (pane === 'inspector' && aiPanel.contains(doc.activeElement)) inspectButton.focus();
    }
    inspector.dataset.workbenchPane = pane;
    aiPanel.hidden = pane !== 'ai';
    inspectButton.setAttribute('aria-pressed', String(pane === 'inspector'));
    aiButton.setAttribute('aria-pressed', String(pane === 'ai'));
    dockControls(pane === 'ai' && !panel.hidden);
    if (changed) inspector.scrollTop = pane === 'ai' ? 0 : (restoreScroll ? previousScroll : 0);
    if (focus) (pane === 'ai' ? aiButton : inspectButton).focus();
  };
  const setMediaPoolVisible = (visible, persist = true) => {
    mediaPoolVisible = Boolean(visible);
    if (!mediaPoolVisible && shelf.contains(doc.activeElement)) poolToggle.focus();
    shelf.inert = !mediaPoolVisible;
    shelf.setAttribute('aria-hidden', String(!mediaPoolVisible));
    panel.classList.toggle('media-pool-collapsed', !mediaPoolVisible);
    poolToggle.setAttribute('aria-expanded', String(mediaPoolVisible));
    poolToggle.setAttribute('aria-pressed', String(mediaPoolVisible));
    if (persist) try { win.localStorage.setItem(preferenceKey, String(mediaPoolVisible)); } catch {}
    // Let the established player and timeline measure their new available space.
    win.dispatchEvent(new win.Event('resize'));
  };
  listen(poolToggle, 'click', () => setMediaPoolVisible(!mediaPoolVisible));
  listen(inspectButton, 'click', () => setPane('inspector'));
  listen(aiButton, 'click', () => setPane('ai'));
  // Selecting another editing workspace always reveals its tools, even when the
  // user selects Edit again. This also covers keyboard-triggered native clicks.
  const nav = panel.querySelector('.advanced-tabs');
  if (nav) listen(nav, 'click', event => {
    if (event.target.closest('[data-tab]')) setPane('inspector', { restoreScroll: false });
  });
  const observer = new win.MutationObserver(records => {
    if (records.some(record => record.attributeName === 'data-workspace' || (record.attributeName === 'hidden' && panel.hidden))) setPane('inspector', { restoreScroll: false });
  });
  observer.observe(panel, { attributes: true, attributeFilter: ['data-workspace', 'hidden'] });
  setPane('inspector');
  setMediaPoolVisible(mediaPoolVisible, false);
  panel.classList.add('workbench-ready');
  const controller = { setPane, setMediaPoolVisible,
    // Call before the host hides Studio or focuses a Setup field. The observer
    // is a fallback, not a substitute for synchronous control restoration.
    leaveEditor() { setPane('inspector', { restoreScroll: false }); },
    destroy() {
    setPane('inspector');
    setMediaPoolVisible(true, false);
    listeners.forEach(remove => remove()); observer.disconnect(); observers.forEach(item => item.disconnect());
    homes.forEach(home => home.marker.remove());
    suggestions.open = original.open;
    original.parent.insertBefore(suggestions, original.next?.parentNode === original.parent ? original.next : null);
    poolToggle.remove(); switcher.remove(); aiPanel.remove();
    shelf.removeAttribute('aria-hidden');
    panel.classList.remove('workbench-ready');
    delete inspector.dataset.workbenchPane;
    delete panel.workbenchController;
  } };
  panel.workbenchController = controller;
  return controller;
}

if (typeof document !== 'undefined') {
  const start = () => {
    if (initWorkbench()) return;
    const panel = document.getElementById('advancedPanel');
    if (!panel) return;
    const ready = new MutationObserver(() => { if (initWorkbench()) ready.disconnect(); });
    ready.observe(panel, { childList: true, subtree: true });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
}
