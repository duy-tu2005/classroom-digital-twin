$ErrorActionPreference = 'Stop'
$pioPath = Join-Path $env:USERPROFILE '.platformio\penv\Scripts\pio.exe'
if (-not (Test-Path -LiteralPath $pioPath)) { throw 'Install PlatformIO in VS Code first.' }
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'secrets.h'))) {
    throw 'Run thingsboard/setup.py first to generate firmware/secrets.h.'
}
# Catch invalid Wokwi pin names and open LED circuits before every build.
& (Join-Path (Split-Path -Parent $pioPath) 'python.exe') (Join-Path (Split-Path -Parent $PSScriptRoot) 'tests/wiring_test.py')
if ($LASTEXITCODE -ne 0) { throw 'Circuit validation failed. Firmware build stopped.' }
# The Windows compiler toolchain needs an ASCII path.
$buildAlias = Join-Path ([IO.Path]::GetPathRoot($PSScriptRoot)) 'classroom_fw'
if (Test-Path -LiteralPath $buildAlias) {
    $existing = Get-Item -LiteralPath $buildAlias
    if ($existing.LinkType -ne 'Junction' -or $existing.Target -ne $PSScriptRoot) {
        throw "Build alias belongs to another directory: $buildAlias"
    }
} else { New-Item -ItemType Junction -Path $buildAlias -Target $PSScriptRoot | Out-Null }
Push-Location $buildAlias
try { & $pioPath run; $buildExit = $LASTEXITCODE } finally { Pop-Location }
exit $buildExit

