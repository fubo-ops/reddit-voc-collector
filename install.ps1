param([string]$InstallRoot=(Join-Path $HOME '.codex\skills'),[switch]$SkipChrome)
$ErrorActionPreference='Stop'
$source=Join-Path $PSScriptRoot 'reddit-voc-collector';if(-not(Test-Path "$source\SKILL.md")){$source=$PSScriptRoot}
$target=Join-Path $InstallRoot 'reddit-voc-collector';New-Item -ItemType Directory -Force -Path $target|Out-Null
foreach($name in @('agents','extension','local_bridge','references','scripts')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination $target -Recurse -Force}
Copy-Item -LiteralPath (Join-Path $source 'SKILL.md') -Destination $target -Force
Copy-Item -LiteralPath (Join-Path $source 'VERSION') -Destination $target -Force
& (Join-Path $PSScriptRoot 'doctor.ps1') -SkillPath $target;if($LASTEXITCODE){exit $LASTEXITCODE}
Write-Host "Installed: $target";Write-Host "Load unpacked extension once from: $(Join-Path $target 'extension')"
if(-not $SkipChrome){Start-Process 'chrome.exe' 'chrome://extensions/' -ErrorAction SilentlyContinue}
