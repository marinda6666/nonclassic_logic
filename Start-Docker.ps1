param([switch]$NoBrowser)

$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot -ErrorAction Stop

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Install Docker Desktop, then run START.cmd again.' -ForegroundColor Yellow
    exit 1
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Starting Docker Desktop...'
    docker desktop start
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Start Docker Desktop manually and wait for the Linux engine, then retry.' -ForegroundColor Yellow
        exit 1
    }
    $engineReady = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $engineReady) {
        Write-Host 'The Docker Linux engine is not ready. Check Docker Desktop and retry.' -ForegroundColor Yellow
        exit 1
    }
}

Write-Host 'Building Weibull Lab and waiting for its health check...'
docker compose up --build --wait --wait-timeout 60
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$binding = docker compose port web 8080
if ($LASTEXITCODE -ne 0 -or -not $binding) { exit 1 }
$appUrl = 'http://' + ($binding | Select-Object -First 1).Trim()
Write-Host "Ready: $appUrl" -ForegroundColor Green
if (-not $NoBrowser) { Start-Process $appUrl }
