(() => {
  document.documentElement.classList.add('js');
  const translations = [...document.querySelectorAll('[data-he]')].map(node => ({node, en: node.innerHTML, he: node.dataset.he}));
  const images = [...document.querySelectorAll('[data-he-alt]')].map(node => ({node, en: node.alt, he: node.dataset.heAlt}));
  const labels = [...document.querySelectorAll('[data-he-aria]')].map(node => ({node, en: node.getAttribute('aria-label'), he: node.dataset.heAria}));
  const languageSwitch = document.getElementById('languageSwitch');
  const mobileLanguageSwitch = document.getElementById('mobileLanguageSwitch');
  const languageSwitches = [languageSwitch, mobileLanguageSwitch].filter(Boolean);
  const dialog = document.getElementById('imageDialog');
  let screenshotOpener = null;
  const motionToggle = document.getElementById('motionToggle');
  const mobileMotionToggle = document.getElementById('mobileMotionToggle');
  const motionControls = [motionToggle, mobileMotionToggle].filter(Boolean);
  const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
  let motionPaused = motionPreference.matches;
  function renderMotion() {
    if (motionPreference.matches) motionPaused = true;
    document.documentElement.dataset.motion = motionPaused ? 'paused' : 'running';
    for (const control of motionControls) {
      control.disabled = motionPreference.matches;
      const state = control.querySelector('[data-motion-state]');
      if (state) {
        control.setAttribute('aria-pressed', String(!motionPaused));
        state.textContent = motionPreference.matches
          ? (language === 'he' ? 'כבוי · הגדרות המכשיר' : 'Off · device setting')
          : (language === 'he' ? (motionPaused ? 'כבוי' : 'פעיל') : (motionPaused ? 'Off' : 'On'));
      } else {
        // An older cached page can still have the previous icon control.
        control.setAttribute('aria-pressed', String(motionPaused));
        const label = motionPreference.matches ? (language === 'he' ? 'תנועה מופחתת' : 'Reduced motion')
          : (language === 'he' ? (motionPaused ? 'הפעלת תנועה' : 'השהיית תנועה') : (motionPaused ? 'Play motion' : 'Pause motion'));
        control.setAttribute('aria-label', label);
        const span = control.querySelector('span'), path = control.querySelector('path');
        if (span) span.textContent = label;
        if (path) path.setAttribute('d', motionPaused ? 'M6 3l9 7-9 7Z' : 'M7 4v12M13 4v12');
      }
    }
  }
  motionControls.forEach(control => control.addEventListener('click', () => {
    if (motionPreference.matches) return;
    motionPaused = !motionPaused;
    renderMotion();
  }));
  motionPreference.addEventListener('change', renderMotion);
  let language = new URL(location.href).searchParams.get('lang') === 'he' ? 'he' : 'en';
  function renderLanguage() {
    renderMotion();
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'he' ? 'rtl' : 'ltr';
    for (const item of translations) {
      if (language === 'he') item.node.textContent = item.he;
      else item.node.innerHTML = item.en;
    }
    images.forEach(item => { item.node.alt = item[language]; });
    labels.forEach(item => { item.node.setAttribute('aria-label', item[language]); });
    for (const link of languageSwitches) {
      link.textContent = language === 'he' ? 'English' : 'עברית';
      link.lang = language === 'he' ? 'en' : 'he';
      link.href = (language === 'he' ? '?lang=en' : '?lang=he') + location.hash;
    }
    document.title = language === 'he' ? 'CUTROOM - חדר העריכה שלך' : 'CUTROOM - Your local editing studio';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עורך וידאו חינמי ומקומי. חיתוכים, סאונד וכתוביות. בטא ל־Windows ול־Mac; Linux מהמקור. AI הוא אפשרות.'
      : 'A free local video editor. Cut footage, mix sound and add captions. Windows/Mac beta; Linux from source. Optional AI drafts, editable by you.';
  }
  languageSwitches.forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    language = language === 'he' ? 'en' : 'he';
    const url = new URL(location.href);
    if (language === 'he') url.searchParams.set('lang', 'he'); else url.searchParams.delete('lang');
    history.replaceState(null, '', url);
    renderLanguage();
    if (link === mobileLanguageSwitch) {
      const navigation = document.getElementById('mobileNav');
      if (navigation?.open) {
        navigation.open = false;
        document.getElementById('mobileNavToggle')?.focus({preventScroll: true});
      }
    }
  }));
  const screenshotLinks = [...document.querySelectorAll('#expandShot, [data-screenshot]')];
  const expandedImage = document.getElementById('expandedImage');
  const originalImage = document.getElementById('originalImage');
  const imageCounter = document.getElementById('imageCounter');
  let screenshotIndex = 0;
  function showScreenshot(index) {
    screenshotIndex = (index + screenshotLinks.length) % screenshotLinks.length;
    const link = screenshotLinks[screenshotIndex];
    const image = link.querySelector('img');
    expandedImage.src = link.href;
    expandedImage.alt = image.alt;
    expandedImage.width = image.naturalWidth || image.width;
    expandedImage.height = image.naturalHeight || image.height;
    originalImage.href = link.href;
    imageCounter.textContent = `${screenshotIndex + 1} / ${screenshotLinks.length}`;
  }
  screenshotLinks.forEach((link, index) => {
    link.setAttribute('aria-haspopup', 'dialog');
    link.setAttribute('aria-controls', 'imageDialog');
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0 || !dialog.showModal) return;
      event.preventDefault();
      screenshotOpener = link;
      showScreenshot(index);
      dialog.showModal();
    });
  });
  document.getElementById('previousImage').addEventListener('click', () => showScreenshot(screenshotIndex - 1));
  document.getElementById('nextImage').addEventListener('click', () => showScreenshot(screenshotIndex + 1));
  document.getElementById('closeImage').addEventListener('click', () => dialog.close());
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const forward = document.documentElement.dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    showScreenshot(screenshotIndex + (event.key === forward ? 1 : -1));
  });
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  dialog.addEventListener('close', () => {
    screenshotOpener?.focus({preventScroll: true});
    screenshotOpener = null;
  });

  // Native details keeps section navigation usable without JavaScript.
  const mobileNav = document.getElementById('mobileNav');
  const mobileNavToggle = document.getElementById('mobileNavToggle');
  if (mobileNav && mobileNavToggle) {
    let mobileNavHasFocus = false;
    mobileNav.addEventListener('focusin', () => { mobileNavHasFocus = true; });
    mobileNav.addEventListener('focusout', event => {
      if (event.relatedTarget && !mobileNav.contains(event.relatedTarget)) mobileNavHasFocus = false;
    });
    mobileNav.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || !mobileNav.open) return;
      event.preventDefault();
      event.stopPropagation();
      mobileNav.open = false;
      mobileNavToggle.focus({preventScroll: true});
    });
    mobileNav.addEventListener('click', event => {
      if (event.target.closest('a[href^="#"]')) { mobileNavHasFocus = false; mobileNav.open = false; }
    });
    document.addEventListener('click', event => {
      if (!mobileNav.contains(event.target)) { mobileNavHasFocus = false; mobileNav.open = false; }
    });
    window.matchMedia('(max-width: 767px)').addEventListener('change', event => {
      if (event.matches) return;
      const hadFocus = mobileNavHasFocus && document.hasFocus();
      mobileNavHasFocus = false;
      mobileNav.open = false;
      if (hadFocus) languageSwitch.focus({preventScroll: true});
    });
  }

  // Workspace tour: without this script every panel stays visible in reading order.
  const tabList = document.querySelector('.tour-tabs');
  const tabs = [...tabList.querySelectorAll('.tour-tab')];
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
  tabList.setAttribute('role', 'tablist');
  // The redesigned workspace browser is horizontal at every width.
  tabList.setAttribute('aria-orientation', 'horizontal');
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
    if (current < 0 || event.altKey || event.ctrlKey || event.metaKey) return;
    const forward = document.documentElement.dir === 'rtl' ? 'ArrowLeft' : 'ArrowRight';
    const backward = document.documentElement.dir === 'rtl' ? 'ArrowRight' : 'ArrowLeft';
    let next = null;
    if (event.key === forward || event.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (event.key === backward || event.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    selectTab(next, true);
  });
  selectTab(0, false);

  // Feature links select the actual gallery workspace, with normal anchors as fallback.
  document.querySelectorAll('[data-workspace]').forEach(link => {
    link.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
      const index = tabs.findIndex(tab => tab.id === `tab-${link.dataset.workspace}`);
      if (index >= 0) selectTab(index, false);
    });
  });

  function revealLinkedHelp() {
    const target = document.getElementById(location.hash.slice(1));
    const details = target?.closest('details');
    if (details) {
      details.open = true;
      const focusTarget = target === details ? details.querySelector('summary') : target;
      if (focusTarget !== details.querySelector('summary')) focusTarget.tabIndex = -1;
      focusTarget.focus({preventScroll: true});
      target.scrollIntoView({block:'start'});
    }
  }
  window.addEventListener('hashchange', revealLinkedHelp);
  document.addEventListener('click', event => {
    const link = event.target.closest?.('a[href^="#"]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const hash = link.getAttribute('href');
    if (hash === location.hash && document.getElementById(hash.slice(1))?.closest('details')) {
      event.preventDefault();
      revealLinkedHelp();
    }
  });
  // Active section navigation mirrors actual scroll position without changing
  // URLs, browser history or the user's current keyboard focus.
  const sectionLinks = [...document.querySelectorAll('.site-header .nav-section, .site-header .nav-download')];
  const sections = [...new Set(sectionLinks.map(link => document.getElementById(link.hash.slice(1))).filter(Boolean))];
  const markSection = id => sectionLinks.forEach(link => {
    if (link.hash === `#${id}`) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
  if ('IntersectionObserver' in window) {
    const visibleSections = new Set();
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) visibleSections.add(entry.target);
        else visibleSections.delete(entry.target);
      });
      const active = sections.find(section => visibleSections.has(section));
      if (active) markSection(active.id);
    }, {rootMargin:'-104px 0px -45% 0px', threshold:0});
    sections.forEach(section => observer.observe(section));
  }
  if ('IntersectionObserver' in window && !motionPreference.matches) {
    const reveals = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in-view');
          reveals.unobserve(entry.target);
        }
      });
    }, {threshold:0.08});
    document.querySelectorAll('.editing-steps article, .start-options li, .ai-options article').forEach(node => {
      node.classList.add('motion-ready');
      reveals.observe(node);
    });
  }
  renderLanguage();
  revealLinkedHelp();
})();
