import {test} from 'node:test';
import assert from 'node:assert/strict';
import {link, lstat, mkdir, mkdtemp, readFile, readdir, rm, symlink, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, join} from 'node:path';
import {prepareAssets} from './prepare-assets.mjs';

const pairs = [
  ['docs/images/welcome.png', 'website/public/assets/welcome.png'],
  ['docs/images/editor.png', 'website/public/assets/editor.png'],
  ['docs/images/ai-options.png', 'website/public/assets/ai-options.png'],
  ['LICENSE', 'website/public/downloads/LICENSE'],
  ['docs/USER_GUIDE_EN.md', 'website/public/downloads/USER_GUIDE_EN.md'],
  ['docs/USER_GUIDE_HE.md', 'website/public/downloads/USER_GUIDE_HE.md'],
];

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'cutroom-assets-'));
  t.after(() => rm(root, {recursive: true, force: true}));
  for (const [index, [source]] of pairs.entries()) {
    await put(root, source, Buffer.from([0, 255, index, 13, 10, 128]));
  }
  await mkdir(join(root, 'website'));
  return root;
}

async function put(root, path, bytes) {
  await mkdir(dirname(join(root, path)), {recursive: true});
  await writeFile(join(root, path), bytes);
}

async function listFiles(root, relative = '') {
  const files = [];
  for (const entry of await readdir(join(root, relative), {withFileTypes: true})) {
    const path = relative ? `${relative}/${entry.name}` : entry.name;
    files.push(...(entry.isDirectory() ? await listFiles(root, path) : [path]));
  }
  return files.sort();
}

test('copies only the six approved files byte-for-byte and is idempotent', async t => {
  const root = await fixture(t);
  await put(root, 'docs/images/unapproved.png', 'not public');
  await put(root, 'private.txt', 'not public');
  const untouched = ['website/public/assets/favicon.svg', 'website/public/downloads/release.zip', 'website/public/downloads/release.zip.sha256'];
  for (const path of untouched) await put(root, path, 'untouched');
  await put(root, pairs[0][1], 'stale generated screenshot');
  assert.deepEqual(await prepareAssets(root), {copied: 6, unchanged: 0});
  for (const [source, destination] of pairs) {
    assert.deepEqual(await readFile(join(root, destination)), await readFile(join(root, source)));
  }
  for (const path of untouched) assert.equal(await readFile(join(root, path), 'utf8'), 'untouched');
  assert.deepEqual(await listFiles(join(root, 'website/public')), [...pairs.map(([, path]) => path.replace('website/public/', '')), ...untouched.map(path => path.replace('website/public/', ''))].sort());
  const timestamps = await Promise.all(pairs.map(([, path]) => lstat(join(root, path)).then(info => info.mtimeMs)));
  assert.deepEqual(await prepareAssets(root), {copied: 0, unchanged: 6});
  assert.deepEqual(await Promise.all(pairs.map(([, path]) => lstat(join(root, path)).then(info => info.mtimeMs))), timestamps);
  assert.deepEqual(await prepareAssets(root, {check: true}), {copied: 0, unchanged: 6});
});

test('check mode reports missing or stale assets without creating or changing them', async t => {
  const root = await fixture(t);
  await assert.rejects(prepareAssets(root, {check: true}), /missing or stale/);
  assert.deepEqual(await readdir(join(root, 'website')), []);
  await prepareAssets(root);
  await put(root, pairs[5][1], 'stale');
  await assert.rejects(prepareAssets(root, {check: true}), /missing or stale/);
  assert.equal(await readFile(join(root, pairs[5][1]), 'utf8'), 'stale');
});

test('a missing final source is rejected before any output is written', async t => {
  const root = await fixture(t);
  await put(root, pairs[0][1], 'preserve this output');
  await rm(join(root, pairs[5][0]));
  await assert.rejects(prepareAssets(root), {code: 'ENOENT'});
  assert.equal(await readFile(join(root, pairs[0][1]), 'utf8'), 'preserve this output');
  assert.deepEqual(await listFiles(join(root, 'website/public')), ['assets/welcome.png']);
});

test('rejects a hard-linked output without modifying its other link', async t => {
  const root = await fixture(t);
  const backing = join(root, 'keep.txt');
  await writeFile(backing, 'must not be changed');
  await mkdir(dirname(join(root, pairs[5][1])), {recursive: true});
  await link(backing, join(root, pairs[5][1]));
  await assert.rejects(prepareAssets(root), /Hard-linked output is not allowed/);
  assert.equal(await readFile(backing, 'utf8'), 'must not be changed');
  await assert.rejects(lstat(join(root, pairs[0][1])), {code: 'ENOENT'});
});

for (const target of ['source', 'destination']) {
  test(`rejects a directory in place of a ${target} file before writing`, async t => {
    const root = await fixture(t);
    const path = join(root, pairs[5][target === 'source' ? 0 : 1]);
    if (target === 'source') await rm(path);
    await mkdir(path, {recursive: true});
    await assert.rejects(prepareAssets(root), /Expected a regular file/);
    await assert.rejects(lstat(join(root, pairs[0][1])), {code: 'ENOENT'});
  });
}

for (const target of ['source file', 'source directory', 'destination file', 'destination directory']) {
  test(`rejects a linked ${target} before writing`, async t => {
    const root = await fixture(t);
    const isDirectory = target.endsWith('directory');
    const source = target.startsWith('source');
    const relative = isDirectory ? (source ? 'docs/images' : 'website/public/assets') : pairs[5][source ? 0 : 1];
    const path = join(root, relative);
    const backing = join(root, isDirectory ? 'link-directory' : 'link-file');
    if (isDirectory) await mkdir(backing);
    else await writeFile(backing, 'must not be changed');
    if (source) await rm(path, {recursive: isDirectory});
    await mkdir(dirname(path), {recursive: true});
    try { await symlink(backing, path, isDirectory ? 'junction' : 'file'); } catch (error) {
      if (process.platform === 'win32' && ['EPERM', 'EACCES'].includes(error.code) && !isDirectory) {
        t.skip('Windows file symlinks require Developer Mode or elevation; directory junction cases still run.');
        return;
      }
      throw error;
    }
    await assert.rejects(prepareAssets(root), /Symbolic links are not allowed/);
    await assert.rejects(lstat(join(root, pairs[0][1])), {code: 'ENOENT'});
    if (!isDirectory) assert.equal(await readFile(backing, 'utf8'), 'must not be changed');
  });
}
