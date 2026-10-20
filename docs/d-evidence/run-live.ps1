param([Parameter(Mandatory=$true)][string]$Scenario)
$testRoot='<SYNTHETIC_EVIDENCE_ROOT>'
$configuration=Join-Path $testRoot ($Scenario+'.json')
$runConfig=Get-Content -Raw -LiteralPath $configuration | ConvertFrom-Json
$installedPackage=Join-Path $runConfig.agentDir 'git/github.com/ainazemtsau/zaratustra'
if($runConfig.trustedScopes) {$env:ZARATUSTRA_SCOPES=ConvertTo-Json -Compress -InputObject @($runConfig.trustedScopes)} else {Remove-Item Env:ZARATUSTRA_SCOPES -ErrorAction SilentlyContinue}
New-Item -ItemType Directory -Force -Path $runConfig.output | Out-Null
$before=@{sha=(git -C $installedPackage rev-parse HEAD);budget=(Get-Content -Raw -LiteralPath $runConfig.budgetPath | ConvertFrom-Json);scenario=$Scenario;cwd=$runConfig.cwd;trusted_scopes=$env:ZARATUSTRA_SCOPES}
$before | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 (Join-Path $runConfig.output 'controller-before.json')
$env:ZARA_PI_SDK=Join-Path (npm root -g) '@earendil-works/pi-coding-agent/dist/index.js'
$env:ZARA_AUTH_PATH=Join-Path $env:USERPROFILE '.pi/agent/auth.json'
Push-Location $runConfig.cwd
try {node (Join-Path $installedPackage 'scripts/live.mjs') $configuration *> (Join-Path $testRoot ('live-'+$Scenario+'.log'));$runExit=$LASTEXITCODE}
finally {Pop-Location}
@{sha=(git -C $installedPackage rev-parse HEAD);exit=$runExit;budget=(Get-Content -Raw -LiteralPath $runConfig.budgetPath | ConvertFrom-Json)} | ConvertTo-Json -Depth 20 | Set-Content -Encoding utf8 (Join-Path $runConfig.output 'controller-after.json')
Get-Content -LiteralPath (Join-Path $testRoot ('live-'+$Scenario+'.log')) -Tail 30
exit $runExit
