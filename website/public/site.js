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
    document.title = language === 'he' ? 'CUTROOM 1.1 Beta — העריכה בידיים שלכם.' : 'CUTROOM 1.1 Beta — Your footage. Your edit.';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עורך וידאו חינמי בקוד פתוח שפועל על המחשב שלכם. חותכים קטעים, מוסיפים כתוביות ומייצאים MP4. ZIP בטא ל־Windows ול־Mac; Linux מקוד מקור.'
      : 'A free, open-source video editor that runs on your computer. Cut clips, add captions and export MP4. Windows/Mac beta ZIP; Linux from source.';
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
