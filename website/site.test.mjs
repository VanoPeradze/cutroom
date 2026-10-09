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

test('one download area offers distinct real Windows and Mac archives, with Linux guide only', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  const buttons = [...html.matchAll(/<a\b[^>]*class="[^"]*\bbutton\b[^"]*"[^>]*>/g)];
  assert.equal(buttons.length, 2);
  assert.equal(new Set(buttons.map(row => row[0].match(/href="([^"]+)"/)[1])).size, 2);
  for (const platform of ['windows', 'mac']) {
    const entry = release.platforms[platform];
    const links = linksTo(html, `/downloads/${entry.filename}`);
    assert.equal(links.length, 1);
    assert.match(links[0][1], /\bdownload\b/);
    assertLocalized(links[0]);
    assert.equal(linksTo(html, `/downloads/${entry.filename}.sha256`).length, 1);
  }
  assert.equal(linksTo(html, `/downloads/${release.filename}`).length, 1);
  assert.equal(linksTo(html, `/downloads/${release.filename}.sha256`).length, 1);
  assert.doesNotMatch(html, /href="[^"]*Linux[^"\n]*\.zip/i);
  assert.ok(linksTo(html, `${repository}/blob/master/docs/PLATFORMS.md#linux-source-based-development-path`).length);
});

test('source and issue links remain visible without competing with download', () => {
  const source = linksTo(region('nav'), repository)[0];
  assert.ok(source);
  assert.match(source[2], /GitHub/);
  assert.match(source[2], /<img\b[^>]*src="\/assets\/github-mark\.svg"[^>]*alt=""/);
  assert.equal(linksTo(region('footer'), repository).length, 1);
  const issue = linksTo(region('footer'), `${repository}/issues/new/choose`);
  assert.equal(issue.length, 1);
  assertLocalized(issue[0]);
  assert.equal(linksTo(html, '/downloads/LICENSE').length, 1);
  for (const guide of ['USER_GUIDE_EN.md', 'USER_GUIDE_HE.md']) {
    assert.equal(linksTo(html, `/downloads/${guide}`).length, 1);
  }
});

test('language switching preserves links, images and actionable controls', () => {
  for (const element of html.matchAll(/<([a-z][\w-]*)\b([^>]*\bdata-he=["'][^"']*["'][^>]*)>([\s\S]*?)<\/\1>/gi)) {
    assert.doesNotMatch(element[3], /<a\b|<img\b|<svg\b/i, 'Translate text, not ancestors of interactive content');
  }
  assert.match(html, /<html\b[^>]*lang="en"[^>]*dir="ltr"/);
  const languageLink = linksTo(html, '?lang=he');
  assert.equal(languageLink.length, 1);
  assert.match(languageLink[0][1], /lang="he"/);
  assert.match(languageLink[0][1], /aria-label="Read this website in Hebrew"/);
});

test('the concise introduction shows an authentic bilingual dark editor preview', () => {
  const hero = region('section', 'download');
  assert.equal([...html.matchAll(/<h1\b/g)].length, 1);
  const heading = hero.match(/<h1>([\s\S]*?)<\/h1>/)?.[1];
  assert.ok(heading);
  const lines = [...heading.matchAll(/<(?:span|em)\b([^>]*)>([^<]+)<\/(?:span|em)>/g)];
  assert.equal(lines.length, 2);
  lines.forEach(line => { assert.match(line[1], /data-he="[^"]*[\u0590-\u05ff]/); assert.match(line[2], /[A-Za-z]/); });
  const image = hero.match(/<img\b[^>]*id="editorImage"[^>]*>/)?.[0];
  assert.ok(image, 'The first section must show the editor');
  assert.match(image, /src="\/assets\/studio-edit\.png\?v=[a-zA-Z0-9-]+"/);
  assert.match(image, /width="1600" height="900"/);
  assert.match(image, /alt="[^"]+"/);
  assert.match(image, /data-he-alt="[^"]*[\u0590-\u05ff]/);
  assert.match(image, /fetchpriority="high"/);
  const imageUrl = image.match(/src="([^"]+)"/)[1];
  assert.ok(region('dialog', 'imageDialog').includes(`src="${imageUrl}"`), 'Enlargement must show the same real screenshot');
  assert.match(hero, /Actual editor · Synthetic gameplay demo/);
  assert.match(hero, /No third-party game is shown\./);
  assert.doesNotMatch(html, /(?:welcome|ai-options)\.png|\bdata-shot=|<table\b/);
});

test('platform download help remains readable and localized', () => {
  const setup = region('details', 'install-help');
  for (const platform of ['windows', 'mac', 'linux']) {
    assert.match(setup, new RegExp(`id="${platform}-install"[^>]*data-he="[^"]*[\\u0590-\\u05ff]`));
  }
  assert.match(setup, /Double-click START CUTROOM\.bat/);
  assert.match(setup, /START CUTROOM\.command/);
  assert.match(setup, /exactly two folders: windows and mac/);
  assert.match(setup, /macOS 15\+/);
  assert.match(setup, /Local transcription uses the CPU/);
  assert.match(setup, /not a signed Mac app/);
  assert.match(setup, /uses Python 3\.12\. If it isn't installed, Windows setup downloads a private copy/);
  assert.match(setup, /into the CUTROOM folder\./);
  assert.match(setup, /Linux: source only, with no packaged download or verified native Linux QA/);
  assert.ok(linksTo(setup, `${repository}/blob/master/docs/PLATFORMS.md`).length);
  assert.ok(linksTo(setup, `${repository}/blob/master/docs/MAC_BETA.md`).length);
});

test('optional AI and privacy information stay accessible with full guides', () => {
  const ai = region('details', 'ai-help');
  assert.match(ai, /Manual editing and export need no AI models or account/);
  assert.match(ai, /choice and consent/);
  assert.match(ai, /provider quotas and charges apply/);
  assert.ok(linksTo(ai, `${repository}/blob/master/docs/AI_CONNECTIONS.md`).length);
  assert.ok(linksTo(region('details', 'privacy-help'), '/privacy.html').length);
  for (const id of ['install-help', 'ai-help', 'privacy-help']) {
    assert.match(region('details', id), /<summary\b[^>]*data-he="[^"]*[\u0590-\u05ff]/);
  }
});

test('keyboard focus, reduced motion and screenshot enlargement remain available', () => {
  assert.match(css, /:focus-visible\s*\{[^}]*outline:\s*3px solid/);
  const reducedMotion = css.slice(css.indexOf('@media(prefers-reduced-motion:reduce)'));
  assert.match(reducedMotion, /html\s*\{scroll-behavior:auto\}/);
  assert.match(reducedMotion, /transition:none!important/);
  assert.match(reducedMotion, /animation:none!important/);
  assert.match(html, /<button\b[^>]*id="expandShot"[^>]*aria-label="[^"]+"/);
  assert.match(html, /<dialog\b[^>]*id="imageDialog"[^>]*aria-label="[^"]+"/);
  assert.match(html, /<button\b[^>]*id="closeImage"/);
});

test('the workspace tour follows the editor order and stays readable without script', () => {
  const tabs = [...html.matchAll(/<button\b[^>]*class="tour-tab"[^>]*id="tab-([a-z]+)"[^>]*aria-controls="panel-\1"[^>]*>([\s\S]*?)<\/button>/g)];
  assert.deepEqual(tabs.map(tab => tab[1]), ['media', 'edit', 'layout', 'audio', 'captions', 'output']);
  for (const [, id, label] of tabs) {
    assert.match(label, /<span\b[^>]*data-he="[^"]*[֐-׿]/, `${id} tab needs a Hebrew label`);
    const panel = html.match(new RegExp(`<article\\b[^>]*id="panel-${id}"[^>]*>`))?.[0];
    assert.ok(panel, `Missing ${id} panel`);
    assert.match(panel, new RegExp(`aria-labelledby="tab-${id}"`));
    assert.doesNotMatch(panel, /\bhidden\b/, 'Panels are hidden only by the script that makes tabs usable');
  }
  assert.doesNotMatch(html, /role="tab(?:list|panel)?"/, 'Tab roles are added by script, never promised in static HTML');
  assert.match(css, /\.tour-tabs\{display:none\}/);
  assert.match(script, /setAttribute\('role', 'tablist'\)/);
  for (const key of ['ArrowLeft', 'ArrowRight', 'Home', 'End']) assert.match(script, new RegExp(`'${key}'`));
});

test('each workspace has a local, full-size, bilingual product screenshot', () => {
  const shots = [...html.matchAll(/<img\b[^>]*class="workspace-shot"[^>]*>/g)];
  assert.equal(shots.length, 6);
  for (const [index, name] of ['media', 'edit', 'layout', 'audio', 'captions', 'output'].entries()) {
    assert.ok(shots[index][0].includes(`/assets/studio-${name}.png?`));
    assert.match(shots[index][0], /data-he-alt="[^"]*[\u0590-\u05ff]/);
    assert.match(shots[index][0], /loading="lazy"/);
    const png = readFileSync(new URL(`./public/assets/studio-${name}.png`, import.meta.url));
    assert.equal(png.subarray(1, 4).toString(), 'PNG');
    assert.equal(png.readUInt32BE(16), 1600);
    assert.equal(png.readUInt32BE(20), 900);
  }
  assert.doesNotMatch(html, /class="(?:art|panel-art)\b/);
});

test('inline styles stay out of the strict CSP', () => {
  assert.doesNotMatch(html, /\sstyle\s*=/i, 'style-src blocks inline style attributes');
  assert.doesNotMatch(html, /<style\b/i);
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
