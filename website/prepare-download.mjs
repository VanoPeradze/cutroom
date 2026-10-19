import {createHash} from 'node:crypto';
import {readFile, stat, open} from 'node:fs/promises';
import {dirname, resolve, basename} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

function assertArchiveFilename(filename) {
  if (typeof filename !== 'string' || filename !== filename.trim() || basename(filename) !== filename
    || !/^(?:CUTROOM-[\w.-]+|SOURCE-(?:[a-f0-9]{7,40}|\d{8}-hotfix[1-9]\d*))\.zip$/.test(filename)) throw new Error('Invalid release filename');
}

export function verifyArchive(bytes, release) {
  assertArchiveFilename(release.filename);
  if (bytes.length !== release.bytes) throw new Error('Release size mismatch; nothing was written');
  if (createHash('sha256').update(bytes).digest('hex') !== release.sha256) throw new Error('Release checksum mismatch; nothing was written');
  return bytes;
}

async function readLocal(path, release) {
  if ((await stat(path)).size !== release.bytes) throw new Error('Local ZIP size does not match the approved release');
  return verifyArchive(await readFile(path), release);
}

export function downloadEntries(release) {
  const platforms = release.platforms;
  if (platforms && Object.keys(platforms).sort().join(',') !== 'mac,windows') throw new Error('Only Windows and Mac packages are supported; Linux uses the source guide');
  if (platforms && platforms.windows?.filename === platforms.mac?.filename) throw new Error('Windows and Mac downloads must remain distinct');
  if (platforms?.mac?.filename === release.filename
    && (release.layout !== 'windows-mac-folders-v1' || platforms.mac.folder !== 'mac')) throw new Error('Combined Mac download must identify its mac folder');
  const entries = [release, ...(platforms ? [platforms.windows, platforms.mac] : []), ...(release.source_archive ? [release.source_archive] : [])];
  return uniqueDownloadEntries(entries);
}

export function uniqueDownloadEntries(entries) {
  const unique = new Map();
  for (const entry of entries) {
    assertArchiveFilename(entry?.filename);
    const previous = unique.get(entry.filename);
    if (previous && (previous.sha256 !== entry.sha256 || previous.bytes !== entry.bytes || previous.url !== entry.url)) throw new Error('Shared download filename has mismatched bytes, checksum or URL');
    if (!previous) unique.set(entry.filename, entry);
  }
  return [...unique.values()];
}

function hasBetaNativeProvenance(release) {
  const native = release.native_validation;
  return native?.application_source_commit === release.source_commit
    && native.head_commit === release.validated_pr_head && native.transcription_run === false
    && Number.isSafeInteger(native.run_id) && native.run_id > 0
    && release.mac_validation_url === `https://github.com/VanoPeradze/cutroom/actions/runs/${native.run_id}`
    && ['arm64', 'x64'].every(architecture => {
      const checks = native.architectures?.[architecture];
      return checks?.status === 'passed' && checks.skipped === 0
        && ['offline_checks_passed', 'feature_tests_passed', 'required_cases_passed'].every(key => Number.isSafeInteger(checks[key]) && checks[key] > 0)
        && ['fresh_app_install', 'missing_pip_recovery', 'restart_persistence'].every(key => checks[key] === 'passed');
    });
}

export function assertPublishable(release) {
  if (release.release_state === 'local-candidate') throw new Error('Local candidate only: native Mac checks and publication approval remain pending');
  if (release.release_state === 'beta' && !release.platforms) throw new Error('Platform release requires authorization, accepted beta limits and exact source/native Mac validation provenance');
  const authorizedBeta = release.release_state === 'beta' && release.public_beta_authorized === true
    && release.full_release_qualified === false && Array.isArray(release.accepted_limitations)
    && release.accepted_limitations.length > 0 && release.accepted_limitations.every(limit => typeof limit === 'string' && limit.trim());
  const nativePassed = (release.release_state === 'validated' && release.native_mac_validation === 'passed')
    || (authorizedBeta && release.native_mac_validation === 'automated-passed'
      && release.native_validation_app_source_commit === release.source_commit && hasBetaNativeProvenance(release));
  if (release.platforms && ((!authorizedBeta && release.release_state !== 'validated') || !nativePassed
    || !/^[a-f0-9]{40}$/.test(release.source_commit || '') || !/^[a-f0-9]{40}$/.test(release.validated_pr_head || '')
    || !/^https:\/\/github\.com\/VanoPeradze\/cutroom\/actions\/runs\/\d+$/.test(release.mac_validation_url || ''))) {
    throw new Error('Platform release requires authorization, accepted beta limits and exact source/native Mac validation provenance');
  }
}

async function prepareOne(release, localPath) {
  if (!Number.isSafeInteger(release.bytes) || release.bytes <= 0 || release.bytes > 10 * 1024 * 1024) throw new Error('Invalid release size');
  // Validate the filename before using it as a filesystem path.
  assertArchiveFilename(release.filename);
  const destination = resolve(root, 'public/downloads', release.filename);
  try {
    await readLocal(destination, release);
    console.log('Approved download already present; checksum verified.');
    return;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  let bytes;
  if (localPath) {
    bytes = await readLocal(resolve(localPath), release);
  } else {
    if (new URL(release.url).protocol !== 'https:') throw new Error('Release URL must use HTTPS');
    const response = await fetch(release.url, {signal: AbortSignal.timeout(30000)});
    if (!response.ok || !response.body) throw new Error('Approved download unavailable; provide the matching local ZIP path instead.');
    const chunks = [];
    let length = 0;
    for await (const chunk of response.body) {
      length += chunk.length;
      if (length > release.bytes) throw new Error('Download exceeds the approved size');
      chunks.push(chunk);
    }
    bytes = verifyArchive(Buffer.concat(chunks), release);
  }
  // Exclusive creation: never replace another release or an existing corrupt file.
  const file = await open(destination, 'wx');
  try { await file.writeFile(bytes); } finally { await file.close(); }
  console.log('Approved beta ZIP prepared locally. It remains excluded from Git.');
}

async function main() {
  const release = JSON.parse(await readFile(resolve(root, 'release.json'), 'utf8'));
  assertPublishable(release);
  const retained = JSON.parse(await readFile(resolve(root, 'retained-downloads.json'), 'utf8'));
  const entries = uniqueDownloadEntries([...downloadEntries(release), ...retained]);
  for (const [index, entry] of entries.entries()) {
    await prepareOne(entry, index === 0 ? process.argv[2] : undefined);
    const sidecar = resolve(root, 'public/downloads', entry.filename + '.sha256');
    const expected = `${entry.sha256}  ${entry.filename}\n`;
    try {
      if ((await readFile(sidecar, 'utf8')).trim() !== expected.trim()) throw new Error('Release checksum sidecar mismatch');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      const file = await open(sidecar, 'wx');
      try { await file.writeFile(expected); } finally { await file.close(); }
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
