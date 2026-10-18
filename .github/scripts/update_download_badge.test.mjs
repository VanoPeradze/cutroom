import {test} from 'node:test';
import assert from 'node:assert/strict';
import {baselineRequests, collectDownloads, expoBaseline, githubApi, installationZip, publishBadge, updateBadge} from './update_download_badge.mjs';

const release = (id, draft = false) => ({id, draft, prerelease: true, published_at: draft ? null : '2026-10-11T12:00:00Z'});
const asset = (id, name, count) => ({id, name, download_count: count, state: 'uploaded'});
const windows = 'CUTROOM-1.1-Beta-Windows.zip';

test('counts published installation ZIPs only, including prereleases and excluding drafts', async () => {
  const api = async path => {
    if (path.startsWith('releases?')) return [release(1), release(2, true)];
    assert.ok(path.startsWith('releases/1/assets?'), 'Draft assets must never be queried');
    return [asset(1, windows, 7), asset(2, 'CUTROOM-1.1-Beta-Mac.zip', 3), asset(3, 'CUTROOM-1.1-Beta.zip', 2),
      asset(4, windows + '.sha256', 80), asset(5, 'CUTROOM-source.zip', 90), asset(6, 'CUTROOM-tested-macos-arm64.zip', 100)];
  };
  assert.equal((await collectDownloads(api)).message, '175'); // 163 observed Expo + 12 GitHub.
  for (const name of ['CUTROOM-1.1-Beta-tests.zip', 'CUTROOM-1.1-Beta-source.zip', 'source.zip', 'CUTROOM-1.1-Beta.zip.sha256']) {
    assert.equal(installationZip.test(name), false);
  }
});

test('paginates both releases and assets and avoids duplicate asset counts', async () => {
  const calls = [];
  const api = async path => {
    calls.push(path);
    if (path === 'releases?per_page=100&page=1') return Array.from({length: 100}, (_, i) => release(i + 1, i !== 0));
    if (path === 'releases?per_page=100&page=2') return [release(101)];
    if (path === 'releases/1/assets?per_page=100&page=1') return Array.from({length: 100}, (_, i) => asset(i + 1, windows, 1));
    if (path === 'releases/1/assets?per_page=100&page=2') return [asset(1, windows, 1), asset(101, windows, 7)];
    if (path === 'releases/101/assets?per_page=100&page=1') return [asset(102, windows, 3)];
    throw new Error(`Unexpected path: ${path}`);
  };
  assert.equal((await collectDownloads(api)).message, '273'); // Baseline once, not per release/page.
  assert.equal(calls.length, 5);
});

test('counts the exact promoted review pair while excluding its draft, source and unrelated reviews', async () => {
  const promotedWindows = 'CUTROOM-1.2-Beta-Windows-review-fe35453.zip';
  const promotedCombined = 'CUTROOM-1.2-Beta-combined-review-fe35453.zip';
  for (const name of [promotedWindows, promotedCombined]) assert.equal(installationZip.test(name), true);
  for (const name of ['SOURCE-fe35453.zip', promotedWindows + '.sha256', promotedCombined + '.sha256',
    'CUTROOM-1.2-Beta-Mac-review-fe35453.zip', 'CUTROOM-1.2-Beta-Windows-review-31ebfd0.zip',
    'CUTROOM-1.2-Beta-combined-review-31ebfd0.zip', 'CUTROOM-1.2-Beta-Windows-review-fe35453-tests.zip',
    'CUTROOM-1.2-Beta-Windows-review-fe35453.zip.extra']) {
    assert.equal(installationZip.test(name), false, name);
  }
  const calls = [];
  const api = async path => {
    calls.push(path);
    if (path.startsWith('releases?')) return [release(1), release(2, true)];
    assert.ok(path.startsWith('releases/1/assets?'), 'Private draft assets must never be queried');
    return [asset(11, promotedWindows, 7), asset(12, promotedCombined, 4),
      asset(11, promotedWindows, 7), asset(13, 'SOURCE-fe35453.zip', 80),
      asset(14, 'CUTROOM-1.2-Beta-combined-review-31ebfd0.zip', 90)];
  };
  assert.equal((await collectDownloads(api)).message, '174'); // 163 observed Expo + 11 published ZIP requests.
  assert.equal(calls.length, 2);
});

test('a later API failure prevents every write and preserves the last good count', async () => {
  const api = async (path, options) => {
    assert.equal(options, undefined, 'No writes may occur after a partial count');
    if (path.startsWith('releases?')) return [release(1), release(2)];
    if (path.startsWith('releases/1/')) return [asset(1, windows, 5)];
    throw new Error('rate limit');
  };
  await assert.rejects(updateBadge(api, true), /rate limit/);
});

test('invalid counts fail instead of replacing valid data with a misleading total', async () => {
  for (const count of [-1, null, '10', Number.MAX_SAFE_INTEGER + 1]) {
    await assert.rejects(collectDownloads(async path => path.startsWith('releases?') ? [release(1)] : [asset(1, windows, count)]), /Invalid installation/);
  }
});

test('API failures are not interpreted as an empty list or an absent data branch', async () => {
  for (const status of [403, 429, 500]) {
    await assert.rejects(githubApi(null, async () => ({ok: false, status}))('git/ref/heads/download-stats', {allowMissing: true}), /HTTP/);
  }
});

test('unchanged totals do not create commits; changed totals use the previous blob SHA', async () => {
  const badge = {schemaVersion: 1, label: 'download requests', message: '175', color: '1bd9ce'};
  let writes = 0;
  const api = async (path, options) => {
    if (path.startsWith('git/ref/')) return {object: {sha: 'previous-commit'}};
    if (path === 'contents/downloads.json?ref=previous-commit') return {type: 'file', encoding: 'base64', sha: 'previous-blob', content: Buffer.from(JSON.stringify(badge, null, 2) + '\n').toString('base64')};
    assert.equal(path, 'contents/downloads.json');
    assert.equal(options.method, 'PUT');
    assert.equal(options.body.sha, 'previous-blob');
    assert.equal(options.body.branch, 'download-stats');
    writes++;
    return {};
  };
  assert.equal(await publishBadge(api, badge), false);
  assert.equal(writes, 0);
  assert.equal(await publishBadge(api, {...badge, message: '176'}), true);
  assert.equal(writes, 1);
});

test('adds the observed baseline once on every run, including repeat runs with persisted data', async () => {
  let saved = {schemaVersion: 1, label: 'GitHub downloads', message: '8', color: '1bd9ce'};
  let writes = 0;
  const api = async (path, options) => {
    if (path.startsWith('releases?')) return [release(1)];
    if (path.startsWith('releases/1/assets?')) return [asset(1, windows, 3), asset(2, 'CUTROOM-1.1-Beta-Mac.zip', 3), asset(3, 'CUTROOM-1.1-Beta.zip', 2)];
    if (path.startsWith('git/ref/')) return {object: {sha: 'previous-commit'}};
    if (path === 'contents/downloads.json?ref=previous-commit') return {type: 'file', encoding: 'base64', sha: 'previous-blob', content: Buffer.from(JSON.stringify(saved, null, 2) + '\n').toString('base64')};
    assert.equal(path, 'contents/downloads.json');
    assert.equal(options.method, 'PUT');
    saved = JSON.parse(Buffer.from(options.body.content, 'base64').toString('utf8'));
    writes++;
    return {};
  };
  assert.equal((await updateBadge(api, true)).message, '171');
  assert.equal(saved.label, 'download requests');
  assert.equal((await updateBadge(api, true)).message, '171');
  assert.equal(writes, 1);
});

test('baseline is limited to the verified GET/200 window and rejects inconsistent totals', () => {
  assert.equal(baselineRequests(expoBaseline), 163);
  assert.deepEqual(Object.values(expoBaseline.requests_by_path), [46, 32, 85]);
  assert.throws(() => baselineRequests({...expoBaseline, total_requests: 166}), /total/);
  assert.throws(() => baselineRequests({...expoBaseline, method: 'HEAD'}), /coverage/);
  assert.throws(() => baselineRequests({...expoBaseline, window_end_utc: '2026-10-12T10:35:00Z'}), /coverage/);
  assert.throws(() => baselineRequests({...expoBaseline, requests_by_path: {...expoBaseline.requests_by_path, '/downloads/other.zip': 1}}), /coverage/);
  assert.throws(() => baselineRequests({...expoBaseline, requests_by_path: {...expoBaseline.requests_by_path, '/downloads/CUTROOM-1.1-Beta.zip': -1}}), /total/);
});

test('a confirmed empty GitHub result keeps the baseline; errors never publish a baseline-only fallback', async () => {
  assert.equal((await collectDownloads(async () => [])).message, '163');
  await assert.rejects(updateBadge(async () => { throw new Error('GitHub unavailable'); }, true), /GitHub unavailable/);
  await assert.rejects(collectDownloads(async () => ({message: 'API error'})), /Invalid GitHub list/);
});
