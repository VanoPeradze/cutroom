'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

// Exercise the exact setup decision, but replace every external executable with
// an in-process stub. No package manager, AI service, or network is invoked.
const app = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(app, 'setup_windows.ps1'), 'utf8');
const winOnly = { skip: process.platform !== 'win32' };

function optionalAiBlock() {
  const start = source.search(/\r?\n {4}\$ollamaPath = Resolve-Executable -Name "ollama\.exe"/);
  const end = source.indexOf('    $runtimeDirectories = @(', start);
  assert.ok(start >= 0 && end > start, 'Optional AI setup block not found');
  return source.slice(start, end);
}

function runDecision({ installed, winget }) {
  const script = [
    '$ErrorActionPreference = "Stop"',
    'Set-StrictMode -Version 2.0',
    `function Resolve-Executable { param([string]$Name) if ($Name -ne "ollama.exe") { throw "Unexpected executable" }; ${installed ? 'return "C:\\cutroom-test\\ollama.exe"' : 'return $null'} }`,
    `function Get-WingetPath { ${winget ? 'return "C:\\cutroom-test\\winget.exe"' : 'return $null'} }`,
    'function Install-WingetPackage { param([string]$PackageId, [string]$DisplayName) Write-Host "UNEXPECTED-INSTALL"; Start-Sleep -Seconds 30 }',
    'function Add-ProcessPath { param([string]$Directory) Write-Host "EXISTING-ENGINE-RETAINED" }',
    optionalAiBlock(),
    'Write-Host "SETUP-CONTINUES"',
  ].join('\r\n');
  return spawnSync('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(script, 'utf16le').toString('base64')], {
    encoding: 'utf8', timeout: 8000, windowsHide: true,
  });
}

for (const winget of [false, true]) {
  test(`setup continues without optional AI when winget is ${winget ? 'present' : 'missing'}`, winOnly, () => {
    const result = runDecision({ installed: false, winget });
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stderr);
    assert.doesNotMatch(result.stdout, /UNEXPECTED-INSTALL/);
    assert.match(result.stdout, /AI Connection/);
    assert.match(result.stdout, /SETUP-CONTINUES/);
  });
}

test('setup retains an existing local AI engine', winOnly, () => {
  const result = runDecision({ installed: true, winget: true });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /EXISTING-ENGINE-RETAINED/);
  assert.match(result.stdout, /SETUP-CONTINUES/);
});

test('installer verifier accepts the changed setup and rejects damaged inputs', winOnly, (t) => {
  const tempRoot = fs.realpathSync(os.tmpdir());
  const root = fs.realpathSync(fs.mkdtempSync(path.join(tempRoot, 'cutroom-installer-test-')));
  assert.equal(path.dirname(root).toLowerCase(), tempRoot.toLowerCase());
  assert.ok(path.basename(root).startsWith('cutroom-installer-test-'));
  // Only our own verified, uniquely named test fixture is removed.
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  for (const file of [
    'requirements.txt', 'config.json', 'server.py', 'scripts/preflight.py',
    'cutroom/__init__.py', 'cutroom/director.py', 'cutroom/render.py',
    'web/index.html', 'web/styles.css', 'web/app.js',
  ]) {
    const target = path.join(root, file);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, 'synthetic fixture\n');
  }
  const setup = path.join(root, 'setup_windows.ps1');
  const verify = path.join(root, 'scripts', 'verify_windows_installer.ps1');
  fs.writeFileSync(setup, source);
  fs.copyFileSync(path.join(app, 'scripts', 'verify_windows_installer.ps1'), verify);
  function verifyFixture() {
    return spawnSync('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-File', verify], { encoding: 'utf8', timeout: 15000, windowsHide: true });
  }
  let result = verifyFixture();
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stdout + result.stderr);
  fs.unlinkSync(path.join(root, 'server.py'));
  result = verifyFixture();
  assert.notEqual(result.status, 0);
  assert.match(result.stdout, /missing server\.py/);
  fs.writeFileSync(path.join(root, 'server.py'), 'synthetic fixture\n');
  fs.writeFileSync(setup, `${source}\r\n# Install-WingetPackage -PackageId "Ollama.Ollama"\r\n`);
  result = verifyFixture();
  assert.notEqual(result.status, 0, 'Automatic optional AI installation must be rejected');
});
