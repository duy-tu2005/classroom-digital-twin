param([string]$ServerHost = 'localhost')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path (Join-Path $PSScriptRoot '.env'))) {
    python (Join-Path $PSScriptRoot 'init-env.py') --host $ServerHost
    if ($LASTEXITCODE -ne 0) { throw 'Config generation failed' }
}
Push-Location $PSScriptRoot
try {
    docker compose up -d --wait --wait-timeout 120 postgres
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL failed' }
    $user = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
    $db = (docker compose exec -T postgres printenv POSTGRES_DB).Trim()
    $schema = (docker compose exec -T postgres psql -U $user -d $db -tAc "SELECT to_regclass('public.tb_schema_settings') IS NOT NULL;").Trim()
    if ($schema -ne 't') {
        docker compose --profile init run --rm -T thingsboard-install
        if ($LASTEXITCODE -ne 0) { throw 'Schema install failed' }
    }
    docker compose up -d thingsboard-ce
    if ($LASTEXITCODE -ne 0) { throw 'ThingsBoard start failed' }
    docker compose --profile bootstrap run --rm --build -T bootstrap
    if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed' }
    Copy-Item -LiteralPath 'runtime\.env.local' -Destination '..\.env.local' -Force
    Copy-Item -LiteralPath 'runtime\firmware\secrets.h' -Destination '..\firmware\secrets.h' -Force
} finally { Pop-Location }
