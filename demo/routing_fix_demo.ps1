# routing_fix_demo.ps1 - live demo: measured 93.7% routing -> add ONE config rule -> 100%.
#
# Honest framing (say this, not "100% accurate"):
#   "93.7% measured against ground truth; one configurable rule closes the gap."
#   We tuned a rule to a known miss in a known dataset - we do not claim universal accuracy.
#
# Requirement met: the routing engine (route_cases.py) reads routing_rules with a fresh
# SELECT on every run. There is NO cache and NO service to restart, so the rule applies on
# the next re-route immediately.
#
# Rehearsable: every run first REMOVES the demo rule and re-establishes the 93.7% baseline,
# so you can run this repeatedly. Use -Reset to just return to baseline; -NoPause to run
# end-to-end without the between-step prompts.

param([switch]$Reset, [switch]$NoPause)
$ErrorActionPreference = 'Stop'

. "$PSScriptRoot\_env.ps1"   # loads CAMPUSPULSE_DB_PASSWORD (+ PGPASSWORD) from .env if unset
$py   = 'C:\Users\ibrah\miniconda3\python.exe'
$psql = 'C:\Program Files\PostgreSQL\18\bin\psql.exe'
$env:PGPASSWORD = $env:CAMPUSPULSE_DB_PASSWORD
$db    = @('-U', 'postgres', '-h', 'localhost', '-d', 'campuspulse')
$route = 'C:\Users\ibrah\CampusPulse\intelligence\route_cases.py'

# The demo rule is tagged rule_order = 25 so reset can find and remove it precisely.
$removeRule = "DELETE FROM routing_rules WHERE rule_order = 25;"
$addRule = "INSERT INTO routing_rules (rule_order, match_category_id, match_location_type, match_keyword, target_department_id, active) SELECT 25, (SELECT id FROM categories WHERE key = 'SANITATION'), 'OTHER', NULL, (SELECT id FROM departments WHERE name = 'Civil Maintenance'), TRUE;"
$showMiss = "WITH case_gt AS (SELECT c.id, dep.name routed, mode() WITHIN GROUP (ORDER BY p.gt_department) gt FROM cases c JOIN departments dep ON dep.id=c.department_id JOIN reports r ON r.case_id=c.id JOIN report_provenance p ON p.report_id=r.id GROUP BY c.id, dep.name) SELECT id AS case_id, routed, gt AS should_be FROM case_gt WHERE routed <> gt ORDER BY id;"

function Pause-Step($msg) { if (-not $NoPause) { Read-Host "`n>>> $msg  (Enter to continue)" } }

if ($Reset) {
    & $psql @db -c $removeRule | Out-Null
    & $py $route | Out-Null
    Write-Host "Reset to baseline: demo rule removed, cases re-routed (back to 93.7%)."
    return
}

# STEP 1/4 - establish the honest baseline (remove any demo rule, then re-route + measure)
& $psql @db -c $removeRule | Out-Null
Write-Host "`n===== STEP 1/4 - baseline routing, measured against ground truth =====" -ForegroundColor Cyan
& $py $route

# STEP 2/4 - show the 4 misroutes explicitly
Write-Host "`n===== STEP 2/4 - the 4 misroutes (SANITATION defaults to Housekeeping; outdoor drainage should be Civil) =====" -ForegroundColor Cyan
& $psql @db -c $showMiss
Pause-Step "Explain the miss, then add the configurable rule"

# STEP 3/4 - add ONE config rule (the 'configurable per institution' moment)
Write-Host "`n===== STEP 3/4 - add rule #25: SANITATION at an OTHER-type (outdoor/perimeter) location -> Civil Maintenance =====" -ForegroundColor Cyan
& $psql @db -c $addRule
Write-Host "Rule added. No restart needed - the engine reads routing_rules fresh on the next run."
Pause-Step "Re-route to apply the rule"

# STEP 4/4 - re-route; the gap closes
Write-Host "`n===== STEP 4/4 - re-route with the new rule =====" -ForegroundColor Cyan
& $py $route

Write-Host "`nFraming: 93.7 percent measured against ground truth; one config rule closed the gap." -ForegroundColor Yellow
Write-Host "NOT a claim of universal accuracy." -ForegroundColor Yellow
