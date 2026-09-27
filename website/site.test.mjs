import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';

const html = readFileSync(new URL('./public/index.html', import.meta.url), 'utf8');
const privacy = readFileSync(new URL('./public/privacy.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('./public/styles.css', import.meta.url), 'utf8');
const script = readFileSync(new URL('./public/site.js', import.meta.url), 'utf8');
const repository = 'https://github.com/VanoPeradze/cutroom';

function region(tag, id) {
  const selector = id ? `[^>]*\\bid=["']${id}["']` : '';
  const match = html.match(new RegExp(`<${tag}\\b${selector}[^>]*>([\\s\\S]*?)</${tag}>`, 'i'));
  assert.ok(match, `Missing ${id ? `#${id}` : tag} region`);
  return match[1];
}

function linksTo(markup, url) {
  return [...markup.matchAll(/<a\b([^>]*)>([\s\S]*?)<\/a>/gi)]
    .filter(link => link[1].match(/\bhref=["']([^"']+)["']/i)?.[1] === url);
}

function assertLocalized(link) {
  assert.match(link[0], /\bdata-he=["'][^"']*[\u0590-\u05ff][^"']*["']/);
  // Assert visible text in this static fixture; this is not an HTML sanitizer.
  assert.match(link[0], />[^<>]*[A-Za-z][^<>]*</, 'The default link text must be English');
}

test('repository links appear in navigation, download section, and footer', () => {
  assert.equal(linksTo(html, repository).length, 3);
  for (const markup of [region('nav'), region('section', 'download'), region('footer')]) {
    assert.equal(linksTo(markup, repository).length, 1);
  }
  assertLocalized(linksTo(region('section', 'download'), repository)[0]);
});

test('the FAQ offers a localized GitHub issue link', () => {
  const links = linksTo(region('section', 'help'), `${repository}/issues/new/choose`);
  assert.equal(links.length, 1);
  assertLocalized(links[0]);
});

test('language switching cannot replace links with plain text', () => {
  // site.js replaces each data-he element's contents with textContent in Hebrew.
  for (const element of html.matchAll(/<([a-z][\w-]*)\b([^>]*\bdata-he=["'][^"']*["'][^>]*)>([\s\S]*?)<\/\1>/gi)) {
    assert.doesNotMatch(element[3], /<a\b/i, 'Put data-he on the link or its text, not an ancestor');
  }
});

test('the editorial introduction keeps a bilingual heading and an identifiable real product image', () => {
  const hero = region('section');
  assert.equal([...html.matchAll(/<h1\b/g)].length, 1);
  const heading = hero.match(/<h1>([\s\S]*?)<\/h1>/)?.[1];
  assert.ok(heading);
  for (const line of heading.matchAll(/<(?:span|em)\b([^>]*)>([^<]+)<\/(?:span|em)>/g)) {
    assert.match(line[1], /data-he="[^"]*[\u0590-\u05ff]/);
    assert.match(line[2], /[A-Za-z]/);
  }
  assert.match(hero, /class="hero-aside"/);
  assert.match(hero, /class="hero-stage"/);
  const image = hero.match(/<img\b[^>]*src="\/assets\/editor\.png\?v=20260927"[^>]*>/)?.[0];
  assert.ok(image, 'The introductory image must show the actual editor');
  assert.match(image, /\balt="[^"]+"/);
  assert.match(image, /\bdata-he-alt="[^"]*[\u0590-\u05ff]/);
  assert.match(image, /fetchpriority="high"/);
  assert.match(hero, /Actual editor · Synthetic demo footage/);
});

test('product-tour controls retain accessible targets and bilingual group labels', () => {
  const tour = region('section', 'inside');
  assert.match(tour, /class="tour-controls" role="group" aria-label="Product tour"/);
  const controls = [...tour.matchAll(/<button\b[^>]*\bdata-shot="([^"]+)"[^>]*>/g)];
  assert.deepEqual(controls.map(control => control[1]), ['editor', 'welcome', 'ai-options']);
  assert.equal(controls.filter(control => /aria-pressed="true"/.test(control[0])).length, 1);
  for (const control of controls) {
    assert.match(control[0], /aria-controls="tourImage tourCaption"/);
    assert.match(control[0], /aria-pressed="(?:true|false)"/);
  }
  assert.match(tour, /id="tourCaption" aria-live="polite"/);
  assert.match(script, /querySelector\('\.tour-controls'\)\.setAttribute\('aria-label', language === 'he' \? '[^']*[\u0590-\u05ff][^']*' : 'Product tour'\)/);
  assert.match(script, /querySelector\('\.format-strip'\)\.setAttribute\('aria-label', language === 'he' \? '[^']*[\u0590-\u05ff][^']*' : 'Video formats'\)/);
});

test('the editorial stylesheet provides visible focus and a reduced-motion path', () => {
  assert.match(css, /:focus-visible\s*\{[^}]*outline:\s*3px solid/);
  const reducedMotion = css.slice(css.indexOf('@media(prefers-reduced-motion:reduce)'));
  assert.match(reducedMotion, /html\s*\{scroll-behavior:auto\}/);
  assert.match(reducedMotion, /transition:none!important/);
  assert.match(reducedMotion, /animation:none!important/);
});

test('public website copy does not describe the repository as private', () => {
  assert.doesNotMatch(html, /private (?:GitHub )?(?:repository|repo)\b|\b(?:repository|repo) (?:is|remains) private|מאגר פרטי|המאגר (?:פרטי|נשאר פרטי)/i);
});

test('AI choices explain compatibility, Groq Free limits and independent credit', () => {
  assert.match(html, /OpenAI-compatible API/);
  assert.match(html, /word timestamps/);
  assert.match(html, /JSON-object/);
  assert.match(html, /free API tier with usage limits/);
  assert.match(html, /not sponsored or endorsed by Groq/);
  assert.ok(linksTo(html, 'https://console.groq.com/docs/rate-limits').length);
  assert.doesNotMatch(html, /Currently supports Groq only|This integration currently supports Groq only/);
});

test('download instructions identify the single launcher and simple folder layout', () => {
  assert.match(html, /Double-click START CUTROOM\.bat/);
  assert.match(html, /Just three items: START CUTROOM\.bat/);
  assert.match(html, /START HERE\.html for help, and App for technical files/);
  assert.doesNotMatch(html, /Double-click run_windows\.bat/);
});

test('the footer links to a privacy notice with readable English and Hebrew sections', () => {
  const links = linksTo(region('footer'), '/privacy.html');
  assert.equal(links.length, 1);
  assertLocalized(links[0]);
  for (const [id, language, direction] of [['english', 'en', 'ltr'], ['hebrew', 'he', 'rtl']]) {
    assert.match(privacy, new RegExp(`<section id="${id}" lang="${language}" dir="${direction}"`));
    assert.equal(linksTo(privacy, `#${id}`).length, 2);
  }
  assert.doesNotMatch(privacy, /<script\b|\bhidden\b/i, 'Both languages must be readable without scripts');
  assert.equal(linksTo(privacy, '/?lang=he').length, 2);
});

test('the notice distinguishes hosting, local editing and optional cloud processing', () => {
  assert.match(privacy, /website's own code does not set or read cookies/);
  assert.match(privacy, /hosting or security providers can never use essential cookies/);
  assert.match(privacy, /IP address, requested URL, request time and browser information/);
  assert.match(privacy, /Visiting this website does not upload your recordings/);
  assert.match(privacy, /If you choose and confirm cloud AI/);
  assert.equal(linksTo(privacy, 'https://expo.dev/privacy').length, 2);
  assert.doesNotMatch(privacy, /href="[^"]*\/issues\b/i, 'Privacy requests must not be sent to public issues');
  assert.equal(linksTo(privacy, 'mailto:Vano17p@gmail.com').length, 2);
  for (const id of ['english', 'hebrew']) {
    const section = privacy.match(new RegExp(`<section id="${id}"[^>]*>([\\s\\S]*?)</section>`))?.[1];
    assert.ok(section, `Missing ${id} privacy section`);
    assert.equal(linksTo(section, 'mailto:Vano17p@gmail.com').length, 1);
  }
  assert.doesNotMatch(privacy, /No dedicated privacy email|trusted private channel/);
});

test('website resources remain local with no tracking or browser-storage APIs', () => {
  const publicRoot = new URL('./public/', import.meta.url);
  for (const filename of readdirSync(publicRoot, {recursive: true}).filter(name => /\.(?:html|css|js)$/.test(name))) {
    const source = readFileSync(new URL(filename.replaceAll('\\', '/'), publicRoot), 'utf8');
    if (filename.endsWith('.html')) {
      assert.doesNotMatch(source, /<(?:iframe|object|embed|form)\b|\b(?:srcset|ping)\s*=/i, filename);
      for (const tag of source.matchAll(/<(?:script|img|link)\b[^>]*>/gi)) {
        if (/<link\b/i.test(tag[0]) && /rel="canonical"/i.test(tag[0])) continue;
        const url = tag[0].match(/\b(?:src|href)="([^"]+)"/i)?.[1];
        assert.ok(url && (/^\/(?!\/)/.test(url) || url.startsWith('data:image/')), `Unexpected resource in ${filename}: ${tag[0]}`);
      }
    } else if (filename.endsWith('.css')) {
      assert.doesNotMatch(source, /@import\b|url\(\s*["']?(?:https?:)?\/\//i, filename);
    } else {
      assert.doesNotMatch(source, /document\s*\.\s*cookie\b|\bcookieStore\b|\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bsendBeacon\b|\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b|\bserviceWorker\b/, filename);
    }
  }
});
