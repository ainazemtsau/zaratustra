$ErrorActionPreference = 'Stop'
$zaraRepo = 'C:/projects/zaratustra'
foreach ($zaraControl in @('STOP', 'STEER.md')) {
    if (Test-Path -LiteralPath (Join-Path $zaraRepo $zaraControl)) {
        Get-Content -Raw -LiteralPath (Join-Path $zaraRepo $zaraControl)
        throw "Read and resolve $zaraControl before proceeding"
    }
}
$zaraSamples = @(
    @{
        name = 'accepted-work1'
        root = 'C:/Users/Anton/AppData/Local/Temp/solmax-work1-accept-20260907-a1/retained-trial'
        version = '0.1.0'
        db = 'ec4fd2c045922578fa1344a5c126c94b0b929215efd57e93b773baf3785ca207'
        wheel = '4f71d1b2aff54d8680d22e01cb58483681a69969c3c3501667e2bb5aabb9482c'
    },
    @{
        name = 'executor-work2'
        root = 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-8cv9m8jt'
        version = '0.2.0'
        db = 'cd8169923aa0836bf6964537f2ea59543a44fffec3d4c4d7c2104ab221759de0'
        wheel = 'a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c'
    },
    @{
        name = 'binding-work2'
        root = 'C:/Users/Anton/AppData/Local/Temp/zaratustra-work2-ltyq1qsb'
        version = '0.2.0'
        db = 'e6e4d430e575e17feca718b1063e6640af09103263848030bbb6d81a72905fe1'
        wheel = 'a50f0f2d195b33a5eac08d9dd8a2479b9863cd029af703341781fb0c63d5d53c'
    }
)
$zaraTrial = Join-Path ([IO.Path]::GetTempPath()) ('zaratustra-work3-inputs-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $zaraTrial | Out-Null
Write-Output "New copies only: $zaraTrial"
$zaraObserved = @()
foreach ($zaraSample in $zaraSamples) {
    $zaraWorkspace = Join-Path $zaraSample.root 'workspace'
    $zaraDb = Join-Path $zaraWorkspace '.zara/state.sqlite3'
    $zaraWheel = Join-Path $zaraSample.root ('zaratustra-' + $zaraSample.version + '-py3-none-any.whl')
    $zaraBeforeDb = (Get-FileHash -Algorithm SHA256 -LiteralPath $zaraDb).Hash.ToLowerInvariant()
    $zaraBeforeWheel = (Get-FileHash -Algorithm SHA256 -LiteralPath $zaraWheel).Hash.ToLowerInvariant()
    if ($zaraBeforeDb -ne $zaraSample.db -or $zaraBeforeWheel -ne $zaraSample.wheel) {
        throw ('Retained input mismatch: ' + $zaraSample.name)
    }
    $zaraCopy = Join-Path $zaraTrial $zaraSample.name
    Copy-Item -LiteralPath $zaraWorkspace -Destination $zaraCopy -Recurse
    $zaraExecutable = Join-Path $zaraSample.root 'venv/Scripts/zara.exe'
    Write-Output ('$ ' + $zaraExecutable + ' --version')
    & $zaraExecutable --version
    if ($LASTEXITCODE -ne 0) { throw 'Installed version read failed' }
    Write-Output ('$ ' + $zaraExecutable + ' status ' + $zaraCopy)
    & $zaraExecutable status $zaraCopy
    if ($LASTEXITCODE -ne 0) { throw 'Installed metadata read failed' }
    if ($zaraSample.version -eq '0.2.0') {
        Write-Output ('$ ' + $zaraExecutable + ' records read ' + $zaraCopy)
        & $zaraExecutable records read $zaraCopy
        if ($LASTEXITCODE -ne 0) { throw 'Installed record read failed' }
    }
    $zaraAfterDb = (Get-FileHash -Algorithm SHA256 -LiteralPath $zaraDb).Hash.ToLowerInvariant()
    $zaraAfterWheel = (Get-FileHash -Algorithm SHA256 -LiteralPath $zaraWheel).Hash.ToLowerInvariant()
    $zaraCopyDb = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $zaraCopy '.zara/state.sqlite3')).Hash.ToLowerInvariant()
    if ($zaraAfterDb -ne $zaraBeforeDb -or $zaraAfterWheel -ne $zaraBeforeWheel -or $zaraCopyDb -ne $zaraBeforeDb) {
        throw ('Preservation mismatch: ' + $zaraSample.name)
    }
    $zaraObserved += [ordered]@{
        sample = $zaraSample.name
        original = $zaraSample.root
        copied_workspace = $zaraCopy
        installed_command = $zaraExecutable
        version = $zaraSample.version
        database_sha256_before_after = $zaraAfterDb
        wheel_sha256_before_after = $zaraAfterWheel
        copy_database_sha256_after_read = $zaraCopyDb
    }
}
$zaraObserved | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 -LiteralPath (Join-Path $zaraRepo 'docs/work3/evidence/retained-inputs.json')
Write-Output 'PASS: three accepted input DB/wheel pairs match their accepted hashes; new copies read with installed versions; originals unchanged.'
Write-Output 'This is accepted-baseline evidence only. No Work 3 mutation or owner runtime acceptance is claimed.'
