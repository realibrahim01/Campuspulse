# stack_up.ps1 - bring the whole CampusPulse stack up for a demo/rehearsal.
# Launches Postgres (service), the API, the department console, and the Expo student app,
# each in its own window so you can see their logs. Run stack_down.ps1 to tear it all down.
#
# No prereqs from a cold terminal: the DB password is read from the gitignored .env at the
# project root (or from CAMPUSPULSE_DB_PASSWORD if you've already set it). Just:
#     cd C:\Users\ibrah\CampusPulse ; .\demo\stack_up.ps1

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\_env.ps1"   # loads CAMPUSPULSE_DB_PASSWORD from .env if not already set
$root = 'C:\Users\ibrah\CampusPulse'
$jar  = "$root\api\target\api-0.1.0.jar"

if (-not (Test-Path $jar)) {
    throw "API jar not found. Build it first: mvn -f $root\api\pom.xml -DskipTests package"
}

# 0. PostgreSQL service
$svc = Get-Service 'postgresql-x64-18' -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -ne 'Running') { Start-Service 'postgresql-x64-18'; Write-Host "Postgres: started" }
else { Write-Host "Postgres: running" }

# 1. API :8080  (child cmd inherits CAMPUSPULSE_DB_PASSWORD from this shell)
Start-Process cmd -ArgumentList "/k","title CampusPulse-API && java -jar $jar"
# 2. Department console :5173
Start-Process cmd -ArgumentList "/k","cd /d $root\console && title CampusPulse-Console && npm run dev"
# 3. Student app (Expo web) :8081
Start-Process cmd -ArgumentList "/k","cd /d $root\mobile && title CampusPulse-Mobile && npx expo start --web --port 8081"

Write-Host ""
Write-Host "Bringing up (each in its own window):" -ForegroundColor Green
Write-Host "  API              http://localhost:8080"
Write-Host "  Dept console     http://localhost:5173   (house@ / admin@campus.edu)"
Write-Host "  Student app      http://localhost:8081   (student01@campus.edu)"
Write-Host "  All passwords    campus123"
Write-Host ""
Write-Host "Give it ~30s (Expo bundles on first load). Tear down with:  .\demo\stack_down.ps1" -ForegroundColor Yellow
