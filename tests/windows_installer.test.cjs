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
    'requirements.txt', 'config.json', 'server.py', 'scripts/preflight.py', 'scripts/windows_runtime.py',
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

test('generated runtime paths survive a Hebrew folder and reach the launched program', winOnly, (t) => {
  const tempRoot = fs.realpathSync(os.tmpdir());
  const root = fs.realpathSync(fs.mkdtempSync(path.join(tempRoot, 'cutroom-unicode-test-')));
  assert.equal(path.dirname(root).toLowerCase(), tempRoot.toLowerCase());
  assert.ok(path.basename(root).startsWith('cutroom-unicode-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const toolDir = path.join(root, '\u05e9\u05dc\u05d5\u05dd', 'bin');
  fs.mkdirSync(toolDir, { recursive: true });
  fs.mkdirSync(path.join(root, 'scripts'));
  fs.copyFileSync(path.join(app, 'scripts', 'windows_runtime.py'), path.join(root, 'scripts', 'windows_runtime.py'));
  const resultPath = path.join(root, 'result.json');
  const fakeProgram = [
    'import json, os, sys',
    'with open(os.environ["CUTROOM_TEST_RESULT"], "w", encoding="utf-8") as out:',
    '    json.dump({"path": os.environ.get("PATH", ""), "argv": sys.argv}, out, ensure_ascii=False)',
    'raise SystemExit(17)',
    '',
  ].join('\n');
  fs.writeFileSync(path.join(root, 'scripts', 'preflight.py'), fakeProgram);
  fs.writeFileSync(path.join(root, 'server.py'), fakeProgram);

  const from = source.indexOf('function Write-RuntimePaths {');
  const to = source.indexOf('function Stop-SetupTranscript {', from);
  assert.ok(from >= 0 && to > from, 'Runtime path writer missing');
  const writer = source.slice(from, to).replaceAll('$PSScriptRoot', '$env:CUTROOM_TEST_ROOT');
  const command = `${writer}\r\nWrite-RuntimePaths -Directories @($env:CUTROOM_TEST_TOOL_DIR)\r\n`;
  const fixtureEnv = Object.fromEntries(Object.entries(process.env).filter(([key]) => key.toUpperCase() !== 'PATH'));
  Object.assign(fixtureEnv, {
    PATH: process.env.PATH || process.env.Path || '',
    CUTROOM_TEST_ROOT: root, CUTROOM_TEST_TOOL_DIR: toolDir, CUTROOM_TEST_RESULT: resultPath,
  });
  const generated = spawnSync('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', Buffer.from(command, 'utf16le').toString('base64')], {
    cwd: root, env: fixtureEnv, encoding: 'utf8', timeout: 15000, windowsHide: true,
  });
  assert.ifError(generated.error);
  assert.equal(generated.status, 0, generated.stdout + generated.stderr);
  const saved = fs.readFileSync(path.join(root, '.runtime-paths.cmd'));
  assert.ok([...saved].every(byte => byte < 128), 'Batch runtime file must remain ASCII-safe');
  assert.match(saved.toString('ascii'), /CUTROOM_RUNTIME_PATHS_B64=/);

  const launch = path.join(root, 'launch-fixture.cmd');
  fs.writeFileSync(launch, '@echo off\r\nsetlocal EnableExtensions DisableDelayedExpansion\r\ncall ".runtime-paths.cmd"\r\npython "scripts\\windows_runtime.py" preflight\r\nexit /b %errorlevel%\r\n');
  let result = spawnSync('cmd.exe', ['/d', '/c', `"${launch}"`], {
    cwd: root, env: fixtureEnv, encoding: 'utf8', timeout: 15000, windowsHide: true, windowsVerbatimArguments: true,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 17, result.stdout + result.stderr);
  let payload = JSON.parse(fs.readFileSync(resultPath, 'utf8'));
  assert.equal(payload.path.split(path.delimiter)[0], toolDir);
  assert.ok(payload.argv[0].endsWith('preflight.py'));

  // An older install without encoded paths keeps its inherited environment.
  const legacyEnv = { ...fixtureEnv, CUTROOM_RUNTIME_PATHS_B64: '' };
  result = spawnSync('python', [path.join(root, 'scripts', 'windows_runtime.py'), 'server'], {
    cwd: root, env: legacyEnv, encoding: 'utf8', timeout: 15000, windowsHide: true,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 17, result.stdout + result.stderr);
  payload = JSON.parse(fs.readFileSync(resultPath, 'utf8'));
  assert.equal(payload.path, legacyEnv.PATH);
  assert.ok(payload.argv[0].endsWith('server.py'));

  result = spawnSync('python', [path.join(root, 'scripts', 'windows_runtime.py'), 'preflight'], {
    cwd: root, env: { ...fixtureEnv, CUTROOM_RUNTIME_PATHS_B64: 'invalid*base64' }, encoding: 'utf8', timeout: 15000, windowsHide: true,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Saved tool paths are invalid/);
});
