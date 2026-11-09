# Register the daily operator check.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File ops\install-daily.ps1
#   powershell ... -Remove      # unregister
#
# Runs as the current user, once a day. The check calls the bridge, so it needs
# your session - never run it as SYSTEM.

param(
    [string]$At = "09:30",
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$TASK = "WorkBuddyBridge-Ops"
$script = Join-Path $PSScriptRoot "daily.py"

if ($Remove) {
    try {
        Unregister-ScheduledTask -TaskName $TASK -Confirm:$false -ErrorAction Stop
        Write-Host "removed task $TASK"
    } catch {
        Write-Host "task $TASK was not registered"
    }
    exit 0
}

if (-not (Test-Path $script)) { throw "daily.py not found at $script" }

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { throw "python not found on PATH" }

$action = New-ScheduledTaskAction -Execute $py -Argument "`"$script`"" `
    -WorkingDirectory $PSScriptRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$user = "$env:USERDOMAIN\$env:USERNAME"
Register-ScheduledTask -TaskName $TASK -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily WorkBuddy Bridge operator check" `
    -Force | Out-Null

Write-Host "registered: $TASK (daily at $At, user $user)"
Write-Host "report dir: $(Join-Path $PSScriptRoot 'reports')"
