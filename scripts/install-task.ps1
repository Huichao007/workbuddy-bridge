# Register autostart + keepalive for the bridge(s).
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-task.ps1
#
# Both tasks run as the current user on purpose: the bridge borrows *your*
# WorkBuddy session, so it must never run as SYSTEM or another account.
#
#   WorkBuddyBridge-Logon      at logon
#   WorkBuddyBridge-Keepalive  every 10 minutes (restarts a bridge that died)
#
# Remove with:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-task.ps1 -Remove

param([switch]$Remove)

$ErrorActionPreference = "Stop"
$launcher = Join-Path $PSScriptRoot "start-bridge.ps1"
$LOGON = "WorkBuddyBridge-Logon"
$KEEP  = "WorkBuddyBridge-Keepalive"

if ($Remove) {
    foreach ($t in @($LOGON, $KEEP)) {
        try {
            Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction Stop
            Write-Host "removed task $t"
        } catch {
            Write-Host "task $t was not registered"
        }
    }
    exit 0
}

if (-not (Test-Path $launcher)) { throw "launcher not found: $launcher" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcher`""
$user = "$env:USERDOMAIN\$env:USERNAME"

Register-ScheduledTask -TaskName $LOGON -Action $action `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) `
    -Description "Start the local WorkBuddy bridge(s) at logon" -Force | Out-Null

Register-ScheduledTask -TaskName $KEEP -Action $action `
    -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
        -RepetitionInterval (New-TimeSpan -Minutes 10)) `
    -Description "Keep the local WorkBuddy bridge(s) alive" -Force | Out-Null

Write-Host "registered: $LOGON, $KEEP"
Write-Host "launcher  : $launcher"
