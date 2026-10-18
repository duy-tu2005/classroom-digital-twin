[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Server,
    [Parameter(Mandatory=$true)][string]$KeyPath,
    [ValidateSet('Existing','Standalone')][string]$Mode='Existing'
)
$ErrorActionPreference='Stop'
if ($Server -notmatch '^[A-Za-z0-9.-]+$') { throw 'Invalid server address' }
$key=(Resolve-Path -LiteralPath $KeyPath).Path
$root=Split-Path -Parent $PSScriptRoot
$envFile=Join-Path $PSScriptRoot '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    python (Join-Path $PSScriptRoot 'init-env.py') --host $Server
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate config' }
}
# Preserve private values and update only the server endpoint.
$content=Get-Content -Raw -Encoding UTF8 -LiteralPath $envFile
$content=[regex]::Replace($content,'(?m)^TB_PUBLIC_BASE_URL=.*$',"TB_PUBLIC_BASE_URL=http://$Server")
$content=[regex]::Replace($content,'(?m)^TB_MQTT_HOST=.*$',"TB_MQTT_HOST=$Server")
[IO.File]::WriteAllText($envFile,$content,(New-Object Text.UTF8Encoding($false)))
$alias=Join-Path ([IO.Path]::GetPathRoot($root)) 'classroom_project'
if (Test-Path -LiteralPath $alias) {
    $existing=Get-Item -LiteralPath $alias
    if ($existing.LinkType -ne 'Junction' -or $existing.Target -ne $root) { throw 'ASCII build alias points elsewhere' }
} else { New-Item -ItemType Junction -Path $alias -Target $root | Out-Null }
$archive=Join-Path $env:TEMP ('classroom-deploy-'+[guid]::NewGuid().ToString('N')+'.tgz')
tar.exe -czf $archive --exclude=.git --exclude=assets/references --exclude=firmware/.pio --exclude=firmware/secrets.h --exclude=deployment/.env --exclude=deployment/runtime --exclude=deployment/backups --exclude=.env.local --exclude=preview --exclude=tools/.runtime --exclude=tests/results --exclude=__pycache__ -C $alias .
if ($LASTEXITCODE -ne 0) { throw 'Package failed' }
$remoteArchive='/tmp/'+[IO.Path]::GetFileName($archive)
ssh -i $key -o BatchMode=yes "ubuntu@$Server" 'sudo mkdir -p /opt/classroom-digital-twin/deployment && sudo chown -R ubuntu:ubuntu /opt/classroom-digital-twin'
if ($LASTEXITCODE -ne 0) { throw 'SSH failed' }
scp -q -i $key -o BatchMode=yes $archive "ubuntu@${Server}:$remoteArchive"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed' }
scp -q -i $key -o BatchMode=yes $envFile "ubuntu@${Server}:/opt/classroom-digital-twin/deployment/.env"
if ($LASTEXITCODE -ne 0) { throw 'Private config upload failed' }
$start=if ($Mode -eq 'Existing') {'deployment/bootstrap-existing.sh'} else {'deployment/start.sh'}
$remote=@"
set -eu
umask 077
test -d /opt/classroom-digital-twin
tar -xzf $remoteArchive -C /opt/classroom-digital-twin
chmod 600 /opt/classroom-digital-twin/deployment/.env
cd /opt/classroom-digital-twin
sh $start
"@
$b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remote.Replace("`r",'')))
ssh -i $key -o BatchMode=yes "ubuntu@$Server" "echo '$b64' | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { throw 'AWS bootstrap failed' }
foreach ($item in @('.env.local','firmware/secrets.h')) {
    $target=Join-Path $root $item
    scp -q -i $key -o BatchMode=yes "ubuntu@${Server}:/opt/classroom-digital-twin/$item" $target
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $item" }
}
scp -q -r -i $key -o BatchMode=yes "ubuntu@${Server}:/opt/classroom-digital-twin/deployment/runtime/exports" (Join-Path $root 'thingsboard')
if ($LASTEXITCODE -ne 0) { throw 'Export download failed' }
Write-Host '[deploy] AWS ready. Rebuild firmware and restart Wokwi when the IP changes.'

