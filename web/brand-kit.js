/* Brand kit. One place for what makes every video look like the creator's:
   a brand colour for the spoken word and key words in captions, a logo in a
   corner for the whole video, and saved templates (caption style, position,
   size, words per line, brand colour and colour look) to apply to any
   project in one click. Templates are kept in this app on this computer. */
import { normalizeColor } from './color-motion.js?v=20261128-autozoom1';

const STORE = 'cutroom-brand-templates';
const MAX_TEMPLATES = 24;
const CORNERS = [['top-left', 'Top left'], ['top-right', 'Top right'], ['bottom-left', 'Bottom left'], ['bottom-right', 'Bottom right']];
const ACCENTS = ['#FFE14D', '#FF8A3D', '#FF4D6D', '#39FF88', '#4DB8FF', '#B07CFF'];
const round4 = (n) => Math.floor(n * 10000) / 10000;

export const isAccent = (value) => typeof value === 'string' && /^#[0-9A-Fa-f]{6}$/.test(value);

/** Logo box in frame fractions, keeping the logo's own shape and an even margin. */
export function logoPlacement({ corner = 'top-right', size = 0.14, frameRatio = 16 / 9, imageRatio = 1, margin = 0.03 } = {}) {
  const fr = frameRatio > 0 ? frameRatio : 16 / 9, ir = imageRatio > 0 ? imageRatio : 1;
  let w = Math.max(0.03, Math.min(0.4, size)), h = (w * fr) / ir;
  if (h > 0.4) { h = 0.4; w = (h * ir) / fr; }
  const mx = margin, my = Math.min(0.1, margin * fr);
  const left = corner.endsWith('left'), top = corner.startsWith('top');
  w = round4(w); h = round4(h);
  const x = round4(left ? mx : Math.max(0, 1 - w - mx)), y = round4(top ? my : Math.max(0, 1 - h - my));
  return { x, y, w, h };
}

/** Output frame width / height from the project's aspect setting. */
export function frameRatioOf(project, fallback = 16 / 9) {
  const match = String(project?.settings?.aspect || '').match(/^(\d+):(\d+)$/);
  return match ? Number(match[1]) / Number(match[2]) : fallback;
}

/** A template from the project as it looks now. */
export function templateFromProject(project, name) {
  const s = project?.settings || {};
  return {
    name: String(name || 'My brand').trim().slice(0, 40) || 'My brand',
    caption_style: s.caption_style || 'bold', caption_position: s.caption_position || 'auto',
    caption_scale: Number.isInteger(s.caption_scale) ? s.caption_scale : 100,
    caption_words_per_line: Number.isInteger(s.caption_words_per_line) ? s.caption_words_per_line : 9,
    caption_accent: isAccent(s.caption_accent) ? s.caption_accent.toUpperCase() : '',
    look: normalizeColor(project?.manual?.color).look || 'none',
  };
}

/** Saved templates, keeping only well-formed rows. */
export function readTemplates(storage) {
  try {
    const rows = JSON.parse(storage?.getItem(STORE) || '[]');
    return Array.isArray(rows) ? rows.filter((r) => r && typeof r.name === 'string' && typeof r.caption_style === 'string').slice(0, MAX_TEMPLATES) : [];
  } catch { return []; }
}

export function writeTemplates(storage, rows) {
  try { storage?.setItem(STORE, JSON.stringify(rows.slice(0, MAX_TEMPLATES))); return true; } catch { return false; }
}

/** Add or replace by name (case-insensitive), newest first. */
export function upsertTemplate(rows, template) {
  return [template, ...rows.filter((r) => r.name.toLowerCase() !== template.name.toLowerCase())].slice(0, MAX_TEMPLATES);
}

export function initBrandKit(doc = document) {
  const button = doc.getElementById('brandKitButton');
  if (!button || doc.getElementById('brandKitDialog')) return null;
  const win = doc.defaultView;
  const storage = (() => { try { return win.localStorage; } catch { return null; } })();
  const dialog = doc.createElement('dialog');
  dialog.id = 'brandKitDialog';
  dialog.className = 'cleanup-dialog brand-kit-dialog';
  dialog.setAttribute('aria-labelledby', 'brandKitTitle');
  dialog.innerHTML = `
    <header><h2 id="brandKitTitle">Brand kit</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <div class="brand-kit-body">
      <section aria-labelledby="brandColourTitle">
        <h3 id="brandColourTitle">Brand colour</h3>
        <p class="brand-note">Colours the spoken word and key words in the word-timed caption styles.</p>
        <div class="brand-colour-row">
          <input type="color" class="brand-colour" aria-label="Brand colour" value="#FFE14D">
          <div class="brand-swatches" role="group" aria-label="Suggested colours"></div>
          <button type="button" class="brand-colour-reset">Style colour</button>
        </div>
      </section>
      <section aria-labelledby="brandLogoTitle">
        <h3 id="brandLogoTitle">Logo</h3>
        <p class="brand-note brand-logo-note"></p>
        <div class="brand-logo-row">
          <label>Image <select class="brand-logo-asset"></select></label>
          <label>Corner <select class="brand-logo-corner">${CORNERS.map(([v, l]) => `<option value="${v}"${v === 'top-right' ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label>Size <input type="range" class="brand-logo-size" min="6" max="30" step="1" value="14"><output class="brand-logo-size-out">14%</output></label>
          <button type="button" class="brand-logo-add">Add logo to the whole video</button>
        </div>
      </section>
      <section aria-labelledby="brandTemplatesTitle">
        <h3 id="brandTemplatesTitle">Templates</h3>
        <p class="brand-note">A template keeps the caption style, position, size, words per caption, brand colour and colour look. Saved in this app on this computer.</p>
        <form class="brand-save-row"><input type="text" class="brand-template-name" maxlength="40" placeholder="Template name" aria-label="Template name" dir="auto"><button type="submit">Save current look</button></form>
        <ul class="brand-templates" aria-label="Saved templates"></ul>
      </section>
    </div>
    <footer><span class="cleanup-total brand-status" aria-live="polite"></span><button type="button" class="cleanup-cancel">Close</button></footer>`;
  doc.body.append(dialog);
  const $ = (sel) => dialog.querySelector(sel);
  const host = () => win.cutroomCleanupHost;
  const colour = $('.brand-colour'), status = $('.brand-status'), list = $('.brand-templates');
  const logoAsset = $('.brand-logo-asset'), logoCorner = $('.brand-logo-corner'), logoSize = $('.brand-logo-size'), logoAdd = $('.brand-logo-add');

  const setAccent = (value) => {
    const accent = isAccent(value) ? value.toUpperCase() : '';
    host()?.saveSettings?.({ caption_accent: accent });
    if (accent) colour.value = accent;
    paintSwatches(accent);
    status.textContent = accent ? `Brand colour ${accent} saved.` : 'Captions use each style’s own colour.';
  };
  const paintSwatches = (accent) => {
    for (const chip of dialog.querySelectorAll('.brand-swatches button')) chip.setAttribute('aria-pressed', String(chip.dataset.colour === accent));
    $('.brand-colour-reset').setAttribute('aria-pressed', String(!accent));
  };
  $('.brand-swatches').replaceChildren(...ACCENTS.map((value) => {
    const chip = doc.createElement('button'); chip.type = 'button'; chip.dataset.colour = value;
    chip.style.setProperty('--swatch', value); chip.setAttribute('aria-label', value);
    chip.addEventListener('click', () => setAccent(value));
    return chip;
  }));
  colour.addEventListener('change', () => setAccent(colour.value));
  $('.brand-colour-reset').addEventListener('click', () => setAccent(''));

  const images = (project) => Object.entries(project?.assets || {}).filter(([, a]) => a?.kind === 'image' && a.status === 'ready')
    .map(([id, a]) => ({ id, name: a.name || a.original_name || a.filename || id, ratio: a.width > 0 && a.height > 0 ? a.width / a.height : 1 }));
  const renderLogo = (project) => {
    const rows = images(project);
    logoAsset.replaceChildren(...rows.map((r) => Object.assign(doc.createElement('option'), { value: r.id, textContent: r.name })));
    const note = $('.brand-logo-note');
    note.textContent = !rows.length ? 'Import your logo as an image (a PNG with a transparent background works best), then add it here.'
      : 'Adds the logo as an image layer for the whole video. Add it last: Clean up and Script cuts need an edit without layers.';
    $('.brand-logo-row').hidden = !rows.length;
  };
  logoSize.addEventListener('input', () => { $('.brand-logo-size-out').textContent = `${logoSize.value}%`; });
  logoAdd.addEventListener('click', async () => {
    const h = host(), project = h?.project();
    const image = images(project).find((r) => r.id === logoAsset.value);
    const duration = Number(project?.editor_sequence?.duration);
    if (!image || !(duration > 0.1)) return;
    const video = doc.querySelector('#previewStage video');
    const frameRatio = frameRatioOf(project, video?.videoWidth > 0 ? video.videoWidth / video.videoHeight : 16 / 9);
    const box = logoPlacement({ corner: logoCorner.value, size: Number(logoSize.value) / 100, frameRatio, imageRatio: image.ratio });
    logoAdd.disabled = true;
    const result = await h.edit?.('media_add', { asset_id: image.id, start: 0, end: Math.floor(duration * 1000) / 1000, ...box, fit: 'cover', audio_enabled: false });
    logoAdd.disabled = false;
    status.textContent = result ? 'Logo added. Select it on the timeline to move, fade or remove it.' : 'The logo could not be added.';
  });

  const renderTemplates = () => {
    const rows = readTemplates(storage);
    list.replaceChildren(...(rows.length ? rows.map((t) => {
      const li = doc.createElement('li');
      const swatch = doc.createElement('span'); swatch.className = 'brand-template-swatch'; swatch.setAttribute('aria-hidden', 'true');
      if (t.caption_accent) swatch.style.setProperty('--swatch', t.caption_accent);
      const name = doc.createElement('b'); name.textContent = t.name; name.dir = 'auto';
      const meta = doc.createElement('small'); meta.textContent = `${t.caption_style} captions · ${t.look === 'none' ? 'no look' : t.look.replace(/_/g, ' ')}`;
      const use = doc.createElement('button'); use.type = 'button'; use.className = 'cleanup-apply'; use.textContent = 'Apply';
      use.addEventListener('click', () => applyTemplate(t));
      const del = doc.createElement('button'); del.type = 'button'; del.textContent = 'Delete'; del.setAttribute('aria-label', `Delete ${t.name}`);
      del.addEventListener('click', () => { writeTemplates(storage, readTemplates(storage).filter((r) => r.name !== t.name)); renderTemplates(); status.textContent = `Deleted “${t.name}”.`; });
      li.append(swatch, name, meta, use, del);
      return li;
    }) : [Object.assign(doc.createElement('li'), { className: 'brand-empty', textContent: 'No templates yet.' })]));
  };
  const setControl = (id, value, event) => {
    const el = doc.getElementById(id);
    if (!el || value === undefined) return;
    if (el.tagName === 'SELECT' && ![...el.options].some((o) => o.value === String(value))) return;
    el.value = String(value);
    if (event === 'input') el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const applyTemplate = (t) => {
    const h = host(), project = h?.project();
    if (!project) return;
    setControl('captionStyleSelect', t.caption_style);
    setControl('captionPositionSelect', t.caption_position);
    setControl('captionScale', t.caption_scale, 'input');
    setControl('captionWordsPerLine', t.caption_words_per_line, 'input');
    h.saveSettings?.({ caption_accent: isAccent(t.caption_accent) ? t.caption_accent : '' });
    h.saveManual?.({ color: normalizeColor({ ...normalizeColor(project.manual?.color), look: t.look || 'none' }) });
    h.refreshMotion?.();
    if (isAccent(t.caption_accent)) colour.value = t.caption_accent;
    paintSwatches(isAccent(t.caption_accent) ? t.caption_accent : '');
    status.textContent = `Applied “${t.name}”.`;
  };
  $('.brand-save-row').addEventListener('submit', (e) => {
    e.preventDefault();
    const project = host()?.project(); if (!project) return;
    const input = $('.brand-template-name');
    const template = templateFromProject(project, input.value);
    const saved = writeTemplates(storage, upsertTemplate(readTemplates(storage), template));
    input.value = '';
    renderTemplates();
    status.textContent = saved ? `Saved “${template.name}”.` : 'This browser does not allow saving templates.';
  });

  const open = () => {
    const project = host()?.project();
    if (!project) return;
    const accent = isAccent(project.settings?.caption_accent) ? project.settings.caption_accent.toUpperCase() : '';
    if (accent) colour.value = accent;
    paintSwatches(accent);
    renderLogo(project);
    renderTemplates();
    status.textContent = '';
    dialog.showModal();
    colour.focus();
  };
  $('.cleanup-close').addEventListener('click', () => dialog.close());
  $('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', open);
  return { open };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initBrandKit(document), { once: true });
  else initBrandKit(document);
}
