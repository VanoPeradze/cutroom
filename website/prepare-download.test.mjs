import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {verifyArchive, downloadEntries, assertPublishable} from './prepare-download.mjs';

const bytes = Buffer.from('synthetic archive fixture');
const release = {filename: 'CUTROOM-test.zip', bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')};
test('accepts the exact approved bytes', () => assert.equal(verifyArchive(bytes, release), bytes));
test('rejects wrong size', () => assert.throws(() => verifyArchive(Buffer.alloc(1), release), /size mismatch/));
test('rejects same-size corruption', () => assert.throws(() => verifyArchive(Buffer.alloc(bytes.length), release), /checksum mismatch/));
test('rejects unsafe release paths', () => {
  for (const filename of ['../CUTROOM-test.zip', '/CUTROOM-test.zip', '..\\CUTROOM-test.zip', 'other.zip']) {
    assert.throws(() => verifyArchive(bytes, {...release, filename}), /filename/);
  }
});

test('platform package mapping is distinct and excludes fictitious Linux archives', () => {
  const platforms = {windows: {...release, filename:'CUTROOM-1.1-Beta-Windows.zip'}, mac:{...release, filename:'CUTROOM-1.1-Beta-Mac.zip'}};
  assert.equal(downloadEntries({...release, platforms}).length, 3);
  assert.throws(()=>downloadEntries({...release,platforms:{...platforms,linux:release}}),/Only Windows and Mac/);
  assert.throws(()=>downloadEntries({...release,platforms:{...platforms,mac:platforms.windows}}),/filename/);
});
test('local candidates cannot enter the existing production deployment workflow', () => {
  assert.throws(()=>assertPublishable({...release,release_state:'local-candidate'}),/Local candidate/);
  assert.throws(()=>assertPublishable({...release,platforms:{}}),/validation provenance/);
  assert.doesNotThrow(()=>assertPublishable(release)); // Preserve the previous combined-release workflow.
});
