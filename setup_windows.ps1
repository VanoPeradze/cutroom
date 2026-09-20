$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0
Set-Location -LiteralPath $PSScriptRoot

$script:CutroomVersion = "1.1 Beta"
$script:UvVersion = "0.12.5"
$script:TranscriptStarted = $false
$script:LogDirectory = Join-Path $PSScriptRoot "data\logs"
$script:LogPath = Join-Path $script:LogDirectory "setup-windows.log"
$script:LastErrorPath = Join-Path $script:LogDirectory "setup-last-error.txt"

function Write-Step {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Add-ProcessPath {
    param([string]$Directory)
    if (-not $Directory -or -not (Test-Path -LiteralPath $Directory -PathType Container)) {
        return
    }
    $parts = @($env:Path -split ";")
    if (-not ($parts | Where-Object { $_ -and $_.TrimEnd("\") -ieq $Directory.TrimEnd("\") })) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $currentPath = $env:Path
    $paths = @($machinePath, $userPath, $currentPath)
    if ($env:LOCALAPPDATA) {
        $paths += (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps")
        $paths += (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links")
        $paths += (Join-Path $env:LOCALAPPDATA "Programs\Ollama")
    }
    $unique = New-Object System.Collections.Generic.List[string]
    foreach ($entry in $paths) {
        if (-not $entry) { continue }
        foreach ($part in ($entry -split ";")) {
            $clean = $part.Trim().TrimEnd("\")
            if (-not $clean) { continue }
            if (-not ($unique | Where-Object { $_ -ieq $clean })) {
                $unique.Add($clean)
            }
        }
    }
    $env:Path = ($unique -join ";")
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$FailureMessage = "External command failed."
    )
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 2>&1 | ForEach-Object { Write-Host $_ }
        $code = if ($null -eq $LASTEXITCODE) { 0 } else { [int]$LASTEXITCODE }
    } catch {
        throw "$FailureMessage $($_.Exception.Message)"
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($code -ne 0) {
        throw "$FailureMessage Exit code: $code"
    }
}

function Test-External {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    try {
        Invoke-External -FilePath $FilePath -Arguments $Arguments -FailureMessage "Probe failed."
        return $true
    } catch {
        return $false
    }
}

function Resolve-Executable {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command -and $command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)) {
        return $command.Source
    }

    $candidates = New-Object System.Collections.Generic.List[string]
    if ($env:LOCALAPPDATA) {
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\$Name"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\$Name"))
        $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Ollama\$Name"))
    }
    if ($env:ProgramFiles) {
        $candidates.Add((Join-Path $env:ProgramFiles "Ollama\$Name"))
        $candidates.Add((Join-Path $env:ProgramFiles "FFmpeg\bin\$Name"))
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates.Add((Join-Path ${env:ProgramFiles(x86)} "FFmpeg\bin\$Name"))
    }
    if ($env:ChocolateyInstall) {
        $candidates.Add((Join-Path $env:ChocolateyInstall "bin\$Name"))
    }
    if ($env:USERPROFILE) {
        $candidates.Add((Join-Path $env:USERPROFILE "scoop\shims\$Name"))
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    if ($env:LOCALAPPDATA) {
        $winGetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $winGetPackages -PathType Container) {
            $found = Get-ChildItem -LiteralPath $winGetPackages -Filter $Name -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                return $found.FullName
            }
        }
    }
    return $null
}

function Get-WingetPath {
    return Resolve-Executable -Name "winget.exe"
}

function Install-WingetPackage {
    param(
        [Parameter(Mandatory = $true)][string]$PackageId,
        [Parameter(Mandatory = $true)][string]$DisplayName
    )
    $winget = Get-WingetPath
    if (-not $winget) {
        throw "$DisplayName is missing and Windows Package Manager (winget) is unavailable."
    }
    Write-Step "Installing $DisplayName"
    Invoke-External -FilePath $winget -Arguments @(
        "install", "--id", $PackageId, "--exact", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements",
        "--disable-interactivity", "--silent"
    ) -FailureMessage "$DisplayName installation failed."
    Refresh-ProcessPath
}

function Download-File {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    Remove-Item -LiteralPath $Destination -Force -ErrorAction SilentlyContinue
    $curl = Resolve-Executable -Name "curl.exe"
    if ($curl) {
        Invoke-External -FilePath $curl -Arguments @(
            "-fL", "--retry", "5", "--retry-delay", "2",
            "--connect-timeout", "30", "--max-time", "900",
            "-o", $Destination, $Url
        ) -FailureMessage "Download failed: $Url"
        return
    }

    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing -TimeoutSec 900
}

function Resolve-SystemPython {
    $probe = "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)"
    $candidates = New-Object System.Collections.Generic.List[string]

    if ($env:LOCALAPPDATA) {
        foreach ($version in @("Python311", "Python312")) {
            $candidates.Add((Join-Path $env:LOCALAPPDATA "Programs\Python\$version\python.exe"))
        }
        $pythonRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
        if (Test-Path -LiteralPath $pythonRoot -PathType Container) {
            Get-ChildItem -LiteralPath $pythonRoot -Directory -Filter "Python31*" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -in @("Python311", "Python312") } |
                ForEach-Object { $candidates.Add((Join-Path $_.FullName "python.exe")) }
        }
    }
    if ($env:ProgramFiles) {
        foreach ($version in @("Python311", "Python312")) {
            $candidates.Add((Join-Path $env:ProgramFiles "$version\python.exe"))
        }
    }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if ((Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-External -FilePath $candidate -Arguments @("-c", $probe))) {
            return [PSCustomObject]@{ FilePath = $candidate; PrefixArgs = @(); Description = $candidate }
        }
    }

    $py = Resolve-Executable -Name "py.exe"
    if ($py) {
        foreach ($selector in @("-3.11", "-3.12")) {
            if (Test-External -FilePath $py -Arguments @($selector, "-c", $probe)) {
                return [PSCustomObject]@{ FilePath = $py; PrefixArgs = @($selector); Description = "Python through py.exe $selector" }
            }
        }
    }

    foreach ($name in @("python3.11.exe", "python3.12.exe", "python.exe")) {
        $candidate = Resolve-Executable -Name $name
        if ($candidate -and (Test-External -FilePath $candidate -Arguments @("-c", $probe))) {
            return [PSCustomObject]@{ FilePath = $candidate; PrefixArgs = @(); Description = $candidate }
        }
    }
    return $null
}

function Get-UvAsset {
    $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITEW6432")
    if (-not $architecture) {
        $architecture = [Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE")
    }
    if (-not $architecture) {
        $architecture = "AMD64"
    }

    switch ($architecture.ToUpperInvariant()) {
        "AMD64" {
            return [PSCustomObject]@{
                FileName = "uv-x86_64-pc-windows-msvc.zip"
                Sha256 = "4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a"
            }
        }
        "ARM64" {
            return [PSCustomObject]@{
                FileName = "uv-aarch64-pc-windows-msvc.zip"
                Sha256 = "724279317fee6e5fa8ad1908e4eba2bbe764ef1ece5b3f4597927b62b1fe562a"
            }
        }
        "X86" {
            return [PSCustomObject]@{
                FileName = "uv-i686-pc-windows-msvc.zip"
                Sha256 = "a5993a7c2e75b418e60d5ed733204222330085b14e85269545b084c273c1629b"
            }
        }
        default {
            throw "Unsupported Windows architecture: $architecture"
        }
    }
}

function Install-UvBootstrap {
    $uvDirectory = Join-Path $PSScriptRoot ".tools\uv"
    $uvExe = Join-Path $uvDirectory "uv.exe"
    $versionMarker = Join-Path $uvDirectory "version.txt"

    if ((Test-Path -LiteralPath $uvExe -PathType Leaf) -and (Test-Path -LiteralPath $versionMarker -PathType Leaf)) {
        $savedVersion = (Get-Content -LiteralPath $versionMarker -Raw).Trim()
        if ($savedVersion -eq $script:UvVersion) {
            try {
                Invoke-External -FilePath $uvExe -Arguments @("--version") -FailureMessage "The existing private Python bootstrap is damaged."
                return $uvExe
            } catch {
                Remove-Item -LiteralPath $uvDirectory -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Remove-Item -LiteralPath $uvDirectory -Recurse -Force -ErrorAction SilentlyContinue

    Write-Step "Preparing the private Python bootstrap"
    $asset = Get-UvAsset
    $downloadDirectory = Join-Path $PSScriptRoot ".tools\downloads"
    $archive = Join-Path $downloadDirectory $asset.FileName
    $extractDirectory = Join-Path $downloadDirectory "uv-extracted"
    New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null
    Remove-Item -LiteralPath $extractDirectory -Recurse -Force -ErrorAction SilentlyContinue

    $baseName = "https://releases.astral.sh/github/uv/releases/download/$($script:UvVersion)/$($asset.FileName)"
    $fallbackName = "https://github.com/astral-sh/uv/releases/download/$($script:UvVersion)/$($asset.FileName)"
    $downloaded = $false
    $errors = New-Object System.Collections.Generic.List[string]
    foreach ($url in @($baseName, $fallbackName)) {
        try {
            Download-File -Url $url -Destination $archive
            $downloaded = $true
            break
        } catch {
            $errors.Add($_.Exception.Message)
            Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        }
    }
    if (-not $downloaded) {
        throw "Could not download the private Python bootstrap. Check the internet connection. $($errors -join ' | ')"
    }

    $actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $asset.Sha256.ToLowerInvariant()) {
        Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
        throw "The private Python bootstrap failed SHA-256 verification. Expected $($asset.Sha256), received $actualHash."
    }

    Expand-Archive -LiteralPath $archive -DestinationPath $extractDirectory -Force
    $extractedUv = Get-ChildItem -LiteralPath $extractDirectory -Filter "uv.exe" -File -Recurse | Select-Object -First 1
    if (-not $extractedUv) {
        throw "The verified uv archive did not contain uv.exe."
    }

    Remove-Item -LiteralPath $uvDirectory -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $uvDirectory -Force | Out-Null
    Copy-Item -LiteralPath $extractedUv.FullName -Destination $uvExe -Force
    Unblock-File -LiteralPath $uvExe -ErrorAction SilentlyContinue
    $extractedUvx = Get-ChildItem -LiteralPath $extractDirectory -Filter "uvx.exe" -File -Recurse | Select-Object -First 1
    if ($extractedUvx) {
        Copy-Item -LiteralPath $extractedUvx.FullName -Destination (Join-Path $uvDirectory "uvx.exe") -Force
    }
    Set-Content -LiteralPath $versionMarker -Value $script:UvVersion -Encoding ASCII
    Remove-Item -LiteralPath $extractDirectory -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue

    Invoke-External -FilePath $uvExe -Arguments @("--version") -FailureMessage "The private Python bootstrap could not start."
    return $uvExe
}

function Configure-UvEnvironment {
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot ".tools\python"
    $env:UV_CACHE_DIR = Join-Path $PSScriptRoot ".tools\uv-cache"
    $env:UV_PYTHON_INSTALL_REGISTRY = "0"
    $env:UV_NO_MODIFY_PATH = "true"
    $env:UV_SYSTEM_CERTS = "true"
    $env:UV_HTTP_TIMEOUT = "120"
    $env:UV_HTTP_RETRIES = "5"
    $env:UV_LINK_MODE = "copy"
    $env:UV_PYTHON_DOWNLOADS = "automatic"
    $env:UV_NO_CONFIG = "1"
    Remove-Item Env:UV_NATIVE_TLS -ErrorAction SilentlyContinue
    Remove-Item Env:UV_MANAGED_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:UV_PYTHON_PREFERENCE -ErrorAction SilentlyContinue
    Remove-Item Env:UV_OFFLINE -ErrorAction SilentlyContinue
    Remove-Item Env:UV_NO_PYTHON_DOWNLOADS -ErrorAction SilentlyContinue
}

function Prepare-PythonEnvironment {
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $venvProbe = "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)"
    if ((Test-Path -LiteralPath $venvPython -PathType Leaf) -and (Test-External -FilePath $venvPython -Arguments @("-c", $venvProbe))) {
        Write-Step "Using the existing CUTROOM Python environment"
        return $venvPython
    }

    if (Test-Path -LiteralPath ".venv") {
        Write-Step "Removing an incomplete Python environment"
        Remove-Item -LiteralPath ".venv" -Recurse -Force
    }

    $systemPython = Resolve-SystemPython
    if ($systemPython) {
        Write-Step "Creating CUTROOM with the working Python already on this PC"
        Write-Host "Using $($systemPython.Description)" -ForegroundColor Green
        $arguments = @($systemPython.PrefixArgs) + @("-m", "venv", ".venv")
        Invoke-External -FilePath $systemPython.FilePath -Arguments $arguments -FailureMessage "CUTROOM could not create its Python environment."
    } else {
        Write-Step "No suitable system Python was found; preparing a private Python"
        $uvPath = Install-UvBootstrap
        Configure-UvEnvironment
        Invoke-External -FilePath $uvPath -Arguments @(
            "--no-config", "python", "install", "--no-registry", "3.11"
        ) -FailureMessage "CUTROOM could not download its private Python runtime."
        Invoke-External -FilePath $uvPath -Arguments @(
            "--no-config", "venv", "--clear", "--no-project", "--python", "3.11", "--seed", ".venv"
        ) -FailureMessage "CUTROOM could not create its private Python environment."
    }

    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw "The CUTROOM Python environment was created without python.exe."
    }
    Invoke-External -FilePath $venvPython -Arguments @("-c", $venvProbe) -FailureMessage "CUTROOM created an unsupported Python version."
    return $venvPython
}

function Install-PythonDependencies {
    param([Parameter(Mandatory = $true)][string]$PythonPath)
    Write-Step "Installing CUTROOM and local AI dependencies"
    Invoke-External -FilePath $PythonPath -Arguments @(
        "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"
    ) -FailureMessage "CUTROOM could not prepare pip."
    Invoke-External -FilePath $PythonPath -Arguments @(
        "-m", "pip", "install", "--upgrade", "-r", "requirements.txt"
    ) -FailureMessage "CUTROOM Python dependency installation failed."
    Invoke-External -FilePath $PythonPath -Arguments @(
        "-m", "pip", "check"
    ) -FailureMessage "CUTROOM Python dependency verification failed."
}

function Test-OllamaServer {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -Method Get -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function Start-OllamaServerIfNeeded {
    param([Parameter(Mandatory = $true)][string]$OllamaPath)
    if (Test-OllamaServer) { return $true }
    try {
        Start-Process -FilePath $OllamaPath -ArgumentList @("serve") -WindowStyle Hidden | Out-Null
    } catch {
        Write-Warning "Ollama could not be started automatically: $($_.Exception.Message)"
        return $false
    }
    for ($attempt = 0; $attempt -lt 25; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-OllamaServer) { return $true }
    }
    return $false
}

function Write-RuntimePaths {
    param([string[]]$Directories)
    $unique = New-Object System.Collections.Generic.List[string]
    foreach ($directory in $Directories) {
        if (-not $directory -or -not (Test-Path -LiteralPath $directory -PathType Container)) { continue }
        $clean = [System.IO.Path]::GetFullPath($directory).TrimEnd("\")
        if (-not ($unique | Where-Object { $_ -ieq $clean })) {
            $unique.Add($clean)
        }
    }
    $prefix = $unique -join ";"
    $lines = @("@echo off")
    if ($prefix) {
        $lines += "set `"PATH=$prefix;%PATH%`""
    }
    $payload = ($lines -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot ".runtime-paths.cmd"), $payload, [System.Text.Encoding]::ASCII)
}

function Stop-SetupTranscript {
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch { }
        $script:TranscriptStarted = $false
    }
}

try {
    New-Item -ItemType Directory -Path $script:LogDirectory -Force | Out-Null
    Remove-Item -LiteralPath $script:LastErrorPath -Force -ErrorAction SilentlyContinue
    try {
        Start-Transcript -LiteralPath $script:LogPath -Append | Out-Null
        $script:TranscriptStarted = $true
    } catch {
        Write-Warning "Setup logging could not start: $($_.Exception.Message)"
    }

    Remove-Item -LiteralPath ".setup-complete" -Force -ErrorAction SilentlyContinue
    Refresh-ProcessPath

    Write-Host "CUTROOM AI $($script:CutroomVersion) - local setup" -ForegroundColor White
    Write-Host "CUTROOM reuses the working v3 Python path when available and falls back to a private Python." -ForegroundColor DarkGray

    $venvPython = Prepare-PythonEnvironment
    Install-PythonDependencies -PythonPath $venvPython

    $ffmpegPath = Resolve-Executable -Name "ffmpeg.exe"
    $ffprobePath = Resolve-Executable -Name "ffprobe.exe"
    if (-not $ffmpegPath -or -not $ffprobePath) {
        try {
            Install-WingetPackage -PackageId "Gyan.FFmpeg" -DisplayName "FFmpeg and FFprobe"
        } catch {
            Write-Warning "winget did not report a clean FFmpeg installation result. CUTROOM will verify the files directly. Details: $($_.Exception.Message)"
            Refresh-ProcessPath
        }
        $ffmpegPath = Resolve-Executable -Name "ffmpeg.exe"
        $ffprobePath = Resolve-Executable -Name "ffprobe.exe"
    }
    if (-not $ffmpegPath -or -not $ffprobePath) {
        throw "FFmpeg installation completed, but ffmpeg.exe or ffprobe.exe could not be located. See data\logs\setup-windows.log."
    }
    Add-ProcessPath -Directory (Split-Path -Parent $ffmpegPath)
    Add-ProcessPath -Directory (Split-Path -Parent $ffprobePath)

    $ollamaPath = Resolve-Executable -Name "ollama.exe"
    if (-not $ollamaPath) {
        $wingetPath = Get-WingetPath
        if ($wingetPath) {
            try {
                Install-WingetPackage -PackageId "Ollama.Ollama" -DisplayName "Ollama"
                $ollamaPath = Resolve-Executable -Name "ollama.exe"
            } catch {
                Write-Warning "Ollama installation did not finish. CUTROOM can still start with deterministic editing. Details: $($_.Exception.Message)"
            }
        } else {
            Write-Warning "winget is unavailable, so Ollama was not installed automatically. CUTROOM can still start with deterministic editing."
        }
    }
    if ($ollamaPath) {
        Add-ProcessPath -Directory (Split-Path -Parent $ollamaPath)
    }

    $runtimeDirectories = @(
        (Split-Path -Parent $ffmpegPath),
        (Split-Path -Parent $ffprobePath)
    )
    if ($ollamaPath) {
        $ollamaDirectory = Split-Path -Parent $ollamaPath
        $runtimeDirectories += $ollamaDirectory
        # Current CTranslate2 Windows wheels need the CUDA 12 BLAS runtime. Ollama
        # already ships a compatible copy on NVIDIA installations, so reuse it
        # instead of making users install a second CUDA toolkit just for Whisper.
        $ollamaCuda12 = Join-Path $ollamaDirectory "lib\ollama\cuda_v12"
        if (Test-Path -LiteralPath (Join-Path $ollamaCuda12 "cublas64_12.dll") -PathType Leaf) {
            Add-ProcessPath -Directory $ollamaCuda12
            $runtimeDirectories += $ollamaCuda12
        }
    }
    Write-RuntimePaths -Directories $runtimeDirectories

    $config = Get-Content -LiteralPath "config.json" -Raw | ConvertFrom-Json
    if ($ollamaPath) {
        $ollamaReady = Start-OllamaServerIfNeeded -OllamaPath $ollamaPath
        if ($ollamaReady -and [bool]$config.ai.download_models_on_setup) {
            $editorModel = [string]$config.ai.editor_model
            Write-Step "Downloading the recommended local editor model: $editorModel"
            try {
                Invoke-External -FilePath $ollamaPath -Arguments @("pull", $editorModel) -FailureMessage "The Ollama editor model download failed."
            } catch {
                Write-Warning "The editor model was not downloaded. CUTROOM can start, and the model can be installed later. Details: $($_.Exception.Message)"
            }
        } elseif (-not $ollamaReady) {
            Write-Warning "Ollama is installed, but its local service did not become ready. CUTROOM can still start with deterministic editing."
        }
    } else {
        Write-Warning "Ollama is unavailable. Semantic AI decisions remain disabled until Ollama is installed."
    }

    if ([bool]$config.ai.download_models_on_setup) {
        $env:CUTROOM_SETUP_WHISPER_MODEL = [string]$config.ai.whisper_model
        Write-Step "Preparing the local Whisper model: $env:CUTROOM_SETUP_WHISPER_MODEL"
        $whisperCode = "import os; from faster_whisper import WhisperModel; name = os.environ['CUTROOM_SETUP_WHISPER_MODEL']; WhisperModel(name, device='cpu', compute_type='int8'); print('Whisper model ready: ' + name)"
        try {
            Invoke-External -FilePath $venvPython -Arguments @("-c", $whisperCode) -FailureMessage "Whisper model preparation failed."
        } catch {
            Write-Warning "Whisper will download automatically when the first edit is created. Details: $($_.Exception.Message)"
        } finally {
            Remove-Item Env:CUTROOM_SETUP_WHISPER_MODEL -ErrorAction SilentlyContinue
        }
    }

    Write-Step "Checking the completed installation"
    Invoke-External -FilePath $venvPython -Arguments @(
        "-c", "import flask, waitress, numpy, cv2, faster_whisper, cutroom; print('Python dependencies ready')"
    ) -FailureMessage "CUTROOM dependency verification failed."
    Invoke-External -FilePath $venvPython -Arguments @(
        "-m", "compileall", "-q", "server.py", "cutroom"
    ) -FailureMessage "CUTROOM Python validation failed."
    Invoke-External -FilePath $ffmpegPath -Arguments @("-version") -FailureMessage "FFmpeg verification failed."
    Invoke-External -FilePath $ffprobePath -Arguments @("-version") -FailureMessage "FFprobe verification failed."

    Set-Content -LiteralPath ".setup-complete" -Value "CUTROOM AI $($script:CutroomVersion) setup completed $(Get-Date -Format o)" -Encoding ASCII
    Write-Host "`nCUTROOM is ready. Run run_windows.bat." -ForegroundColor Green
    Write-Host "Setup log: $script:LogPath" -ForegroundColor DarkGray
    Stop-SetupTranscript
    exit 0
} catch {
    Remove-Item -LiteralPath ".setup-complete" -Force -ErrorAction SilentlyContinue
    $errorText = @(
        "CUTROOM AI $($script:CutroomVersion) setup failed.",
        "Time: $(Get-Date -Format o)",
        "Message: $($_.Exception.Message)",
        "Position: $($_.InvocationInfo.PositionMessage)",
        "Stack: $($_.ScriptStackTrace)"
    ) -join "`r`n"
    try {
        New-Item -ItemType Directory -Path $script:LogDirectory -Force | Out-Null
        [System.IO.File]::WriteAllText($script:LastErrorPath, $errorText + "`r`n", [System.Text.Encoding]::UTF8)
    } catch { }
    Write-Host "`nCUTROOM setup failed." -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "`nDetailed log: $script:LogPath" -ForegroundColor Yellow
    Write-Host "Last error: $script:LastErrorPath" -ForegroundColor Yellow
    Stop-SetupTranscript
    exit 1
}
