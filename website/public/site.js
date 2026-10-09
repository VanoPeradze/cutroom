(() => {
  document.documentElement.classList.add('js');
  const translations = [...document.querySelectorAll('[data-he]')].map(node => ({node, en: node.innerHTML, he: node.dataset.he}));
  const images = [...document.querySelectorAll('[data-he-alt]')].map(node => ({node, en: node.alt, he: node.dataset.heAlt}));
  const labels = [...document.querySelectorAll('[data-he-aria]')].map(node => ({node, en: node.getAttribute('aria-label'), he: node.dataset.heAria}));
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
    labels.forEach(item => { item.node.setAttribute('aria-label', item[language]); });
    languageSwitch.textContent = language === 'he' ? 'English' : 'עברית';
    languageSwitch.lang = language === 'he' ? 'en' : 'he';
    languageSwitch.setAttribute('aria-label', language === 'he' ? 'Read this website in English' : 'קריאת האתר בעברית');
    languageSwitch.href = (language === 'he' ? '?lang=en' : '?lang=he') + location.hash;
    document.title = language === 'he' ? 'CUTROOM — שעות של חומר. דקות לקליפ מצוין.' : 'CUTROOM — Hours of footage. Minutes to a great clip.';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עורך וידאו חינמי ומקומי. חיתוכים, סאונד וכתוביות. בטא ל־Windows ול־Mac; Linux מהמקור. AI הוא אפשרות.'
      : 'A free local video editor. Cut footage, mix sound and add captions. Windows/Mac beta; Linux from source. Optional AI drafts, editable by you.';
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

  // Workspace tour: without this script every panel stays visible in reading order.
  const tabList = document.querySelector('.tour-tabs');
  const tabs = [...tabList.querySelectorAll('.tour-tab')];
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
  tabList.setAttribute('role', 'tablist');
  tabs.forEach(tab => tab.setAttribute('role', 'tab'));
  panels.forEach(panel => { panel.setAttribute('role', 'tabpanel'); panel.tabIndex = 0; });
  function selectTab(index, focus) {
    tabs.forEach((tab, i) => {
      const selected = i === index;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
      panels[i].hidden = !selected;
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, index) => tab.addEventListener('click', () => selectTab(index, false)));
  tabList.addEventListener('keydown', event => {
    const current = tabs.indexOf(document.activeElement);
    if (current < 0) return;
    const forward = document.documentElement.dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    const backward = document.documentElement.dir === 'rtl' ? 'ArrowRight' : 'ArrowLeft';
    let next = null;
    if (event.key === forward) next = (current + 1) % tabs.length;
    else if (event.key === backward) next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    selectTab(next, true);
  });
  selectTab(0, false);

  function revealLinkedHelp() {
    const target = document.getElementById(location.hash.slice(1));
    const details = target?.closest('details');
    if (details) { details.open = true; target.scrollIntoView({block:'start'}); }
  }
  window.addEventListener('hashchange', revealLinkedHelp);
  renderLanguage();
  revealLinkedHelp();
})();
