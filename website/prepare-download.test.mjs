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
  for (const filename of ['../CUTROOM-test.zip', '/CUTROOM-test.zip', '..\\CUTROOM-test.zip', 'CUTROOM-..\\test.zip', 'SOURCE-../test.zip', 'other.zip']) {
    assert.throws(() => verifyArchive(bytes, {...release, filename}), /filename/);
  }
});

test('a Mac download may use the exact combined archive once, with a separate source archive', () => {
  const platforms = {windows: {...release, filename:'CUTROOM-1.2-Beta-Windows-review-fe35453.zip'}, mac:{...release,folder:'mac'}};
  const source_archive = {...release, filename:'SOURCE-fe35453.zip'};
  const combined = {...release,layout:'windows-mac-folders-v1',platforms,source_archive};
  assert.deepEqual(downloadEntries(combined).map(entry => entry.filename), [release.filename, platforms.windows.filename, source_archive.filename]);
  assert.throws(()=>downloadEntries({...release,platforms:{...platforms,linux:release}}),/Only Windows and Mac/);
  assert.throws(()=>downloadEntries({...combined,platforms:{...platforms,mac:{...platforms.mac,bytes:release.bytes+1}}}),/mismatched/);
  assert.throws(()=>downloadEntries({...combined,platforms:{...platforms,mac:{...platforms.mac,sha256:'0'.repeat(64)}}}),/mismatched/);
  assert.throws(()=>downloadEntries({...combined,platforms:{...platforms,mac:{...platforms.mac,url:'https://example.com/wrong.zip'}}}),/mismatched/);
  assert.throws(()=>downloadEntries({...combined,platforms:{...platforms,mac:{...platforms.mac,folder:'windows'}}}),/mac folder/);
  assert.throws(()=>downloadEntries({...release,platforms:{...platforms,mac:{...release,filename:'../CUTROOM-test.zip'}}}),/filename/);
  assert.throws(()=>downloadEntries({...release,source_archive:{...source_archive,filename:'../SOURCE-fe35453.zip'}}),/filename/);
});

test('older distinct platform archives remain supported', () => {
  const platforms = {windows:{...release,filename:'CUTROOM-1.1-Beta-Windows.zip'},mac:{...release,filename:'CUTROOM-1.1-Beta-Mac.zip'}};
  assert.equal(downloadEntries({...release,platforms}).length,3);
});
test('local candidates cannot enter the existing production deployment workflow', () => {
  assert.throws(()=>assertPublishable({...release,release_state:'local-candidate'}),/Local candidate/);
  assert.throws(()=>assertPublishable({...release,platforms:{}}),/validation provenance/);
  assert.doesNotThrow(()=>assertPublishable(release)); // Preserve the previous combined-release workflow.
});

test('public beta authorization keeps native provenance and accepted limits mandatory', () => {
  const source_commit = 'a'.repeat(40);
  const architecture = {status:'passed',offline_checks_passed:69,feature_tests_passed:340,required_cases_passed:50,skipped:0,
    fresh_app_install:'passed',missing_pip_recovery:'passed',restart_persistence:'passed'};
  const beta = {...release,platforms:{windows:release,mac:release},release_state:'beta',public_beta_authorized:true,
    full_release_qualified:false,accepted_limitations:['Human editing and model acceptance remain pending.'],
    source_commit,native_validation_app_source_commit:source_commit,validated_pr_head:'b'.repeat(40),
    native_mac_validation:'automated-passed',mac_validation_url:'https://github.com/VanoPeradze/cutroom/actions/runs/39139136807',
    native_validation:{run_id:39139136807,head_commit:'b'.repeat(40),application_source_commit:source_commit,transcription_run:false,
      architectures:{arm64:architecture,x64:architecture}}};
  assert.doesNotThrow(()=>assertPublishable(beta));
  for (const changed of [{public_beta_authorized:false},{full_release_qualified:true},{accepted_limitations:[]},
    {native_mac_validation:'pending'},{native_validation_app_source_commit:'c'.repeat(40)},
    {validated_pr_head:'unknown'},{mac_validation_url:'https://example.com/run'},
    {native_validation:{...beta.native_validation,architectures:{arm64:architecture}}},
    {native_validation:{...beta.native_validation,architectures:{arm64:architecture,x64:{...architecture,skipped:1}}}}]) {
    assert.throws(()=>assertPublishable({...beta,...changed}),/validation provenance/);
  }
});
