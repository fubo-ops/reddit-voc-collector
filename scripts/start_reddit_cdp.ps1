[CmdletBinding()]
param(
    [int]$Port = 9222,
    [string]$ProfileDir = (Join-Path $env:USERPROFILE ".codex\browser-profiles\reddit-cdp"),
    [string]$ChromePath,
    [ValidateRange(1, 60)][int]$WaitSeconds = 15
)

$ErrorActionPreference = "Stop"

function Test-CdpPort {
    param([int]$LocalPort)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $LocalPort, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(500)) {
            return $false
        }
        $client.EndConnect($pending)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Write-JsonResult {
    param([hashtable]$Value, [int]$ExitCode = 0)
    $Value | ConvertTo-Json -Compress -Depth 5
    exit $ExitCode
}

if (Test-CdpPort -LocalPort $Port) {
    Write-JsonResult @{status="ready"; port=$Port; already_listening=$true; started=$false; profile_dir=$ProfileDir}
}

$profileUsers = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine.IndexOf($ProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
})
if ($profileUsers.Count -gt 0) {
    $processes = @($profileUsers | ForEach-Object { @{pid=$_.ProcessId; command_line=$_.CommandLine} })
    Write-JsonResult @{status="profile_locked"; port=$Port; already_listening=$false; started=$false; profile_dir=$ProfileDir; processes=$processes; action="Close only the listed dedicated Chrome window, then rerun this script."} 3
}

if (-not $ChromePath) {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
        (Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")
    )
    $ChromePath = $candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
}
if (-not $ChromePath -or -not (Test-Path -LiteralPath $ChromePath -PathType Leaf)) {
    Write-JsonResult @{status="chrome_not_found"; port=$Port; already_listening=$false; started=$false; checked="ProgramFiles, ProgramFiles(x86), LOCALAPPDATA"} 2
}

New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
$arguments = @(
    "--remote-debugging-port=$Port",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=`"$ProfileDir`"",
    "--no-first-run",
    "https://www.reddit.com/"
)

try {
    $process = Start-Process -FilePath $ChromePath -ArgumentList $arguments -PassThru
} catch {
    Write-JsonResult @{status="start_failed"; port=$Port; already_listening=$false; started=$false; profile_dir=$ProfileDir; reason=$_.Exception.Message} 4
}

for ($second = 1; $second -le $WaitSeconds; $second++) {
    Start-Sleep -Seconds 1
    if (Test-CdpPort -LocalPort $Port) {
        Write-JsonResult @{status="ready"; port=$Port; already_listening=$false; started=$true; process_id=$process.Id; profile_dir=$ProfileDir; waited_seconds=$second}
    }
}

$dedicated = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -and $_.CommandLine.IndexOf($ProfileDir, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
} | ForEach-Object { @{pid=$_.ProcessId; command_line=$_.CommandLine} })
Write-JsonResult @{status="cdp_not_listening"; port=$Port; already_listening=$false; started=$true; profile_dir=$ProfileDir; processes=$dedicated; reason="Chrome did not open the CDP port within $WaitSeconds seconds. Inspect only the listed dedicated Chrome process/window."} 5
