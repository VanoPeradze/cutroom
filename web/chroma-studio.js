export const CHROMA_DEFAULTS = Object.freeze({enabled:false, color:'#00FF00', tolerance:.12, edge_softness:.08, background_color:'#000000', background_asset_id:null, background_mode:'replace'});

export function chromaSettings(value = {}) {
  value = value && typeof value === 'object' ? value : {};
  const color = key => /^#[0-9a-f]{6}$/i.test(String(value[key] || '')) ? value[key].toUpperCase() : CHROMA_DEFAULTS[key];
  const number = (key, minimum) => Number.isFinite(Number(value[key])) ? Math.max(minimum, Math.min(1, Number(value[key]))) : CHROMA_DEFAULTS[key];
  return {enabled:value.enabled === true, color:color('color'), tolerance:number('tolerance', .01), edge_softness:number('edge_softness', 0), background_color:color('background_color'), background_asset_id:/^asset_[0-9a-f]{32}$/.test(value.background_asset_id) ? value.background_asset_id : null, background_mode:value.background_mode === 'transparent' ? 'transparent' : 'replace'};
}

const copies = {
  chromaTitle:'Green screen / Chroma key', chromaHelp:'Choose the foreground video, choose what appears behind it, then remove the color and apply.',
  chromaFineTune:'Fine-tune edges', chromaHow:'How layers work',
  chromaSource:'1 · Foreground video', chromaEnable:'Enable chroma key', chromaColor:'2 · Color to remove',
  chromaTolerance:'Tolerance', chromaEdge:'Edge softness', chromaBackground:'Replacement color',
  chromaReplacement:'Replacement background', chromaSolid:'Solid color', chromaImport:'Add an image in Media', chromaImageMissing:'Unavailable image — choose another or reset',
  chromaToleranceHelp:'Higher values remove a wider range of colors.', chromaEdgeHelp:'Higher values blend the edges into the replacement color.',
  chromaOpaque:'Video underneath reveals earlier timeline layers. Color or image replaces the background inside this video. The final MP4 combines all layers.',
  chromaApply:'Apply & preview', chromaReset:'Reset this source', chromaOff:'Off', chromaOn:'On',
  chromaReady:'Applies to this source throughout the edit. Changes support Undo.',
  chromaPending:'Changes are not saved yet. Apply them to use them in export.',
  chromaSaving:'Saving chroma key.', chromaSaved:'Saved. Edited playback and export use these settings. You can Undo this change.',
  chromaFailed:'Changes were not saved. Try again.', chromaNeedsSource:'Add footage and create an edit to use chroma key.',
  chromaFrame:'Current-frame key preview', chromaRefresh:'Refresh current frame',
  chromaPlayback:'Edited playback shows the saved key. This processed frame checks exact edges; checkerboard means the video underneath will show through.',
  chromaChecking:'Checking local chroma-key support.', chromaPreviewing:'Preparing the saved-settings frame preview.',
  chromaApplyFirst:'Apply changes before refreshing the frame preview.', chromaPreviewFailed:'Could not prepare this frame. Try again.',
  chromaLocked:'This source is protected. Unlock it in Edit to change chroma key.',
  chromaAddVideo:'Add video in Media', chromaLibraryVideo:'Media video', chromaMainVideo:'Main source',
  chromaUnavailable:'This video is unavailable. Choose another video or import it in Media.',
  chromaPreparing:'Preparing video', chromaFailedVideo:'Import failed — retry in Media',
  chromaTime:'Frame time (source seconds)', chromaPlayerTime:'Uses the selected source player time.',
  chromaTargetHelp:'Each video has its own settings. Repeated timeline uses of the same video share them.',
  chromaMode:'3 · Background', chromaUnderneath:'Video underneath (Media layer)', chromaReplace:'Color or image',
  chromaGreenDefaults:'Use green-screen defaults', chromaHighTolerance:'This tolerance can remove the subject too. Start with the green-screen defaults, then increase gradually.',
  chromaLayerHelp:'For a moving background, keep it as main footage and add the green-screen video in Media, on top. Choose Video underneath here.',

};

export class ChromaStudio {
  constructor(root, options) {
    this.options = options; this.drafts = new Map(); this.selections = new Map(); this.times = new Map(); this.identities = new Map(); this.saving = false; this.capability = null; this.previewGeneration = 0;
    this.node = document.createElement('section'); this.node.className = 'chroma-tool'; this.node.id = 'chromaKeyTool';
    this.node.dataset.editorShortcuts = 'off'; this.node.setAttribute('aria-labelledby', 'chromaTitle');
    this.node.innerHTML = `
      <header class="chroma-heading"><h3 id="chromaTitle" data-chroma-copy="chromaTitle"></h3><small data-chroma-summary></small></header>
      <fieldset class="chroma-targets"><legend data-chroma-copy="chromaSource"></legend><div class="chroma-source-list" data-chroma-targets></div></fieldset>
      <select data-chroma-source hidden aria-hidden="true" tabindex="-1"></select>
      <button type="button" class="chroma-import" data-chroma-add-video data-chroma-copy="chromaAddVideo"></button>
      <p class="chroma-selected sr-only" data-chroma-selected></p>
      <div class="chroma-workspace"><div class="chroma-controls">
      <label class="chroma-enable"><input type="checkbox" data-chroma="enabled"><span data-chroma-copy="chromaEnable"></span></label>
      <div class="chroma-settings">
        <label class="chroma-color"><span data-chroma-copy="chromaColor"></span><input type="color" data-chroma="color"><output data-chroma-value="color"></output></label>
        <button type="button" data-chroma-defaults data-chroma-copy="chromaGreenDefaults"></button>
        <label class="chroma-source"><span data-chroma-copy="chromaMode"></span><select data-chroma="background_mode"><option value="transparent" data-chroma-copy="chromaUnderneath"></option><option value="replace" data-chroma-copy="chromaReplace"></option></select></label>
        <label class="chroma-source" data-chroma-replacement><span data-chroma-copy="chromaReplacement"></span><select data-chroma="background_asset_id" data-chroma-background aria-label="Replacement background"></select></label>
        <button type="button" class="chroma-import" data-chroma-import data-chroma-copy="chromaImport"></button>
        <label class="chroma-color" data-chroma-solid><span data-chroma-copy="chromaBackground"></span><input type="color" data-chroma="background_color"><output data-chroma-value="background_color"></output></label>
        <details class="chroma-fine-tune"><summary data-chroma-copy="chromaFineTune"></summary><div class="chroma-fine-tune-controls">
        <label class="chroma-range"><span data-chroma-copy="chromaTolerance"></span><input type="range" data-chroma="tolerance" min="0.01" max="1" step="0.01" aria-describedby="chromaToleranceHelp"><output data-chroma-value="tolerance"></output></label>
        <p class="media-help" id="chromaToleranceHelp" data-chroma-copy="chromaToleranceHelp"></p>
        <label class="chroma-range"><span data-chroma-copy="chromaEdge"></span><input type="range" data-chroma="edge_softness" min="0" max="1" step="0.01" aria-describedby="chromaEdgeHelp"><output data-chroma-value="edge_softness"></output></label>
        <p class="media-help" id="chromaEdgeHelp" data-chroma-copy="chromaEdgeHelp"></p>
        </div></details>
        <p class="chroma-warning" data-chroma-warning data-chroma-copy="chromaHighTolerance" role="status" hidden></p>
      </div>
      <div class="chroma-actions"><button type="button" data-chroma-apply data-chroma-copy="chromaApply"></button><button type="button" data-chroma-reset data-chroma-copy="chromaReset"></button></div>
      <p class="media-status" data-chroma-status role="status" aria-live="polite"></p>
      </div>
      <details class="chroma-preview" aria-label="Current-frame key preview">
        <summary data-chroma-copy="chromaFrame"></summary><p class="media-help" data-chroma-copy="chromaPlayback"></p>
        <label class="chroma-time"><span data-chroma-copy="chromaTime"></span><input type="number" data-chroma-time min="0" step="0.001"></label>
        <p class="media-help" data-chroma-player-time data-chroma-copy="chromaPlayerTime"></p>
        <button type="button" data-chroma-refresh data-chroma-copy="chromaRefresh"></button>
        <figure hidden><img data-chroma-frame alt="Saved chroma-key frame"><figcaption data-chroma-frame-caption></figcaption></figure>
        <p class="media-status" data-chroma-preview-status role="status" aria-live="polite"></p>
      </details></div>
      <details class="chroma-help"><summary data-chroma-copy="chromaHow"></summary><p class="media-help" data-chroma-copy="chromaLayerHelp"></p><p class="media-help" data-chroma-copy="chromaTargetHelp"></p><p class="media-help" data-chroma-copy="chromaOpaque"></p></details>`;
    root.append(this.node);
    this.source = this.node.querySelector('[data-chroma-source]'); this.status = this.node.querySelector('[data-chroma-status]');
    this.apply = this.node.querySelector('[data-chroma-apply]'); this.reset = this.node.querySelector('[data-chroma-reset]');
    this.refresh = this.node.querySelector('[data-chroma-refresh]'); this.previewStatus = this.node.querySelector('[data-chroma-preview-status]');
    this.frame = this.node.querySelector('[data-chroma-frame]');
    this.background = this.node.querySelector('[data-chroma-background]');
    this.node.querySelector('[data-chroma-defaults]').onclick = () => {
      if (!this.validSource() || this.saving || this.options.busy() || this.project()?.manual?.track_locks?.[this.source.value] || !this.capability?.available) return;
      this.drafts.set(this.source.value, {...CHROMA_DEFAULTS,enabled:true,background_mode:['A','B'].includes(this.source.value) ? 'replace' : 'transparent'});
      this.options.pause(); this.message=null; this.invalidatePreview(); this.render();
    };
    this.node.querySelector('[data-chroma-import]').onclick = () => { if (!this.saving && !this.options.busy()) this.options.openMedia?.(); };
    this.node.querySelector('[data-chroma-add-video]').onclick = () => { if (!this.saving && !this.options.busy()) this.options.openMedia?.(); };
    this.timeInput = this.node.querySelector('[data-chroma-time]');
    this.timeInput.oninput = () => {
      if (!this.validSource() || this.saving || this.options.busy() || ['A','B'].includes(this.source.value)) return;
      this.times.set(this.timeKey(), this.boundedTime(Number(this.timeInput.value)));
      this.invalidatePreview(); this.render();
    };
    this.source.onchange = () => {
      this.selections.set(this.project()?.id, this.source.value); this.message = null;
      this.invalidatePreview(); this.render();
    };
    this.node.addEventListener('input', event => {
      const key = event.target.dataset.chroma;
      if (!key || this.saving || this.options.busy()) return;
      const value = event.target.type === 'checkbox' ? event.target.checked : ['tolerance','edge_softness'].includes(key) ? Number(event.target.value) : key === 'background_asset_id' ? event.target.value || null : event.target.value;
      if (!this.validSource() || this.project()?.manual?.track_locks?.[this.source.value] === true
        || (key === 'background_mode' && value === 'transparent' && ['A','B'].includes(this.source.value))
        || (key === 'background_asset_id' && value && !this.images().some(asset => asset.id === value))
        || (!this.capability?.available && (key !== 'enabled' || value !== false))) return;
      this.options.pause();
      const settings={...this.settings(), [key]:value};
      if (key === 'enabled' && value && !['A','B'].includes(this.source.value) && !this.project()?.manual?.chroma_key?.[this.source.value]) settings.background_mode='transparent';
      this.drafts.set(this.source.value, chromaSettings(settings));
      this.message = null; this.invalidatePreview(); this.render();
    });
    this.apply.onclick = () => this.save(false); this.reset.onclick = () => this.save(true);
    this.refresh.onclick = () => this.refreshFrame();
    this.render();
    this.ready = this.checkCapability();
  }

  copy(key) { return this.options.translate?.(key, copies[key]) || copies[key]; }
  project() { return this.options.project(); }
  targetSource(slot = this.source.value) {
    if (['A','B'].includes(slot)) return this.project()?.sources?.[slot];
    const asset = this.project()?.assets?.[slot];
    return /^asset_[0-9a-f]{32}$/.test(slot) && asset?.id === slot && asset.kind === 'video' ? asset : null;
  }
  sourceIdentity(slot) {
    const source = this.targetSource(slot);
    return JSON.stringify(source ? [source.id, source.kind, source.name, source.path, source.relative_path,
      source.generation, source.status, source.width, source.height, source.duration] : null);
  }
  validSource(slot = this.source.value) {
    const source = this.targetSource(slot);
    return Boolean(source && (['A','B'].includes(slot) || source.status === 'ready')
      && ['width','height','duration'].every(key => Number.isFinite(Number(source[key])) && Number(source[key]) > 0));
  }
  targets() {
    const project = this.project(), rows = [];
    for (const id of ['A','B']) if (project?.sources?.[id]) rows.push({id, ...project.sources[id]});
    for (const [id, source] of Object.entries(project?.assets || {})) {
      if (/^asset_[0-9a-f]{32}$/.test(id) && source?.id === id && source.kind === 'video') rows.push({...source,id});
    }
    return rows;
  }
  targetLabel(slot = this.source.value) {
    const source = this.targetSource(slot), identity = ['A','B'].includes(slot) ? `${this.copy('chromaMainVideo')} ${slot}` : `${this.copy('chromaLibraryVideo')} · ${String(slot).slice(6,14)}`;
    return source ? `${source.name || slot} · ${identity}` : this.copy('chromaUnavailable');
  }
  timeKey() { return `${this.project()?.id}:${this.source.value}`; }
  boundedTime(value) { return Math.max(0, Math.min(Number.isFinite(value) ? value : 0, Math.max(0, Number(this.targetSource()?.duration || 0) - .001))); }
  renderTargets(busy, selected = this.source.value) {
    const list = this.node.querySelector('[data-chroma-targets]');
    list.innerHTML = ''; this.source.innerHTML = '';
    const targets = this.targets();
    if (selected && !targets.some(row => row.id === selected)) targets.push({id:selected, missing:true});
    for (const target of targets) {
      const ready = this.validSource(target.id), label = document.createElement('label'); label.className = 'chroma-source-card';
      label.dataset.selected = String(target.id === selected);
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'chroma-video-target';
      radio.dataset.chromaTarget = target.id; radio.value = target.id; radio.checked = target.id === selected; radio.disabled = busy || !ready;
      radio.onchange = () => { if (!radio.disabled) { this.source.value = target.id; this.source.onchange(); } };
      label.append(radio);
      const thumbnail = target.thumbnail_url || target.thumbnail_urls?.[0];
      if (typeof thumbnail === 'string' && thumbnail.startsWith('/') && !thumbnail.startsWith('//')) {
        const image = document.createElement('img'); image.className = 'chroma-source-thumb'; image.src = thumbnail; image.alt = ''; image.loading = 'lazy'; label.append(image);
      }
      const caption = document.createElement('span'); caption.className = 'chroma-source-caption';
      caption.textContent = this.targetLabel(target.id); label.append(caption);
      if (!ready) { const state = document.createElement('small'); state.textContent = this.copy(target.status === 'preparing' || target.status === 'queued' ? 'chromaPreparing' : target.status === 'failed' || target.status === 'cancelled' ? 'chromaFailedVideo' : 'chromaUnavailable'); label.append(state); }
      list.append(label);
      const option = document.createElement('option'); option.value = target.id; option.textContent = this.targetLabel(target.id); option.disabled = !ready; this.source.append(option);
    }
    this.source.value = selected;
    this.node.querySelector('[data-chroma-selected]').textContent = this.targetLabel();
  }
  images() {
    if (!this.capability?.supports?.includes('image')) return [];
    return Object.entries(this.project()?.assets || {}).filter(([id, asset]) => /^asset_[0-9a-f]{32}$/.test(id) && asset?.id === id && asset.kind === 'image' && asset.status === 'ready'
      && ['width','height'].every(key => Number.isFinite(Number(asset[key])) && Number(asset[key]) > 0 && Number(asset[key]) <= 16384)
      && Number(asset.width) * Number(asset.height) <= 64000000).map(([,asset]) => asset);
  }
  saved(slot = this.source.value) { return chromaSettings(this.project()?.manual?.chroma_key?.[slot]); }
  settings(slot = this.source.value) { return this.drafts.get(slot) || this.saved(slot); }
  dirty(slot = this.source.value) { return JSON.stringify(this.settings(slot)) !== JSON.stringify(this.saved(slot)); }

  render() {
    const project = this.project(), changedProject = this.projectId !== project?.id;
    if (changedProject) {
      if (this.projectId) this.selections.set(this.projectId, this.source.value);
      const targets = this.targets();
      const preferred = this.options.selectedTarget?.();
      const selected = this.selections.get(project?.id) || (this.validSource(preferred) && preferred)
        || targets.find(row => this.validSource(row.id) && this.saved(row.id).enabled)?.id
        || targets.find(row => this.validSource(row.id))?.id || targets[0]?.id || '';
      // Populate native select options before assigning the initial value.
      this.renderTargets(this.saving || this.options.busy(), selected);
      this.identities.clear();
    }
    const changedMedia = [...this.identities].some(([slot, identity]) => this.sourceIdentity(slot) !== identity);
    if (changedProject || this.revision !== project?.revision || changedMedia) {
      this.drafts.clear();
      if (this.saving && this.saveProjectId === project?.id) {
        for (const [slot, candidate] of this.otherDrafts || []) {
          if (candidate.saved === JSON.stringify(this.saved(slot)) && candidate.source === this.sourceIdentity(slot)) this.drafts.set(slot, candidate.settings);
        }
      }
      this.message = null; this.invalidatePreview(); this.projectId = project?.id; this.revision = project?.revision;
    }
    this.identities = new Map(this.targets().map(row => [row.id, this.sourceIdentity(row.id)]));
    const settings = this.settings(), hasSource = Boolean(project?.draft && this.validSource());
    const available = hasSource && this.capability?.available === true;
    const locked = project?.manual?.track_locks?.[this.source.value] === true;
    const busy = this.saving || this.options.busy();
    this.renderTargets(busy);
    this.node.querySelector('[data-chroma-add-video]').disabled = busy;
    const nativeTime = !['A','B'].includes(this.source.value);
    this.timeInput.disabled = busy || !hasSource || !nativeTime;
    this.timeInput.max = Math.max(0, Number(this.targetSource()?.duration || 0) - .001);
    this.timeInput.value = this.boundedTime(nativeTime ? this.times.get(this.timeKey()) || 0 : Number(this.options.sourceTime(this.source.value)) || 0);
    this.node.querySelector('[data-chroma-player-time]').hidden = nativeTime;
    this.background.innerHTML = '<option value=""></option>';
    this.background.querySelector('option').textContent = this.copy('chromaSolid');
    for (const asset of this.images()) { const option = document.createElement('option'); option.value = asset.id; option.textContent = asset.name || asset.id; this.background.append(option); }
    if (settings.background_asset_id && !this.images().some(asset => asset.id === settings.background_asset_id)) {
      const option = document.createElement('option'); option.value = settings.background_asset_id; option.textContent = this.copy('chromaImageMissing'); option.disabled = true; this.background.append(option);
    }
    const transparent = settings.background_mode === 'transparent';
    this.node.querySelector('[data-chroma="background_mode"]').querySelector('[value="transparent"]').disabled = ['A','B'].includes(this.source.value);
    this.node.querySelector('[data-chroma-replacement]').hidden = transparent;
    this.node.querySelector('[data-chroma-solid]').hidden = transparent || Boolean(settings.background_asset_id);
    this.node.querySelector('[data-chroma-import]').hidden = transparent;
    this.node.querySelector('[data-chroma-warning]').hidden = !settings.enabled || settings.tolerance < .5;
    this.node.querySelector('[data-chroma-defaults]').disabled = !available || busy || locked;
    this.node.querySelector('[data-chroma-import]').disabled = busy;
    for (const node of this.node.querySelectorAll('[data-chroma-copy]')) node.textContent = this.copy(node.dataset.chromaCopy);
    this.node.querySelector('[data-chroma-summary]').textContent = this.copy(settings.enabled ? 'chromaOn' : 'chromaOff');
    for (const input of this.node.querySelectorAll('[data-chroma]')) {
      const key = input.dataset.chroma;
      if (input.type === 'checkbox') input.checked = settings[key]; else input.value = settings[key] ?? '';
      input.disabled = !hasSource || busy || locked || (!this.capability?.available && (key !== 'enabled' || !settings.enabled));
      const output = this.node.querySelector(`[data-chroma-value="${key}"]`);
      if (output) output.textContent = ['tolerance','edge_softness'].includes(key) ? `${Math.round(settings[key] * 100)}%` : settings[key];
    }
    this.source.disabled = busy || !this.targets().length;
    this.apply.disabled = !hasSource || busy || locked || (settings.enabled && !this.capability?.available) || !this.dirty();
    this.reset.disabled = !hasSource || busy || locked || JSON.stringify(settings) === JSON.stringify(CHROMA_DEFAULTS);
    this.refresh.disabled = !available || busy || this.previewing || this.dirty();
    this.status.textContent = this.message || (hasSource && !this.capability?.available && !this.dirty() ? this.capability?.message || this.copy('chromaChecking') : this.copy(this.saving ? 'chromaSaving' : !hasSource ? (this.source.value && !this.validSource() ? 'chromaUnavailable' : 'chromaNeedsSource') : locked ? 'chromaLocked' : this.dirty() ? 'chromaPending' : 'chromaReady'));
    if (this.dirty()) this.previewStatus.textContent = this.copy('chromaApplyFirst');
  }

  async checkCapability() {
    try { this.capability = await this.options.api('/api/chroma-key/status'); }
    catch (error) { this.capability = {available:false, message:error.message || this.copy('chromaPreviewFailed')}; }
    this.render();
  }

  invalidatePreview() {
    this.previewGeneration++; this.previewAbort?.abort(); this.previewing = false;
    if (this.frameUrl) URL.revokeObjectURL(this.frameUrl); this.frameUrl = null;
    this.frame?.removeAttribute('src');
    if (this.frame) this.frame.parentElement.hidden = true;
    if (this.previewStatus) this.previewStatus.textContent = '';
  }

  async refreshFrame() {
    const project = this.project(), slot = this.source.value;
    if (!project?.draft || !this.validSource(slot) || !this.capability?.available || this.saving || this.options.busy() || this.dirty()) return;
    this.options.pause(); this.invalidatePreview();
    const time = this.boundedTime(['A','B'].includes(slot) ? Number(this.options.sourceTime(slot)) || 0 : this.times.get(this.timeKey()) || 0);
    const generation = this.previewGeneration; this.previewing = true; this.previewAbort = new AbortController();
    this.previewStatus.textContent = this.copy('chromaPreviewing'); this.render();
    try {
      const blob = await this.options.frame({projectId:project.id, slot, time, revision:project.revision}, this.previewAbort.signal);
      if (generation !== this.previewGeneration || this.project()?.id !== project.id || this.project()?.revision !== project.revision || this.source.value !== slot) return;
      this.frameUrl = URL.createObjectURL(blob); this.frame.src = this.frameUrl; this.frame.parentElement.hidden = false;
      this.node.querySelector('.chroma-preview').open = true;
      this.frame.alt = `${this.copy('chromaFrame')} · ${this.targetLabel(slot)} · ${time.toFixed(3)} s`;
      this.node.querySelector('[data-chroma-frame-caption]').textContent = `${this.targetLabel(slot)} · ${time.toFixed(3)} s · ${this.copy('chromaReady')}`;
      this.previewStatus.textContent = '';
    } catch (error) { if (generation === this.previewGeneration && error.name !== 'AbortError') this.previewStatus.textContent = error.message || this.copy('chromaPreviewFailed'); }
    finally { if (generation === this.previewGeneration) { this.previewing = false; this.render(); } }
  }

  async save(reset) {
    const project = this.project(), slot = this.source.value;
    if (!project?.draft || !this.validSource(slot) || project.manual?.track_locks?.[slot] === true || (!reset && this.settings(slot).enabled && !this.capability?.available) || this.saving || this.options.busy() || (!reset && !this.dirty())) return;
    const projectId = project.id, settings = {...this.settings(slot)};
    this.saveProjectId = projectId;
    this.otherDrafts = new Map([...this.drafts].filter(([key]) => key !== slot).map(([key, value]) => [key, {settings:{...value}, saved:JSON.stringify(this.saved(key)), source:this.sourceIdentity(key)}]));
    this.saving = true; this.message = null; this.options.pause(); this.render();
    try {
      const result = await this.options.edit(reset ? 'reset_chroma_key' : 'set_chroma_key', reset ? {slot} : {slot, ...settings}, {isCurrent:() => this.project()?.id === projectId});
      if (this.project()?.id !== projectId) return;
      if (!result) throw new Error(this.copy('chromaFailed'));
      this.drafts.delete(slot); this.revision = this.project()?.revision; this.message = this.copy('chromaSaved');
    } catch (error) { if (this.project()?.id === projectId) this.message = error.message || this.copy('chromaFailed'); }
    finally { this.saving = false; this.saveProjectId = null; this.otherDrafts = null; this.render(); }
    if (this.options.autoPreview && this.project()?.id === projectId && this.source.value === slot && !this.dirty() && this.message === this.copy('chromaSaved')) await this.refreshFrame();
  }
}
