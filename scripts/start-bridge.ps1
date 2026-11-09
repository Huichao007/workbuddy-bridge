# WorkBuddy bridge launcher - idempotent, works from any install location.
#
#   scripts\start-bridge.ps1              # start every instance in instances.json
#   scripts\start-bridge.ps1 -All         # same (explicit)
#   scripts\start-bridge.ps1 -Instance cn # start one instance by name
#   scripts\start-bridge.ps1 -Port 18490  # legacy: one bridge on a given port
#
# Safe to run repeatedly (logon task, keepalive task, manual): a port that is
# already listening is left alone.

param(
    [string]$Instance = "",
    [int]$Port = 0,
    [switch]$All
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$log  = Join-Path $root "launcher.log"

function Write-Log($msg) {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try { Add-Content -Path $log -Value "$stamp $msg" -Encoding UTF8 } catch { }
}

function Find-Python {
    foreach ($cand in @("python", "py", "python3")) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($cmd) { return @{ Exe = $cmd.Source; Args = @() } }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Log "ERROR no python found on PATH"
    Write-Error "Python 3.9+ is required. Install it and make sure 'python' is on PATH."
    exit 1
}

function Port-Up([int]$p) {
    return [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

function Start-One([string]$name, [int]$p) {
    if (Port-Up $p) {
        Write-Log "port $p already listening ($name) - nothing to do"
        return 0
    }
    $env:WB_BRIDGE_DUMP = if ($env:WB_BRIDGE_DUMP) { $env:WB_BRIDGE_DUMP } else { "err" }
    # --instance resolves the port/config dir from instances.json; strip stale
    # inherited overrides so they cannot leak between editions.
    $savedPort = $env:WB_BRIDGE_PORT
    $savedCfg  = $env:WORKBUDDY_CONFIG_DIR
    Remove-Item Env:WB_BRIDGE_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:WORKBUDDY_CONFIG_DIR -ErrorAction SilentlyContinue
    try {
        $argList = @((Join-Path $root "bridge.py"))
        if ($name) { $argList += @("--instance", $name) } elseif ($p -gt 0) { $argList += @("--port", "$p") }
        Write-Log "launching bridge instance='$name' port=$p"
        Start-Process -FilePath $py.Exe -ArgumentList $argList `
            -WorkingDirectory $root -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $root "bridge.out") `
            -RedirectStandardError  (Join-Path $root "bridge.err")
    } finally {
        if ($savedPort) { $env:WB_BRIDGE_PORT = $savedPort }
        if ($savedCfg)  { $env:WORKBUDDY_CONFIG_DIR = $savedCfg }
    }
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 500
        if (Port-Up $p) { Write-Log "bridge up on $p"; return 0 }
    }
    Write-Log "ERROR bridge did not come up on $p - see bridge.err"
    return 1
}

$instancesFile = Join-Path $root "instances.json"
if ($Instance -or $Port -gt 0) {
    if ($Instance) {
        $target = $null
        if (Test-Path $instancesFile) {
            $blob = Get-Content $instancesFile -Raw -Encoding UTF8 | ConvertFrom-Json
            $table = if ($blob.instances) { $blob.instances } else { $blob }
            $target = $table.$Instance
        }
        if (-not $target) {
            Write-Error "unknown instance '$Instance' - run: python setup.py"
            exit 1
        }
        exit (Start-One $Instance ([int]$target.port))
    }
    exit (Start-One "" $Port)
}

if (-not (Test-Path $instancesFile)) {
    Write-Log "no instances.json - falling back to a single bridge on 18490"
    exit (Start-One "" 18490)
}

$blob = Get-Content $instancesFile -Raw -Encoding UTF8 | ConvertFrom-Json
$table = if ($blob.instances) { $blob.instances } else { $blob }
$rc = 0
foreach ($prop in $table.PSObject.Properties) {
    $rc = [Math]::Max($rc, (Start-One $prop.Name ([int]$prop.Value.port)))
}
exit $rc
