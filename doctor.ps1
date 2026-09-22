param([string]$SkillPath='')
$ErrorActionPreference='Stop'
if(-not $SkillPath){$SkillPath=Join-Path $PSScriptRoot 'reddit-voc-collector';if(-not(Test-Path "$SkillPath\SKILL.md")){$SkillPath=$PSScriptRoot}}
$expected='edpfinibjpbkdnognnhealnfepkeopem'
$required=@('SKILL.md','extension\manifest.json','extension\service_worker.js','local_bridge\reddit_bridge_server.py','scripts\reddit_playwright_collector.cjs')
$missing=@($required|Where-Object{-not(Test-Path -LiteralPath (Join-Path $SkillPath $_))})
$manifest=Get-Content -LiteralPath (Join-Path $SkillPath 'extension\manifest.json') -Raw|ConvertFrom-Json
$bytes=[Convert]::FromBase64String($manifest.key);$sha=[Security.Cryptography.SHA256]::Create().ComputeHash($bytes)[0..15]
$alphabet='abcdefghijklmnop';$id=-join($sha|ForEach-Object{$alphabet[$_ -shr 4].ToString()+$alphabet[$_ -band 15].ToString()})
$checks=[ordered]@{
  required_files=($missing.Count -eq 0); fixed_extension_id=($id -eq $expected)
  manifest_permissions=(@($manifest.permissions).Count -eq 0)
  reddit_host_only=(@($manifest.host_permissions)-join ',') -eq 'https://www.reddit.com/*,http://127.0.0.1:43127/*'
  python=[bool](Get-Command python -ErrorAction SilentlyContinue); node=[bool](Get-Command node -ErrorAction SilentlyContinue)
  bridge_port_free=-not[bool](Get-NetTCPConnection -LocalPort 43127 -State Listen -ErrorAction SilentlyContinue)
}
$ok=-not($checks.Values -contains $false)
[ordered]@{status=if($ok){'ready'}else{'failed'};version=$manifest.version_name;extension_id=$id;skill_path=(Resolve-Path $SkillPath).Path;checks=$checks;missing=$missing}|ConvertTo-Json -Depth 4
if(-not $ok){exit 1}
