// Repository automation: count installation ZIPs only, then publish after all reads succeed.
import {pathToFileURL} from 'node:url';
import {resolve} from 'node:path';

export const repository = 'VanoPeradze/cutroom';
export const statsBranch = 'download-stats';
export const installationZip = /^CUTROOM-\d+\.\d+(?:\.\d+)?(?:-Beta)?(?:-(?:Windows|Mac))?\.zip$/;

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

export async function collectDownloads(api) {
  let total = 0;
  const releases = new Set();
  const assets = new Set();
  for await (const release of pages(api, 'releases')) {
    if (!Number.isSafeInteger(release.id) || typeof release.draft !== 'boolean') throw new Error('Invalid release data');
    // Include published betas, but never drafts visible to an authenticated maintainer.
    if (release.draft || releases.has(release.id)) continue;
    if (!release.published_at) throw new Error('Release is missing its publication date');
    releases.add(release.id);
    // Paginate assets separately: the embedded release.assets list may be incomplete.
    for await (const asset of pages(api, `releases/${release.id}/assets`)) {
      if (typeof asset.name !== 'string' || !Number.isSafeInteger(asset.id)) throw new Error('Invalid asset data');
      if (!installationZip.test(asset.name) || assets.has(asset.id)) continue;
      if (asset.state !== 'uploaded' || !Number.isSafeInteger(asset.download_count) || asset.download_count < 0) {
        throw new Error('Invalid installation asset count or upload state');
      }
      assets.add(asset.id);
      total += asset.download_count;
      if (!Number.isSafeInteger(total)) throw new Error('Download total exceeds safe integer range');
    }
  }
  return {schemaVersion: 1, label: 'GitHub downloads', message: total.toLocaleString('en-US'), color: '1bd9ce'};
}

export async function publishBadge(api, badge) {
  const content = `${JSON.stringify(badge, null, 2)}\n`;
  const ref = await api(`git/ref/heads/${statsBranch}`, {allowMissing: true});
  if (ref) {
    const previous = await api(`contents/downloads.json?ref=${ref.object.sha}`);
    if (previous.type !== 'file' || previous.encoding !== 'base64') throw new Error('Invalid previous badge data');
    if (Buffer.from(previous.content, 'base64').toString('utf8') === content) return false;
    await api('contents/downloads.json', {method: 'PUT', body: {
      message: 'Update GitHub installation download count', branch: statsBranch,
      sha: previous.sha, content: Buffer.from(content).toString('base64'),
    }});
  } else {
    // An independent data-only branch keeps generated commits out of protected master.
    const tree = await api('git/trees', {method: 'POST', body: {
      tree: [{path: 'downloads.json', mode: '100644', type: 'blob', content}],
    }});
    const commit = await api('git/commits', {method: 'POST', body: {
      message: 'Initialize GitHub installation download count', tree: tree.sha, parents: [],
    }});
    await api('git/refs', {method: 'POST', body: {ref: `refs/heads/${statsBranch}`, sha: commit.sha}});
  }
  return true;
}

export async function updateBadge(api, publish = false) {
  // Any failure above publication leaves the last good public JSON untouched.
  const badge = await collectDownloads(api);
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
