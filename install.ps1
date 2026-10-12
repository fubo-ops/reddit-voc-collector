param([string]$InstallRoot=(Join-Path $HOME '.codex\skills'),[switch]$SkipChrome)
$ErrorActionPreference='Stop'
$source=$PSScriptRoot;$target=Join-Path $InstallRoot 'reddit-voc-collector'
if((Resolve-Path -LiteralPath $source).Path -eq $target){throw 'Source and install directory must differ'}
New-Item -ItemType Directory -Force -Path $target|Out-Null
foreach($name in @('agents','extension','local_bridge','references','scripts','tests')){
  foreach($file in Get-ChildItem -LiteralPath (Join-Path $source $name) -Recurse -File){
    if($file.FullName -match '[\\/](?:__pycache__|node_modules)[\\/]' -or $file.Extension -eq '.pyc'){continue}
    $dest=Join-Path $target $file.FullName.Substring($source.Length+1)
    New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent)|Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $dest -Force
  }
}
foreach($name in @('SKILL.md','VERSION','package.json','package-lock.json','pyproject.toml','requirements.txt','README.md','doctor.ps1','install.ps1')){Copy-Item -LiteralPath (Join-Path $source $name) -Destination $target -Force}
& (Join-Path $PSScriptRoot 'doctor.ps1') -SkillPath $target -Offline
Write-Host "Installed: $target"
Write-Host 'Default: installed OpenCLI CLI/extension and a collector-owned normal Chrome tab; login is manual.'
Write-Host 'No Chrome window/Profile is launched by installation. RC1 extension is compatibility-only.'
