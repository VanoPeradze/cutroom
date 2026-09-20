import {readFileSync, existsSync} from 'node:fs';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import assert from 'node:assert/strict';
const root = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(resolve(root,'public/index.html'),'utf8');
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
assert.equal(new Set(ids).size,ids.length,'Duplicate element ids');
for (const match of html.matchAll(/(?:src|href)="(\/[^"?#]+)"/g)) {
  const path = resolve(root,'public','.' + match[1]);
  assert.ok(path.startsWith(resolve(root,'public')) && existsSync(path),'Missing public asset: '+match[1]);
}
for (const match of html.matchAll(/href="#([^"]+)"/g)) assert.ok(ids.includes(match[1]),'Missing anchor: '+match[1]);
const zip = 'CUTROOM-5.6.1-test-20260919-223724.zip';
const bytes = readFileSync(resolve(root,'public/downloads',zip));
const hash = createHash('sha256').update(bytes).digest('hex');
assert.equal(hash,readFileSync(resolve(root,'public/downloads',zip+'.sha256'),'utf8').trim().split(/\s+/)[0]);
assert.equal(hash,'8c8e32972438e7304b6d1d67399234ccb336fc334e4eab62119efa395265c0a7','The approved beta archive changed');
assert.equal(bytes.length,1059269);
assert.ok(!html.includes('127.0.0.1')&&!html.includes('C:/Users/'),'Local-only reference leaked');
const {expo}=JSON.parse(readFileSync(resolve(root,'app.json'),'utf8'));
assert.equal(expo.web.output,'static','Only the static website may be deployed');
assert.ok(expo.extra?.eas?.projectId,'Expo project must be linked before publishing');
assert.ok(html.includes('https://cutroom-studio.expo.app/'),'Canonical must point to the Expo website');
assert.ok(!html.includes('chatgpt.site'),'The public page must not refer visitors to the previous host');
console.log('Verified: local assets, anchors, unique IDs, Expo config and exact approved download.');
