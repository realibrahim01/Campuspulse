# rescore.ps1 - rebuild all intelligence outputs from the CURRENT set of reports.
# Clusters (including any freshly submitted reports), routes, scores (as_of = now, so a
# just-submitted report scores ~0 on age), explains, and seeds acknowledgement activity.
# Use after a live report submission to bring it into a scored, explained case.
#
# Routing rules are read fresh (no cache). This does NOT touch routing rules - if you want
# the 93.7% baseline, run  .\demo\routing_fix_demo.ps1 -Reset  first.

# NOTE: do NOT use ErrorActionPreference 'Stop' here - the ML libs print harmless warnings
# to stderr, which 'Stop' would treat as fatal. HF_HUB_OFFLINE uses the cached model (no
# network, no warning).
$ErrorActionPreference = 'Continue'
. "$PSScriptRoot\_env.ps1"   # loads CAMPUSPULSE_DB_PASSWORD (+ PGPASSWORD) from .env if unset
$env:TOKENIZERS_PARALLELISM = 'false'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$py = 'C:\Users\ibrah\miniconda3\python.exe'
$d  = 'C:\Users\ibrah\CampusPulse\intelligence'

& $py "$d\persist_cases.py"        | Select-String 'Persisted'
& $py "$d\route_cases.py"          | Select-String 'accuracy'
& $py "$d\score_cases.py" --fresh  | Select-String 'Wrote'
& $py "$d\explain_cases.py"        | Select-String 'Generated'
& $py "$d\seed_activity.py"        | Select-String 'Seeded'
Write-Host "Rebuild complete - newest case is the most recently submitted report." -ForegroundColor Green
