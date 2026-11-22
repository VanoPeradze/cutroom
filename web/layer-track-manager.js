import {layerTrackState, layerTrackKind, layerMutationIssue, createLayerMutationPlanner} from './layer-tracks.js?v=20261116-track-levels2';

// Presentation only: the host owns saved projects, admission, revisions and Undo.
export function initLayerTrackManager(root, {snapshot, action, planMove, lockIssue}) {
  const doc = root.ownerDocument;
  const make = (tag, cls, text) => {
    const node = doc.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const details = make('details', 'layer-track-details');
  const summary = make('summary', 'layer-track-summary', 'Tracks');
  const note = make('p', 'layer-track-note', 'Visual tracks stack bottom to top. Text stays above visuals. Audio tracks do not change sound routing. Original A/B and automatic captions stay separate. Locks protect saved clips and track order, not global output or mix settings. Protection stays outside Undo.');
  const status = make('p', 'layer-track-status');
  status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite');
  const button = (text, key, fn) => {
    const node = make('button', '', text); node.type = 'button'; node.dataset.trackAction = key;
    node.addEventListener('click', () => { if (!destroyed && !node.disabled) fn(); });
    return node;
  };
  const enable = button('Enable editable tracks', 'enable', () => run('layer_tracks_enable', {}));
  const list = make('div', 'layer-track-list');
  const add = make('div', 'layer-track-add');
  const kindLabel = make('label', '', 'Track type');
  const kind = make('select');
  for (const value of ['visual', 'audio', 'text']) { const o = make('option', '', value[0].toUpperCase() + value.slice(1)); o.value = value; kind.append(o); }
  kind.value = 'visual'; kindLabel.append(kind);
  const nameLabel = make('label', '', 'New track name');
  const name = make('input', 'layer-track-name'); name.type = 'text'; name.maxLength = 80; nameLabel.append(name);
  const addButton = button('Add track', 'add', () => {
    const value = name.value.trim();
    run('layer_track_add', {kind: kind.value, name: value}, () => { if (name.value.trim() === value) name.value = ''; });
  });
  name.addEventListener('input', () => sync()); add.append(kindLabel, nameLabel, addButton);
  const assignment = make('div', 'layer-track-assignment');
  const membership = make('p', 'layer-track-membership');
  const destinationLabel = make('label', '', 'Move selected clip to track');
  const destination = make('select'); destinationLabel.append(destination);
  const assign = button('Move selected clip', 'assign', () => {
    const s = read(), clip = selected(s.project, s.selectedClipId);
    if (!clip) return;
    const p = movePlan(clip, destination.value);
    if (!p.issue && p.patch && Object.keys(p.patch).length)
      run('layer_move', {clip_id: clip.id, track_id: destination.value, start: clip.start});
  });
  const assignmentHelp = make('p', 'layer-track-membership', 'Moving a clip adopts the destination track sound level and mute. Other clip settings stay unchanged.');
  destination.addEventListener('change', () => sync()); assignment.append(destinationLabel, assign, membership, assignmentHelp);
  details.append(summary, note, enable, add, assignment, list, status);
  root.dataset.editorShortcuts = 'off'; root.append(details);
  let destroyed = false, pending = false, projectId = null, epoch = 0, message = '', optionKey = '', selectionId = null;
  const rows = new Map();
  function read() { try { return snapshot() || {}; } catch { return {issue: 'Track state is unavailable.'}; } }
  function clipsOf(project) { return [project?.manual?.media_clips, project?.manual?.text_clips].flatMap(value => Array.isArray(value) ? value : []); }
  function selected(project, id) {
    const clips = clipsOf(project);
    return clips.find(c => c?.id === id) || null;
  }
  function movePlan(clip, trackId) {
    try { return planMove(clip.id, clip.start, trackId) || {issue: 'Placement is unavailable.'}; }
    catch { return {issue: 'Placement is unavailable.'}; }
  }
  function gate(s, state) { return s.issue || state.issue || (pending ? 'Saving track change…' : s.busy ? 'Finish the current edit first.' : ''); }
  function protectionGate(s, state, trackId, locked) {
    const unlocking = locked === false && state.tracks.some(track => track.id === trackId && track.locked === true);
    if (!unlocking || typeof lockIssue !== 'function') return gate(s, state);
    if (state.issue || pending) return state.issue || 'Saving track change.';
    // The host alone can distinguish a retained draft from a real in-flight save.
    try { const issue = lockIssue(trackId, locked); return typeof issue === 'string' ? issue : 'Track protection readiness could not be confirmed.'; }
    catch { return 'Track protection readiness could not be confirmed.'; }
  }
  function mutationIssue(project, type, payload) {
    try { const issue = layerMutationIssue(project, type, payload); return typeof issue === 'string' ? issue : 'Track protection readiness could not be confirmed.'; }
    catch { return 'Track protection readiness could not be confirmed.'; }
  }
  async function run(type, payload, accepted) {
    const s = read(), state = layerTrackState(s.project);
    const admission = type === 'layer_track_lock' ? protectionGate(s,state,payload.track_id,payload.locked) : gate(s,state);
    if (destroyed || !s.project?.id || admission) return;
    const issue = mutationIssue(s.project, type, payload);
    if (issue) { message = issue; sync(); return; }
    const id = s.project.id, ticket = epoch;
    const origin = type === 'layer_track_lock' && doc.activeElement?.dataset?.trackLock === payload.track_id ? doc.activeElement : null;
    let focusOwned = Boolean(origin);
    const noticeFocus = event => {
      if (event.type === 'focusin' ? event.target !== origin && event.target !== doc.body
        : event.type === 'keydown' ? ![' ', 'Enter'].includes(event.key) : true) focusOwned = false;
    };
    if (origin) for (const type of ['focusin', 'pointerdown', 'keydown']) doc.addEventListener?.(type, noticeFocus, true);
    const releaseFocus = () => {
      if (origin) for (const type of ['focusin', 'pointerdown', 'keydown']) doc.removeEventListener?.(type, noticeFocus, true);
      if (focusOwned && !destroyed && epoch === ticket && read().project?.id === id
        && doc.activeElement === doc.body && origin.isConnected && !origin.disabled && origin.getClientRects?.().length)
        origin.focus?.({preventScroll:true});
    };
    pending = true; message = ''; sync();
    try {
      const result = await action(type, payload);
      if (destroyed || epoch !== ticket || read().project?.id !== id) return;
      const current = read().project, receiptState = layerTrackState(result), currentState = layerTrackState(current);
      const protectionMatches = type !== 'layer_track_lock' || (!receiptState.issue && !currentState.issue
        && receiptState.tracks.some(track => track.id === payload.track_id && track.locked === payload.locked)
        && currentState.tracks.some(track => track.id === payload.track_id && track.locked === payload.locked));
      if (result?.id === id && Number.isInteger(result.revision) && result.revision === current?.revision && protectionMatches) {
        accepted?.(); message = type === 'layer_track_lock' ? 'Protection saved. Locks stay outside Undo.' : 'Track change saved.';
      } else if (type !== 'layer_track_lock' || current === s.project) message = 'Track change was not applied. Check the current edit and try again.';
    } catch (error) {
      if (!destroyed && epoch === ticket && read().project?.id === id && (type !== 'layer_track_lock' || read().project === s.project)) message = error?.message || 'Track change could not be saved.';
    } finally {
      if (!destroyed && epoch === ticket) { pending = false; sync(); }
      releaseFocus();
    }
  }
  function row(track) {
    const node = make('section', 'layer-track-row'); node.dataset.trackId = track.id;
    const label = make('label', '', 'Track name');
    const input = make('input', 'layer-track-name'); input.type = 'text'; input.maxLength = 80; label.append(input);
    const info = make('p', 'layer-track-info');
    const controls = make('div', 'layer-track-actions');
    const protection = make('label', 'layer-track-protection');
    const lock = make('input'); lock.type = 'checkbox'; lock.dataset.trackLock = track.id;
    const lockText = make('span', '', 'Lock track edits'); protection.append(lock, lockText);
    const record = {node, input, info, lock, protection, dirty: false, buttons: {}};
    lock.addEventListener('change', () => {
      const saved = layerTrackState(read().project).tracks.find(row => row.id === track.id);
      const requested = lock.checked;
      lock.checked = saved?.locked === true;
      if (!destroyed && !lock.disabled && saved && requested !== (saved.locked === true))
        run('layer_track_lock', {track_id:track.id, locked:requested});
    });
    input.addEventListener('input', () => { record.dirty = true; sync(); });
    record.buttons.rename = button('Rename', 'rename', () => {
      const value = input.value.trim();
      run('layer_track_rename', {track_id: track.id, name: value}, () => { if (input.value.trim() === value) record.dirty = false; });
    });
    for (const [position, text] of [['back', 'To bottom'], ['backward', 'Down'], ['forward', 'Up'], ['front', 'To top']])
      record.buttons[position] = button(text, position, () => run('layer_track_reorder', {track_id: track.id, position}));
    record.buttons.remove = button('Remove empty track', 'remove', () => run('layer_track_remove', {track_id: track.id}));
    controls.append(...Object.values(record.buttons)); node.append(label, info, protection, controls); return record;
  }
  function disabled(node, issue) { node.disabled = Boolean(issue); node.title = issue || ''; }
  function sync() {
    if (destroyed) return;
    const s = read(), project = s.project, id = project?.id || null;
    if (id !== projectId) {
      projectId = id; epoch++; pending = false; message = ''; name.value = ''; optionKey = ''; selectionId = null;
      for (const r of rows.values()) r.node.remove(); rows.clear();
    }
    root.hidden = !id;
    const state = layerTrackState(project), issue = gate(s, state), tracks = state.tracks || [];
    // Reuse validated saved state only for this synchronous paint, never admission.
    let mutationPlan; try { mutationPlan = createLayerMutationPlanner(project); } catch { /* Fail closed. */ }
    const readinessIssue = (type, payload) => {
      try { const value = mutationPlan?.(type, payload); return typeof value === 'string' ? value : 'Track protection readiness could not be confirmed.'; }
      catch { return 'Track protection readiness could not be confirmed.'; }
    };
    enable.hidden = state.enabled || Boolean(state.issue); disabled(enable, issue);
    add.hidden = assignment.hidden = list.hidden = !state.enabled || Boolean(state.issue);
    summary.textContent = state.enabled ? `Tracks (${tracks.length})` : 'Tracks';
    status.textContent = issue || message || (state.enabled ? 'Track edits support Undo. Protection stays outside Undo; unlock before restoring protected content.' : 'Enable once to turn existing layers into saved tracks without changing their picture or sound.');
    disabled(kind, issue); disabled(name, issue);
    disabled(addButton, issue || (tracks.length >= 4096 ? 'Track limit reached.' : !name.value.trim() || name.value.trim().length > 80 ? 'Enter a track name (1–80 characters).' : ''));
    const allClips = clipsOf(project);
    const live = new Set(tracks.map(t => t.id));
    for (const [key, r] of rows) if (!live.has(key)) { r.node.remove(); rows.delete(key); }
    const displayTracks = ['text', 'visual', 'audio'].flatMap(kind => tracks.filter(t => t.kind === kind).reverse());
    displayTracks.forEach((track, index) => {
      let r = rows.get(track.id); if (!r) { r = row(track); rows.set(track.id, r); }
      if (list.children[index] !== r.node) {
        const focused = doc.activeElement;
        list.insertBefore(r.node, list.children[index] || null);
        if (focused && r.node.contains(focused) && doc.activeElement !== focused) focused.focus?.({preventScroll: true});
      }
      r.node.dataset.kind = track.kind; r.node.dataset.trackLocked = String(track.locked === true);
      r.lock.checked = track.locked === true;
      r.lock.setAttribute('aria-label', `Lock edits on track ${track.name}`);
      const toggleIssue = protectionGate(s,state,track.id,track.locked !== true) || readinessIssue('layer_track_lock', {track_id:track.id, locked:track.locked !== true});
      disabled(r.lock, toggleIssue); r.protection.title = toggleIssue || 'Protects saved clips and track order. Selection, source audition, export and renaming stay available. Protection is kept outside Undo.';
      if (!r.dirty) r.input.value = track.name;
      const band = tracks.filter(t => t.kind === track.kind), rank = band.findIndex(t => t.id === track.id), count = allClips.filter(c => c?.track_id === track.id).length;
      r.info.textContent = `${track.kind} · ${rank + 1} of ${band.length}, bottom to top · ${count} clip${count === 1 ? '' : 's'} (including disabled)`;
      disabled(r.input, issue);
      disabled(r.buttons.rename, issue || readinessIssue('layer_track_rename', {track_id:track.id,name:r.input.value.trim()}) || (!r.input.value.trim() || r.input.value.trim().length > 80 ? 'Enter a track name (1–80 characters).' : r.input.value.trim() === track.name ? 'Name is unchanged.' : ''));
      for (const position of ['back', 'backward', 'forward', 'front']) disabled(r.buttons[position], issue || readinessIssue('layer_track_reorder', {track_id:track.id,position}) || ((position === 'back' || position === 'backward') ? rank === 0 : rank === band.length - 1) && 'Already at this edge of its track type.');
      disabled(r.buttons.remove, issue || readinessIssue('layer_track_remove', {track_id:track.id}) || (count ? 'Move or remove every clip before removing this track.' : ''));
    });
    const clip = selected(project, s.selectedClipId), clipKind = clip ? layerTrackKind(project, clip) : null;
    const compatible = displayTracks.filter(t => t.kind === clipKind);
    const currentTrack = tracks.find(t => t.id === clip?.track_id);
    membership.textContent = clip && currentTrack ? `Current track: ${currentTrack.name}${currentTrack.locked === true ? " (locked)" : ""}` : 'No single imported media or custom text clip selected.';
    const key = JSON.stringify([s.selectedClipId, compatible.map(t => [t.id, t.name, t.locked === true])]);
    if (key !== optionKey) {
      const previous = selectionId === s.selectedClipId ? destination.value : clip?.track_id;
      destination.replaceChildren();
      for (const t of compatible) { const option = make('option', '', t.name + (t.locked === true ? ' (locked)' : '')); option.value = t.id; destination.append(option); }
      destination.value = compatible.some(t => t.id === previous) ? previous : (clip?.track_id || compatible[0]?.id || '');
      optionKey = key; selectionId = s.selectedClipId;
    }
    const p = clip && destination.value ? movePlan(clip, destination.value) : {issue: 'Select one imported media or custom text clip.'};
    disabled(destination, issue || (!compatible.length ? 'Select one imported media or custom text clip.' : ''));
    disabled(assign, issue || p.issue || (!p.patch || !Object.keys(p.patch).length ? 'Selected clip is already on this track.' : ''));
  }
  sync();
  return {
    sync,
    reveal(trackId) { if (destroyed) return false; sync(); const r = rows.get(trackId); if (!r) return false; details.open = true; r.node.scrollIntoView?.({block: 'nearest'}); r.input.focus?.({preventScroll: true}); return true; },
    destroy() { if (destroyed) return; destroyed = true; epoch++; details.remove(); rows.clear(); },
  };
}
