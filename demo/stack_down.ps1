# stack_down.ps1 - tear down the CampusPulse stack started by stack_up.ps1.
# Stops whatever is listening on the three app ports (API 8080, console 5173, Expo 8081).
# Leaves the Postgres service running (it's a shared local service).

$ErrorActionPreference = 'SilentlyContinue'
$ports = @{ 8080 = 'API'; 5173 = 'Console'; 8081 = 'Expo/Mobile' }
foreach ($port in $ports.Keys) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen
    if ($conns) {
        foreach ($c in $conns) {
            $p = Get-Process -Id $c.OwningProcess
            Stop-Process -Id $c.OwningProcess -Force
            Write-Host "Stopped $($ports[$port]) on :$port (pid $($c.OwningProcess), $($p.ProcessName))"
        }
    } else {
        Write-Host "$($ports[$port]) on :$port - not running"
    }
}
Write-Host ""
Write-Host "Stack down. (Postgres service left running; the empty cmd windows can be closed.)"
