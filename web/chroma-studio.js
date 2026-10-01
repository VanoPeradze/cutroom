export const CHROMA_DEFAULTS = Object.freeze({enabled:false, color:'#00FF00', tolerance:.12, edge_softness:.08, background_color:'#000000', background_asset_id:null});

export function chromaSettings(value = {}) {
  value = value && typeof value === 'object' ? value : {};
  const color = key => /^#[0-9a-f]{6}$/i.test(String(value[key] || '')) ? value[key].toUpperCase() : CHROMA_DEFAULTS[key];
  const number = (key, minimum) => Number.isFinite(Number(value[key])) ? Math.max(minimum, Math.min(1, Number(value[key]))) : CHROMA_DEFAULTS[key];
  return {enabled:value.enabled === true, color:color('color'), tolerance:number('tolerance', .01), edge_softness:number('edge_softness', 0), background_color:color('background_color'), background_asset_id:/^asset_[0-9a-f]{32}$/.test(value.background_asset_id) ? value.background_asset_id : null};
}

const copies = {
  chromaTitle:'Chroma key', chromaHelp:'Remove a green screen or another flat color from one source.',
  chromaSource:'Footage', chromaEnable:'Enable chroma key', chromaColor:'Color to remove',
  chromaTolerance:'Tolerance', chromaEdge:'Edge softness', chromaBackground:'Replacement color',
  chromaReplacement:'Replacement background', chromaSolid:'Solid color', chromaImport:'Add an image in Media', chromaImageMissing:'Unavailable image — choose another or reset',
  chromaToleranceHelp:'Higher values remove a wider range of colors.', chromaEdgeHelp:'Higher values blend the edges into the replacement color.',
  chromaOpaque:'The removed area uses this color or project image before Layout is applied. Images fill the source frame; edges may be cropped. MP4 has no transparency.',
  chromaApply:'Apply changes', chromaReset:'Reset this source', chromaOff:'Off', chromaOn:'On',
  chromaReady:'Applies to this source throughout the edit. Changes support Undo.',
  chromaPending:'Changes are not saved yet. Apply them to use them in export.',
  chromaSaving:'Saving chroma key.', chromaSaved:'Saved. Refresh the current-frame preview; export uses these settings. You can Undo this change.',
  chromaFailed:'Changes were not saved. Try again.', chromaNeedsSource:'Add footage and create an edit to use chroma key.',
  chromaFrame:'Current-frame key preview', chromaRefresh:'Refresh current frame',
  chromaPlayback:'The main player shows original footage. This frame and export use the saved chroma settings.',
  chromaChecking:'Checking local chroma-key support.', chromaPreviewing:'Preparing the saved-settings frame preview.',
  chromaApplyFirst:'Apply changes before refreshing the frame preview.', chromaPreviewFailed:'Could not prepare this frame. Try again.',
  chromaLocked:'This source is protected. Unlock it in Edit to change chroma key.',
};

export class ChromaStudio {
  constructor(root, options) {
    this.options = options; this.drafts = new Map(); this.saving = false; this.capability = null; this.previewGeneration = 0;
    this.node = document.createElement('details'); this.node.className = 'chroma-tool'; this.node.id = 'chromaKeyTool';
    this.node.dataset.editorShortcuts = 'off';
    this.node.innerHTML = `
      <summary><span data-chroma-copy="chromaTitle"></span><small data-chroma-summary></small></summary>
      <p class="media-help" data-chroma-copy="chromaHelp"></p>
      <label class="chroma-source"><span data-chroma-copy="chromaSource"></span><select data-chroma-source aria-label="Chroma key footage"><option value="A">A</option><option value="B">B</option></select></label>
      <label class="chroma-enable"><input type="checkbox" data-chroma="enabled"><span data-chroma-copy="chromaEnable"></span></label>
      <div class="chroma-settings">
        <label class="chroma-color"><span data-chroma-copy="chromaColor"></span><input type="color" data-chroma="color"><output data-chroma-value="color"></output></label>
        <label class="chroma-range"><span data-chroma-copy="chromaTolerance"></span><input type="range" data-chroma="tolerance" min="0.01" max="1" step="0.01" aria-describedby="chromaToleranceHelp"><output data-chroma-value="tolerance"></output></label>
        <p class="media-help" id="chromaToleranceHelp" data-chroma-copy="chromaToleranceHelp"></p>
        <label class="chroma-range"><span data-chroma-copy="chromaEdge"></span><input type="range" data-chroma="edge_softness" min="0" max="1" step="0.01" aria-describedby="chromaEdgeHelp"><output data-chroma-value="edge_softness"></output></label>
        <p class="media-help" id="chromaEdgeHelp" data-chroma-copy="chromaEdgeHelp"></p>
        <label class="chroma-source"><span data-chroma-copy="chromaReplacement"></span><select data-chroma="background_asset_id" data-chroma-background aria-label="Replacement background"></select></label>
        <button type="button" class="chroma-import" data-chroma-import data-chroma-copy="chromaImport"></button>
        <label class="chroma-color" data-chroma-solid><span data-chroma-copy="chromaBackground"></span><input type="color" data-chroma="background_color"><output data-chroma-value="background_color"></output></label>
      </div>
      <p class="media-help" data-chroma-copy="chromaOpaque"></p>
      <div class="chroma-actions"><button type="button" data-chroma-apply data-chroma-copy="chromaApply"></button><button type="button" data-chroma-reset data-chroma-copy="chromaReset"></button></div>
      <p class="media-status" data-chroma-status role="status" aria-live="polite"></p>
      <section class="chroma-preview" aria-label="Current-frame key preview">
        <h4 data-chroma-copy="chromaFrame"></h4><p class="media-help" data-chroma-copy="chromaPlayback"></p>
        <button type="button" data-chroma-refresh data-chroma-copy="chromaRefresh"></button>
        <figure hidden><img data-chroma-frame alt="Saved chroma-key frame"><figcaption data-chroma-frame-caption></figcaption></figure>
        <p class="media-status" data-chroma-preview-status role="status" aria-live="polite"></p>
      </section>`;
    root.append(this.node);
    this.source = this.node.querySelector('[data-chroma-source]'); this.status = this.node.querySelector('[data-chroma-status]');
    this.apply = this.node.querySelector('[data-chroma-apply]'); this.reset = this.node.querySelector('[data-chroma-reset]');
    this.refresh = this.node.querySelector('[data-chroma-refresh]'); this.previewStatus = this.node.querySelector('[data-chroma-preview-status]');
    this.frame = this.node.querySelector('[data-chroma-frame]');
    this.background = this.node.querySelector('[data-chroma-background]');
    this.node.querySelector('[data-chroma-import]').onclick = () => { if (!this.saving && !this.options.busy()) this.options.openMedia?.(); };
    this.source.onchange = () => { this.invalidatePreview(); this.render(); };
    this.node.addEventListener('input', event => {
      const key = event.target.dataset.chroma;
      if (!key || this.saving || this.options.busy()) return;
      const value = event.target.type === 'checkbox' ? event.target.checked : ['tolerance','edge_softness'].includes(key) ? Number(event.target.value) : key === 'background_asset_id' ? event.target.value || null : event.target.value;
      if (!this.validSource() || this.project()?.manual?.track_locks?.[this.source.value] === true
        || (key === 'background_asset_id' && value && !this.images().some(asset => asset.id === value))
        || (!this.capability?.available && (key !== 'enabled' || value !== false))) return;
      this.options.pause();
      this.drafts.set(this.source.value, chromaSettings({...this.settings(), [key]:value}));
      this.message = null; this.invalidatePreview(); this.render();
    });
    this.apply.onclick = () => this.save(false); this.reset.onclick = () => this.save(true);
    this.refresh.onclick = () => this.refreshFrame();
    this.render();
    this.ready = this.checkCapability();
  }

  copy(key) { return this.options.translate?.(key, copies[key]) || copies[key]; }
  project() { return this.options.project(); }
  validSource(slot = this.source.value) {
    const source = this.project()?.sources?.[slot];
    return Boolean(source && ['width','height','duration'].every(key => Number.isFinite(Number(source[key])) && Number(source[key]) > 0));
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
    const project = this.project();
    if (this.projectId !== project?.id || this.revision !== project?.revision) {
      this.drafts.clear();
      if (this.saving && this.saveProjectId === project?.id) {
        for (const [slot, candidate] of this.otherDrafts || []) {
          if (candidate.saved === JSON.stringify(this.saved(slot)) && candidate.source === JSON.stringify(project.sources?.[slot])) this.drafts.set(slot, candidate.settings);
        }
      }
      this.message = null; this.invalidatePreview(); this.projectId = project?.id; this.revision = project?.revision;
    }
    if (!project?.sources?.[this.source.value]) this.source.value = project?.sources?.A ? 'A' : project?.sources?.B ? 'B' : 'A';
    for (const option of this.source.querySelectorAll('option')) {
      const source = project?.sources?.[option.value]; option.disabled = !source;
      option.textContent = source?.name ? `${option.value} · ${source.name}` : option.value;
    }
    const settings = this.settings(), hasSource = Boolean(project?.draft && this.validSource());
    const available = hasSource && this.capability?.available === true;
    const locked = project?.manual?.track_locks?.[this.source.value] === true;
    const busy = this.saving || this.options.busy();
    this.background.innerHTML = '<option value=""></option>';
    this.background.querySelector('option').textContent = this.copy('chromaSolid');
    for (const asset of this.images()) { const option = document.createElement('option'); option.value = asset.id; option.textContent = asset.name || asset.id; this.background.append(option); }
    if (settings.background_asset_id && !this.images().some(asset => asset.id === settings.background_asset_id)) {
      const option = document.createElement('option'); option.value = settings.background_asset_id; option.textContent = this.copy('chromaImageMissing'); option.disabled = true; this.background.append(option);
    }
    this.node.querySelector('[data-chroma-solid]').hidden = Boolean(settings.background_asset_id);
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
    this.source.disabled = busy || (!project?.sources?.A && !project?.sources?.B);
    this.apply.disabled = !hasSource || busy || locked || (settings.enabled && !this.capability?.available) || !this.dirty();
    this.reset.disabled = !hasSource || busy || locked || JSON.stringify(settings) === JSON.stringify(CHROMA_DEFAULTS);
    this.refresh.disabled = !available || busy || this.previewing || this.dirty();
    this.status.textContent = this.message || (hasSource && !this.capability?.available && !this.dirty() ? this.capability?.message || this.copy('chromaChecking') : this.copy(this.saving ? 'chromaSaving' : !hasSource ? 'chromaNeedsSource' : locked ? 'chromaLocked' : this.dirty() ? 'chromaPending' : 'chromaReady'));
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
    const time = Math.max(0, Math.min(Number(this.options.sourceTime(slot)) || 0, Math.max(0, Number(project.sources[slot].duration || 0) - .001)));
    const generation = this.previewGeneration; this.previewing = true; this.previewAbort = new AbortController();
    this.previewStatus.textContent = this.copy('chromaPreviewing'); this.render();
    try {
      const blob = await this.options.frame({projectId:project.id, slot, time, revision:project.revision}, this.previewAbort.signal);
      if (generation !== this.previewGeneration || this.project()?.id !== project.id || this.project()?.revision !== project.revision || this.source.value !== slot) return;
      this.frameUrl = URL.createObjectURL(blob); this.frame.src = this.frameUrl; this.frame.parentElement.hidden = false;
      this.frame.alt = `${this.copy('chromaFrame')} · ${slot} · ${time.toFixed(3)} s`;
      this.node.querySelector('[data-chroma-frame-caption]').textContent = `${slot} · ${time.toFixed(3)} s · ${this.copy('chromaReady')}`;
      this.previewStatus.textContent = '';
    } catch (error) { if (generation === this.previewGeneration && error.name !== 'AbortError') this.previewStatus.textContent = error.message || this.copy('chromaPreviewFailed'); }
    finally { if (generation === this.previewGeneration) { this.previewing = false; this.render(); } }
  }

  async save(reset) {
    const project = this.project(), slot = this.source.value;
    if (!project?.draft || !this.validSource(slot) || project.manual?.track_locks?.[slot] === true || (!reset && this.settings(slot).enabled && !this.capability?.available) || this.saving || this.options.busy() || (!reset && !this.dirty())) return;
    const projectId = project.id, settings = {...this.settings(slot)};
    this.saveProjectId = projectId;
    this.otherDrafts = new Map([...this.drafts].filter(([key]) => key !== slot).map(([key, value]) => [key, {settings:{...value}, saved:JSON.stringify(this.saved(key)), source:JSON.stringify(project.sources?.[key])}]));
    this.saving = true; this.message = null; this.options.pause(); this.render();
    try {
      const result = await this.options.edit(reset ? 'reset_chroma_key' : 'set_chroma_key', reset ? {slot} : {slot, ...settings}, {isCurrent:() => this.project()?.id === projectId});
      if (this.project()?.id !== projectId) return;
      if (!result) throw new Error(this.copy('chromaFailed'));
      this.drafts.delete(slot); this.revision = this.project()?.revision; this.message = this.copy('chromaSaved');
    } catch (error) { if (this.project()?.id === projectId) this.message = error.message || this.copy('chromaFailed'); }
    finally { this.saving = false; this.saveProjectId = null; this.otherDrafts = null; this.render(); }
  }
}
