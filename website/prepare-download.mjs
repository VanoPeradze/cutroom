import {createHash} from 'node:crypto';
import {readFile, stat, open} from 'node:fs/promises';
import {dirname, resolve, basename} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));

export function verifyArchive(bytes, release) {
  if (!release.filename || basename(release.filename) !== release.filename || !/^CUTROOM-[\w.-]+\.zip$/.test(release.filename)) throw new Error('Invalid release filename');
  if (bytes.length !== release.bytes) throw new Error('Release size mismatch; nothing was written');
  if (createHash('sha256').update(bytes).digest('hex') !== release.sha256) throw new Error('Release checksum mismatch; nothing was written');
  return bytes;
}

async function readLocal(path, release) {
  if ((await stat(path)).size !== release.bytes) throw new Error('Local ZIP size does not match the approved release');
  return verifyArchive(await readFile(path), release);
}

async function main() {
  const release = JSON.parse(await readFile(resolve(root, 'release.json'), 'utf8'));
  if (!Number.isSafeInteger(release.bytes) || release.bytes <= 0 || release.bytes > 10 * 1024 * 1024) throw new Error('Invalid release size');
  // Validate the filename before using it as a filesystem path.
  if (basename(release.filename) !== release.filename || !/^CUTROOM-[\w.-]+\.zip$/.test(release.filename)) throw new Error('Invalid release filename');
  const destination = resolve(root, 'public/downloads', release.filename);
  try {
    await readLocal(destination, release);
    console.log('Approved download already present; checksum verified.');
    return;
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  let bytes;
  if (process.argv[2]) {
    bytes = await readLocal(resolve(process.argv[2]), release);
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

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
