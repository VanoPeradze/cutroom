/* Style packs: "how should it feel?". One click sets the caption style, the
   colour look and (for the energetic packs) short punch-ins on key words.
   Every part stays editable afterwards in its own control. */
import { autoZoomKeyframes, normalizeColor } from './color-motion.js?v=20261128-autozoom1';

export const LOOK_PACKS = [
  { id: 'clean', name: 'Clean', feel: 'Calm and professional', caption: 'clean', look: 'none', zoom: false },
  { id: 'social', name: 'Bold social', feel: 'Energetic short-form', caption: 'pop', look: 'punchy', zoom: true },
  { id: 'podcast', name: 'Podcast', feel: 'Warm conversation', caption: 'box', look: 'warm', zoom: false },
  { id: 'gaming', name: 'Gaming', feel: 'Loud and bright', caption: 'neon', look: 'teal_orange', zoom: true },
  { id: 'minimal', name: 'Minimal', feel: 'One word at a time', caption: 'word', look: 'matte', zoom: false },
  { id: 'explainer', name: 'Explainer', feel: 'Clear, key points stand out', caption: 'emphasis', look: 'cool', zoom: true },
  { id: 'cinematic', name: 'Cinematic', feel: 'Moody, story first', caption: 'clean', look: 'teal_orange', zoom: false },
  { id: 'vintage', name: 'Vintage', feel: 'Nostalgic, soft', caption: 'bold', look: 'vintage', zoom: false },
];

/** The manual patch a pack writes: full colour object, and keyframes if it zooms. */
export function packManualPatch(pack, project) {
  const manual = project?.manual || {};
  const patch = { color: normalizeColor({ ...normalizeColor(manual.color), look: pack.look }) };
  if (pack.zoom) {
    const keyframes = autoZoomKeyframes(project?.editor_captions || [], manual.keyframes || []);
    if (keyframes.length !== (manual.keyframes || []).length) patch.keyframes = keyframes;
  }
  return patch;
}

export function initLookPacks(doc = document) {
  const button = doc.getElementById('lookPackButton');
  if (!button || doc.getElementById('lookPackDialog')) return null;
  const dialog = doc.createElement('dialog');
  dialog.id = 'lookPackDialog';
  dialog.className = 'cleanup-dialog look-pack-dialog';
  dialog.setAttribute('aria-labelledby', 'lookPackTitle');
  dialog.innerHTML = `
    <header><h2 id="lookPackTitle">How should it feel?</h2><button type="button" class="cleanup-close" aria-label="Close">×</button></header>
    <p class="cleanup-intro">A style pack sets the caption style and colour look together. Energetic packs also add short zooms on key words. You can change each part afterwards.</p>
    <div class="look-pack-grid" role="list"></div>
    <footer><span class="cleanup-total" aria-live="polite"></span><button type="button" class="cleanup-cancel">Close</button></footer>`;
  doc.body.append(dialog);
  const grid = dialog.querySelector('.look-pack-grid'), status = dialog.querySelector('.cleanup-total');
  const host = () => doc.defaultView.cutroomCleanupHost;
  grid.replaceChildren(...LOOK_PACKS.map((pack) => {
    const card = doc.createElement('button');
    card.type = 'button'; card.className = 'look-pack'; card.dataset.pack = pack.id; card.setAttribute('role', 'listitem');
    const swatch = doc.createElement('span'); swatch.className = 'look-pack-swatch'; swatch.dataset.look = pack.look; swatch.setAttribute('aria-hidden', 'true');
    const sample = doc.createElement('i'); sample.dataset.caption = pack.caption; sample.textContent = pack.caption === 'word' ? 'WOW' : 'Big idea';
    swatch.append(sample);
    const name = doc.createElement('b'); name.textContent = pack.name;
    const feel = doc.createElement('small'); feel.textContent = pack.feel + (pack.zoom ? ' · zooms' : '');
    card.append(swatch, name, feel);
    card.addEventListener('click', () => {
      const h = host(), project = h?.project(), select = doc.getElementById('captionStyleSelect');
      if (!project) return;
      if (select && [...select.options].some((o) => o.value === pack.caption)) {
        select.value = pack.caption;
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
      const patch = packManualPatch(pack, project);
      h.saveManual(patch);
      h.refreshMotion?.();
      for (const other of grid.querySelectorAll('.look-pack')) other.setAttribute('aria-pressed', String(other === card));
      const zooms = patch.keyframes ? (patch.keyframes.length - (project.manual?.keyframes || []).length) / 4 : 0;
      status.textContent = `${pack.name} applied${zooms ? ` with ${zooms} zoom${zooms === 1 ? '' : 's'}` : ''}.`;
    });
    return card;
  }));
  dialog.querySelector('.cleanup-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('.cleanup-cancel').addEventListener('click', () => dialog.close());
  button.addEventListener('click', () => { status.textContent = ''; dialog.showModal(); grid.querySelector('.look-pack')?.focus(); });
  return {};
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initLookPacks(document), { once: true });
  else initLookPacks(document);
}
