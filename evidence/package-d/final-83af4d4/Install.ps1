param(
    [Parameter(Mandatory = $true)][string]$RuntimeRoot,
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [string]$PiCli,
    [string]$PiAuthPath
)
$ErrorActionPreference = 'Stop'
function Require-NewOutsideGit([string]$Value) {
    $resolved = [IO.Path]::GetFullPath($Value)
    if (Test-Path -LiteralPath $resolved) { throw "Choose a NEW path: $resolved" }
    $ancestor = [IO.DirectoryInfo]::new([IO.Path]::GetDirectoryName($resolved))
    while ($null -ne $ancestor) {
        if (Test-Path -LiteralPath (Join-Path $ancestor.FullName '.git')) {
            throw "Choose a path outside Git checkouts: $resolved"
        }
        $ancestor = $ancestor.Parent
    }
    return $resolved
}
$selectedRuntime = Require-NewOutsideGit $RuntimeRoot
$selectedData = Require-NewOutsideGit $DataRoot
if ($selectedRuntime -eq $selectedData) { throw 'Runtime and data-root must differ.' }
if ([bool]$PiCli -ne [bool]$PiAuthPath) { throw 'Select both PiCli and PiAuthPath, or neither.' }
New-Item -ItemType Directory -Path $selectedRuntime | Out-Null
& uv venv (Join-Path $selectedRuntime 'env') --python 3.13.7
if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
$selectedPython = Join-Path $selectedRuntime 'env/Scripts/python.exe'
& uv pip install --python $selectedPython --no-index --find-links (Join-Path $PSScriptRoot 'wheels') --require-hashes -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Verified wheel installation failed.' }
$selectedEntry = Join-Path $selectedRuntime 'env/Scripts/zaratustra-next.exe'
& $selectedEntry --data-root $selectedData init
if ($LASTEXITCODE -ne 0) { throw 'New empty Core initialization failed.' }
if ($PiCli) {
    if (-not (Test-Path -LiteralPath $PiCli -PathType Leaf)) { throw 'Selected Pi CLI is unavailable.' }
    if (-not (Test-Path -LiteralPath $PiAuthPath -PathType Leaf)) { throw 'Complete Pi Sign in with ChatGPT first.' }
    $selectedProfile = Join-Path $selectedRuntime 'pi-profile.json'
    @{
        pi_cli = [IO.Path]::GetFullPath($PiCli)
        endpoint = 'https://api.openai.com/v1'
        model = 'gpt-6-luna'
        auth_mode = 'pi-chatgpt'
        auth_path = [IO.Path]::GetFullPath($PiAuthPath)
        max_tokens = 8192
        context_window = 32768
        timeout = 150
    } | ConvertTo-Json | Set-Content -LiteralPath $selectedProfile -Encoding utf8NoBOM
}
@{ data_root = $selectedData; profile = (Join-Path $selectedRuntime 'pi-profile.json') } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $selectedRuntime 'entry.json') -Encoding utf8NoBOM
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Start.ps1') -Destination (Join-Path $selectedRuntime 'Start.ps1')
& $selectedEntry --data-root $selectedData diagnostics
if ($LASTEXITCODE -ne 0) { throw 'Model-free diagnostics failed.' }
Write-Output "Installed. Start ordinary conversation: & '$selectedRuntime/Start.ps1'"
Write-Output 'No personal data was imported. The data root is new and empty.'
