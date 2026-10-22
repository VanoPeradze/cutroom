import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync, readdirSync} from 'node:fs';
import {downloadEntries, assertPublishable} from './prepare-download.mjs';

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

test('Windows and Mac have separate archives with an optional combined download and exact source', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  const buttons = [...html.matchAll(/<a\b[^>]*class="[^"]*\bbutton\b[^"]*"[^>]*>/g)];
  assert.equal(buttons.length, 2);
  assert.equal(new Set(buttons.map(row => row[0].match(/href="([^"]+)"/)[1])).size, 2);
  for (const platform of ['windows', 'mac']) {
    const entry = release.platforms[platform];
    const links = linksTo(html, entry.url).filter(link => /\bdownload-link\b/.test(link[1]));
    assert.equal(links.length, 1);
    assert.match(links[0][1], /\bdownload-link\b/);
    assert.doesNotMatch(links[0][1], /\sdownload(?:\s|=|$)/, 'Cross-origin downloads rely on GitHub attachment headers');
    assertLocalized(links[0]);
    const mirror = linksTo(region('details', 'install-help'), `/downloads/${entry.filename}`);
    assert.equal(mirror.length, 1);
    assertLocalized(mirror[0]);
    assert.match(mirror[0][2], /mirror/i);
    assert.ok(linksTo(html, `/downloads/${entry.filename}.sha256`).length >= 1);
  }
  assert.equal(release.filename, 'CUTROOM-1.2-Beta-20261022-maintenance1.zip');
  assert.equal(release.platforms.windows.filename, 'CUTROOM-1.2-Beta-Windows-20261022-maintenance1.zip');
  assert.equal(release.platforms.mac.filename, 'CUTROOM-1.2-Beta-Mac-20261022-maintenance1.zip');
  assert.notEqual(release.platforms.mac.filename, release.filename);
  assert.ok(!release.platforms.mac.folder, 'The standalone Mac launcher is beside App, without a mac subfolder');
  assert.equal(linksTo(html, release.url).length, 1); // Optional combined ZIP help link, separate from the Mac button.
  assert.equal(linksTo(html, `/downloads/${release.filename}`).length, 1);
  assert.equal(linksTo(html, `/downloads/${release.filename}.sha256`).length, 1);
  assert.match(html, /Mac has its own ZIP\. Extract it and run START CUTROOM\.command beside App\./);
  assert.match(region('details', 'install-help'), /The optional combined ZIP has exactly two folders: windows and mac/);
  const source = release.source_archive;
  assert.equal(source.filename, 'SOURCE-203d164.zip');
  for (const url of [source.url, `/downloads/${source.filename}`, `/downloads/${source.filename}.sha256`]) assert.equal(linksTo(html,url).length,1);
  assert.equal(downloadEntries(release).length,4);
  assert.doesNotMatch(html, /href="[^"]*Linux[^"\n]*\.zip/i);
  assert.ok(linksTo(html, `${repository}/blob/master/docs/PLATFORMS.md#linux-source-based-development-path`).length);
});

test('download metadata pins a dated release and preserves Expo mirrors and provenance', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  assert.equal(release.github_release.tag, 'v1.2-beta-20261022-maintenance1');
  assert.equal(release.github_release.previous_public_tag, 'v1.2-beta-20261019-hotfix1');
  assert.equal(release.github_release.tag_commit, release.source_commit);
  assert.equal(release.github_release.package_bytes_changed, false);
  assert.equal(release.github_release.url, `${repository}/releases/tag/${release.github_release.tag}`);
  for (const entry of downloadEntries(release)) {
    assert.equal(entry.url, `${repository}/releases/download/${release.github_release.tag}/${entry.filename}`);
    assert.deepEqual(entry.mirrors, [`https://cutroom-studio.expo.app/downloads/${entry.filename}`]);
  }
});

test('public beta retains exact automated native provenance and visible pending acceptance', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  assertPublishable(release);
  assert.equal(release.release_state,'beta');
  assert.equal(release.full_release_qualified,false);
  assert.equal(release.source_commit,'203d164d04ef9d610cc9aedf55fe640b99f19f85');
  assert.equal(release.github_release.tag,'v1.2-beta-20261022-maintenance1');
  assert.equal(release.native_validation.run_id,39723914568);
  assert.equal(release.validated_pr_head,'39d319c832a079dd55600df233bfa77e98bdc518');
  assert.equal(release.native_validation.transcription_run,false);
  for (const architecture of ['arm64','x64']) {
    const checks = release.native_validation.architectures[architecture];
    assert.equal(checks.offline_checks_passed,69);
    assert.equal(checks.feature_tests_passed,348);
    assert.equal(checks.required_cases_passed,50);
    assert.equal(checks.skipped,0);
  }
  assert.match(html,/Public beta\./);
  assert.match(html,/Windows requires WinGet and Microsoft Visual C\+\+ x64 runtime first\./);
  assert.match(html,/The required Visual C\+\+ runtime is not installed by the launcher\./);
  assert.equal(release.windows_fresh_install_acceptance,'passed-scoped-windows-10-sandbox');
  assert.equal(release.windows_fresh_install.result,'passed_scoped_guest_install_exports_and_process_restart');
  assert.equal(release.windows_fresh_install.application_source_commit,release.source_commit);
  assert.equal(release.windows_fresh_install.source_tree,release.source_tree);
  assert.equal(release.windows_fresh_install.archive_sha256,release.platforms.windows.sha256);
  assert.equal(release.windows_fresh_install.archive_sha256,'9a6d20825ad9f66dd29859fa683519400f8756bc6c572f66a8c82962060433ee');
  assert.equal(release.windows_fresh_install.manifest_sha256,'1782ffd5ce91d5813d3e7ba93cdeae0877bf60751c6cd7f548517d8886077c82');
  assert.equal(release.windows_fresh_install.prerequisite_installed_by_launcher,false);
  for(const field of ['fresh_install','portrait_encoded_export','landscape_encoded_export','full_decode',
    'process_restart_acceptance','saved_project_and_export_bytes','model_cache_audit']) assert.equal(release.windows_fresh_install[field],'passed');
  assert.equal(release.windows_fresh_install.encoded_export_count,2);
  assert.equal(release.windows_fresh_install.configuration_unchanged,true);
  assert.equal(release.windows_fresh_install.restart_acceptance,'application-process-only');
  assert.equal(release.windows_fresh_install.os_reboot_acceptance,'not_performed');
  assert.equal(release.windows_fresh_install.model_inference,'not_run');
  for(const field of ['physical_device_acceptance','physical_windows11_acceptance','ui_acceptance']) assert.equal(release.windows_fresh_install[field],'pending');
  for(const binary of ['ffmpeg','ffprobe']) {
    const runtime=release.windows_fresh_install.runtime[binary];
    assert.equal(runtime.major,9);
    assert.match(runtime.version_first_line,new RegExp(`^${binary} version 9\\.0\\.2-`));
    assert.match(runtime.sha256,/^[a-f0-9]{64}$/);
  }
  assert.match(release.windows_fresh_install.scope,/Windows 10 Sandbox/);
  assert.match(release.windows_fresh_install.scope,/no human UI\/listening, physical Windows 11, OS reboot, SmartScreen, quarantine or model acceptance/);
  assert.equal(release.windows_conditional_setup,undefined,'Previous Windows results must not qualify the new downloads');
  const previous = release.historical_windows_validation.find(entry=>entry.release_tag==='v1.2-beta-20261018');
  assert.ok(previous,'Preserve the previous Windows validation as history');
  assert.match(previous.scope,/Historical only/);
  assert.equal(previous.application_source_commit,'fe35453119305a33e0890a25e627a4fa47ad353d');
  assert.equal(previous.archive_sha256,'d20f33568ebaeb702717baade8e2a76dda88cb10e81461d61cc48ec96f725aca');
  assert.notEqual(previous.application_source_commit,release.source_commit);
  assert.equal(previous.windows_fresh_install_acceptance,'failed-native-dll-check');
  assert.equal(previous.windows_fresh_install.result,'failed');
  assert.equal(previous.windows_conditional_setup.application_source_commit,previous.application_source_commit);
  assert.equal(previous.windows_conditional_setup.archive_sha256,previous.archive_sha256);
  assert.equal(previous.windows_conditional_setup.result,'isolated_guest_install_and_first_http_launch_passed_with_explicit_winget_and_msvc_prerequisites');
  assert.equal(previous.windows_conditional_setup.scoped_guest_acceptance,'passed');
  assert.equal(previous.windows_conditional_setup.full_guest_acceptance,'not-established-beyond-scoped-install-and-first-http');
  assert.deepEqual(previous.windows_conditional_setup.homepage,{status_code:200,contains_cutroom:true});
  assert.equal(previous.windows_conditional_setup.configuration.before_sha256,previous.windows_conditional_setup.configuration.after_sha256);
  for(const field of ['physical_device_acceptance','restart_acceptance','ui_acceptance']) assert.equal(previous.windows_conditional_setup[field],'pending');
  assert.deepEqual(previous.windows_conditional_setup.health.models,[]);
  const preceding = release.historical_windows_validation.find(entry=>entry.release_tag==='v1.2-beta-20261019');
  assert.ok(preceding,'Preserve the exact preceding package regression as history');
  assert.equal(preceding.application_source_commit,'7019b6423ce9d66531e933ee5cac42968f9e96e7');
  assert.equal(preceding.archive_sha256,'24fc4767c7c80547308f03484c043d58e81c2592dcfdce6288e96cd3a98ccb89');
  const regression=preceding.subsequent_exact_package_validation;
  assert.equal(regression.source_commit,preceding.application_source_commit);
  assert.equal(regression.archive_sha256,preceding.archive_sha256);
  assert.equal(regression.status,'blocked_or_failed');
  assert.equal(regression.observed_error,"Unrecognized option 'filter_complex_script'");
  assert.equal(regression.observed_ffmpeg,'Gyan.FFmpeg 9.0.2');
  assert.equal(regression.actual_results.completed_export_count,0);
  assert.match(regression.scope,/Historical regression only; does not qualify the hotfix/);
  const runtimeHelp=linksTo(region('details','install-help'),'https://aka.ms/vc14/vc_redist.x64.exe');
  assert.equal(runtimeHelp.length,1);
  assertLocalized(runtimeHelp[0]);
  assert.match(html,/Automated checks do not replace a test on your computer\./);
  assert.match(html,/Transcription and AI, physical-device installation, Finder\/Gatekeeper\/Safari/);
  assert.match(html,/representative English\/Hebrew editing and listening still need manual acceptance\./);
  assert.match(html,/confirm that both sources show the same moment before relying on synchronization/);
  assert.match(html,/an empty B track does not create camera footage/);
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
  assert.match(languageLink[0][2], /[\u0590-\u05ff]/);
  assert.doesNotMatch(languageLink[0][1], /aria-label=/, 'The visible language name is the accessible name');
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
  assert.match(hero, /Actual editor · Captured 19 October 2026/);
  assert.match(hero, /No third-party footage or real person is shown\./);
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
  assert.match(html, /<dialog\b[^>]*id="imageDialog"[^>]*aria-labelledby="imageDialogTitle"[^>]*aria-describedby="imageDialogHelp"/);
  assert.match(html, /<button\b[^>]*id="closeImage"/);
});

test('skip navigation, named mobile links and tab hosts retain valid accessible semantics', () => {
  assert.equal([...html.matchAll(/<main\b/g)].length, 1);
  assert.match(html, /<main\b[^>]*id="main"[^>]*tabindex="-1"/);
  assert.match(html, /<a\b[^>]*class="skip"[^>]*href="#main"/);
  assert.doesNotMatch(html, /tabindex="[1-9]\d*"/);
  const github = linksTo(region('nav'), repository)[0];
  assert.match(github[1], /aria-label="[^"]*GitHub[^"]*"/);
  assert.match(github[1], /data-he-aria="[^"]*GitHub[^"]*"/);
  assert.match(html, /class="download-action" role="group" aria-label="[^"]+"/);
  assert.doesNotMatch(html, /<article\b[^>]*class="tour-panel"/);
  assert.equal(linksTo(region('footer'), '#accessibility-help').length, 1);
  const help = region('details', 'accessibility-help');
  assert.match(help, /<summary\b[^>]*data-he="[^"]*[\u0590-\u05ff]/);
  assertLocalized(linksTo(help, `${repository}/issues/new/choose`)[0]);
});

test('theme text and dual focus colors retain readable contrast', () => {
  const tokens = Object.fromEntries([...css.matchAll(/--([a-z-]+):\s*(#[a-f0-9]{6})\b/gi)].map(match => [match[1], match[2]]));
  function luminance(hex) {
    const channels = hex.slice(1).match(/../g).map(part => {
      const value = parseInt(part, 16) / 255;
      return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  }
  function contrast(first, second) {
    const pair = [luminance(first), luminance(second)].sort((a, b) => b - a);
    return (pair[0] + 0.05) / (pair[1] + 0.05);
  }
  for (const foreground of ['text', 'dim', 'muted']) {
    for (const background of ['bg', 'panel']) {
      assert.ok(contrast(tokens[foreground], tokens[background]) >= 4.5, `${foreground} on ${background} must retain text contrast`);
    }
  }
  assert.ok(contrast(tokens.ink, tokens.cyan) >= 4.5, 'Download labels need readable contrast');
  for (const foreground of ['#183127', '#476353', '#486555']) assert.ok(contrast(foreground, '#e7eadd') >= 4.5);
  assert.ok(contrast(tokens.cyan, tokens.bg) >= 3 && contrast(tokens.bg, '#e7eadd') >= 3,
    'The two focus-ring colors must remain distinguishable on dark and light sections');
  assert.match(css, /:focus-visible\s*\{[^}]*box-shadow:/);
  assert.match(css, /@media\(forced-colors:active\)/);
});

test('the workspace tour follows the editor order and stays readable without script', () => {
  const tabs = [...html.matchAll(/<button\b[^>]*class="tour-tab"[^>]*id="tab-([a-z]+)"[^>]*aria-controls="panel-\1"[^>]*>([\s\S]*?)<\/button>/g)];
  assert.deepEqual(tabs.map(tab => tab[1]), ['media', 'edit', 'layout', 'audio', 'captions', 'output']);
  for (const [, id, label] of tabs) {
    assert.match(label, /<span\b[^>]*data-he="[^"]*[֐-׿]/, `${id} tab needs a Hebrew label`);
    const panel = html.match(new RegExp(`<div\\b[^>]*id="panel-${id}"[^>]*>`))?.[0];
    assert.ok(panel, `Missing ${id} panel`);
    assert.match(panel, new RegExp(`aria-labelledby="tab-${id}"`));
    assert.match(panel, /role="region"/, 'Without JavaScript every named workspace remains a valid region');
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
