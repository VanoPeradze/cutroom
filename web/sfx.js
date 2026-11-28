/* Sound effects library: original sounds made by scripts/generate_sfx.py.
   Play previews a sound; "Add" imports it into the project media through the
   normal import, so it is placed, trimmed and mixed like any other audio. */

export async function loadCatalog(fetcher = fetch) {
  const response = await fetcher('/assets/sfx/catalog.json');
  if (!response.ok) throw new Error('Sound effects are unavailable.');
  const data = await response.json();
  return Array.isArray(data?.sounds) ? data.sounds.filter((s) => /^[a-z]+$/.test(s.id) && /^[a-z]+\.wav$/.test(s.file)) : [];
}

export function initSfx(doc = document) {
  const root = doc.getElementById('sfxLibrary');
  if (!root || root.dataset.ready) return null;
  root.dataset.ready = '1';
  const list = root.querySelector('.sfx-list');
  let player = null, playing = null;
  const host = () => doc.defaultView.cutroomCleanupHost;

  const stop = () => { player?.pause(); if (playing) { playing.textContent = 'Play'; playing.setAttribute('aria-pressed', 'false'); } playing = null; };

  const render = (sounds) => {
    list.replaceChildren(...sounds.map((sound) => {
      const li = doc.createElement('li');
      const text = doc.createElement('div'); text.className = 'sfx-text';
      const name = doc.createElement('b'); name.textContent = sound.name;
      const use = doc.createElement('small'); use.textContent = `${sound.use} · ${sound.seconds.toFixed(1)} s`;
      text.append(name, use);
      const play = doc.createElement('button'); play.type = 'button'; play.textContent = 'Play';
      play.setAttribute('aria-pressed', 'false'); play.setAttribute('aria-label', `Play ${sound.name}`);
      play.addEventListener('click', () => {
        if (playing === play) { stop(); return; }
        stop();
        player = new Audio(`/assets/sfx/${sound.file}`);
        player.addEventListener('ended', stop, { once: true });
        player.play().catch(stop);
        playing = play; play.textContent = 'Stop'; play.setAttribute('aria-pressed', 'true');
      });
      const add = doc.createElement('button'); add.type = 'button'; add.textContent = 'Add';
      add.setAttribute('aria-label', `Add ${sound.name} to project media`);
      add.addEventListener('click', async () => {
        const h = host();
        if (!h?.project()) return;
        add.disabled = true;
        try {
          const blob = await (await fetch(`/assets/sfx/${sound.file}`)).blob();
          await h.importFiles([new File([blob], `${sound.name} - Cutroom SFX.wav`, { type: 'audio/wav' })]);
        } finally { add.disabled = false; }
      });
      li.append(text, play, add);
      return li;
    }));
  };

  root.addEventListener('toggle', async () => {
    if (!root.open || list.childElementCount) return;
    try { render(await loadCatalog()); } catch (error) { list.textContent = error.message; }
  });
  return { stop };
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => initSfx(document), { once: true });
  else initSfx(document);
}
