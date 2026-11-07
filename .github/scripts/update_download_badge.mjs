// Fixed Expo requests plus the asset-ID union of public GitHub history and live counts.
// Refresh the public snapshot immediately before hiding releases; never count private draft activity.
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';

export const repository = 'VanoPeradze/cutroom';
export const statsBranch = 'download-stats';
// Only installation naming families, never SOURCE, checksums, tests or arbitrary review labels.
// Drafts are excluded before matching; a public review-named installation is still a download.
export const installationZip = /^CUTROOM-\d+\.\d+(?:\.\d+)?(?:-Beta)?(?:(?:-(?:Windows|Mac|combined))?(?:-(?:\d{8}(?:-(?:hotfix|maintenance|update|ui|installfix|stability|perf|editor)\d+)?|[a-f0-9]{7,40}))?|-(?:Windows|combined)-review-[a-f0-9]{7,40})\.zip$/;
export const githubSnapshot = JSON.parse(readFileSync(new URL('../download-request-github-history.json', import.meta.url), 'utf8'));
export const expoBaseline = JSON.parse(readFileSync(new URL('../download-request-baseline.json', import.meta.url), 'utf8'));

export function baselineRequests(baseline) {
  const paths = ['/downloads/CUTROOM-1.1-Beta-Windows.zip', '/downloads/CUTROOM-1.1-Beta-Mac.zip', '/downloads/CUTROOM-1.1-Beta.zip'];
  if (baseline.method !== 'GET' || baseline.http_status !== 200
    || baseline.window_start_date !== '2026-10-04' || baseline.window_end_utc !== '2026-10-11T10:35:00Z'
    || Object.keys(baseline.requests_by_path || {}).sort().join(',') !== paths.sort().join(',')) {
    throw new Error('Invalid historical Expo request coverage');
  }
  const values = Object.values(baseline.requests_by_path);
  if (values.some(value => !Number.isSafeInteger(value) || value < 0)
    || !Number.isSafeInteger(baseline.total_requests) || baseline.total_requests < 0
    || values.reduce((sum, value) => sum + value, 0) !== baseline.total_requests) {
    throw new Error('Invalid historical Expo request total');
  }
  return baseline.total_requests;
}

export function githubApi(token, fetcher = fetch) {
  return async (path, {method = 'GET', body, allowMissing = false} = {}) => {
    const response = await fetcher(`https://api.github.com/repos/${repository}/${path}`, {
      method,
      headers: {
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'CUTROOM-download-badge',
        ...(token ? {Authorization: `Bearer ${token}`} : {}),
        ...(body ? {'Content-Type': 'application/json'} : {}),
      },
      ...(body ? {body: JSON.stringify(body)} : {}),
      signal: AbortSignal.timeout(30000),
    });
    if (allowMissing && response.status === 404) return null;
    if (!response.ok) throw new Error(`GitHub ${method} ${path}: HTTP ${response.status}`);
    return response.json();
  };
}

async function* pages(api, path) {
  for (let page = 1; ; page++) {
    const rows = await api(`${path}?per_page=100&page=${page}`);
    if (!Array.isArray(rows)) throw new Error(`Invalid GitHub list: ${path}`);
    yield* rows;
    if (rows.length < 100) return;
  }
}

export function snapshotAssets(snapshot) {
  if (snapshot.schema_version !== 1 || snapshot.source !== `https://api.github.com/repos/${repository}/releases`
    || typeof snapshot.observed_at !== 'string' || !Number.isFinite(Date.parse(snapshot.observed_at))
    || !Array.isArray(snapshot.assets)) throw new Error('Invalid historical GitHub snapshot');
  const assets = new Map();
  for (const asset of snapshot.assets) {
    if (!Number.isSafeInteger(asset.asset_id) || asset.asset_id <= 0
      || !Number.isSafeInteger(asset.release_id) || asset.release_id <= 0
      || typeof asset.name !== 'string' || !installationZip.test(asset.name)
      || typeof asset.tag !== 'string' || !/^v\d+\.\d+/.test(asset.tag)
      || typeof asset.published_at !== 'string' || !Number.isFinite(Date.parse(asset.published_at))
      || !Number.isSafeInteger(asset.download_count) || asset.download_count < 0
      || assets.has(asset.asset_id)) throw new Error('Invalid historical GitHub asset');
    assets.set(asset.asset_id, {...asset});
  }
  return assets;
}

export async function collectDownloads(api, baseline = expoBaseline, snapshot = githubSnapshot) {
  const historicalRequests = baselineRequests(baseline);
  const assets = snapshotAssets(snapshot);
  const releases = new Set();
  for await (const release of pages(api, 'releases')) {
    if (!Number.isSafeInteger(release.id) || typeof release.draft !== 'boolean') throw new Error('Invalid release data');
    // Never query private drafts. Formerly public assets retain only their recorded public count.
    if (release.draft || releases.has(release.id)) continue;
    if (!release.published_at) throw new Error('Release is missing its publication date');
    releases.add(release.id);
    for await (const asset of pages(api, `releases/${release.id}/assets`)) {
      if (typeof asset.name !== 'string' || !Number.isSafeInteger(asset.id)) throw new Error('Invalid asset data');
      if (!installationZip.test(asset.name)) continue;
      if (asset.state !== 'uploaded' || !Number.isSafeInteger(asset.download_count) || asset.download_count < 0) {
        throw new Error('Invalid installation asset count or upload state');
      }
      const previous = assets.get(asset.id);
      if (previous && (previous.name !== asset.name || previous.release_id !== release.id)) {
        throw new Error('Historical or repeated asset identity mismatch');
      }
      assets.set(asset.id, {asset_id: asset.id, release_id: release.id, name: asset.name,
        download_count: Math.max(previous?.download_count ?? 0, asset.download_count)});
    }
  }
  // Union by asset ID, not filename or old badge total; live counts replace rather than add to history.
  let total = 0;
  for (const asset of assets.values()) {
    total += asset.download_count;
    if (!Number.isSafeInteger(total)) throw new Error('Download total exceeds safe integer range');
  }
  const requests = historicalRequests + total;
  if (!Number.isSafeInteger(requests)) throw new Error('Combined request total exceeds safe integer range');
  return {schemaVersion: 1, label: 'download requests', message: requests.toLocaleString('en-US'), color: '1bd9ce'};
}

export async function publishBadge(api, badge) {
  const content = `${JSON.stringify(badge, null, 2)}\n`;
  const ref = await api(`git/ref/heads/${statsBranch}`, {allowMissing: true});
  if (ref) {
    const previous = await api(`contents/downloads.json?ref=${ref.object.sha}`);
    if (previous.type !== 'file' || previous.encoding !== 'base64') throw new Error('Invalid previous badge data');
    if (Buffer.from(previous.content, 'base64').toString('utf8') === content) return false;
    await api('contents/downloads.json', {method: 'PUT', body: {
      message: 'Update download request count', branch: statsBranch,
      sha: previous.sha, content: Buffer.from(content).toString('base64'),
    }});
  } else {
    // An independent data-only branch keeps generated commits out of protected master.
    const tree = await api('git/trees', {method: 'POST', body: {
      tree: [{path: 'downloads.json', mode: '100644', type: 'blob', content}],
    }});
    const commit = await api('git/commits', {method: 'POST', body: {
      message: 'Initialize download request count', tree: tree.sha, parents: [],
    }});
    await api('git/refs', {method: 'POST', body: {ref: `refs/heads/${statsBranch}`, sha: commit.sha}});
  }
  return true;
}

export async function updateBadge(api, publish = false, snapshot = githubSnapshot) {
  // Any failure above publication leaves the last good public JSON untouched.
  const badge = await collectDownloads(api, expoBaseline, snapshot);
  if (publish) await publishBadge(api, badge);
  return badge;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const publish = process.argv.includes('--publish');
  if (publish && (!process.env.GITHUB_TOKEN || process.env.GITHUB_REPOSITORY !== repository)) {
    throw new Error('Publication requires the existing CUTROOM repository Actions token');
  }
  updateBadge(githubApi(process.env.GITHUB_TOKEN), publish)
    .then(badge => console.log(JSON.stringify(badge)))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
