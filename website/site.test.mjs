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

test('the 1.3 beta uses exact Windows, shared Mac/combined and source downloads', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  const buttons = [...html.matchAll(/<a\b[^>]*class="(?:button|[^"]* button)(?: [^"]*)?"[^>]*>/g)];
  assert.equal(buttons.length, 2);
  assert.equal(new Set(buttons.map(row => row[0].match(/href="([^"]+)"/)[1])).size, 2);
  for (const platform of ['windows', 'mac']) {
    const entry = release.platforms[platform];
    const links = linksTo(html, entry.url).filter(link => /\bdownload-link\b/.test(link[1]));
    assert.equal(links.length, 1);
    assert.match(links[0][1], /\bdownload-link\b/);
    assert.doesNotMatch(links[0][1], /\sdownload(?:\s|=|$)/, 'Cross-origin downloads rely on GitHub attachment headers');
    assertLocalized(links[0]);
    const mirror = linksTo(region('details', 'install-help'), `/downloads/${entry.filename}`).filter(link => link[2].includes(platform === 'mac' ? 'Mac mirror' : 'Windows mirror'));
    assert.equal(mirror.length, 1);
    assertLocalized(mirror[0]);
    assert.match(mirror[0][2], /mirror/i);
    assert.ok(linksTo(html, `/downloads/${entry.filename}.sha256`).length >= 1);
  }
  assert.equal(release.filename, 'CUTROOM-1.3-Beta-combined-ba67003.zip');
  assert.equal(release.platforms.windows.filename, 'CUTROOM-1.3-Beta-Windows-ba67003.zip');
  assert.equal(release.platforms.mac.filename, 'CUTROOM-1.3-Beta-combined-ba67003.zip');
  assert.equal(release.platforms.mac.filename, release.filename);
  assert.equal(release.platforms.mac.folder,'mac', 'Mac uses the shared combined archive mac folder');
  assert.equal(linksTo(html, release.url).length, 2); // Optional combined ZIP help link, separate from the Mac button.
  assert.equal(linksTo(html, `/downloads/${release.filename}`).length, 2);
  assert.equal(linksTo(html, `/downloads/${release.filename}.sha256`).length, 2);
  assert.match(html, /Mac uses the combined ZIP\. Extract it, open mac, then run START CUTROOM\.command beside App\./);
  assert.match(region('details', 'install-help'), /The optional combined ZIP has exactly two folders: windows and mac/);
  const source = release.source_archive;
  assert.equal(source.filename, 'SOURCE-ba67003.zip');
  for (const url of [source.url, `/downloads/${source.filename}`, `/downloads/${source.filename}.sha256`]) assert.equal(linksTo(html,url).length,1);
  assert.equal(downloadEntries(release).length,3);
  assert.match(html, /1\.3 Beta · Hebrew-first speech and independent routing/);
  const update = region('details', 'update-status');
  assert.match(update, /if FFprobe is missing or unavailable, import explains how to repair and retry/);
  assert.match(update, /A failed replacement preserves your saved media and edits/);
  assert.match(update, /Saved silent overlays stay silent until you turn their sound on\./);
  assert.match(update, /It still flags a draft shorter than requested/);
  assert.match(update, /Layer sound plays at normal speed from Source in\./);
  assert.doesNotMatch(html, /In review|public 1\.2 beta until|not in the downloads yet/i);
  assert.doesNotMatch(html, /href="[^"]*Linux[^"\n]*\.zip/i);
  assert.ok(linksTo(html, `${repository}/blob/master/docs/PLATFORMS.md#linux-source-based-development-path`).length);
});

test('download metadata pins a dated release and preserves Expo mirrors and provenance', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url), 'utf8'));
  assert.equal(release.github_release.tag, 'v1.3-beta-20261111-hebrew1');
  assert.equal(release.github_release.previous_public_tag, 'v1.3-beta-20261111-gray1');
  assert.equal(release.github_release.tag_commit, release.source_commit);
  assert.equal(release.github_release.package_bytes_changed, true);
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
  assert.equal(release.source_commit,'ba67003726e80e0d394b1927b6b710f191a60157');
  assert.equal(release.github_release.tag,'v1.3-beta-20261111-hebrew1');
  assert.equal(release.native_validation.run_id,42977968863);
  assert.equal(release.validated_pr_head,'ba67003726e80e0d394b1927b6b710f191a60157');
  assert.equal(release.native_validation.head_commit,release.validated_pr_head);
  assert.equal(release.native_validation.application_source_commit,release.source_commit);
  assert.equal(release.native_validation.transcription_run,false);
  assert.equal(release.native_validation.review_record_commit,'acc6ceec1cbad8ac8b5382767df64b48fd1b7ae5');
  for (const architecture of ['arm64','x64']) {
    const checks = release.native_validation.architectures[architecture];
    assert.equal(checks.status,'passed');
    assert.equal(checks.offline_checks_passed,undefined);
    for (const key of ["status", "launcher_health_and_api", "restart_persistence", "repeat_launch", "different_data_port_collision", "source_audio_and_caption_checks", "offline_ready_setup", "installed_packages_unchanged"]) assert.equal(checks.installation_checks[key],'passed');
    assert.equal(checks.installation_checks.unicode_and_spaces_path,true);
    assert.equal(checks.feature_tests_passed,357);
    assert.equal(checks.required_cases_passed,50);
    assert.equal(checks.skipped,0);
    assert.equal(checks.source_audio_and_caption_checks,'passed');
    assert.equal(checks.job_id,architecture === 'arm64' ? 130386852359 : 130386852742);
    for (const gate of ['fresh_app_install','missing_pip_recovery','restart_persistence']) assert.equal(checks[gate],'passed');
    assert.equal(checks.combined_archive_sha256,release.sha256);
  }
  assert.match(html,/Public beta\./);
  assert.match(html,/Windows requires WinGet and Microsoft Visual C\+\+ x64 runtime first\./);
  assert.match(html,/The required Visual C\+\+ runtime is not installed by the launcher\./);
  assert.equal(release.windows_fresh_install_acceptance,'not-completed-user-accepted-beta-gap');
  assert.equal(release.windows_fresh_install.result,'not_performed_for_revised_package');
  assert.equal(release.windows_fresh_install.status,'not_verified');
  assert.equal(release.windows_fresh_install.guest_report_received,false);
  assert.equal(release.windows_fresh_install.beta_gate_waiver,'explicitly-accepted-not-passed');
  assert.equal(release.windows_fresh_install.application_source_commit,release.source_commit);
  assert.equal(release.windows_fresh_install.archive_sha256,release.platforms.windows.sha256);
  const installedWindows = release.windows_installed_validation;
  assert.equal(installedWindows.application_source_commit,release.source_commit);
  assert.equal(installedWindows.archive_sha256,release.platforms.windows.sha256);
  assert.equal(installedWindows.packaged_batch_launcher,'not_run');
  assert.equal(installedWindows.model_inference,'not_run');
  assert.equal(installedWindows.clean_os_installation,'not_run');
  assert.equal(installedWindows.human_listening,'not_performed');
  for (const gate of ['portrait_720x1280','two_source_stacked_30_70_pixels','selected_source_b_audio_detected','full_decode','direct_unmodified_setup_without_ollama','saved_project_and_export_after_server_restart']) assert.equal(installedWindows[gate],'passed');
  const resourceAbort = release.historical_windows_validation.find(entry=>entry.application_source_commit==='50843dd178282cf7d55846aad7ec1d8de61aeed7');
  assert.ok(resourceAbort,'Preserve the earlier candidate resource abort without qualifying the revised package');
  assert.equal(resourceAbort.archive_sha256,'4a9fa16ad1894d9837f53f163d41ce25cf852262321ae8f727d7982ef48cb95e');
  assert.equal(resourceAbort.windows_fresh_install.result,'resource_abort');
  assert.equal(resourceAbort.windows_fresh_install.guest_report_received,true);
  assert.equal(resourceAbort.windows_fresh_install.passed_stages,7);
  assert.equal(resourceAbort.windows_fresh_install.resource_aborted_stages,1);
  assert.equal(resourceAbort.windows_fresh_install.not_run_stages,4);
  assert.equal(resourceAbort.windows_fresh_install.export_restart_persistence,'not_completed');
  assert.equal(resourceAbort.windows_fresh_install.attempt_consumed,true);
  assert.match(html,/Windows clean-install qualification for this ZIP is incomplete/);
  assert.match(html,/Hebrew accuracy and automatic speaker framing remain unfinished/);
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
  assert.equal(languageLink.length, 2);
  for (const link of languageLink) {
    assert.match(link[1], /lang="he"/);
    assert.match(link[2], /[\u0590-\u05ff]/);
    assert.doesNotMatch(link[1], /aria-label=/, 'The visible language name is the accessible name');
  }
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
  assert.match(image, /src="\/assets\/studio-edit\.png\?v=20261019"/);
  assert.match(image, /width="1600" height="900"/);
  assert.match(image, /alt="[^"]+"/);
  assert.match(image, /data-he-alt="[^"]*[\u0590-\u05ff]/);
  assert.match(image, /fetchpriority="high"/);
  assert.ok(region('dialog', 'imageDialog').includes('src="/assets/studio-edit.png?v=20261019"'), 'Enlargement preserves the original screenshot, without artwork framing');
  assert.match(hero, /Interface captured 19 October 2026/);
  assert.match(hero, /Screenshots show an earlier interface, not a new downloadable build\./);
  assert.doesNotMatch(html, /src="[^"]*showcase|<table\b/);
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
  assert.match(html, /<a\b[^>]*id="expandShot"[^>]*aria-label="[^"]+"/);
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
  assert.deepEqual(tabs.map(tab => tab[1]), ['home', 'media', 'edit', 'layout', 'audio', 'captions', 'output', 'settings', 'projects', 'export']);
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

test('every gallery image links to the exact same full-resolution PNG', () => {
  const links = [...html.matchAll(/<a class="workspace-image-link"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)];
  assert.equal(links.length, 10);
  for (const [, href, contents] of links) {
    const src = contents.match(/src="([^"]+)"/)[1];
    assert.equal(src, href);
    assert.match(contents, /loading="lazy"/);
    assert.match(contents, /data-he-alt="[^"]*[\u0590-\u05ff]/);
    const bytes = readFileSync(new URL('./public' + src.split('?')[0], import.meta.url));
    assert.equal(bytes.subarray(1, 4).toString(), 'PNG');
    assert.equal(bytes.readUInt32BE(16), src.includes('20261015') ? 1440 : 1600);
    assert.ok(contents.includes(`width="${bytes.readUInt32BE(16)}"`));
    assert.equal(bytes.readUInt32BE(20), 900);
  }
  assert.match(css, /\.workspace-shot, \.shot-button img \{ aspect-ratio:auto/);
  assert.match(html, /Additional windows are not yet pictured here/);
});

test('sharing metadata uses the actual editor PNG without artwork', () => {
  const url = 'https://cutroom-studio.expo.app/assets/studio-edit.png';
  for (const field of ['property="og:image"', 'name="twitter:image"']) assert.ok(html.includes(`${field} content="${url}"`));
  assert.match(html, /property="og:image:type" content="image\/png"/);
  assert.match(html, /property="og:image:width" content="1600"/);
  assert.match(html, /property="og:image:height" content="900"/);
});

test('gallery has progressive enhancement, original links and keyboard controls', () => {
  assert.match(html, /<a id="expandShot" href="\/assets\/studio-edit.png\?v=20261019"/);
  for (const id of ['previousImage', 'nextImage', 'originalImage', 'imageCounter']) assert.ok(html.includes(`id="${id}"`));
  assert.match(script, /event.ctrlKey \|\| event.metaKey/);
  assert.match(script, /expandedImage.src = link.href/);
  assert.match(script, /originalImage.href = link.href/);
  assert.match(script, /screenshotOpener\?\.focus/);
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

test('mobile navigation keeps section links available without script', () => {
  const menu = region('details', 'mobileNav');
  assert.match(menu, /<summary\b[^>]*id="mobileNavToggle"/);
  for (const target of ['#start', '#workspaces', '#ai', '#guide']) {
    const links = linksTo(menu, target);
    assert.equal(links.length, 1, `Missing mobile link to ${target}`);
    if (target !== "#ai") assertLocalized(links[0]);
    else assert.match(links[0][0], /data-he="AI"/);
  }
  assert.match(css, /@media\s*\(max-width:\s*767px\)[\s\S]*?\.mobile-nav\s*\{\s*display:\s*block/);
  assert.match(css, /\.mobile-nav-menu\s*\{[^}]*max-height:[^}]*overflow-y:\s*auto/);
});

test('cached pages without the mobile menu do not break site initialization', async () => {
  const {runInNewContext} = await import('node:vm');
  const block = script.slice(script.indexOf('  // Native details keeps section navigation'), script.indexOf('  // Workspace tour:'));
  assert.ok(block.includes('mobileNav'));
  assert.doesNotThrow(() => runInNewContext(block, {document:{getElementById:()=>null},window:{}}));
});

test('mobile navigation restores focus after its element is hidden on resize', async () => {
  const {runInNewContext} = await import('node:vm');
  const block = script.slice(script.indexOf('  // Native details keeps section navigation'), script.indexOf('  // Workspace tour:'));
  const listeners={}, documentListeners={}; let mediaChange, focused=false;
  const menu={open:true,addEventListener:(name,fn)=>{listeners[name]=fn;},contains:()=>false};
  const summary={focus(){}};
  const document={getElementById:id=>id==='mobileNav'?menu:summary,addEventListener:(name,fn)=>{documentListeners[name]=fn;},hasFocus:()=>true,activeElement:{}};
  const window={matchMedia:()=>({addEventListener:(name,fn)=>{mediaChange=fn;}})};
  const languageSwitch={focus:()=>{focused=true;}};
  runInNewContext(block,{document,window,languageSwitch});
  listeners.focusin();
  mediaChange({matches:false});
  assert.equal(menu.open,false);
  assert.equal(focused,true);
});

test('background animation controls stay synchronized and respect device motion settings', async () => {
  const {runInNewContext} = await import('node:vm');
  const start = script.indexOf("  const motionToggle = document.getElementById('motionToggle');");
  const end = script.indexOf('  let language = new URL(location.href)', start);
  assert.ok(start >= 0 && end > start);
  const block = script.slice(start, end);
  const createControl = () => {
    const state={textContent:''}, attributes={}, listeners={};
    return {state,attributes,listeners,disabled:false,
      querySelector:selector=>selector==='[data-motion-state]' ? state : null,
      setAttribute:(name,value)=>{attributes[name]=value;},
      addEventListener:(name,fn)=>{listeners[name]=fn;}};
  };
  const desktop=createControl(),mobile=createControl(), preference={matches:false};
  preference.addEventListener=(name,fn)=>{preference[name]=fn;};
  const document={documentElement:{dataset:{}},getElementById:id=>id==='motionToggle'?desktop:mobile};
  const window={matchMedia:()=>preference};
  runInNewContext("let language='he';\n"+block+'\nrenderMotion();',{document,window});
  assert.equal(document.documentElement.dataset.motion,'running');
  assert.equal(desktop.attributes['aria-pressed'],'true');
  assert.equal(mobile.state.textContent,'פעיל');
  mobile.listeners.click();
  assert.equal(document.documentElement.dataset.motion,'paused');
  assert.equal(desktop.attributes['aria-pressed'],'false');
  assert.equal(mobile.state.textContent,'כבוי');
  desktop.listeners.click();
  assert.equal(document.documentElement.dataset.motion,'running');
  preference.matches=true; preference.change();
  assert.equal(document.documentElement.dataset.motion,'paused');
  assert.equal(desktop.disabled,true);
  assert.equal(mobile.disabled,true);
  assert.match(mobile.state.textContent,/הגדרות המכשיר/);
  mobile.listeners.click();
  assert.equal(document.documentElement.dataset.motion,'paused');
  preference.matches=false; preference.change();
  assert.equal(mobile.disabled,false);
  assert.equal(document.documentElement.dataset.motion,'paused');
});

test('an older cached page retains a working legacy motion control', async () => {
  const {runInNewContext} = await import('node:vm');
  const start=script.indexOf("  const motionToggle = document.getElementById('motionToggle');");
  const end=script.indexOf('  let language = new URL(location.href)',start);
  const block=script.slice(start,end), attrs={}, listeners={}, span={textContent:''}, path={d:'',setAttribute:(key,value)=>{path[key]=value;}};
  const legacy={disabled:false,setAttribute:(name,value)=>{attrs[name]=value;},
    querySelector:selector=>selector==='span'?span:selector==='path'?path:null,
    addEventListener:(name,fn)=>{listeners[name]=fn;}};
  const preference={matches:false,addEventListener(){}};
  const document={documentElement:{dataset:{}},getElementById:id=>id==='motionToggle'?legacy:null};
  runInNewContext("let language='en';\n"+block+'\nrenderMotion();',{document,window:{matchMedia:()=>preference}});
  assert.equal(attrs['aria-label'],'Pause motion');
  assert.equal(document.documentElement.dataset.motion,'running');
  listeners.click();
  assert.equal(attrs['aria-label'],'Play motion');
  assert.equal(document.documentElement.dataset.motion,'paused');
});


test('published Windows installer fix is clear in both languages', () => {
  assert.match(html,/Windows setup no longer installs Ollama automatically/);
  assert.match(html,/After opening the editor, choose AI connection, On my computer, then Get Ollama/);
  const statusTag = html.match(/<p\b[^>]*id="download-build-status"[^>]*>/i)?.[0] || '';
  const helpTag = html.match(/<p\b[^>]*id="local-help"[^>]*>/i)?.[0] || '';
  for (const tag of [statusTag, helpTag]) assert.match(tag,/data-he="[^"]*[\u0590-\u05ff][^"]*Ollama/);
});


test('preceding public release validation remains historical', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url),'utf8'));
  const windows = release.historical_windows_validation.find(entry=>entry.release_tag==='v1.3-beta-20261103-ui2');
  const mac = release.historical_native_validation.find(entry=>entry.release_tag==='v1.3-beta-20261103-ui2');
  assert.equal(windows?.application_source_commit,'3caa23d2119e3963c044fc3281615227b2bea8e0');
  assert.equal(windows?.archive_sha256,'04d3f59f916c9b5409ae1cdc3346f6c948093419744d51bdd80176ac6e175e99');
  assert.equal(windows?.windows_fresh_install?.status,'not_verified');
  assert.equal(mac?.source_commit,'3caa23d2119e3963c044fc3281615227b2bea8e0');
  assert.equal(mac?.native_validation?.run_id,41710068813);
});

test('screenshot dialog follows the selected original, wraps, respects modifiers and restores focus', async () => {
  const {runInNewContext} = await import('node:vm');
  const start = script.indexOf('  const screenshotLinks =');
  const end = script.indexOf('  // Native details', start);
  const element = () => ({events:{}, addEventListener(type, fn) {this.events[type] = fn;}, setAttribute() {}});
  const links = ['home', 'edit', 'settings'].map(name => ({...element(), href:`/assets/${name}.png`,
    querySelector:() => ({alt:name, naturalWidth:1600, naturalHeight:900, width:400, height:225}),
    focus(){this.focused=true;}}));
  const ids = Object.fromEntries(['expandedImage', 'originalImage', 'imageCounter', 'previousImage', 'nextImage', 'closeImage'].map(id => [id, element()]));
  const dialog = {...element(), open:false, showModal(){this.open=true;}, close(){this.open=false;this.events.close();}};
  const document = {querySelectorAll:()=>links, getElementById:id=>ids[id], documentElement:{dir:'ltr'}};
  runInNewContext('let screenshotOpener = null;\n'+script.slice(start,end), {document,dialog});
  const click = (link, modifiers={}) => {
    const event={button:0, preventDefault(){this.prevented=true;}, ...modifiers}; link.events.click(event); return event;
  };
  assert.equal(click(links[1],{ctrlKey:true}).prevented,undefined);
  assert.equal(dialog.open,false);
  assert.equal(click(links[1]).prevented,true);
  assert.equal(dialog.open,true);
  assert.equal(ids.expandedImage.src,links[1].href);
  assert.equal(ids.originalImage.href,links[1].href);
  assert.equal(ids.expandedImage.width,1600);
  ids.nextImage.events.click();
  assert.equal(ids.expandedImage.alt,'settings');
  ids.nextImage.events.click();
  assert.equal(ids.expandedImage.alt,'home');
  dialog.events.keydown({key:'ArrowLeft',preventDefault(){}});
  assert.equal(ids.expandedImage.alt,'settings');
  document.documentElement.dir='rtl';
  dialog.events.keydown({key:'ArrowLeft',preventDefault(){}});
  assert.equal(ids.expandedImage.alt,'home');
  ids.closeImage.events.click();
  assert.equal(dialog.open,false);
  assert.equal(links[1].focused,true);
  click(links[0]);
  dialog.events.click({target:dialog});
  assert.equal(dialog.open,false);
  assert.equal(links[0].focused,true);
});

test('archived supplemental views and undated AI setup are labeled honestly', () => {
  assert.match(html, /The AI setup capture date was not recorded/);
  assert.match(html, /These are archived originals, not new captures/);
  for (const id of ['projects', 'export']) {
    const panel = html.slice(html.indexOf(`id="panel-${id}"`));
    assert.match(panel.slice(0, panel.indexOf('class="original-link"')), /Archived interface from 15 October 2026/);
  }
});


test('current release discloses archival screenshots and preserves preceding Nov6, Nov7 and Nov8 provenance', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url),'utf8'));
  assert.ok(release.known_limitations.some(text => /[Gg]allery.*archiv/.test(text)));
  assert.match(html, /Transcription settings were checked in desktop and mobile browser layouts/);
  assert.match(html, /live Cloudflare, accuracy measurements, physical-device acceptance and human listening remain untested/);
  assert.equal(release.historical_native_validation.find(row=>row.release_tag==='v1.3-beta-20261106-stability1').native_validation.run_id,42291275917);
  assert.equal(release.historical_native_validation.find(row=>row.release_tag==='v1.3-beta-20261107-editor1').native_validation.run_id,42406800822);
  assert.equal(release.historical_native_validation.find(row=>row.release_tag==='v1.3-beta-20261108-studio1').native_validation.run_id,42489336008);
  assert.equal(release.historical_native_validation.find(row=>row.release_tag==='v1.3-beta-20261111-gray1').native_validation.run_id,42965402773);
  const retained = JSON.parse(readFileSync(new URL('./retained-downloads.json', import.meta.url),'utf8'));
  assert.equal(retained.length,48);
  for (const entry of retained) {
    assert.equal(entry.url,`https://cutroom-studio--${entry.filename.includes('4fc52ae') ? 'nbymjtivwx' : entry.filename.includes('d2c6f6f') ? 'oz9pego43i' : entry.filename.includes('2dacba3') ? 'o6r0sixwri' : 'cfqtj1cb86'}.expo.app/downloads/${entry.filename}`);
    assert.ok(entry.github_url.startsWith('https://github.com/VanoPeradze/cutroom/releases/download/'));
  }
});

// Studio navigation follows its responsive visual orientation and stays operable
// without a browser render. Pixel geometry is verified separately in a browser.
test('studio tour supports horizontal navigation, RTL and keyboard boundaries', async()=>{
 const {runInNewContext}=await import('node:vm');
 const nodes=new Map();
 const document={documentElement:{dir:'ltr'},activeElement:null,getElementById:id=>nodes.get(id),querySelectorAll:()=>[]};
 const element=(id)=>({id,attrs:{},events:{},hidden:false,tabIndex:-1,setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},addEventListener(k,f){this.events[k]=f;},focus(){document.activeElement=this;}});
 const tabs=['home','media','edit'].map(id=>{const t=element('tab-'+id);t.attrs['aria-controls']='panel-'+id;nodes.set('panel-'+id,element('panel-'+id));return t;});
 const list=element('tour');list.querySelectorAll=()=>tabs;document.querySelector=()=>list;
 const preference={matches:true,addEventListener(k,f){this.change=f;}};
 const start=script.indexOf("  const tabList = document.querySelector('.tour-tabs');");
 const end=script.indexOf('  function revealLinkedHelp()',start);
 assert.ok(start>=0&&end>start);
 runInNewContext(script.slice(start,end),{document,window:{matchMedia:query=>{assert.equal(query,'(min-width: 1040px)');return preference;}}});
 assert.equal(list.attrs['aria-orientation'],'horizontal');assert.equal(tabs[0].attrs['aria-selected'],'true');
 const key=(key,extra={})=>{let prevented=false;list.events.keydown({key,preventDefault(){prevented=true;},...extra});return prevented;};
 tabs[0].focus();assert.equal(key('ArrowDown'),true);assert.equal(document.activeElement,tabs[1]);
 assert.equal(nodes.get('panel-home').hidden,true);assert.equal(nodes.get('panel-media').hidden,false);
 key('End');assert.equal(document.activeElement,tabs[2]);key('ArrowDown');assert.equal(document.activeElement,tabs[0]);
 document.documentElement.dir='rtl';key('ArrowLeft');assert.equal(document.activeElement,tabs[1]);key('ArrowRight');assert.equal(document.activeElement,tabs[0]);
 key('ArrowUp');assert.equal(document.activeElement,tabs[2]);
 assert.equal(key('ArrowDown',{ctrlKey:true}),false);assert.equal(document.activeElement,tabs[2]);
 assert.equal(list.attrs['aria-orientation'],'horizontal');
 tabs[1].events.click();assert.equal(tabs[1].attrs['aria-selected'],'true');assert.equal(tabs.filter(t=>t.tabIndex===0).length,1);
});

test('studio finish stays local, preserves real imagery and has bounded responsive rules',()=>{
 const finish=readFileSync(new URL('./public/studio.css',import.meta.url),'utf8');
 assert.match(html,/href="\/studio.css\?v=20261108-cuttingroom3"/);
 assert.match(finish,/grid-template-columns:repeat\(5,minmax\(0,1fr\)\)/);
 assert.match(finish,/@media\(max-width:767px\)/);
 assert.match(finish,/@media\(max-width:359px\)/);
 assert.match(finish,/@media\(prefers-reduced-motion:reduce\)/);
 assert.doesNotMatch(finish,/@import|url\(['"]?https?:/);
 assert.match(html,/<span data-he="החומר שלך\.">Your footage\.<\/span>/);
 assert.match(html,/Interface captured 19 October 2026/);
});


test('section navigation tracks visible sections without changing location or focus', async()=>{
 const {runInNewContext}=await import('node:vm');
 const sections=['start','workspaces','ai','guide','download'].map(id=>({id}));
 const links=sections.map(s=>({hash:'#'+s.id,attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}}));
 let callback,options;const observed=[];
 class IntersectionObserver { constructor(cb,opts){callback=cb;options=opts;} observe(section){observed.push(section);} }
 const document={querySelectorAll:()=>links,getElementById:id=>sections.find(s=>s.id===id)};
 const start=script.indexOf('  const sectionLinks =');
 const end=script.indexOf("  if ('IntersectionObserver' in window && !motionPreference.matches)",start);
 assert.ok(start>=0&&end>start);
 runInNewContext(script.slice(start,end),{document,IntersectionObserver,window:{IntersectionObserver}});
 assert.equal(options.rootMargin,'-104px 0px -45% 0px');
 assert.equal(observed.length,5);
 callback([{target:sections[4],isIntersecting:true}]);assert.equal(links[4].attrs['aria-current'],'location');
 callback([{target:sections[4],isIntersecting:false},{target:sections[1],isIntersecting:true}]);
 assert.equal(links[4].attrs['aria-current'],undefined);assert.equal(links[1].attrs['aria-current'],'location');
 const finish=readFileSync(new URL('./public/studio.css',import.meta.url),'utf8');
 assert.match(finish,/overflow-x:clip/);
 assert.match(finish,/@media\(min-width:768px\) and \(max-width:980px\)/);
});


test('the cutting-room redesign uses locally licensed fonts and a real workflow',()=>{
 const finish=readFileSync(new URL('./public/studio.css',import.meta.url),'utf8');
 assert.match(html,/class="marketing-page cutting-room"/);
 assert.match(finish,/@font-face\{font-family:Geist/);
 assert.match(finish,/font-display:swap/);
 for(const font of ['Geist','NotoSansHebrew']) {
  assert.ok(readFileSync(new URL(`./public/assets/${font}.ttf`,import.meta.url)).length>10000);
  assert.match(readFileSync(new URL(`./public/assets/${font}-OFL.txt`,import.meta.url),'utf8'),/SIL OPEN FONT LICENSE/);
 }
 for(const workspace of ['media','edit','output']) {
  assert.match(html,new RegExp(`data-workspace="${workspace}" href="#workspaces"`));
 }
 assert.match(script,/const index = tabs.findIndex/);
 assert.match(script,/if \(index >= 0\) selectTab\(index, false\)/);
 assert.match(finish,/html\[data-motion=paused\][^{}]+\.motion-ready\{transform:none;opacity:1;transition:none\}/);
 assert.doesNotMatch(html, /class="hero-atmosphere"/);
});

test('new light surfaces and platform buttons maintain readable contrast',()=>{
 const L=hex=>hex.match(/[a-f0-9]{2}/gi).map(v=>parseInt(v,16)/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((v,c,i)=>v+c*[.2126,.7152,.0722][i],0);
 const ratio=(a,b)=>{const x=L(a),y=L(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
 for(const background of ['f2f4f1','e7ece7','e5ece5'])for(const text of ['16231e','46584e','53645a','14644b'])assert.ok(ratio(text,background)>=4.5,`${text}/${background}`);
 assert.ok(ratio('16231e','a2e3c1')>=4.5);
 assert.ok(ratio('f2f4f1','16231e')>=4.5);
});


test('gray and Hebrew release copy is bilingual and limits its accuracy claims', () => {
  const update = region('details', 'update-status');
  const note = update.match(/<p data-he="([^"]+)">11 November: ([^<]+)<\/p>/);
  assert.ok(note, 'The new release needs a localized change note');
  assert.match(note[1], /[\u0590-\u05ff]/);
  for (const text of ['neutral gray light-mode surfaces', 'already-cached local model',
    'preserves the original transcript when the result is weak', 'does not download a new model',
    'Mixed Hebrew-English caption rendering is corrected', 'Real-speech transcription accuracy has not been measured']) {
    assert.ok(note[2].includes(text), text);
  }
  assert.match(html, /Beta build · 11 November 2026/);
  assert.match(html, /Beta release notes - build 11 November 2026/);
  assert.match(html, /Gallery screenshots remain archival/);
});


test('Hebrew-first and optional cloud disclosure remains bilingual and unmeasured', () => {
  const release = JSON.parse(readFileSync(new URL('./release.json', import.meta.url),'utf8'));
  const update = region('details','update-status');
  const note = update.match(/<p data-he="([^"]+)">New: ([^<]+)<\/p>/);
  assert.ok(note);
  assert.match(note[1], /[\u0590-\u05ff]/);
  for (const text of ['ivrit.ai in both Balanced and Quality','memory checks','local speech never uploads audio','experimental and off by default','explicit account/model/future-job consent','No real audio was uploaded','accuracy or billing behavior is not verified']) assert.ok(note[2].includes(text),text);
  assert.match(update,/prior upload attempts remain visible/);
  assert.match(update,/not transcription-accuracy certification/);
  assert.equal(release.local_regression_validation.real_speech_inference,false);
  assert.equal(release.local_regression_validation.cloud_audio_uploaded,false);
  assert.equal(release.local_regression_validation.bidi_browser.passed,250);
  assert.equal(release.local_regression_validation.frontend.passed,919);
  assert.ok(release.known_limitations.some(text=>/Cloudflare.*experimental.*mocked/.test(text)));
});
