$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
Set-Location -LiteralPath $PSScriptRoot

$required = @(
    "setup_windows.ps1", "requirements.txt", "config.json", "server.py", "scripts\preflight.py",
    "cutroom\__init__.py", "cutroom\director.py", "cutroom\render.py",
    "web\index.html", "web\styles.css", "web\app.js"
)
foreach ($relativePath in $required) {
    $requiredPath = Join-Path $PSScriptRoot $relativePath
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        Write-Host "CUTROOM installer validation failed: missing $relativePath" -ForegroundColor Red
        exit 1
    }
}

$target = Join-Path $PSScriptRoot "setup_windows.ps1"
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile($target, [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) {
    Write-Host "CUTROOM installer validation failed." -ForegroundColor Red
    foreach ($parseError in $errors) {
        Write-Host ("Line {0}, column {1}: {2}" -f $parseError.Extent.StartLineNumber, $parseError.Extent.StartColumnNumber, $parseError.Message) -ForegroundColor Red
    }
    exit 1
}

$sourceBytes = [System.IO.File]::ReadAllBytes($target)
if ($sourceBytes.Length -eq 0 -or ($sourceBytes | Where-Object { $_ -gt 127 } | Select-Object -First 1)) {
    Write-Host "CUTROOM installer validation failed: setup_windows.ps1 must remain ASCII-safe." -ForegroundColor Red
    exit 1
}
$sourceText = [System.Text.Encoding]::ASCII.GetString($sourceBytes)
$requiredMarkers = @(
    '$script:CutroomVersion = "1.1 Beta"',
    'Resolve-SystemPython',
    '$script:UvVersion = "0.12.5"',
    'UV_PYTHON_INSTALL_DIR',
    'UV_SYSTEM_CERTS',
    'Get-FileHash',
    'uv-x86_64-pc-windows-msvc.zip',
    'uv-aarch64-pc-windows-msvc.zip',
    'uv-i686-pc-windows-msvc.zip',
    'Gyan.FFmpeg',
    'Ollama.Ollama'
)
foreach ($marker in $requiredMarkers) {
    if (-not $sourceText.Contains($marker)) {
        Write-Host "CUTROOM installer validation failed: required bootstrap marker is missing." -ForegroundColor Red
        exit 1
    }
}
$prohibitedMarkers = @(
    'UV_PYTHON_PREFERENCE = "only-managed"',
    '--managed-python',
    'UV_NATIVE_TLS = "true"'
)
foreach ($marker in $prohibitedMarkers) {
    if ($sourceText.Contains($marker)) {
        Write-Host "CUTROOM installer validation failed: an incompatible uv option was found." -ForegroundColor Red
        exit 1
    }
}
exit 0
