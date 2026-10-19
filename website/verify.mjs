import {readFileSync, existsSync, readdirSync} from 'node:fs';
import {resolve, dirname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {downloadEntries, uniqueDownloadEntries, verifyArchive, assertPublishable} from './prepare-download.mjs';
const root = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(resolve(root,'public/index.html'),'utf8');
const publicRoot = resolve(root,'public');
const pageFiles = readdirSync(publicRoot).filter(name => name.endsWith('.html'));
assert.ok(pageFiles.includes('privacy.html'),'Missing privacy and cookie notice');
for (const filename of pageFiles) {
  const page = readFileSync(resolve(publicRoot, filename),'utf8');
  const ids = [...page.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  assert.equal(new Set(ids).size,ids.length,filename+': duplicate element ids');
  for (const match of page.matchAll(/(?:src|href)="(\/[^\"]*)"/g)) {
    const url = new URL(match[1],'https://cutroom-studio.expo.app');
    assert.equal(url.origin,'https://cutroom-studio.expo.app','Unexpected resource origin: '+match[1]);
    const path = resolve(publicRoot,'.' + decodeURIComponent(url.pathname));
    assert.ok((path === publicRoot || path.startsWith(publicRoot + sep)) && existsSync(path),'Missing public asset: '+match[1]);
    if (url.hash && (url.pathname === '/' || url.pathname.endsWith('.html'))) {
      const target = readFileSync(url.pathname === '/' ? resolve(publicRoot,'index.html') : path,'utf8');
      const targetIds = [...target.matchAll(/\bid="([^"]+)"/g)].map(item=>item[1]);
      assert.ok(targetIds.includes(decodeURIComponent(url.hash.slice(1))),'Missing linked anchor: '+match[1]);
    }
  }
  for (const match of page.matchAll(/href="#([^"]+)"/g)) assert.ok(ids.includes(match[1]),filename+': missing anchor '+match[1]);
}
const release = JSON.parse(readFileSync(resolve(root,'release.json'),'utf8'));
const zip = release.filename;
assert.match(zip, /^CUTROOM-[A-Za-z0-9.-]+\.zip$/, 'Unsafe release filename');
assert.equal(release.version, '1.2-beta');
assert.equal(release.label, '1.2 Beta');
assert.equal(release.layout, 'windows-mac-folders-v1');
assert.ok(html.includes('Double-click START CUTROOM.bat'), 'The page must explain the single download launcher');
assert.equal(JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version, '1.2.0-beta');
assert.ok(html.includes('WINDOWS + MAC · 1.2 BETA'), 'The download must display both platforms and 1.2 Beta');
assertPublishable(release);
assert.equal(release.release_state, 'beta');
assert.equal(release.source_commit, '7019b6423ce9d66531e933ee5cac42968f9e96e7');
assert.equal(release.filename, 'CUTROOM-1.2-Beta-20261019.zip');
assert.equal(release.platforms.windows.filename, 'CUTROOM-1.2-Beta-Windows-20261019.zip');
assert.equal(release.platforms.mac.filename, 'CUTROOM-1.2-Beta-Mac-20261019.zip');
assert.equal(release.source_archive.filename, 'SOURCE-20261019.zip');
assert.equal(downloadEntries(release).length,4,'Four distinct public archives must be prepared');
assert.notEqual(release.platforms.mac.filename, release.filename);
assert.ok(!release.platforms.mac.folder,'The standalone Mac launcher must not require a mac subfolder');
assert.ok(html.includes('Mac has its own ZIP. Extract it and run START CUTROOM.command beside App.'), 'Explain the standalone Mac launcher');
assert.ok(html.includes('Public beta.') && html.includes('still need manual acceptance.'), 'Disclose beta acceptance limits');
assert.ok(html.includes('START CUTROOM.command') && html.includes('exactly two folders: windows and mac'), 'Both platform launchers must be explained');
assert.ok(html.includes('/downloads/'+zip+'"'), 'The download must match the release manifest');
assert.ok(html.includes('/downloads/'+zip+'.sha256"'), 'The checksum link must match the release manifest');
assert.ok(!html.includes('5.6.1'), 'Stale application version on the public page');
assert.match(release.sha256, /^[a-f0-9]{64}$/);
assert.ok(Number.isSafeInteger(release.bytes) && release.bytes > 0);
assert.equal(release.github_release.tag, 'v1.2-beta-20261019');
assert.equal(release.github_release.previous_public_tag, 'v1.2-beta-20261018');
assert.equal(release.github_release.tag_commit, release.source_commit);
const releaseBase = `https://github.com/VanoPeradze/cutroom/releases/download/${release.github_release.tag}/`;
const retained = JSON.parse(readFileSync(resolve(root,'retained-downloads.json'),'utf8'));
const retainedTags = new Map([
  ...['CUTROOM-1.1-Beta.zip','CUTROOM-1.1-Beta-Windows.zip','CUTROOM-1.1-Beta-Mac.zip'].map(filename=>[filename,'v1.1-beta-20261011']),
  ...['CUTROOM-1.2-Beta.zip','CUTROOM-1.2-Beta-Windows.zip','CUTROOM-1.2-Beta-Mac.zip'].map(filename=>[filename,'v1.2-beta-20261015']),
  ...['CUTROOM-1.2-Beta-Windows-review-fe35453.zip','CUTROOM-1.2-Beta-combined-review-fe35453.zip','SOURCE-fe35453.zip'].map(filename=>[filename,'v1.2-beta-20261018']),
]);
assert.deepEqual(retained.map(entry=>entry.filename).sort(),[...retainedTags.keys()].sort(),'Preserve all historical 1.1, October 15 and October 18 mirrors');
uniqueDownloadEntries([...downloadEntries(release), ...retained]);
for (const entry of downloadEntries(release)) {
  assert.equal(entry.url, releaseBase + entry.filename);
  assert.ok(html.includes('href="'+entry.url+'"'), 'Missing tag-specific GitHub primary download');
  assert.deepEqual(entry.mirrors, ['https://cutroom-studio.expo.app/downloads/'+entry.filename]);
  assert.ok(html.includes('href="/downloads/'+entry.filename+'"'), 'Missing preserved Expo mirror link');
  assert.ok(html.includes('/downloads/'+entry.filename+'.sha256"'), 'Missing exact checksum link');
  const bytes = readFileSync(resolve(root,'public/downloads',entry.filename));
  verifyArchive(bytes, entry);
  const sidecar = readFileSync(resolve(root,'public/downloads',entry.filename+'.sha256'),'utf8').trim().split(/\s+/);
  assert.equal(sidecar[0], entry.sha256);
  assert.equal(sidecar[1], entry.filename);
}
for (const entry of retained) {
  assert.equal(entry.url,`https://github.com/VanoPeradze/cutroom/releases/download/${retainedTags.get(entry.filename)}/${entry.filename}`);
  verifyArchive(readFileSync(resolve(root,'public/downloads',entry.filename)),entry);
  const sidecar = readFileSync(resolve(root,'public/downloads',entry.filename+'.sha256'),'utf8').trim().split(/\s+/);
  assert.equal(sidecar[0],entry.sha256);
  assert.equal(sidecar[1],entry.filename);
}
assert.ok(!html.includes('127.0.0.1')&&!html.includes('C:/Users/'),'Local-only reference leaked');
const {expo}=JSON.parse(readFileSync(resolve(root,'app.json'),'utf8'));
assert.equal(expo.web.output,'static','Only the static website may be deployed');
assert.ok(expo.extra?.eas?.projectId,'Expo project must be linked before publishing');
const canonicalTag = html.match(/<link\b[^>]*\brel=["']canonical["'][^>]*>/i)?.[0];
assert.equal(canonicalTag?.match(/\bhref=["']([^"']+)["']/i)?.[1], 'https://cutroom-studio.expo.app/', 'Canonical must point to the Expo website');
assert.ok(!html.includes('chatgpt.site'),'The public page must not refer visitors to the previous host');
console.log('Verified: all public pages, privacy notice, local assets, anchors, unique IDs, Expo config and exact approved download.');
