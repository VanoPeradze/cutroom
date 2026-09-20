import {lstat, mkdir, readFile, writeFile} from 'node:fs/promises';
import {dirname, join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const repository = resolve(dirname(fileURLToPath(import.meta.url)), '..');
// Only these public files may be copied. Do not copy whole source directories.
const assets = [
  ['docs/images/welcome.png', 'website/public/assets/welcome.png'],
  ['docs/images/editor.png', 'website/public/assets/editor.png'],
  ['docs/images/ai-options.png', 'website/public/assets/ai-options.png'],
  ['LICENSE', 'website/public/downloads/LICENSE'],
  ['docs/USER_GUIDE_EN.md', 'website/public/downloads/USER_GUIDE_EN.md'],
  ['docs/USER_GUIDE_HE.md', 'website/public/downloads/USER_GUIDE_HE.md'],
];

async function inspectPath(root, relative, optional = false) {
  const parts = relative.split('/');
  let path = root;
  for (let index = -1; index < parts.length; index++) {
    if (index >= 0) path = join(path, parts[index]);
    let info;
    try { info = await lstat(path); } catch (error) {
      if (optional && error.code === 'ENOENT') return undefined;
      throw error;
    }
    if (info.isSymbolicLink()) throw new Error(`Symbolic links are not allowed: ${path}`);
    if (index < parts.length - 1) {
      if (!info.isDirectory()) throw new Error(`Expected a directory: ${path}`);
    } else {
      if (!info.isFile()) throw new Error(`Expected a regular file: ${path}`);
      if (optional && info.nlink > 1) throw new Error(`Hard-linked output is not allowed: ${path}`);
      return info;
    }
  }
}

export async function prepareAssets(root = repository, {check = false} = {}) {
  root = resolve(root);
  const planned = [];
  // Read and validate every input and output before making any filesystem changes.
  for (const [source, destination] of assets) {
    await inspectPath(root, source);
    const existing = await inspectPath(root, destination, true);
    const bytes = await readFile(join(root, source));
    const current = existing ? await readFile(join(root, destination)) : undefined;
    planned.push({destination, bytes, existing, matches: current?.equals(bytes) ?? false});
  }
  const changed = planned.filter(asset => !asset.matches);
  if (check) {
    if (changed.length) throw new Error(`Public assets are missing or stale: ${changed.map(asset => asset.destination).join(', ')}. Run npm run prepare:assets.`);
    return {copied: 0, unchanged: planned.length};
  }
  for (const asset of changed) {
    const destination = join(root, asset.destination);
    await mkdir(dirname(destination), {recursive: true});
    await writeFile(destination, asset.bytes, {flag: asset.existing ? 'w' : 'wx'});
  }
  return {copied: changed.length, unchanged: planned.length - changed.length};
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2);
  if (args.length > 1 || (args.length === 1 && args[0] !== '--check')) {
    console.error('Usage: node prepare-assets.mjs [--check]');
    process.exitCode = 1;
  } else {
    prepareAssets(repository, {check: args[0] === '--check'})
      .then(({copied, unchanged}) => console.log(`Canonical website assets: ${copied} copied, ${unchanged} already match. No download required.`))
      .catch(error => { console.error(error.message); process.exitCode = 1; });
  }
}
