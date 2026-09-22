param([string]$InstallRoot=(Join-Path $HOME '.codex\skills'),[string]$ExportRoot=(Join-Path $HOME 'Documents'),[switch]$SkipChrome)
$ErrorActionPreference='Stop';$target=Join-Path $InstallRoot 'reddit-voc-collector'
if(-not(Test-Path $target)){Write-Host 'Already uninstalled.';exit 0}
$excel=@(Get-ChildItem (Join-Path $target 'outputs') -Recurse -File -Filter *.xlsx -ErrorAction SilentlyContinue)
if($excel){$backup=Join-Path $ExportRoot ("reddit-voc-excel-"+(Get-Date -Format yyyyMMdd_HHmmss));New-Item -ItemType Directory -Force $backup|Out-Null;$excel|ForEach-Object{Copy-Item $_.FullName $backup -Force};Write-Host "Excel preserved: $backup"}
Remove-Item -LiteralPath $target -Recurse -Force
Write-Host 'Skill removed. Remove the extension on chrome://extensions using ID edpfinibjpbkdnognnhealnfepkeopem.'
if(-not $SkipChrome){Start-Process 'chrome.exe' 'chrome://extensions/?id=edpfinibjpbkdnognnhealnfepkeopem' -ErrorAction SilentlyContinue}
