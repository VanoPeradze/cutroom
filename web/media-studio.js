// Additional footage and sound are edit-clock layers, not replacement A/B sources.
export function clipEnvelope(clip, time) {
  const elapsed = time - clip.start, remaining = clip.end - time;
  if (elapsed < 0 || remaining <= 0 || clip.muted) return 0;
  return Math.min(1, clip.fade_in > 0 ? elapsed / clip.fade_in : 1,
    clip.fade_out > 0 ? remaining / clip.fade_out : 1);
}

export function mediaGain(clip, mixer, time) {
  const role = clip.role || 'music';
  if (mixer[`${role}_muted`]) return 0;
  return clipEnvelope(clip, time) * 10 ** ((Number(clip.volume_db || 0) + Number(mixer[`${role}_db`] || 0)) / 20);
}

// Export normalizes loudness after the channel faders when the draft asks for
// it (draft.audio_policy), then applies Master. The preview follows with a slow
// gain from loudness measured on the summed mix (K-weighted, 3 s window), so a
// fader changes the balance, not the overall level, exactly as in the export.
export const PREVIEW_LOUDNESS_WINDOW_MS = 3000;
export function previewNormalizationGain(previousDb, measuredLufs, targetLufs, elapsed) {
  if (!Number.isFinite(measuredLufs) || measuredLufs < -70) return previousDb; // Silence holds the gain.
  const desired = Math.max(-30, Math.min(30, targetLufs - measuredLufs));
  return previousDb + (desired - previousDb) * (1 - Math.exp(-Math.max(0, elapsed) / 0.8));
}

export function mixerNormalization(project) {
  const policy = project?.draft?.audio_policy;
  if (!policy?.normalize) return null;
  const target = Number(policy.target_lufs);
  return { target: Number.isFinite(target) ? Math.max(-24, Math.min(-10, target)) : -16 };
}

// The control and saved mixer share one 0.1 dB domain. Pointer precision changes
// travel sensitivity, never the gain curve, audio graph or export values.
export function faderGain(value) {
  return Math.round(Math.max(-60, Math.min(12, Number(value) || 0)) * 10) / 10;
}
export function faderPointerGain(start, delta, travel, fine = false) {
  return faderGain(start + delta / Math.max(1, travel) * 72 * (fine ? .1 : 1));
}

export function visualMotion(clip, time) {
  const progress = Math.max(0, Math.min(1, (time - clip.start) / Math.max(.001, clip.end - clip.start)));
  if (clip.motion === 'zoom_in') return `scale(${1 + .12 * progress})`;
  if (clip.motion === 'pan') return `scale(1.12) translateX(${(.5-progress)*100*.12/1.12}%)`;
  return 'none';
}

export function libraryVideoAt(project, time = null) {
  if (time !== null && !Number.isFinite(time)) return null;
  const clips = project?.manual?.media_clips;
  if (!Array.isArray(clips)) return null;
  for (let index = clips.length - 1; index >= 0; index--) {
    const clip = clips[index], asset = project?.assets?.[clip?.asset_id];
    if (asset?.kind !== 'video' || asset.status !== 'ready'
      || !Number.isFinite(clip.start) || !Number.isFinite(clip.end) || clip.start < 0 || clip.end <= clip.start) continue;
    if (time === null || (clip.start <= time && time < clip.end)) return clip;
  }
  return null;
}

// Library rows show a frame (or a waveform for sound) and the clip length.
function libraryClock(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}
function libraryThumb(url, kind) {
  const thumb = document.createElement('span'); thumb.className = 'library-thumb'; thumb.dataset.kind = kind || 'video'; thumb.setAttribute('aria-hidden', 'true');
  if (url) { const image = document.createElement('img'); image.src = url; image.alt = ''; image.loading = 'lazy'; thumb.append(image); }
  return thumb;
}

export function libraryShotRange(asset,start,end) {
  const duration=Number(asset?.duration);
  if(asset?.kind!=="video" || asset.status!=="ready" || !Number.isFinite(duration) || duration<=0)throw new Error("Choose a ready project video.");
  if(![start,end].every(n=>typeof n==="number" && Number.isFinite(n)) || start<0 || end>duration+.000001 || end-start<.08-1e-9)throw new Error("Choose source In / Out inside this video, at least 0.08 seconds apart.");
  return{source_start:start,source_end:end};
}

export function libraryInsertReadiness(project,at) {
  const duration=Number(project?.editor_sequence?.duration ?? project?.draft?.output_duration);
  if(!Number.isFinite(at)||at<0||!Number.isFinite(duration)||at>duration)return 'Choose a playhead inside the edited timeline.';
  if(Math.abs(at-duration)<1e-9)return '';
  if(project?.draft?.audio_plan?.length)return 'A timed audio plan is present. Append remains available; middle insertion is not supported for this plan.';
  if(project?.caption_alternative_status?.active_id && project.caption_alternative_status.active_id!=='original')return 'An alternative caption version is active. Undo that selection before inserting; append remains available.';
  for(const key of ['media_clips','text_clips'])if((project.manual?.[key]||[]).some(row=>row.start<at-1e-9&&row.end>at+1e-9))return 'A media/audio/text clip crosses the playhead. Split it or choose a boundary; append remains available.';
  return '';
}

export class MediaStudio {
  constructor(root, stage, options) {
    this.root = root; this.stage = stage; this.options = options;
    this.selected = null; this.projectId = null; this.players = new Map(); this.overrides = new Map();
    this.pending = new Map(); this.timer = null; this.saving = null; this.uploading = false;
    this.root.innerHTML = `
      <header class="studio-tool-intro"><div><h3>Media</h3></div><span>Import a file, then add it at the playhead.</span></header>
      <button type="button" class="media-import button primary" data-import>Add media</button><input type="file" accept="video/*,audio/*,image/png,image/jpeg,image/webp" hidden>
      <p class="media-status" role="status" aria-live="polite">Import a file, then add it at the playhead.</p>
      <p class="media-storage upload-storage-info" hidden dir="auto"></p>
      <p class="media-selection-empty">Select an added clip on the timeline to adjust its timing, position and sound.</p>
      <section class="media-inspector" hidden data-editor-shortcuts="off">
        <h4 class="media-selected-name"></h4>
        <div class="media-fields">
          <label>Start (seconds)<input data-media="start" type="number" min="0" step="0.01"></label>
          <label>End (seconds)<input data-media="end" type="number" min="0" step="0.01"></label>
          <label data-kind="timed">Source in<input data-media="source_start" type="number" min="0" step="0.01"></label>
          <label data-kind="video">Picture speed<select data-media="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select></label>
          <label data-kind="visual">Framing<select data-media="fit"><option value="cover">Fill frame</option><option value="contain">Fit entire image</option></select></label>
          <label data-kind="image">Motion<select data-media="motion"><option value="none">Still</option><option value="zoom_in">Slow zoom</option><option value="pan">Slow pan</option></select></label>
        </div>
        <details class="inspector-section media-clip-audio" data-kind="sound"><summary>Clip audio</summary><div class="media-fields">
          <label data-kind="sound">Audio group<select data-media="role"><option value="music">Music</option><option value="voice">Voiceover</option><option value="effects">Effects</option></select></label>
          <label data-kind="sound">Clip volume (dB)<input data-media="volume_db" type="range" min="-60" max="12" step="1"><output data-value="volume_db"></output></label>
          <label data-kind="sound">Fade in (seconds)<input data-media="fade_in" type="number" min="0" step="0.1"></label>
          <label data-kind="sound">Fade out (seconds)<input data-media="fade_out" type="number" min="0" step="0.1"></label>
          <label data-kind="video"><input data-media="audio_enabled" type="checkbox"> Use clip audio</label>
        </div></details>
        <details class="media-placement"><summary>Position & size</summary><div class="media-fields">
          <label>Left (%)<input data-media="x" type="number" min="0" max="100" step="1"></label>
          <label>Top (%)<input data-media="y" type="number" min="0" max="100" step="1"></label>
          <label>Width (%)<input data-media="w" type="number" min="1" max="100" step="1"></label>
          <label>Height (%)<input data-media="h" type="number" min="1" max="100" step="1"></label>
        </div></details>
        <p class="media-help">Drag the clip or its edges in the timeline. Changes save automatically. Picture speed does not change the main speech or music.</p>
        <div class="media-actions"><button type="button" data-action="split">Split at playhead</button><button type="button" data-action="duplicate">Duplicate</button><button type="button" data-action="remove">Remove</button></div>
      </section>
      <details class="inspector-section media-library-section" open><summary>Project files</summary>
      <div class="media-library" aria-label="Project media"></div>
      </details>
      <details class="audio-mixer" data-editor-shortcuts="off"><summary><span>Audio mixer</span><small class="mixer-summary-level">Paused</small></summary>
        <div class="mixer-body">
        <p class="mixer-help" id="mixerFaderHelp">Shift + drag for precision. Arrow keys: 0.5 dB; Shift + arrow: 0.1 dB.</p>
        <div class="mixer-channels"></div>
        <div class="mixer-master"></div>
        <label class="ducking-choice"><input type="checkbox" data-ducking> Lower music while speech plays</label>
        <p class="mixer-level-text">Play to monitor the mix.</p>
        <p class="mixer-help mixer-normalization" role="note"></p>
        <p class="mixer-help">M: mute in preview & export. S: solo in preview only. Reset returns a fader to 0 dB.</p>
        <p class="mixer-help mixer-export-note">Meters show live sample peaks of the browser mix, before the preview limiter. The export keeps true peaks under −1 dBTP.</p>
        <datalist id="mixerZeroMark"><option value="0" label="0 dB"></option></datalist>
        </div>
      </details>`;
    const mediaStatus = root.querySelector('.media-status');
    this.storageStatus = root.querySelector('.media-storage');
    const mixerStatus = options.audioPanel?.querySelector('.mixer-save-status');
    // Both tool panels show the same save/error state; controls remain single.
    this.status = mixerStatus ? {get textContent(){return mediaStatus.textContent;},set textContent(value){mediaStatus.textContent=value;mixerStatus.textContent=value;}} : mediaStatus;
    this.channelMeters = new Map();
    for (const [role, name] of [['source','Original'],['music','Music'],['voice','Voiceover'],['effects','Effects'],['master','Master']]) {
      const row = document.createElement('div'); row.className = 'mixer-channel'; row.dataset.channel = role;
      const label = document.createElement('div'); label.className = 'mixer-fader';
      const heading = document.createElement('span'); heading.className = 'mixer-channel-heading';
      const title = document.createElement('span'); title.textContent = name; title.dataset.channelName = role;
      const range = document.createElement('input'); range.type = 'range'; range.min = '-60'; range.max = '12'; range.step = '0.1'; range.dataset.mix = `${role}_db`; range.setAttribute('aria-label', `${name} volume`);
      range.dataset.mixOrientation = role === 'master' ? 'horizontal' : 'vertical';
      range.setAttribute('aria-orientation', range.dataset.mixOrientation);
      range.setAttribute('aria-describedby', 'mixerFaderHelp');
      range.setAttribute('list', 'mixerZeroMark'); range.title = 'Drag to adjust; hold Shift for precision. Double-click to reset to 0 dB.';
      // A typed value (0.1 dB), the same value the fader and the export use.
      const level = document.createElement('span'); level.className = 'mixer-db';
      const typed = document.createElement('input'); typed.type = 'number'; typed.min = '-60'; typed.max = '12'; typed.step = '0.1'; typed.dataset.mixNumber = `${role}_db`;
      typed.setAttribute('aria-label', `${name} level in dB`); typed.inputMode = 'decimal';
      const unit = document.createElement('span'); unit.textContent = 'dB'; unit.setAttribute('aria-hidden', 'true');
      const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'mixer-reset'; reset.textContent = '0 dB'; reset.dataset.mixReset = `${role}_db`;
      reset.title = 'Reset to 0 dB'; reset.setAttribute('aria-label', `Reset ${name} to 0 dB`);
      level.append(typed,unit);
      const lane = document.createElement('div'); lane.className = 'mixer-fader-lane';
      const scale = document.createElement('div'); scale.className = 'mixer-fader-scale'; scale.setAttribute('aria-hidden', 'true');
      for (const db of [12, 0, -12, -24, -36, -48, -60]) {
        const mark = document.createElement('span'); mark.dataset.db = String(db); mark.textContent = db > 0 ? `+${db}` : String(db);
        mark.style.setProperty('--mark-from-top', `${(12 - db) / 72 * 100}%`);
        mark.style.setProperty('--mark-from-left', `${(db + 60) / 72 * 100}%`);
        scale.append(mark);
      }
      const control = document.createElement('div'); control.className = 'mixer-fader-control';
      const rail = document.createElement('span'); rail.className = 'mixer-fader-rail'; rail.setAttribute('aria-hidden', 'true');
      const travel = document.createElement('span'); travel.className = 'mixer-fader-travel'; travel.setAttribute('aria-hidden', 'true');
      const cap = document.createElement('span'); cap.className = 'mixer-fader-cap';
      const grip = document.createElement('span'); grip.className = 'mixer-fader-grip'; cap.append(grip); travel.append(cap);
      control.append(rail,travel,range); lane.append(scale,control);
      range.addEventListener('pointerdown', event => this.startFaderDrag(event, range));
      range.addEventListener('pointermove', event => this.moveFaderDrag(event));
      range.addEventListener('pointerup', event => this.endFaderDrag(event));
      range.addEventListener('pointercancel', event => this.endFaderDrag(event));
      range.addEventListener('lostpointercapture', event => this.endFaderDrag(event));
      range.addEventListener('keydown', event => this.faderKeydown(event, range));
      heading.append(title,level); label.append(heading,lane); row.append(label);
      const signal = document.createElement('div'); signal.className = 'mixer-signal';
      const meter = document.createElement('meter'); meter.className = role === 'master' ? 'mixer-meter mixer-channel-meter' : 'mixer-channel-meter';
      meter.min = 0; meter.max = 1; meter.high = .95; meter.optimum = .65; meter.value = 0;
      meter.setAttribute('aria-label', `${name} live sample peak`);
      const peak = document.createElement('output'); peak.className = 'mixer-signal-value'; peak.textContent = '-inf dBFS';
      signal.append(meter,peak); row.append(signal);
      const actions = document.createElement('div'); actions.className = 'mixer-channel-actions'; row.append(actions);
      if (role !== 'master') {
        const mute = document.createElement('button'); mute.type = 'button'; mute.textContent = 'M'; mute.title = 'Mute in preview and export'; mute.dataset.mute = role; mute.setAttribute('aria-label', `Mute ${name} in preview and export`); actions.append(mute);
        const solo = document.createElement('button'); solo.type = 'button'; solo.textContent = 'S'; solo.title = 'Solo in preview only'; solo.dataset.solo = role; solo.setAttribute('aria-label', `Solo ${name} in preview only`); actions.append(solo);
      }
      actions.append(reset);
      this.channelMeters.set(role,{row,meter,level:peak});
      root.querySelector(role === 'master' ? '.mixer-master' : '.mixer-channels').append(row);
    }
    root.querySelector('input[type=file]').addEventListener('change', event => { const file = event.target.files[0]; event.target.value = ''; if (file) this.upload(file); });
    this.audioRoot = root.querySelector('.audio-mixer');
    if (options.audioPanel) options.audioPanel.append(this.audioRoot);
    const onInput = event => { if (event.target.matches('input[type=range]')) this.change(event.target); };
    const onDoubleClick = event => {
      const fader = event.target.closest?.('[data-mix]');
      if (fader && !this.options.busy()) this.queueMixer({[fader.dataset.mix]: 0});
    };
    const onChange = event => { if (!event.target.matches('input[type=range],input[type=file]')) this.change(event.target); };
    const onClick = event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-import')) root.querySelector('input[type=file]').click();
      if (button.dataset.retry) this.retry(button.dataset.retry);
      if (button.dataset.asset) this.add(button.dataset.asset);
      if (button.dataset.append) this.append(button.dataset.append);
      if (button.dataset.reviewShot) void this.reviewShot(button.dataset.reviewShot).catch(error=>{this.status.textContent=error.message;});
      if (button.dataset.select) this.select(button.dataset.select);
      if (button.dataset.mute) { const key = `${button.dataset.mute}_muted`; this.queueMixer({[key]: !this.mixer()[key]}); }
      if (button.dataset.mixReset && !this.options.busy()) this.queueMixer({[button.dataset.mixReset]: 0});
      if (button.dataset.solo) this.toggleSolo(button.dataset.solo);
      if (button.dataset.action) this.action(button.dataset.action);
    };
    this.library = root.querySelector('.media-library');
    this.sourceLibrary = options.libraryRoot?.querySelector('.source-library');
    if (options.libraryRoot) {
      for (const selector of ['.media-import','.media-status','.media-storage','.media-library-section']) options.libraryRoot.append(root.querySelector(selector));
    }
    for (const eventRoot of [root, ...(options.audioPanel ? [this.audioRoot] : []), ...(options.libraryRoot ? [options.libraryRoot] : [])]) {
      eventRoot.addEventListener('input',onInput);
      eventRoot.addEventListener('change',onChange);
      eventRoot.addEventListener('click',onClick);
      eventRoot.addEventListener('dblclick',onDoubleClick);
    }
  }
  setFaderVisual(input, db) {
    const control = input.closest?.('.mixer-fader-control');
    const progress = (faderGain(db) + 60) / 72;
    control?.style.setProperty('--fader-from-top', `${(1 - progress) * 100}%`);
    control?.style.setProperty('--fader-from-left', `${progress * 100}%`);
    control?.classList.toggle('at-unity', Math.abs(db) < .05);
  }
  setFaderGain(input, value) {
    const gain = faderGain(value);
    input.value = String(gain);
    this.setFaderVisual(input, gain);
    if (gain !== faderGain(this.mixer()[input.dataset.mix])) this.queueMixer({[input.dataset.mix]: gain});
  }
  startFaderDrag(event, input) {
    if (event.button != null && event.button !== 0) return;
    event.preventDefault();
    if (this.options.busy() || input.disabled) return;
    this.endFaderDrag();
    const horizontal = input.dataset.mixOrientation === 'horizontal', rect = input.getBoundingClientRect();
    const coordinate = horizontal ? event.clientX : event.clientY;
    const travel = Math.max(1, (horizontal ? rect.width : rect.height) - 22);
    const original = faderGain(this.mixer()[input.dataset.mix]);
    const progress = (original + 60) / 72;
    const center = (horizontal ? rect.left : rect.top) + 11 + (horizontal ? progress : 1 - progress) * travel;
    input.focus({preventScroll:true});
    // Grabbing the cap preserves the grab point. A rail click seeks the fader;
    // holding Shift always starts a relative, ten-times-finer adjustment.
    const value = event.shiftKey || Math.abs(coordinate - center) <= 14 ? original
      : faderGain(-60 + (horizontal ? coordinate - rect.left - 11 : rect.bottom - coordinate - 11) / travel * 72);
    this.faderDrag = {input, pointerId:event.pointerId, projectId:this.project()?.id, horizontal, travel,
      original, anchorValue:value, anchor:coordinate, last:coordinate, value, fine:Boolean(event.shiftKey)};
    input.closest('.mixer-fader-control').classList.add('is-dragging');
    try { input.setPointerCapture?.(event.pointerId); }
    catch { this.endFaderDrag(); return; }
    this.setFaderGain(input, value);
  }
  moveFaderDrag(event) {
    const drag = this.faderDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    if (drag.projectId !== this.project()?.id || this.options.busy()) { this.endFaderDrag(); return; }
    const coordinate = drag.horizontal ? event.clientX : event.clientY;
    if (Boolean(event.shiftKey) !== drag.fine) {
      drag.anchor = drag.last; drag.anchorValue = drag.value; drag.fine = Boolean(event.shiftKey);
    }
    drag.value = faderPointerGain(drag.anchorValue, (coordinate - drag.anchor) * (drag.horizontal ? 1 : -1), drag.travel, drag.fine);
    drag.last = coordinate;
    this.setFaderGain(drag.input, drag.value);
  }
  endFaderDrag(event) {
    const drag = this.faderDrag;
    if (!drag || (event && event.pointerId !== drag.pointerId)) return;
    this.faderDrag = null;
    drag.input.closest?.('.mixer-fader-control')?.classList.remove('is-dragging');
    try { if (drag.input.hasPointerCapture?.(drag.pointerId)) drag.input.releasePointerCapture(drag.pointerId); }
    catch { /* The browser may already have revoked capture on focus/navigation. */ }
  }
  faderKeydown(event, input) {
    if (event.key === 'Escape' && this.faderDrag?.input === input) {
      event.preventDefault();
      const {original,projectId} = this.faderDrag;
      this.endFaderDrag();
      if (projectId === this.project()?.id && !this.options.busy() && !input.disabled) this.setFaderGain(input, original);
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const directions = {ArrowUp:1, ArrowRight:1, ArrowDown:-1, ArrowLeft:-1, PageUp:1, PageDown:-1};
    if (!(event.key in directions) && !['Home','End'].includes(event.key)) return;
    event.preventDefault();
    if (this.options.busy() || input.disabled) return;
    const value = faderGain(this.mixer()[input.dataset.mix]);
    this.setFaderGain(input, event.key === 'Home' ? -60 : event.key === 'End' ? 12
      : value + directions[event.key] * (event.shiftKey ? .1 : event.key.startsWith('Page') ? 6 : .5));
  }
  openMixer() { if (this.audioRoot) this.audioRoot.open = true; }
  project() { return this.options.project(); }
  videoAt(time = null) { return libraryVideoAt(this.project(), time); }
  clips() { return (this.project()?.manual?.media_clips || []).map(clip => ({...clip,...this.overrides.get(clip.id)})); }
  mixer() { return {...this.project()?.manual?.audio_mixer,...this.mixerOverride}; }
  async upload(file) {
    if (this.options.busy() || this.uploading || !this.project()?.draft) return;
    const projectId = this.project().id;
    this.options.pause(); this.status.textContent = `Checking storage for ${file.name}.`;
    try {
      if (!(await this.flush())) return;
      this.uploading = true;
      this.options.busyChanged?.();
      await this.options.flushSettings(projectId);
      if (this.project()?.id !== projectId) return;
      const result = await this.options.uploadFile(file, projectId, (message, storage) => {
        if (this.project()?.id !== projectId) return;
        this.status.textContent = `${message}: ${file.name}`;
        const info = this.storageStatus || this.root.querySelector('.media-storage');
        if (info) { info.textContent = storage || ''; info.hidden = !storage; }
      });
      if (this.project()?.id === projectId) this.status.textContent = 'Preparing preview and waveform… Use Stop process to cancel.';
      await this.options.acceptUpload(result, projectId);
      if (this.project()?.id === projectId) { this.render(); this.status.textContent = result.import_stop_too_late
        ? 'Import completed before Stop reached the server. The file remains in Media.'
        : 'Ready. Add the file at the playhead.'; }
    } catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; }
    finally { this.uploading = false; this.options.busyChanged?.(); }
  }
  async add(assetId) {
    if (this.options.busy()) return;
    this.options.pause();
    try {
      if (!(await this.flush())) return;
      const result = await this.options.edit('media_add', {asset_id:assetId,start:Math.min(this.options.time(), Math.max(0,this.options.duration()-.1))});
      if (result) { this.selected = result.manual?.media_clips?.at(-1)?.id; this.render(); }
    } catch (error) { this.status.textContent = error.message; }
  }
  async append(assetId) {
    const project = this.project(), projectId = project?.id, asset = project?.assets?.[assetId];
    if (this.options.busy() || this.uploading || !projectId || !project.draft || asset?.kind !== 'video' || asset.status !== 'ready') return;
    this.options.pause();
    try {
      if (!(await this.flush()) || this.project()?.id !== projectId || this.options.busy() || this.uploading) return;
      const current = this.project(), ready = current?.assets?.[assetId];
      if (!current?.draft || ready?.kind !== 'video' || ready.status !== 'ready') return;
      const result = await this.options.edit('media_append', {asset_id:assetId});
      if (this.project()?.id !== projectId) return;
      if (!result) throw new Error('The edit is busy. Try appending the video again.');
      if (result.id !== projectId) return;
      this.selected = result.manual?.media_clips?.at(-1)?.id; this.render();
    } catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; }
  }
  async reviewShot(assetId) {
    if(this.options.busy() || this.uploading)return;
    const projectId=this.project()?.id;
    this.options.pause();
    if(!(await this.flush()) || this.project()?.id!==projectId || this.options.busy())return;
    const project=this.project(),asset=project?.assets?.[assetId];
    const at=Number(this.options.time?.()),insertReason=libraryInsertReadiness(project,at);
    libraryShotRange(asset,0,Number(asset?.duration));
    this.shotReview?.close();
    const revision=project.revision,identity=JSON.stringify([asset.id,asset.url,asset.duration,asset.kind,asset.status,asset.width,asset.height]);
    const current=()=>{const p=this.project(),a=p?.assets?.[assetId];return p?.id===projectId && p.revision===revision && !!a && JSON.stringify([a.id,a.url,a.duration,a.kind,a.status,a.width,a.height])===identity;};
    const make=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};
    const dialog=make('dialog');dialog.className='library-shot-review';dialog.setAttribute('aria-labelledby','libraryShotTitle');
    const title=make('h3','Review source shot');title.id='libraryShotTitle';
    const name=make('p',asset.name);name.dir='auto';name.className='library-shot-name';
    const explanation=make('p','Mark source In / Out, then insert at the edited playhead or append after the edit. Insertion shifts supported downstream items; unsupported crossings are blocked. Original file unchanged; Undo is available.');
    const video=make('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=asset.url;
    const form=make('form');form.className='library-shot-range';
    const fields={};
    for(const [key,label,value]of [['in','Source In (seconds)',0],['out','Source Out (seconds)',asset.duration]]){
      const row=make('label',label),input=make('input');input.type='number';input.required=true;input.min='0';input.max=String(asset.duration);input.step='.001';input.value=String(value);input.dataset.shotPoint=key;row.append(input);form.append(row);fields[key]=input;
      const mark=make('button',key==='in'?'Set In at playhead':'Set Out at playhead');mark.type='button';mark.dataset.shotMark=key;
      mark.addEventListener('click',()=>{input.value=String(Math.round(video.currentTime*1000)/1000);update();});form.append(mark);
    }
    const status=make('p','Loading source preview…');status.setAttribute('role','status');status.className='library-shot-status';
    const preview=make('button','Play selected shot');preview.type='button';preview.dataset.shotPreview='true';
    const append=make('button','Append selected shot to end');append.type='submit';append.dataset.shotAppend='true';append.disabled=true;
    const insert=make('button',Number.isFinite(at)?`Insert at edit playhead (${at.toFixed(3)} s)`:'Insert at edit playhead');insert.type='submit';insert.dataset.shotInsert='true';insert.disabled=true;
    const insertHelp=make('p',insertReason||'Insert shifts downstream A/B footage, framing and non-crossing media/text. Unsupported overlaps are blocked.');insertHelp.className='library-shot-insert-help';
    const close=make('button','Keep current edit');close.type='button';close.dataset.shotKeep='true';
    let metadata=false,busy=false,stopAt=Infinity;
    const range=()=>libraryShotRange(asset,Number(fields.in.value),Number(fields.out.value));
    const update=()=>{
      try{const selected=range();status.textContent=`${(selected.source_end-selected.source_start).toFixed(3)} s selected · source ${selected.source_start.toFixed(3)}–${selected.source_end.toFixed(3)} · manual shot selection`;append.disabled=busy||!metadata||!current();insert.disabled=busy||!metadata||!current()||!!insertReason;preview.disabled=busy||!metadata;}
      catch(error){status.textContent=error.message;append.disabled=true;insert.disabled=true;preview.disabled=true;}
    };
    video.addEventListener('loadedmetadata',()=>{
      if(!Number.isFinite(video.duration) || Math.abs(video.duration-Number(asset.duration))>.25){status.textContent='Preview duration does not match source metadata. Reload the asset before appending.';return;}
      metadata=true;update();
    });
    video.addEventListener('error',()=>{metadata=false;append.disabled=true;insert.disabled=true;preview.disabled=true;status.textContent='Source preview is unavailable. Keep the edit and check this media file.';});
    video.addEventListener('timeupdate',()=>{if(video.currentTime>=stopAt)video.pause();});
    fields.in.addEventListener('input',update);fields.out.addEventListener('input',update);
    preview.addEventListener('click',async()=>{try{const selected=range();stopAt=selected.source_end;video.currentTime=selected.source_start;await video.play();}catch(error){status.textContent=error.message;}});
    form.addEventListener('submit',async event=>{
      event.preventDefault();if(busy || !metadata || this.options.busy() || !form.reportValidity())return;
      if(!current()){status.textContent='The edit or source changed. Close and review the current version; nothing was appended.';append.disabled=true;return;}
      const inserting=event.submitter===insert;
      if(inserting && insertReason){status.textContent=insertReason;return;}
      busy=true;append.disabled=true;insert.disabled=true;preview.disabled=true;video.pause();
      try{
        const result=await this.options.edit(inserting?'media_insert':'media_append',{asset_id:assetId,...range(),...(inserting?{start:at}:{})},{isCurrent:current});
        if(!result)throw new Error('The edit changed or is busy. Close and review again; nothing was appended.');
        if(this.project()?.id===projectId && result.id===projectId){this.selected=result.manual?.media_clips?.at(-1)?.id;this.render();dialog.close();}
      }catch(error){status.textContent=error.message;}
      finally{busy=false;append.disabled=!current();insert.disabled=!current()||!!insertReason;preview.disabled=!metadata;}
    });
    close.addEventListener('click',()=>{if(!busy)dialog.close();});
    dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
    dialog.addEventListener('close',()=>{video.pause();video.removeAttribute('src');video.load();dialog.remove();if(this.shotReview===dialog)this.shotReview=null;});
    const actions=make('div');actions.className='library-shot-actions';actions.append(preview,close,append,insert);form.append(actions,insertHelp);
    dialog.append(title,name,explanation,video,form,status);document.body.append(dialog);this.shotReview=dialog;dialog.showModal();
  }
  select(id) { this.selected = id; this.render(); }
  render() {
    const project = this.project();
    if (this.projectId !== project?.id && this.storageStatus) { this.storageStatus.textContent = ''; this.storageStatus.hidden = true; }
    if (this.projectId !== project?.id) { this.shotReview?.close(); this.endFaderDrag(); this.pause(); this.clearPlayers(); this.pending.clear(); this.overrides.clear(); this.saving=null; this.mixerOverride = null; this.selected = null; this.solo = null; clearTimeout(this.timer); this.projectId = project?.id; }
    const library = this.library; library.replaceChildren();
    if (this.sourceLibrary) {
      this.sourceLibrary.replaceChildren();
      for (const [slot, source] of Object.entries(project?.sources || {})) {
        if (!source) continue;
        const card = document.createElement('button'); card.type = 'button'; card.className = 'source-library-card'; card.dataset.kind = 'video';
        const thumbs = source.thumbnail_urls || [], thumb = libraryThumb(thumbs[Math.floor(thumbs.length / 3)], 'video');
        const badge = document.createElement('b'); badge.textContent = slot;
        const copy = document.createElement('span'); copy.textContent = source.name || `Source ${slot}`;
        const detail = document.createElement('small'); detail.dataset.kind = 'video'; detail.textContent = `${slot} · ${libraryClock(source.duration)}`;
        card.append(thumb,badge,copy,detail); card.addEventListener('click', () => this.options.reviewSource?.(slot)); this.sourceLibrary.append(card);
      }
    }
    for (const asset of Object.values(project?.assets || {})) {
      const card = document.createElement('div'); card.className = 'media-asset'; card.dataset.kind = asset.kind;
      card.append(libraryThumb(asset.thumbnail_url, asset.kind));
      const title = document.createElement('span'); title.textContent = `${asset.name} · ${asset.kind}`; title.title = asset.name; card.append(title);
      const meta = document.createElement('small'); meta.className = 'media-asset-meta'; meta.dataset.kind = asset.kind; meta.textContent = asset.kind === 'image' ? 'Image' : libraryClock(asset.duration); card.append(meta);
      const button = document.createElement('button'); button.type = 'button'; button.dataset.asset = asset.id;
      button.textContent = asset.status === 'ready' ? '+ Add' : asset.status || 'Preparing'; button.disabled = asset.status !== 'ready'; card.append(button); library.append(card);
      if (asset.kind === 'video') {
        const review=document.createElement('button');review.type='button';review.dataset.reviewShot=asset.id;review.textContent='Review shot / In–Out';review.disabled=asset.status!=='ready'||!project?.draft||this.options.busy()||this.uploading;card.append(review);
        const append = document.createElement('button'); append.type = 'button'; append.dataset.append = asset.id;
        append.textContent = 'Append video'; append.title = 'Add this video and its sound at the end of the edit';
        append.disabled = asset.status !== 'ready' || !project?.draft || this.options.busy() || this.uploading; card.append(append);
      }
      if (['failed','cancelled'].includes(asset.status)) { delete button.dataset.asset; button.dataset.retry=asset.id;button.textContent='Retry';button.disabled=false; }
      if (asset.stabilized && asset.status === 'ready' && asset.download_url) {
        const download = document.createElement('a'); download.className = 'media-asset-download'; download.href = asset.download_url;
        download.download = asset.name || 'stabilized.mp4'; download.textContent = 'Download copy'; card.append(download);
      }
    }
    if (!library.children.length) { const note = document.createElement('p'); note.className = 'media-help media-empty'; note.textContent = 'Add music, voiceover, images or more video with Import. Files stay on this computer.'; library.append(note); }
    const clip = this.clips().find(item => item.id === this.selected), asset = project?.assets?.[clip?.asset_id];
    this.root.querySelector('.media-inspector').hidden = !clip;
    this.root.querySelector('.media-selection-empty').hidden = Boolean(clip);
    if (clip && asset) {
      this.root.querySelector('.media-selected-name').textContent = asset.name;
      for (const input of this.root.querySelectorAll('[data-media]')) {
        if (document.activeElement === input) continue;
        const key = input.dataset.media;
        if (input.type === 'checkbox') input.checked = Boolean(clip[key]);
        else input.value = ['x','y','w','h'].includes(key) ? Math.round(Number(clip[key] ?? (['w','h'].includes(key) ? 1 : 0))*100) : clip[key] ?? '';
      }
      this.root.querySelector('[data-value=volume_db]').textContent = `${clip.volume_db || 0} dB`;
      for (const node of this.root.querySelectorAll('[data-kind]')) node.hidden = !({timed:asset.kind !== 'image',visual:asset.kind !== 'audio',sound:asset.kind !== 'image',video:asset.kind === 'video',image:asset.kind === 'image'}[node.dataset.kind]);
      this.root.querySelector('.media-placement').hidden = asset.kind === 'audio';
    }
    this.renderMixer();
  }
  renderMixer() {
    const mixer = this.mixer();
    const root = this.audioRoot || this.root;
    const sourceName = root.querySelector('[data-channel-name=source]');
    if (sourceName) sourceName.textContent = `Original ${this.options.audioSlot?.() || this.project()?.manual?.source_mixer?.audio_slot || this.project()?.settings?.audio_source || 'A'}`;
    root.querySelector('[data-ducking]').checked=Boolean(mixer.ducking);
    for (const input of root.querySelectorAll('[data-mix]')) {
      const db = Number(mixer[input.dataset.mix]) || 0;
      // Ranges have no unfinished typed draft. Reset/undo while focused must
      // update the native value as well as the bespoke cap and spoken value.
      input.value = db;
      input.setAttribute('aria-valuetext', `${db > 0 ? '+' : ''}${db.toFixed(1)} dB`);
      this.setFaderVisual(input, db);
    }
    for (const input of root.querySelectorAll('[data-mix-number]')) { if (document.activeElement !== input) input.value = (Number(mixer[input.dataset.mixNumber]) || 0).toFixed(1); }
    for (const button of root.querySelectorAll('[data-mix-reset]')) button.disabled = !Number(mixer[button.dataset.mixReset] || 0);
    this.renderNormalization(mixer, root);
    for (const button of root.querySelectorAll('[data-mute]')) button.setAttribute('aria-pressed', String(Boolean(mixer[`${button.dataset.mute}_muted`])));
    for (const button of root.querySelectorAll('[data-solo]')) button.setAttribute('aria-pressed', String(this.solo === button.dataset.solo));
    for (const [role,{row}] of this.channelMeters || []) {
      row.classList.toggle('is-muted',Boolean(mixer[`${role}_muted`]) || Boolean(this.solo && role !== 'master' && this.solo !== role));
    }
  }
  // Which channels carry sound in this edit, so the panel can say what a fader does.
  audibleChannels(mixer = this.mixer()) {
    const project = this.project(), active = new Set();
    const slot = this.options.audioSlot?.() || project?.manual?.source_mixer?.audio_slot || project?.settings?.audio_source || 'A';
    if (project?.sources?.[slot]?.has_audio && !mixer.source_muted) active.add('source');
    for (const clip of this.clips()) {
      const asset = project?.assets?.[clip.asset_id], role = clip.role || 'music';
      if (!asset || clip.muted || mixer[`${role}_muted`]) continue;
      if (asset.kind === 'audio' || (asset.has_audio && clip.audio_enabled)) active.add(role);
    }
    return active;
  }
  renderNormalization(mixer, root) {
    const normalization = mixerNormalization(this.project()), active = this.audibleChannels(mixer);
    const note = root.querySelector('.mixer-normalization');
    const names = {source:'Original', music:'Music', voice:'Voiceover', effects:'Effects'};
    const [alone] = active.size === 1 ? [...active] : [];
    if (note) note.textContent = !normalization ? 'Loudness normalization is off. Faders set exported levels directly.'
      : `Loudness normalization is on (${normalization.target} LUFS). Channel faders set the balance between tracks; Master sets the final level.`
        + (alone ? ` ${names[alone]} is the only track playing, so its fader cannot change the exported level.` : '');
    for (const [role,{row}] of this.channelMeters || []) row.dataset.normalizedAlone = String(Boolean(normalization && role === alone));
  }
  toggleSolo(role) {
    if (!['source','music','voice','effects'].includes(role)) return;
    this.solo = this.solo === role ? null : role;
    this.renderMixer(); this.options.preview();
  }
  change(input) {
    if (this.options.busy()) { this.render(); return; }
    if (input.hasAttribute('data-ducking')) { this.queueMixer({ducking:input.checked}); return; }
    if (input.dataset.mix) { this.queueMixer({[input.dataset.mix]:Number(input.value)}); return; }
    if (input.dataset.mixNumber) {
      const value = Number(input.value);
      if (input.value === '' || !Number.isFinite(value)) { this.renderMixer(); return; }
      this.queueMixer({[input.dataset.mixNumber]: Math.round(Math.max(-60, Math.min(12, value)) * 10) / 10});
      return;
    }
    const key = input.dataset.media; if (!key || !this.selected || !input.checkValidity()) return;
    let value = input.type === 'checkbox' ? input.checked : ['role','fit','motion'].includes(key) ? input.value : Number(input.value);
    if (['x','y','w','h'].includes(key)) value /= 100;
    this.queueClip(this.selected, {[key]:value});
  }
  queueClip(id, patch) {
    this.overrides.set(id, {...this.overrides.get(id),...patch});
    this.pending.set(id, {...this.pending.get(id),...patch}); this.schedule(); this.render(); this.options.preview();
  }
  previewClip(id, patch) { if (patch) this.overrides.set(id,patch); else this.overrides.delete(id); this.options.preview(); }
  queueMixer(patch) { this.mixerOverride = {...this.mixerOverride,...patch}; this.pending.set('mixer',{...this.pending.get('mixer'),...patch}); this.schedule(); this.renderMixer(); this.options.preview(); }
  schedule() { clearTimeout(this.timer); this.status.textContent = 'Saving…'; this.timer = setTimeout(()=>this.flush(),400); }
  async flush() {
    clearTimeout(this.timer); if (this.saving) return this.saving;
    const projectId = this.project()?.id;
    const task = Promise.resolve().then(async()=>{
      while (this.pending.size && this.project()?.id === projectId) {
        const [key, patch] = this.pending.entries().next().value; this.pending.delete(key);
        try {
          const result = await this.options.edit(key === 'mixer' ? 'set_audio_mixer' : 'media_update',key === 'mixer' ? patch : {clip_id:key,...patch});
          if (this.project()?.id !== projectId) return false;
          if (!result) throw new Error('The edit is busy. Try the change again.');
          if (!this.pending.has(key)) { if (key === 'mixer') this.mixerOverride = null; else this.overrides.delete(key); }
        } catch(error) {
          if (this.project()?.id !== projectId) return false;
          this.pending.clear(); this.overrides.clear(); this.mixerOverride = null;
          if (this.project()?.id === projectId) { this.status.textContent = `Not saved: ${error.message} Previous settings restored.`; this.render(); this.options.preview(); }
          return false;
        }
      }
      if (this.project()?.id === projectId) {
        // A brief confirmation; a permanent "Saved" line reads as leftover text.
        this.status.textContent = 'Saved'; this.render(); this.options.preview();
        clearTimeout(this.savedTimer);
        this.savedTimer = setTimeout(() => { if (this.status.textContent === 'Saved') this.status.textContent = ''; }, 2000);
      }
      return true;
    }).finally(()=>{if(this.saving===task)this.saving = null;});
    this.saving=task;
    return task;
  }
  async retry(assetId) {
    if(this.options.busy() || this.uploading)return;
    const projectId=this.project().id;this.uploading=true;this.options.busyChanged?.();
    try {const result=await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/prepare`,{method:'POST',body:'{}'});await this.options.acceptUpload(result,projectId);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;}finally{this.uploading=false;this.render();this.options.busyChanged?.();}
  }
  async action(action) {
    if (!this.selected || this.options.busy() || !(await this.flush())) return;
    this.options.pause();
    try { await this.options.edit(`media_${action}`, {clip_id:this.selected,...(action === 'split' ? {time:this.options.time()} : {})}); this.render(); }
    catch(error) { this.status.textContent = error.message; }
  }
  async resumeAudio() {
    try {
      if (!this.context) {
        const Audio = window.AudioContext || window.webkitAudioContext; if (!Audio) return;
        this.context = new Audio(); this.master = this.context.createGain(); this.limiter = this.context.createDynamicsCompressor();
        this.limiter.threshold.value = 20*Math.log10(.98); this.limiter.knee.value = 0; this.limiter.ratio.value = 20;
        this.limiter.attack.value = .005; this.limiter.release.value = .05;
        this.analyser = this.context.createAnalyser(); this.analyser.fftSize = 2048;
        // Meter the actual summed signal before limiting, so clipping/headroom
        // remains visible instead of being hidden by the preview compressor.
        this.master.connect(this.analyser).connect(this.limiter).connect(this.context.destination);
        // Channels -> mix -> loudness normalization (as in export) -> Master.
        this.mixInput = this.context.createGain();
        this.mixInput.channelCount = 2; this.mixInput.channelCountMode = 'explicit'; this.mixInput.channelInterpretation = 'speakers';
        this.normalizer = this.context.createGain();
        this.mixInput.connect(this.normalizer).connect(this.master);
        // ITU-R BS.1770 K-weighting (approximated with Web Audio biquads), per channel.
        const shelf = this.context.createBiquadFilter(); shelf.type = 'highshelf'; shelf.frequency.value = 1681.97; shelf.gain.value = 4;
        const highpass = this.context.createBiquadFilter(); highpass.type = 'highpass'; highpass.frequency.value = 38.13; highpass.Q.value = 20 * Math.log10(.5);
        const split = this.context.createChannelSplitter(2);
        this.loudnessAnalysers = [0, 1].map(channel => { const analyser = this.context.createAnalyser(); analyser.fftSize = 2048; split.connect(analyser, channel); return analyser; });
        this.mixInput.connect(shelf).connect(highpass).connect(split);
      }
      if (this.context.state !== 'running') await this.context.resume();
    } catch { /* Browsers without Web Audio still support attenuation via volume. */ }
  }
  player(key, kind, url, role = 'music') {
    let item = this.players.get(key);
    if (item && (item.url !== url || item.element.tagName.toLowerCase() !== kind)) { this.releasePlayer(key,item); item = null; }
    if (!item) item = this.createPlayer(key,kind,url);
    item.role = role;
    if (kind === 'audio' && this.context && !item.node && !item.basicAudio) {
      // A media element can only acquire one Web Audio source node in its
      // lifetime, even after disconnect(). Never retry a rejected element.
      for (let attempt = 0; attempt < 2; attempt++) {
        try { this.connectAudio(item); break; }
        catch (error) {
          const time = item.element.currentTime;
          this.releasePlayer(key,item);
          item = this.createPlayer(key,kind,url);
          try { item.element.currentTime = time; } catch { /* syncPlayer restores the edit position. */ }
          if (attempt === 1) {
            item.basicAudio = true;
            this.audioFallback = true;
            this.status.textContent = 'Basic audio preview: the audio mixer connection failed. Playback and volume still work; preview boosts, metering and ducking are limited. Reload to retry. Export settings are unchanged.';
            console.warn('CUTROOM audio preview is using basic playback:', error?.name || 'AudioError');
          }
        }
      }
    }
    if (item.analyser && item.busRole !== role) this.routeAudio(item,role);
    return item;
  }
  createPlayer(key,kind,url) {
    const element = document.createElement(kind); element.src = url; element.preload = 'metadata'; element.playsInline = true;
    element.className = kind === 'audio' ? 'media-audio-player' : 'media-overlay-content';
    // After repeated graph failure, keep new audio in basic mode until reload;
    // do not repeat the failed setup at every clip boundary or project switch.
    const item = {element,url,gain:null,node:null,token:0,basicAudio:kind === 'audio' && Boolean(this.audioFallback)};
    if (kind !== 'audio') { item.frame = document.createElement('div'); item.frame.className = 'media-overlay'; item.frame.append(element); this.stage.append(item.frame); }
    else this.root.append(element);
    this.players.set(key,item);
    return item;
  }
  connectAudio(item) {
    item.gain = this.context.createGain();
    item.analyser = this.context.createAnalyser(); item.analyser.fftSize = 256;
    item.node = this.context.createMediaElementSource(item.element);
    item.node.connect(item.gain); item.gain.connect(item.analyser); this.routeAudio(item,item.role || 'music');
    // Before the first user gesture, volume may have provided basic attenuation.
    // Once connected, gain nodes own it; keeping both would attenuate twice.
    item.element.volume = 1;
  }
  routeAudio(item,role) {
    this.audioBuses ||= new Map();
    let bus = this.audioBuses.get(role);
    if (!bus) {
      const gain = this.context.createGain(), analyser = this.context.createAnalyser(); analyser.fftSize = 2048;
      gain.connect(analyser); analyser.connect(this.mixInput || this.master);
      bus = {gain,analyser}; this.audioBuses.set(role,bus);
    }
    item.analyser.disconnect(); item.analyser.connect(bus.gain); item.busRole = role;
  }
  syncPlayer(item, time, speed, playing, gain = 0) {
    const element = item.element; element.playbackRate = speed; element.preservesPitch = true;
    if (item.gain) item.gain.gain.value = gain; else element.volume = Math.max(0,Math.min(1,gain*10**(Number(this.mixer().master_db||0)/20)));
    if (Math.abs(element.currentTime-time) > (playing ? .12 : 1e-6)) { try { element.currentTime = Math.max(0,time); this.meterResetUntil = performance.now()+120; } catch {} }
    item.wanted = playing;
    if (!playing) { item.token++; element.pause(); return; }
    if (element.paused && !item.pending) {
      const token = ++item.token; item.pending = true;
      Promise.resolve(element.play()).then(()=>{ if (token !== item.token || !item.wanted) element.pause(); }).catch(()=>{}).finally(()=>{item.pending=false;});
    }
  }
  sync(time, playing, source = {}) {
    const project = this.project(); if (!project || source.sourceMode) { this.pause(); return; }
    const mixer = this.mixer(), active = new Set(), clips = this.clips();
    let speechRms=0;
    for(const item of this.players.values()) if(item.analyser && ['source','voice'].includes(item.role) && item.wanted) {
      const samples=new Float32Array(256);item.analyser.getFloatTimeDomainData(samples);speechRms+=Math.sqrt(samples.reduce((sum,v)=>sum+v*v,0)/samples.length);
    }
    const desiredDuck=mixer.ducking && speechRms>.025 ? (speechRms/.025)**(1/8-1) : 1;
    const now=performance.now(),elapsed=Math.max(0,Math.min(.2,(now-(this.duckTime||now))/1000));this.duckTime=now;
    this.duckGain=(this.duckGain??1)+(desiredDuck-(this.duckGain??1))*(1-Math.exp(-elapsed/(desiredDuck < (this.duckGain??1) ? .02 : .35)));
    if (this.master) this.master.gain.value = 10 ** (Number(mixer.master_db || 0)/20);
    this.updateNormalizer(playing, mixer);
    const soloGain = role => !this.solo || this.solo === role ? 1 : 0;
    for (const [index,clip] of clips.entries()) {
      const asset = project.assets?.[clip.asset_id]; if (!asset?.url || asset.status !== 'ready' || time < clip.start || time >= clip.end) continue;
      const local = time-clip.start, speed = Number(clip.speed)||1;
      if (asset.kind !== 'audio') {
        const key = `v:${clip.id}`, item = this.player(key,asset.kind === 'image' ? 'img' : 'video',asset.url); active.add(key);
        item.frame.hidden = false; Object.assign(item.frame.style,{left:`${clip.x*100}%`,top:`${clip.y*100}%`,width:`${clip.w*100}%`,height:`${clip.h*100}%`,zIndex:String(3+index)});
        item.frame.style.background=clip.fit==='contain' ? '#000':'transparent';
        Object.assign(item.element.style,{objectFit:clip.fit === 'contain' ? 'contain':'cover',transform:visualMotion(clip,time)});
        if (asset.kind === 'video') { item.element.muted = true; const target = Number(clip.video_source_start ?? clip.source_start ?? 0)+local*speed; this.syncPlayer(item,Math.min(target,Math.max(0,asset.duration-.04)),speed,playing && target < asset.duration,0); }
        if (asset.kind === 'video' && this.options.chromaPreview) {
          const settings=project.manual?.chroma_key?.[clip.asset_id];
          if(settings?.enabled || item.chroma) {
            item.chroma ||= this.options.chromaPreview(item.element);
            item.chroma.update(settings,project.assets?.[settings?.background_asset_id]?.url);
          }
          if(settings?.enabled && settings.background_mode==='transparent')item.frame.style.background='transparent';
        }
      }
      if (asset.kind === 'audio' || (asset.has_audio && clip.audio_enabled)) {
        const key=`a:${clip.id}`, item=this.player(key,'audio',asset.url,clip.role || 'music'); active.add(key);
        const rate = asset.kind === 'video' ? 1 : speed, target=Number(clip.source_start||0)+local*rate;
        item.role=clip.role||'music';
        this.syncPlayer(item,target,rate,playing && target < asset.duration,mediaGain(clip,mixer,time)*soloGain(item.role)*(item.role==='music' ? this.duckGain:1));
      }
    }
    if (source.url && source.point && source.hasAudio) {
      const key='source', item=this.player(key,'audio',source.url,'source'); active.add(key);
      item.role='source';
      this.syncPlayer(item,source.point.sourceTime,1,playing,(mixer.source_muted ? 0 : 10**(Number(mixer.source_db||0)/20))*soloGain('source'));
    }
    for (const [key,item] of this.players) if (!active.has(key)) this.releasePlayer(key,item);
    this.updateMeters(playing);
  }
  meanSquare(analyser) {
    if (!analyser?.getFloatTimeDomainData) return 0;
    this.signalBuffers ||= new WeakMap();
    let samples = this.signalBuffers.get(analyser);
    if (samples?.length !== analyser.fftSize) { samples = new Float32Array(analyser.fftSize); this.signalBuffers.set(analyser,samples); }
    analyser.getFloatTimeDomainData(samples);
    return samples.reduce((sum,value)=>sum+value*value,0) / samples.length;
  }
  updateNormalizer(playing, mixer) {
    if (!this.normalizer) return;
    const normalization = mixerNormalization(this.project()), now = performance.now();
    const elapsed = Math.max(0, Math.min(.5, (now - (this.normalizerTime ?? now)) / 1000)); this.normalizerTime = now;
    if (!normalization || this.audioFallback) {
      this.normalizerDb = 0; this.loudnessWindow = []; this.normalizer.gain.value = 1; return;
    }
    this.loudnessWindow ||= [];
    if (playing && now >= (this.meterResetUntil || 0)) {
      this.loudnessWindow.push([now, this.meanSquare(this.loudnessAnalysers?.[0]) + this.meanSquare(this.loudnessAnalysers?.[1])]);
    }
    while (this.loudnessWindow.length && now - this.loudnessWindow[0][0] > PREVIEW_LOUDNESS_WINDOW_MS) this.loudnessWindow.shift();
    const covered = this.loudnessWindow.length ? now - this.loudnessWindow[0][0] : 0;
    const energy = this.loudnessWindow.reduce((sum,[,value])=>sum+value,0) / Math.max(1,this.loudnessWindow.length);
    let measured = energy > 0 ? -0.691 + 10 * Math.log10(energy) : -Infinity;
    // Before a second of playback is measured, start from the analyzed level of
    // the recording so the first words are not played at the wrong level.
    const summary = this.project()?.analysis?.audio?.summary;
    if (covered < 1000 && Number.isFinite(Number(summary?.integrated_rms_dbfs)) && !mixer.source_muted) {
      measured = Number(summary.integrated_rms_dbfs) + Number(mixer.source_db || 0) + 2.3;
    }
    if (this.normalizerDb == null) this.normalizerDb = Number.isFinite(measured) && measured >= -70 ? Math.max(-30, Math.min(30, normalization.target - measured)) : 0;
    this.normalizerDb = previewNormalizationGain(this.normalizerDb, measured, normalization.target, playing ? elapsed : 0);
    this.normalizer.gain.value = 10 ** (this.normalizerDb / 20);
  }
  signalPeak(analyser) {
    if (!analyser?.getFloatTimeDomainData) return 0;
    this.signalBuffers ||= new WeakMap();
    let samples = this.signalBuffers.get(analyser);
    const size = analyser.fftSize || 256;
    if (samples?.length !== size) { samples = new Float32Array(size); this.signalBuffers.set(analyser,samples); }
    analyser.getFloatTimeDomainData(samples);
    return samples.reduce((peak,value)=>Math.max(peak,Math.abs(value)),0);
  }
  updateMeters(playing) {
    const ready = Boolean(playing && !this.audioFallback && performance.now() >= (this.meterResetUntil || 0));
    const masterPeak = ready ? this.signalPeak(this.analyser) : 0;
    const value = peak => peak > 0 ? Math.max(0,Math.min(1,(20*Math.log10(peak)+60)/60)) : 0;
    const text = peak => peak > 0 ? `${(20*Math.log10(peak)).toFixed(1)} dBFS` : '-inf dBFS';
    for (const [role,{row,meter,level}] of this.channelMeters || []) {
      const hasPlayer = [...this.players.values()].some(item=>item.role === role && item.wanted && !item.element.paused && Number(item.gain?.gain?.value ?? item.element.volume) > 0);
      const peak = role === 'master' ? masterPeak : ready && hasPlayer ? this.signalPeak(this.audioBuses?.get(role)?.analyser) : 0;
      meter.value = value(peak); level.textContent = text(peak);
      row.classList.toggle('is-clipping',peak >= 1);
      meter.setAttribute('aria-valuetext',text(peak));
    }
    const root = this.audioRoot || this.root;
    const meter = root?.querySelector('.mixer-meter'); if (meter) meter.value = value(masterPeak);
    const state = !playing ? 'Paused · play to monitor' : this.audioFallback ? 'Basic preview · live meters unavailable' : !ready ? 'Seeking · waiting for live audio' : masterPeak >= 1 ? 'Clipping · lower a fader' : this.solo ? `Solo: ${this.solo === 'source' ? 'Original' : this.solo} · preview only` : 'Live browser mix';
    const status = root?.querySelector('.mixer-level-text'); if (status) status.textContent = state;
    const summary = root?.querySelector('.mixer-summary-level'); if (summary) summary.textContent = playing && ready ? text(masterPeak) : playing ? 'Preview' : 'Paused';
  }
  pause() {
    for(const item of this.players.values()){ item.wanted=false; item.token++; item.element.pause?.(); if(item.frame)item.frame.hidden=true; }
    this.meterResetUntil = 0; this.updateMeters(false);
  }
  releasePlayer(key,item) {
    item.chroma?.dispose();
    item.wanted=false; item.token++; item.element.pause?.();
    item.node?.disconnect(); item.gain?.disconnect(); item.analyser?.disconnect();
    item.element.removeAttribute?.('src'); item.element.load?.();
    (item.frame||item.element).remove?.(); this.players.delete(key);
  }
  clearPlayers() { for(const [key,item] of this.players)this.releasePlayer(key,item); }
}
