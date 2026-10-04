import {readFileSync, existsSync, readdirSync} from 'node:fs';
import {resolve, dirname, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
import {downloadEntries, verifyArchive} from './prepare-download.mjs';
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
assert.equal(release.version, '1.1-beta');
assert.equal(release.label, '1.1 Beta');
assert.equal(release.layout, 'windows-mac-folders-v1');
assert.ok(html.includes('Double-click START CUTROOM.bat'), 'The page must explain the single download launcher');
assert.equal(JSON.parse(readFileSync(resolve(root,'package.json'),'utf8')).version, '1.1.0-beta');
assert.ok(html.includes('WINDOWS + MAC · 1.1 BETA'), 'The download must display both platforms and 1.1 Beta');
assert.ok(html.includes('START CUTROOM.command') && html.includes('exactly two folders: windows and mac'), 'Both platform launchers must be explained');
assert.ok(html.includes('/downloads/'+zip+'"'), 'The download must match the release manifest');
assert.ok(html.includes('/downloads/'+zip+'.sha256"'), 'The checksum link must match the release manifest');
assert.ok(!html.includes('5.6.1'), 'Stale application version on the public page');
assert.match(release.sha256, /^[a-f0-9]{64}$/);
assert.ok(Number.isSafeInteger(release.bytes) && release.bytes > 0);
assert.equal(release.url, 'https://cutroom-studio.expo.app/downloads/'+zip);
for (const entry of downloadEntries(release)) {
  assert.ok(html.includes('/downloads/'+entry.filename+'"'), 'Missing exact archive link');
  assert.ok(html.includes('/downloads/'+entry.filename+'.sha256"'), 'Missing exact checksum link');
  const bytes = readFileSync(resolve(root,'public/downloads',entry.filename));
  verifyArchive(bytes, entry);
  const sidecar = readFileSync(resolve(root,'public/downloads',entry.filename+'.sha256'),'utf8').trim().split(/\s+/);
  assert.equal(sidecar[0], entry.sha256);
  assert.equal(sidecar[1], entry.filename);
}
assert.ok(!html.includes('127.0.0.1')&&!html.includes('C:/Users/'),'Local-only reference leaked');
const {expo}=JSON.parse(readFileSync(resolve(root,'app.json'),'utf8'));
assert.equal(expo.web.output,'static','Only the static website may be deployed');
assert.ok(expo.extra?.eas?.projectId,'Expo project must be linked before publishing');
const canonicalTag = html.match(/<link\b[^>]*\brel=["']canonical["'][^>]*>/i)?.[0];
assert.equal(canonicalTag?.match(/\bhref=["']([^"']+)["']/i)?.[1], 'https://cutroom-studio.expo.app/', 'Canonical must point to the Expo website');
assert.ok(!html.includes('chatgpt.site'),'The public page must not refer visitors to the previous host');
console.log('Verified: all public pages, privacy notice, local assets, anchors, unique IDs, Expo config and exact approved download.');
