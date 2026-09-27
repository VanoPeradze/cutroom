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
    editor: {en: 'Add your own text or import SRT/VTT captions, then move and trim each layer on the timeline. No AI needed. This is synthetic test footage, not an AI-generated result.', he: 'הוסיפו טקסט או ייבאו כתוביות SRT/VTT, והזיזו וקצרו כל שכבה בטיימליין. ללא צורך ב־AI. זהו חומר בדיקה סינתטי, לא תוצאה שנוצרה ב־AI.', alt: {en: 'CUTROOM editor with custom text, imported captions and independent A/B timeline tracks; synthetic test footage', he: 'עורך CUTROOM עם טקסט אישי, כתוביות מיובאות וערוצי A/B עצמאיים; חומר בדיקה סינתטי'}},
    welcome: {en: 'Choose a Short, a YouTube video or a manual edit. Local model setup is visible before your first AI edit.', he: 'בחרו Short, סרטון יוטיוב או עריכה ידנית. הכנת המודלים המקומיים מופיעה לפני העריכה הראשונה עם AI.', alt: {en: 'CUTROOM welcome screen with three workflows and local setup guidance', he: 'מסך הכניסה של CUTROOM עם שלושה מסלולי עריכה והכוונה להגדרת AI מקומי'}},
    'ai-options': {en: 'Choose local models, Groq Free tier or your compatible API. Model downloads require confirmation; the models shown as downloaded are already installed on this demo computer, not bundled with CUTROOM.', he: 'בחירה בין מודלים מקומיים, המסלול החינמי של Groq או API תואם משלכם. הורדות מודלים דורשות אישור; המודלים שמסומנים כמותקנים כבר נמצאים במחשב ההדגמה, ולא כלולים בהורדת CUTROOM.', alt: {en: 'CUTROOM 1.1 Beta AI options and local model downloads in day mode', he: 'אפשרויות AI והורדת מודלים מקומיים ב־CUTROOM 1.1 Beta במצב יום'}}
  };
  function renderShot() {
    tourImage.src = '/assets/' + currentShot + '.png?v=20260928-text2';
    tourImage.width = currentShot === 'editor' ? 1440 : 1280;
    tourImage.height = currentShot === 'editor' ? 900 : 720;
    tourImage.alt = shots[currentShot].alt[language];
    caption.textContent = shots[currentShot][language];
    tourButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.shot === currentShot)));
    expanded.src = tourImage.src;
    expanded.alt = tourImage.alt;
    expanded.width = tourImage.width;
    expanded.height = tourImage.height;
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
    document.title = language === 'he' ? 'CUTROOM 1.1 Beta — החומר שלכם. העריכה שלכם.' : 'CUTROOM 1.1 Beta — Your footage. Your edit.';
    document.querySelector('meta[name="description"]').content = language === 'he'
      ? 'עריכת וידאו חינמית בקוד פתוח ליוצרי תוכן. התחילו מטיוטה בעזרת AI או ערכו ידנית. הורידו את הבטא ל־Windows ולמדו איך מתחילים.'
      : 'Free, open-source video editing for creators. Start with an AI-assisted draft or edit manually. Download the Windows beta and learn how to get started.';
    document.querySelector('nav').setAttribute('aria-label', language === 'he' ? 'ניווט ראשי' : 'Main navigation');
    document.querySelector('.tour-controls').setAttribute('aria-label', language === 'he' ? 'סיור במוצר' : 'Product tour');
    document.querySelector('.format-strip').setAttribute('aria-label', language === 'he' ? 'סוגי סרטונים' : 'Video formats');
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
