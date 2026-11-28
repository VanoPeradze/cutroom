/* Translated subtitles: a separate .srt in another language, written by the
   configured Story AI from the edit's captions with the same timing. The
   project's captions are not changed. Lives in the Export dialog. */

export const LANGUAGES = [
  ['en', 'English'], ['he', 'Hebrew · עברית'], ['ar', 'Arabic · العربية'], ['es', 'Spanish · Español'],
  ['fr', 'French · Français'], ['de', 'German · Deutsch'], ['ru', 'Russian · Русский'], ['pt', 'Portuguese · Português'],
  ['it', 'Italian · Italiano'], ['hi', 'Hindi · हिन्दी'], ['ja', 'Japanese · 日本語'], ['zh', 'Chinese · 中文'],
];

/** A target language that differs from what is spoken: Hebrew ↔ English by default. */
export function defaultTarget(spoken) {
  return String(spoken || '').toLowerCase().startsWith('en') ? 'he' : 'en';
}

export function initCaptionTranslate(doc = document) {
  const anchor = doc.getElementById('exportHandoff');
  if (!anchor || doc.getElementById('captionTranslate')) return null;
  const row = doc.createElement('div');
  row.id = 'captionTranslate';
  row.className = 'caption-translate';
  row.hidden = true;
  row.innerHTML = `<label>Subtitles in another language <select aria-label="Subtitle language">${LANGUAGES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></label>
    <button type="button" class="button ghost compact">Translate (.srt)</button>
    <a class="caption-translate-link" hidden></a>
    <small class="caption-translate-status" aria-live="polite">Uses your Story AI. Timing stays the same; your captions are not changed.</small>`;
  anchor.after(row);
  const host = () => doc.defaultView.cutroomCleanupHost;
  const select = row.querySelector('select'), button = row.querySelector('button');
  const link = row.querySelector('a'), status = row.querySelector('small');
  let url = null, busy = false;

  const refresh = () => {
    const project = host()?.project?.();
    const has = (project?.editor_captions || []).some((c) => !c.hidden && c.text);
    row.hidden = !project?.id || !has;
    if (!busy && !row.dataset.touched) select.value = defaultTarget(project?.editor_captions?.find((c) => c.language)?.language || project?.language);
  };
  select.addEventListener('change', () => { row.dataset.touched = '1'; link.hidden = true; });
  button.addEventListener('click', async () => {
    const h = host(), project = h?.project?.();
    if (!project?.id || busy) return;
    busy = true; button.disabled = true; link.hidden = true;
    status.textContent = 'Translating… long videos can take a few minutes.';
    try {
      const { translation } = await h.api(`/api/projects/${encodeURIComponent(project.id)}/caption-translation`, { method: 'POST', body: JSON.stringify({ language: select.value }) });
      if (url) URL.revokeObjectURL(url);
      url = URL.createObjectURL(new Blob(['﻿' + translation.srt], { type: 'application/x-subrip;charset=utf-8' }));
      link.href = url; link.download = translation.name; link.hidden = false;
      link.textContent = `Download ${translation.language_name} subtitles`;
      status.textContent = translation.translated < translation.lines
        ? `${translation.translated} of ${translation.lines} lines translated; the rest kept their original text. Check before posting.`
        : `${translation.lines} lines translated by AI. Check before posting.`;
      link.click();
    } catch (error) {
      status.textContent = error?.message || 'The subtitles could not be translated.';
    } finally {
      busy = false; button.disabled = false;
    }
  });
  const dialog = doc.getElementById('exportDialog');
  if (dialog && typeof MutationObserver !== 'undefined') new MutationObserver(() => { if (dialog.open) refresh(); }).observe(dialog, { attributes: true, attributeFilter: ['open'] });
  return { refresh };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initCaptionTranslate(document), { once: true });
  else initCaptionTranslate(document);
}
