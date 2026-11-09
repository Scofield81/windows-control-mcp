param([switch]$Json)

$checks = [ordered]@{
    windows = [Environment]::OSVersion.Version.ToString()
    architecture = [Environment]::Is64BitOperatingSystem
    python = $null
    python_path = $null
    project_root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    launcher = (Test-Path (Join-Path $PSScriptRoot 'run_windows_control_mcp.cmd'))
}
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $pythonCommand) {
    $checks.python_path = $pythonCommand.Source
    $checks.python = (& $pythonCommand.Source --version 2>&1 | Out-String).Trim()
}
$checks.source_entrypoint = Test-Path (Join-Path $checks.project_root 'src\windows_control_mcp\server.py')
$checks.ui_automation_adapter = Test-Path (Join-Path $checks.project_root 'scripts\ui_automation.ps1')
$checks.ready_for_source_run = [bool]($checks.python -and $checks.launcher -and $checks.source_entrypoint)

if ($Json) {
    $checks | ConvertTo-Json -Depth 4 -Compress
} else {
    $checks.GetEnumerator() | Format-Table -AutoSize
}
