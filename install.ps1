$ErrorActionPreference = 'Stop'

$RepoUrl = if ($env:IXEL_REPO_URL) { $env:IXEL_REPO_URL } else { 'https://github.com/OpenIxelAI/ixel-mat.git' }
$Branch = if ($env:IXEL_BRANCH) { $env:IXEL_BRANCH } else { 'main' }
$InstallRoot = if ($env:IXEL_INSTALL_ROOT) { $env:IXEL_INSTALL_ROOT } else { Join-Path $env:LOCALAPPDATA 'IxelMAT' }
$BinDir = if ($env:IXEL_BIN_DIR) { $env:IXEL_BIN_DIR } else { Join-Path $HOME '.local\bin' }
$RepoDir = Join-Path $InstallRoot 'repo'
$VenvDir = Join-Path $InstallRoot '.venv'
$CmdWrapper = Join-Path $BinDir 'ixel.cmd'
$PsWrapper = Join-Path $BinDir 'ixel.ps1'

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $Name"
    }
}

function Get-PythonCommand {
    foreach ($candidate in @('py', 'python', 'python3')) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) { return $candidate }
    }
    throw 'Python 3 is required'
}

function Ensure-UserPath([string]$Dir) {
    if ($env:IXEL_SKIP_PATH_UPDATE -eq '1') { return }
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($userPath) { $parts = $userPath.Split(';') | Where-Object { $_ } }
    if ($parts -contains $Dir) { return }
    $newPath = if ($userPath) { "$userPath;$Dir" } else { $Dir }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
}

Require-Command git
$Python = Get-PythonCommand

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

if (Test-Path (Join-Path $RepoDir '.git')) {
    git -C $RepoDir fetch origin
    git -C $RepoDir checkout $Branch
    git -C $RepoDir pull --ff-only origin $Branch
} else {
    if (Test-Path $RepoDir) { Remove-Item -Recurse -Force $RepoDir }
    git clone --branch $Branch $RepoUrl $RepoDir
}

if ($Python -eq 'py') {
    & py -3 -m venv $VenvDir
} else {
    & $Python -m venv $VenvDir
}

& (Join-Path $VenvDir 'Scripts\python.exe') -m pip install --upgrade pip | Out-Null
& (Join-Path $VenvDir 'Scripts\pip.exe') install -r (Join-Path $RepoDir 'requirements.txt')

$cmdContent = @"
@echo off
setlocal
set "INSTALL_ROOT=%LOCALAPPDATA%\IxelMAT"
set "REPO_DIR=%INSTALL_ROOT%\repo"
set "VENV_DIR=%INSTALL_ROOT%\.venv"
if "%~1"=="" (
  "%VENV_DIR%\Scripts\python.exe" "%REPO_DIR%\mat.py"
) else (
  "%VENV_DIR%\Scripts\python.exe" "%REPO_DIR%\cli.py" %*
)
"@
Set-Content -Path $CmdWrapper -Value $cmdContent -Encoding ASCII

$psContent = @"
`$InstallRoot = if (`$env:IXEL_INSTALL_ROOT) { `$env:IXEL_INSTALL_ROOT } else { Join-Path `$env:LOCALAPPDATA 'IxelMAT' }
`$RepoDir = Join-Path `$InstallRoot 'repo'
`$VenvDir = Join-Path `$InstallRoot '.venv'
if (`$args.Count -eq 0) {
  & (Join-Path `$VenvDir 'Scripts\python.exe') (Join-Path `$RepoDir 'mat.py')
} else {
  & (Join-Path `$VenvDir 'Scripts\python.exe') (Join-Path `$RepoDir 'cli.py') @args
}
"@
Set-Content -Path $PsWrapper -Value $psContent -Encoding UTF8

Ensure-UserPath $BinDir

Write-Host ""
Write-Host "Ixel MAT installed."
Write-Host "Binary directory: $BinDir"
Write-Host "Run: ixel"
Write-Host "If the command is not found in this shell yet, restart PowerShell or run:"
Write-Host "  `$env:Path = '$BinDir;' + `$env:Path"
