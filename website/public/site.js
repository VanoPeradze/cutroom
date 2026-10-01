(() => {
  const translations = [...document.querySelectorAll('[data-he]')].map(node => ({node, en: node.innerHTML, he: node.dataset.he}));
  const images = [...document.querySelectorAll('[data-he-alt]')].map(node => ({node, en: node.alt, he: node.dataset.heAlt}));
  const languageSwitch = document.getElementById('languageSwitch');
  const dialog = document.getElementById('imageDialog');
  let language = new URL(location.href).searchParams.get('lang') === 'he' ? 'he' : 'en';
  function renderLanguage() {
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'he' ? 'rtl' : 'ltr';
    for (const item of translations) {
      if (language === 'he') item.node.textContent = item.he;
      else item.node.innerHTML = item.en;
    }
    images.forEach(item => { item.node.alt = item[language]; });
    languageSwitch.textContent = language === 'he' ? 'English' : 'עברית';
    languageSwitch.lang = language === 'he' ? 'en' : 'he';
    languageSwitch.setAttribute('aria-label', language === 'he' ? 'Read this website in English' : 'קריאת האתר בעברית');
    languageSwitch.href = (language === 'he' ? '?lang=en' : '?lang=he') + location.hash;
    document.title = language === 'he' ? 'CUTROOM — כל פריים. בידיים שלכם.' : 'CUTROOM — Make the cut. Make it yours.';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עורך וידאו חינמי ומקומי. חיתוכים, סאונד וכתוביות. בטא ל־Windows ול־Mac; Linux מהמקור. AI הוא אפשרות.'
      : 'A free local video editor. Cut footage, mix sound and add captions. Windows/Mac beta; Linux from source. Optional AI drafts, editable by you.';
    document.querySelector('nav').setAttribute('aria-label', language === 'he' ? 'ניווט באתר' : 'Site navigation');
    document.querySelector('.capabilities').setAttribute('aria-label', language === 'he' ? 'מהקלטה ל־MP4' : 'From recording to MP4');
    document.getElementById('expandShot').setAttribute('aria-label', language === 'he' ? 'הגדלת צילום העורך' : 'Enlarge editor screenshot');
    dialog.setAttribute('aria-label', language === 'he' ? 'צילום העורך' : 'Editor screenshot');
  }
  languageSwitch.addEventListener('click', event => {
    event.preventDefault();
    language = language === 'he' ? 'en' : 'he';
    const url = new URL(location.href);
    if (language === 'he') url.searchParams.set('lang', 'he'); else url.searchParams.delete('lang');
    history.replaceState(null, '', url);
    renderLanguage();
  });
  document.getElementById('expandShot').addEventListener('click', () => dialog.showModal());
  document.getElementById('closeImage').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  function revealLinkedHelp() {
    const target = document.getElementById(location.hash.slice(1));
    const details = target?.closest('details');
    if (details) { details.open = true; target.scrollIntoView({block:'start'}); }
  }
  window.addEventListener('hashchange', revealLinkedHelp);
  renderLanguage();
  revealLinkedHelp();
})();
