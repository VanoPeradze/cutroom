(() => {
  const translations = [...document.querySelectorAll('[data-he]')].map(node => ({node, en: node.innerHTML, he: node.dataset.he}));
  const imageTranslations = [...document.querySelectorAll('[data-he-alt]')].map(node => ({node, en: node.alt, he: node.dataset.heAlt}));
  const languageSwitch = document.getElementById('languageSwitch');
  const tourImage = document.getElementById('tourImage');
  const caption = document.getElementById('tourCaption');
  const dialog = document.getElementById('imageDialog');
  const expanded = document.getElementById('expandedImage');
  const tourButtons = [...document.querySelectorAll('[data-shot]')];
  let language = new URL(location.href).searchParams.get('lang') === 'he' ? 'he' : 'en';
  let currentShot = 'editor';
  const shots = {
    editor: {en: 'Independent A/B tracks, editable layouts and a live preview. The image uses synthetic test footage, not an AI-generated result.', he: 'ערוצי A/B נפרדים, פריסות ניתנות לשינוי ותצוגה מקדימה. התמונה משתמשת בחומר בדיקה סינתטי, לא בתוצאה שנוצרה ב־AI.', alt: {en: 'CUTROOM editor with separate A/B timeline tracks and synthetic test footage', he: 'עורך CUTROOM עם ערוצי טיימליין A/B נפרדים וחומר בדיקה סינתטי'}},
    welcome: {en: 'Choose a Short, a YouTube video or a manual edit. Local model setup is visible before your first AI edit.', he: 'בחרו Short, סרטון יוטיוב או עריכה ידנית. הכנת המודלים המקומיים מופיעה לפני העריכה הראשונה עם AI.', alt: {en: 'CUTROOM welcome screen with three workflows and local setup guidance', he: 'מסך הכניסה של CUTROOM עם שלושה מסלולי עריכה והכוונה להגדרת AI מקומי'}},
    'ai-options': {en: 'Compare AI modes and inspect local models. Downloads require confirmation. This example correctly reports that the Story engine still needs installation.', he: 'השוו אפשרויות AI ובדקו מודלים מקומיים. הורדות דורשות אישור. בדוגמה הזו מוצג שמנוע Story עדיין דורש התקנה.', alt: {en: 'CUTROOM AI connection and local model setup screen', he: 'מסך חיבור ה־AI והכנת המודלים המקומיים של CUTROOM'}}
  };
  function renderShot() {
    tourImage.src = '/assets/' + currentShot + '.png';
    tourImage.alt = shots[currentShot].alt[language];
    caption.textContent = shots[currentShot][language];
    tourButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.shot === currentShot)));
    expanded.src = tourImage.src;
    expanded.alt = tourImage.alt;
  }
  function renderLanguage() {
    document.documentElement.lang = language;
    document.documentElement.dir = language === 'he' ? 'rtl' : 'ltr';
    for (const item of translations) {
      if (language === 'he') item.node.textContent = item.he;
      else item.node.innerHTML = item.en;
    }
    imageTranslations.forEach(item => { item.node.alt = item[language]; });
    languageSwitch.textContent = language === 'he' ? 'English' : 'עברית';
    languageSwitch.lang = language === 'he' ? 'en' : 'he';
    languageSwitch.setAttribute('aria-label', language === 'he' ? 'Read this website in English' : 'קריאת האתר בעברית');
    languageSwitch.href = language === 'he' ? '?lang=en' + location.hash : '?lang=he' + location.hash;
    document.title = language === 'he' ? 'CUTROOM — החומר שלכם. העריכה שלכם.' : 'CUTROOM — Your footage. Your edit.';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עריכת וידאו חינמית בקוד פתוח ליוצרי תוכן. התחילו מטיוטה בעזרת AI או ערכו ידנית. הורידו את הבטא ל־Windows ולמדו איך מתחילים.'
      : 'Free, open-source video editing for creators. Start with an AI-assisted draft or edit manually. Download the Windows beta and learn how to get started.';
    document.querySelector('nav').setAttribute('aria-label', language === 'he' ? 'ניווט ראשי' : 'Main navigation');
    document.getElementById('expandShot').setAttribute('aria-label', language === 'he' ? 'הגדלת תמונת המוצר' : 'Enlarge product screenshot');
    dialog.setAttribute('aria-label', language === 'he' ? 'תמונת המוצר' : 'Product screenshot');
    renderShot();
  }
  languageSwitch.addEventListener('click', event => {
    event.preventDefault();
    language = language === 'he' ? 'en' : 'he';
    const url = new URL(location.href);
    if (language === 'he') url.searchParams.set('lang', 'he'); else url.searchParams.delete('lang');
    history.replaceState(null, '', url);
    renderLanguage();
  });
  tourButtons.forEach(button => button.addEventListener('click', () => { currentShot = button.dataset.shot; renderShot(); }));
  document.getElementById('expandShot').addEventListener('click', () => dialog.showModal());
  document.getElementById('closeImage').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  function revealLinkedHelp() {
    const target = document.getElementById(location.hash.slice(1));
    if (target?.tagName === 'DETAILS') { target.open = true; target.scrollIntoView({block:'start'}); }
  }
  window.addEventListener('hashchange', revealLinkedHelp);
  renderLanguage();
  revealLinkedHelp();
})();
