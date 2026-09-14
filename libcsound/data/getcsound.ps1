#Requires -Version 5.1
<#
.SYNOPSIS
    Bootstrap installer for Csound 7 on Windows (x86_64).

.DESCRIPTION
    Downloads the official Csound 7 Windows installer produced by the
    "csound_builds" workflow of the csound/csound repository on the "develop"
    branch (Csound 7), then runs it.

    The installer is an Inno Setup executable that installs to
    "%ProgramFiles%\Csound7" and writes machine-wide environment variables, so
    it needs Administrator rights. A UAC prompt will appear unless the current
    PowerShell session is already elevated.

    Windows on ARM64 is not supported yet.

    SAFER USAGE (recommended):
        Invoke-WebRequest -OutFile getcsound.ps1 `
            https://csound-plugins.github.io/getcsound.ps1
        # Read the script, then run it:
        .\getcsound.ps1

    One-line usage (convenient, but inspects nothing before execution):
        irm https://csound-plugins.github.io/getcsound.ps1 | iex

.PARAMETER Help
    Show this help without downloading the installer. Also --help.

.PARAMETER HelpAll
    Show this help plus information about the bundled installer. Also --help-all.

.PARAMETER Release
    Install the installer published with the latest GitHub release instead of
    the latest successful csound_builds workflow run. Also --release.

.PARAMETER Verbose
    Show the download URLs and other diagnostic information. Also --verbose.
#>

$ErrorActionPreference = 'Stop'

# --- Argument parsing ----------------------------------------------
# Arguments are parsed by hand (instead of a param block) so that the same
# long options as the Unix getcsound.sh can be accepted, including the "--"
# separator that forwards the remaining arguments to the bundled installer.
$ShowHelp = $false
$HelpAll = $false
$UseRelease = $false
$VerboseOutput = $false
$InstallerArgs = New-Object System.Collections.Generic.List[string]

$i = 0
while ($i -lt $args.Count) {
    $arg = [string]$args[$i]
    switch ($arg) {
        { $_ -in '--help', '-help', '-h', '/?' } { $ShowHelp = $true }
        { $_ -in '--help-all', '-help-all' }     { $HelpAll = $true }
        { $_ -in '--release', '-release' }       { $UseRelease = $true }
        { $_ -in '--verbose', '-verbose' }       { $VerboseOutput = $true }
        '--' {
            $i++
            while ($i -lt $args.Count) {
                $InstallerArgs.Add([string]$args[$i])
                $i++
            }
            break
        }
        default { $InstallerArgs.Add($arg) }
    }
    $i++
}

# --- Helpers -------------------------------------------------------
function Show-Usage {
    @'
Usage: getcsound.ps1 [OPTIONS] [-- INSTALLER-OPTIONS]

Options:
  --help       Show this help without downloading the installer.
  --help-all   Show this help plus information about the bundled installer.
  --release    Install the installer published with the latest GitHub release
               instead of the latest successful csound_builds workflow run.
  --verbose    Show the download URLs and other diagnostic information.

Arguments after -- are passed unchanged to the Inno Setup installer.

This script resolves the latest successful csound_builds workflow run on the
develop branch of csound/csound and installs the Windows x86_64 installer that
the run produced. Windows on ARM64 is not supported yet.
'@
}

function Write-Err {
    param([string]$Message)
    [Console]::Error.WriteLine("Error: $Message")
}

function Write-VerboseLine {
    param([string]$Message)
    if ($VerboseOutput) { Write-Host $Message }
}

function Get-PlatformArch {
    # RuntimeInformation.OSArchitecture reports the architecture of the OS, not
    # of the PowerShell process, so a 32-bit shell on 64-bit Windows is still
    # detected as x64 (and an emulated x64 shell on ARM64 as Arm64).
    try {
        $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
        switch ($arch) {
            'X64'   { return 'x86_64' }
            'Arm64' { return 'arm64' }
            'X86'   { return 'x86' }
            'Arm'   { return 'arm' }
        }
    } catch {
        Write-VerboseLine "Get-PlatformArch: RuntimeInformation unavailable; using legacy detection."
    }
    # PROCESSOR_ARCHITEW6432 holds the native architecture when a 32-bit shell
    # runs under WOW64 (or an emulated x64 shell runs on ARM64).
    $procArch = $env:PROCESSOR_ARCHITECTURE
    if ($env:PROCESSOR_ARCHITEW6432) { $procArch = $env:PROCESSOR_ARCHITEW6432 }
    switch ($procArch) {
        'AMD64' { return 'x86_64' }
        'ARM64' { return 'arm64' }
        'x86'   { return 'x86' }
        'ARM'   { return 'arm' }
    }
    if ([Environment]::Is64BitOperatingSystem) { return 'x86_64' }
    return 'x86'
}

function Invoke-GitHubApi {
    param([string]$Url)
    $headers = @{
        'User-Agent' = 'getcsound-installer'
        'Accept'     = 'application/vnd.github+json'
    }
    if ($script:Token) {
        $authHeaders = $headers.Clone()
        $authHeaders['Authorization'] = "Bearer $($script:Token)"
        try {
            return Invoke-RestMethod -Uri $Url -Headers $authHeaders -Method Get
        } catch {
            # The token may be invalid or expired; retry anonymously.
            Write-VerboseLine 'Request with token failed; retrying anonymously...'
        }
    }
    return Invoke-RestMethod -Uri $Url -Headers $headers -Method Get
}

function Write-ApiErrorHint {
    Write-Err 'This usually means the GitHub API rate limit was exceeded.'
    Write-Err 'Set CSOUND7_GH_TOKEN, GH_TOKEN or GITHUB_TOKEN to authenticate,'
    Write-Err 'or install the GitHub CLI and run ''gh auth login''.'
}

function Save-Url {
    param([string]$Url, [string]$Path)
    Invoke-WebRequest -Uri $Url -OutFile $Path -UseBasicParsing
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# --- Handle --help / --help-all ------------------------------------
if ($ShowHelp) {
    Show-Usage
    exit 0
}

if ($HelpAll) {
    Show-Usage
    Write-Host ''
    Write-Host 'The Windows Csound installer is a GUI setup program; it has no'
    Write-Host 'bundled textual help to display. Standard Inno Setup switches'
    Write-Host '(for example /VERYSILENT, /SUPPRESSMSGBOXES) are passed through.'
    exit 0
}

# --- Architecture check --------------------------------------------
$PlatformArch = Get-PlatformArch
switch ($PlatformArch) {
    'x86_64' {
        # Supported.
    }
    'arm64' {
        Write-Err 'Windows on ARM64 is not supported yet.'
        Write-Err 'Only Windows x86_64 is supported at the moment.'
        exit 1
    }
    default {
        Write-Err "Unsupported architecture: $PlatformArch. Only Windows x86_64 is supported."
        exit 1
    }
}

# --- Configuration -------------------------------------------------
$Repo         = if ($env:CSOUND7_REPO)            { $env:CSOUND7_REPO }            else { 'csound/csound' }
$Workflow     = if ($env:CSOUND7_WORKFLOW)        { $env:CSOUND7_WORKFLOW }        else { 'csound_builds.yml' }
$Branch       = if ($env:CSOUND7_WINDOWS_BRANCH)  { $env:CSOUND7_WINDOWS_BRANCH }  else { 'develop' }
$ArtifactGlob = if ($env:CSOUND7_WINDOWS_ASSET)   { $env:CSOUND7_WINDOWS_ASSET }   else { 'Csound_x64-*-windows-installer' }
$ExeGlob      = if ($env:CSOUND7_WINDOWS_EXE)     { $env:CSOUND7_WINDOWS_EXE }     else { 'Csound7-windows_x86_64-*.exe' }

# Use a token for the GitHub API queries when one is available in the
# environment (e.g. GITHUB_TOKEN on CI). As a fallback, when no environment
# token is set and the GitHub CLI is available, `gh auth token` is used.
# Anonymous otherwise.
$Token = if ($env:CSOUND7_GH_TOKEN) { $env:CSOUND7_GH_TOKEN }
         elseif ($env:GH_TOKEN)     { $env:GH_TOKEN }
         elseif ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN }
         else                       { '' }
if (-not $Token) {
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if ($gh) {
        try {
            $Token = (& gh auth token 2>$null | Select-Object -First 1)
        } catch {
            $Token = ''
        }
        if ($null -eq $Token) { $Token = '' }
        $Token = $Token.Trim()
    }
}

# GitHub now requires TLS 1.2; Windows PowerShell 5.1 does not enable it by
# default.
try {
    [Net.ServicePointManager]::SecurityProtocol = `
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {
    Write-VerboseLine 'Could not enable TLS 1.2 explicitly.'
}

# --- Prepare temporary directory -----------------------------------
$TmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("getcsound-" + [System.Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null

try {
    $ZipFile = Join-Path $TmpDir 'csound-windows.zip'
    $ArtifactName = $null
    $DownloadUrl = $null

    if ($UseRelease) {
        # --- Resolve the latest release ----------------------------
        $ReleaseTag = if ($env:CSOUND7_RELEASE_TAG) { $env:CSOUND7_RELEASE_TAG } else { 'latest' }
        if ($ReleaseTag -eq 'latest') {
            $releaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
            Write-Host "Looking for the latest release of ${Repo}..."
        } else {
            $releaseUrl = "https://api.github.com/repos/$Repo/releases/tags/$ReleaseTag"
            Write-Host "Looking for release $ReleaseTag of ${Repo}..."
        }
        Write-VerboseLine "Release URL: $releaseUrl"
        try {
            $release = Invoke-GitHubApi -Url $releaseUrl
        } catch {
            Write-Err 'Failed to query the release.'
            Write-Err "URL: $releaseUrl"
            Write-Err $_.Exception.Message
            Write-ApiErrorHint
            exit 1
        }
        $ReleaseTag = $release.tag_name
        if (-not $ReleaseTag) {
            Write-Err 'Could not determine the release tag.'
            Write-Err "URL: $releaseUrl"
            exit 1
        }
        Write-Host "Using release: $ReleaseTag"
        $ArtifactName = "csound-windows-$ReleaseTag.zip"
        $DownloadUrl = "https://github.com/$Repo/releases/download/$ReleaseTag/$ArtifactName"
    } else {
        # --- Resolve the latest successful workflow run ------------
        $RunId = $env:CSOUND7_WINDOWS_RUN_ID
        if (-not $RunId) {
            Write-Host "Looking for the latest successful $Workflow run on branch '$Branch' of ${Repo}..."
            $runsUrl = "https://api.github.com/repos/$Repo/actions/workflows/$Workflow/runs?branch=$Branch&event=push&per_page=30"
            Write-VerboseLine "Runs URL: $runsUrl"
            try {
                $runs = Invoke-GitHubApi -Url $runsUrl
            } catch {
                Write-Err 'Failed to query workflow runs.'
                Write-Err "URL: $runsUrl"
                Write-Err $_.Exception.Message
                Write-ApiErrorHint
                exit 1
            }
            $run = $runs.workflow_runs | Where-Object { $_.conclusion -eq 'success' } | Select-Object -First 1
            if (-not $run) {
                Write-Err "No successful $Workflow run found on branch '$Branch' of ${Repo}."
                Write-Err "Runs URL: $runsUrl"
                exit 1
            }
            $RunId = $run.id
        }
        Write-Host "Using workflow run: $RunId"

        # --- Resolve the matching artifact -------------------------
        $ArtifactName = $env:CSOUND7_WINDOWS_ARTIFACT
        if (-not $ArtifactName) {
            $artifactsUrl = "https://api.github.com/repos/$Repo/actions/runs/$RunId/artifacts?per_page=100"
            Write-VerboseLine "Artifacts URL: $artifactsUrl"
            try {
                $artifacts = Invoke-GitHubApi -Url $artifactsUrl
            } catch {
                Write-Err "Failed to list the artifacts of run $RunId."
                Write-Err "URL: $artifactsUrl"
                Write-Err $_.Exception.Message
                Write-ApiErrorHint
                exit 1
            }
            $artifact = $artifacts.artifacts |
                Where-Object { -not $_.expired -and $_.name -like $ArtifactGlob } |
                Select-Object -First 1
            if (-not $artifact) {
                Write-Err "No artifact matching '$ArtifactGlob' was found in run $RunId."
                exit 1
            }
            $ArtifactName = $artifact.name
        }
        Write-Host "Using artifact: $ArtifactName"

        # --- Download via nightly.link -----------------------------
        # GitHub Actions artifacts cannot be downloaded anonymously, so the
        # archive is fetched through the nightly.link mirror.
        $DownloadUrl = "https://nightly.link/$Repo/actions/runs/$RunId/$ArtifactName.zip"
    }

    # Trust model:
    #   - The archive is downloaded over HTTPS and installed unmodified.
    #   - There is no published checksum for these artifacts, so integrity
    #     cannot be verified independently. nightly.link serves the artifact
    #     bytes as produced by the workflow run; release assets come straight
    #     from the GitHub release.
    Write-VerboseLine "Download URL: $DownloadUrl"
    Write-Host "Downloading $ArtifactName..."
    try {
        Save-Url -Url $DownloadUrl -Path $ZipFile
    } catch {
        Write-Err "Failed to download $ArtifactName"
        Write-Err "URL: $DownloadUrl"
        Write-Err $_.Exception.Message
        exit 1
    }
    Write-Host "Download complete: $ZipFile"

    # --- Extract ---------------------------------------------------
    $ExtractDir = Join-Path $TmpDir 'extracted'
    New-Item -ItemType Directory -Path $ExtractDir -Force | Out-Null
    Write-Host "Extracting $ArtifactName..."
    try {
        # -LiteralPath is not available in Windows PowerShell 5.1.
        Expand-Archive -Path $ZipFile -DestinationPath $ExtractDir -Force
    } catch {
        Write-Err "Failed to extract $ArtifactName"
        Write-Err $_.Exception.Message
        exit 1
    }

    # --- Locate the installer --------------------------------------
    $Installer = Get-ChildItem -LiteralPath $ExtractDir -Recurse -File -Filter $ExeGlob |
        Select-Object -First 1
    if (-not $Installer) {
        Write-Err "No Windows installer ($ExeGlob) was found inside $ArtifactName"
        exit 1
    }
    Write-Host "Installer: $($Installer.Name)"

    # --- Install ---------------------------------------------------
    # The Inno Setup package installs machine-wide, so run it elevated. When
    # the current session is already elevated the UAC prompt is avoided.
    $InstallerSwitches = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=modifypath')
    foreach ($extra in $InstallerArgs) { $InstallerSwitches += $extra }

    Write-Host 'Installing Csound (a UAC prompt may appear)...'
    $startParams = @{
        FilePath     = $Installer.FullName
        ArgumentList = $InstallerSwitches
        Wait         = $true
        PassThru     = $true
    }
    if (-not (Test-IsAdmin)) { $startParams['Verb'] = 'RunAs' }

    try {
        $proc = Start-Process @startParams
    } catch {
        Write-Err 'Failed to start the Csound installer.'
        Write-Err $_.Exception.Message
        Write-Err 'This installer needs Administrator rights. Please run it from an'
        Write-Err 'interactive PowerShell session and accept the UAC prompt.'
        exit 1
    }

    if ($null -ne $proc -and $null -ne $proc.ExitCode -and $proc.ExitCode -ne 0) {
        Write-Err "The Windows installer exited with code $($proc.ExitCode)."
        exit 1
    }

    Write-Host 'Csound installed successfully.'

    $ProgramFiles = if ($env:ProgramW6432) { $env:ProgramW6432 } else { $env:ProgramFiles }
    $CsoundExe = Join-Path $ProgramFiles 'Csound7\bin\csound.exe'
    if (Test-Path -LiteralPath $CsoundExe) {
        Write-Host "Binary: $CsoundExe"
    } else {
        Write-Host "Note: $CsoundExe was not found; a custom install directory may have been used."
    }
} finally {
    Remove-Item -LiteralPath $TmpDir -Recurse -Force -ErrorAction SilentlyContinue
}
