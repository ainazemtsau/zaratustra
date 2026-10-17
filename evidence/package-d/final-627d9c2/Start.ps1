param([ValidateRange(2, 100)][int]$CallLimit = 8)
$ErrorActionPreference = 'Stop'
$settings = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'entry.json') -Raw | ConvertFrom-Json
if (-not (Test-Path -LiteralPath $settings.profile -PathType Leaf)) {
    throw 'Select Pi 1.0.4 and its ChatGPT-authorized auth path during installation first.'
}
Write-Output "Each Work has a finite cap of $CallLimit inference sends. Type /exit to close."
& (Join-Path $PSScriptRoot 'env/Scripts/zaratustra-next.exe') --data-root $settings.data_root chat --profile-file $settings.profile --call-limit $CallLimit
exit $LASTEXITCODE
