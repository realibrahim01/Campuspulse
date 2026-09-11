# _env.ps1 - ensure the DB password is available from ANY fresh terminal.
# Dot-source this at the top of a script:  . "$PSScriptRoot\_env.ps1"
#
# If CAMPUSPULSE_DB_PASSWORD is already set in the environment, we keep it. Otherwise we
# read it from the gitignored .env at the project root. Also mirrors it to PGPASSWORD so
# raw psql commands don't prompt. Env-var changes made here persist to the calling shell
# (env vars are process-level in PowerShell), so the whole demo session is covered.

if (-not $env:CAMPUSPULSE_DB_PASSWORD) {
    $envFile = Join-Path $PSScriptRoot '..\.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            $t = $line.Trim()
            if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
            $k, $v = $t -split '=', 2
            if ($k.Trim() -eq 'CAMPUSPULSE_DB_PASSWORD') {
                $env:CAMPUSPULSE_DB_PASSWORD = $v.Trim().Trim('"').Trim("'")
            }
        }
    }
}

if (-not $env:CAMPUSPULSE_DB_PASSWORD) {
    throw "CAMPUSPULSE_DB_PASSWORD is not set and no .env was found. Create CampusPulse\.env with:  CAMPUSPULSE_DB_PASSWORD=<your postgres password>"
}

# psql reads PGPASSWORD; mirror it so the walkthrough's psql commands never prompt.
$env:PGPASSWORD = $env:CAMPUSPULSE_DB_PASSWORD
