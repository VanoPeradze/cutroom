import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {verifyArchive} from './prepare-download.mjs';

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
