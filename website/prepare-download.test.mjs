import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {verifyArchive, downloadEntries, assertPublishable, assertArchiveSize} from './prepare-download.mjs';

const bytes = Buffer.from('synthetic archive fixture');
const release = {filename: 'CUTROOM-test.zip', bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex')};
test('accepts the exact approved bytes', () => assert.equal(verifyArchive(bytes, release), bytes));
test('rejects wrong size', () => assert.throws(() => verifyArchive(Buffer.alloc(1), release), /size mismatch/));
test('rejects same-size corruption', () => assert.throws(() => verifyArchive(Buffer.alloc(bytes.length), release), /checksum mismatch/));
test('showcase-size packages retain exact size and checksum verification', () => {
  const largerBytes = Buffer.alloc(10 * 1024 * 1024 + 1, 0x5a);
  const largerRelease = {...release, bytes: largerBytes.length, sha256: createHash('sha256').update(largerBytes).digest('hex')};
  assert.equal(verifyArchive(largerBytes, largerRelease), largerBytes);
  largerBytes[largerBytes.length - 1] ^= 1;
  assert.throws(() => verifyArchive(largerBytes, largerRelease), /checksum mismatch/);
  assert.throws(() => verifyArchive(largerBytes.subarray(1), largerRelease), /size mismatch/);
});
test('release sizes remain bounded to 16 MiB before reading or downloading', () => {
  assert.doesNotThrow(() => assertArchiveSize(16 * 1024 * 1024));
  for (const size of [16 * 1024 * 1024 + 1, 0, -1, 1.5, NaN, Infinity, '1024', undefined]) {
    assert.throws(() => assertArchiveSize(size), /Invalid release size/);
    assert.throws(() => verifyArchive(bytes, {...release, bytes: size}), /Invalid release size/);
  }
});
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

test('dated hotfix packages keep source separate and require exact approved bytes', () => {
  const combined = {...release,filename:'CUTROOM-1.2-Beta-20261019-hotfix1.zip',
    platforms:{windows:{...release,filename:'CUTROOM-1.2-Beta-Windows-20261019-hotfix1.zip'},
      mac:{...release,filename:'CUTROOM-1.2-Beta-Mac-20261019-hotfix1.zip'}},
    source_archive:{...release,filename:'SOURCE-20261019-hotfix1.zip'}};
  assert.deepEqual(downloadEntries(combined).map(entry => entry.filename), [combined.filename,
    combined.platforms.windows.filename,combined.platforms.mac.filename,combined.source_archive.filename]);
  assert.equal(verifyArchive(bytes,combined.source_archive),bytes);
  assert.throws(()=>verifyArchive(Buffer.alloc(1),combined.source_archive),/size mismatch/);
  assert.throws(()=>verifyArchive(Buffer.alloc(bytes.length),combined.source_archive),/checksum mismatch/);
});

test('dated source hotfix names cannot broaden into arbitrary names or paths', () => {
  for (const filename of ['SOURCE-20261019-hotfix0.zip','SOURCE-20261019-hotfix01.zip',
    'SOURCE-2026101-hotfix1.zip','SOURCE-202610199-hotfix1.zip','SOURCE-20261019-hotfix.zip',
    'SOURCE-20261019-hotfix1-extra.zip','SOURCE-20261019-hotfix1.zip?download=1',
    'SOURCE-20261019-hotfix1.zip\n','SOURCE-20261019-hotfix1.zip\r','SOURCE-20261019-hotfix1.zip\u2028',
    '../SOURCE-20261019-hotfix1.zip','..\\SOURCE-20261019-hotfix1.zip',
    'SOURCE-20261019-hotfix1/evil.zip','SOURCE-20261019-hotfix1\\evil.zip']) {
    assert.throws(()=>downloadEntries({...release,source_archive:{...release,filename}}),/filename/);
  }
});
test('local candidates cannot enter the existing production deployment workflow', () => {
  assert.throws(()=>assertPublishable({...release,release_state:'local-candidate'}),/Local candidate/);
  assert.throws(()=>assertPublishable({...release,platforms:{}}),/validation provenance/);
  assert.doesNotThrow(()=>assertPublishable(release)); // Preserve the previous combined-release workflow.
});

test('public beta authorization keeps native provenance and accepted limits mandatory', () => {
  const source_commit = 'a'.repeat(40);
  const architecture = {status:'passed',feature_tests_passed:340,required_cases_passed:50,skipped:0,
    combined_archive_sha256:release.sha256,installation_checks:{...Object.fromEntries(["status", "launcher_health_and_api", "restart_persistence", "repeat_launch", "different_data_port_collision", "source_audio_and_caption_checks", "offline_ready_setup", "installed_packages_unchanged"].map(key=>[key,'passed'])),unicode_and_spaces_path:true},
    fresh_app_install:'passed',missing_pip_recovery:'passed',restart_persistence:'passed'};
  const beta = {...release,platforms:{windows:release,mac:release},release_state:'beta',public_beta_authorized:true,
    full_release_qualified:false,accepted_limitations:['Human editing and model acceptance remain pending.'],
    source_commit,native_validation_app_source_commit:source_commit,validated_pr_head:'b'.repeat(40),
    native_mac_validation:'automated-passed',mac_validation_url:'https://github.com/VanoPeradze/cutroom/actions/runs/39139136807',
    native_validation:{run_id:39139136807,head_commit:'b'.repeat(40),application_source_commit:source_commit,transcription_run:false,
      architectures:{arm64:architecture,x64:architecture}}};
  assert.doesNotThrow(()=>assertPublishable(beta));
  for (const key of Object.keys(architecture.installation_checks)) {
    for (const bad of [false, 'failed', 'pending', null, 'true']) {
      const failed = {...architecture.installation_checks,[key]:bad};
      assert.throws(()=>assertPublishable({...beta,native_validation:{...beta.native_validation,architectures:{arm64:architecture,x64:{...architecture,installation_checks:failed}}}}),/validation provenance/);
    }
    const missing = {...architecture.installation_checks}; delete missing[key];
    assert.throws(()=>assertPublishable({...beta,native_validation:{...beta.native_validation,architectures:{arm64:architecture,x64:{...architecture,installation_checks:missing}}}}),/validation provenance/);
  }
  assert.throws(()=>assertPublishable({...beta,native_validation:{...beta.native_validation,architectures:{arm64:architecture,x64:{...architecture,combined_archive_sha256:'0'.repeat(64)}}}}),/validation provenance/);
  for (const changed of [{public_beta_authorized:false},{full_release_qualified:true},{accepted_limitations:[]},
    {native_mac_validation:'pending'},{native_validation_app_source_commit:'c'.repeat(40)},
    {validated_pr_head:'unknown'},{mac_validation_url:'https://example.com/run'},
    {native_validation:{...beta.native_validation,architectures:{arm64:architecture}}},
    {native_validation:{...beta.native_validation,architectures:{arm64:architecture,x64:{...architecture,skipped:1}}}}]) {
    assert.throws(()=>assertPublishable({...beta,...changed}),/validation provenance/);
  }
});
