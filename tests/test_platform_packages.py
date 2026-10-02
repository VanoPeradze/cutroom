"""Separate downloads preserve verified product bytes, permissions and provenance."""
import json
import zipfile
import pytest
from scripts import build_platform_packages as platforms
from test_universal_package import package_source, build, rewrite


def test_separate_downloads_preserve_launchers_source_and_valid_inventories(package_source, tmp_path):
    combined = build(package_source)
    original = combined.read_bytes()
    target = tmp_path / 'platforms'
    result = platforms.build_packages(combined, target)
    assert set(result['platforms']) == {'windows', 'mac'}
    for platform, details in result['platforms'].items():
        path = target / details['filename']
        metadata = platforms.verify_platform(path, combined, platform)
        assert details['source_files_changed'] is False
        assert path.with_suffix('.zip.sha256').read_text().split()[0] == details['sha256']
        with zipfile.ZipFile(path) as package:
            assert all(not name.startswith(('mac/', 'windows/')) for name in package.namelist())
            for name, digest in metadata['files'].items():
                assert platforms.sha(package.read(name)) == digest
            assert 'App/server.py' in package.namelist()
        if platform == 'mac':
            assert metadata['mac_manual_install_verified'] is False
            assert metadata['combined_archive_sha256'] == platforms.sha(original)
    assert combined.read_bytes() == original
    with pytest.raises(FileExistsError):
        platforms.build_packages(combined, target)


@pytest.mark.parametrize('platform,name', [('windows','App/server.py'),('mac','App/server.py'),('mac','START CUTROOM.command')])
def test_projection_rejects_even_self_consistent_payload_replacement(package_source, tmp_path, platform, name):
    combined = build(package_source)
    target = tmp_path / 'platforms'
    result = platforms.build_packages(combined, target)
    def change(files):
        files[name] = (files[name][0], b'replaced')
        info, data = files['App/TEST_BUILD.json']
        manifest = json.loads(data)
        manifest['files'][name] = platforms.sha(b'replaced')
        files['App/TEST_BUILD.json'] = (info, platforms._bytes_json(manifest))
    bad = rewrite(target/result['platforms'][platform]['filename'], tmp_path/'bad.zip', change)
    with pytest.raises(ValueError, match='differs'):
        platforms.verify_platform(bad, combined, platform)


def test_projection_requires_verified_combined_and_retains_mac_permissions(package_source, tmp_path):
    combined = build(package_source)
    target = tmp_path / 'platforms'
    result = platforms.build_packages(combined, target)
    def change(files):
        info, data = files['START CUTROOM.command']
        info.external_attr = 0o100644 << 16
    bad = rewrite(target/result['platforms']['mac']['filename'], tmp_path/'bad-mode.zip', change)
    with pytest.raises(ValueError, match='permissions'):
        platforms.verify_platform(bad, combined, 'mac')
    corrupted = tmp_path/'corrupt.zip';corrupted.write_bytes(b'not a zip')
    with pytest.raises(zipfile.BadZipFile):
        platforms.build_packages(corrupted, tmp_path/'invalid')
    assert not (tmp_path/'invalid').exists()
    with pytest.raises(ValueError, match='Linux'):
        platforms._projection(combined,'linux')
