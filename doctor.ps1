param([string]$SkillPath='',[switch]$Offline)
$ErrorActionPreference='Stop'
if(-not $SkillPath){$SkillPath=$PSScriptRoot}
$required=@('SKILL.md','VERSION','scripts\reddit_opencli_collector.cjs','scripts\reddit_product_rules.cjs','scripts\build_opencli_workbook.mjs','scripts\validate_opencli_run.py','scripts\excel_delivery.cjs')
$missing=@($required|Where-Object{-not(Test-Path -LiteralPath (Join-Path $SkillPath $_))})
$checks=[ordered]@{required_files=($missing.Count -eq 0);node=[bool](Get-Command node -ErrorAction SilentlyContinue);python=[bool](Get-Command python -ErrorAction SilentlyContinue)}
$status=if($checks.Values -contains $false){'failed'}elseif($Offline){'offline_ready'}else{'not_ready'}
$browser='not_checked_offline'
if(-not $Offline -and $status -ne 'failed'){
  $result=& node (Join-Path $SkillPath 'scripts\reddit_playwright_collector.cjs') doctor
  $code=$LASTEXITCODE
  if($code -eq 0){$status='ready';$browser='ready'}else{$status='not_ready';$browser='not_ready'}
}
[ordered]@{status=$status;version=(Get-Content -LiteralPath (Join-Path $SkillPath 'VERSION') -Raw).Trim();session_mode='opencli';skill_path=$SkillPath;browser_connection=$browser;checks=$checks;missing=$missing}|ConvertTo-Json -Depth 4
if($status -notin @('ready','offline_ready')){exit 1}
