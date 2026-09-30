// Optional local preprocessing creates a reusable copy, never a source replacement.
export class StabilizationStudio {
  constructor(root, options) {
    this.options = options;
    this.uploading = false;
    this.capability = null;
    this.node = document.createElement('details');
    this.node.className = 'stabilization-tool';
    this.node.dataset.editorShortcuts = 'off';
    this.node.innerHTML = `
      <summary>Stabilize footage <span>Local copy</span></summary>
      <p class="media-help">Smooth camera shake in a separate copy. Edges may be cropped; your original footage and edit stay unchanged.</p>
      <div class="stabilization-controls">
        <label>Footage<select data-stabilize-source aria-label="Footage to stabilize"></select></label>
        <button type="button" data-stabilize-create>Create stabilized copy</button>
      </div>
      <p class="media-status" data-stabilize-status role="status" aria-live="polite">Checking local stabilization support…</p>
      <button type="button" class="stabilization-check" data-stabilize-check hidden>Check again</button>
      <a class="stabilization-download" data-stabilize-download hidden>Download stabilized copy</a>`;
    root.append(this.node);
    this.source = this.node.querySelector('[data-stabilize-source]');
    this.create = this.node.querySelector('[data-stabilize-create]');
    this.status = this.node.querySelector('[data-stabilize-status]');
    this.retry = this.node.querySelector('[data-stabilize-check]');
    this.download = this.node.querySelector('[data-stabilize-download]');
    this.create.onclick = () => this.createCopy();
    this.source.onchange = () => this.render();
    this.retry.onclick = () => this.checkCapability();
    this.render();
    this.checkCapability();
  }

  project() { return this.options.project(); }

  async checkCapability() {
    if (this.checking || this.uploading) return;
    this.checking = true;
    this.status.textContent = 'Checking local stabilization support…';
    this.retry.hidden = true;
    this.render();
    try {
      this.capability = await this.options.api('/api/stabilization/capability');
      this.status.textContent = this.capability.available
        ? 'Ready. No AI or cloud service is used.'
        : this.capability.message || 'This FFmpeg build does not support stabilization.';
    } catch (error) {
      this.capability = null;
      this.status.textContent = error.message || 'Could not check local stabilization support.';
    } finally {
      this.checking = false;
      this.retry.hidden = Boolean(this.capability?.available);
      this.render();
    }
  }

  render() {
    const project = this.project();
    if (this.activeProjectId !== project?.id) {
      this.activeProjectId = project?.id;
      this.status.textContent = this.checking ? 'Checking local stabilization support…'
        : this.capability?.available ? 'Ready. No AI or cloud service is used.'
        : this.capability?.message || 'Checking local stabilization support…';
    }
    const selected = this.source.value;
    const choices = ['A', 'B'].filter(slot => project?.sources?.[slot]);
    // Rebuilding source labels does not disturb focus, selection or progress.
    const key = JSON.stringify(choices.map(slot => [slot, project.sources[slot].name]));
    if (key !== this.sourceKey) {
      this.source.replaceChildren();
      for (const slot of choices) {
        const option = document.createElement('option');
        option.value = slot;
        option.textContent = `${slot} · ${project.sources[slot].name || 'Original footage'}`;
        this.source.append(option);
      }
      if (choices.includes(selected)) this.source.value = selected;
      this.sourceKey = key;
    }
    const preparation = project?.sources?.[this.source.value]?.preparation;
    const ready = !preparation || preparation === 'ready';
    const busy = this.starting || this.uploading || this.options.busy();
    this.source.disabled = busy || !choices.length;
    this.create.disabled = busy || this.checking || !choices.length || !ready || !this.capability?.available;
    this.create.textContent = this.uploading ? 'Creating copy…' : 'Create stabilized copy';
    this.retry.disabled = this.checking || busy;
    if (this.downloadProjectId !== project?.id) {
      this.download.hidden = true;
      this.download.removeAttribute('href');
    }
  }

  async createCopy() {
    if (this.starting || this.uploading || this.options.busy() || !this.capability?.available) return;
    const projectId = this.project()?.id;
    const slot = this.source.value;
    if (!projectId || !this.project()?.sources?.[slot]) return;
    this.starting = true;
    this.options.pause();
    this.download.hidden = true;
    this.render();
    try {
      if (this.options.flush && !(await this.options.flush())) return;
      this.uploading = true;
      this.options.busyChanged?.();
      this.render();
      await this.options.flushSettings(projectId);
      if (this.project()?.id !== projectId) return;
      this.status.textContent = 'Creating a local copy. Use Stop process to cancel.';
      const result = await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/stabilize`, {
        method: 'POST', body: JSON.stringify({slot, expected_revision: this.project().revision}),
      });
      await this.options.acceptUpload(result, projectId);
      if (this.project()?.id !== projectId) return;
      const asset = this.project().assets?.[result.asset_id];
      if (asset?.status !== 'ready' || !asset.download_url) throw new Error('The copy is not ready. Retry it in the media library.');
      this.download.href = asset.download_url;
      this.download.download = asset.name || 'stabilized.mp4';
      this.download.hidden = false;
      this.downloadProjectId = projectId;
      this.status.textContent = 'Ready in the media library. Download the copy, or add it as extra footage. Your original edit is unchanged.';
    } catch (error) {
      if (this.project()?.id === projectId) this.status.textContent = error.message || 'The copy could not be created. Your original is unchanged.';
    } finally {
      this.uploading = false;
      this.starting = false;
      this.render();
      this.options.busyChanged?.();
    }
  }
}
