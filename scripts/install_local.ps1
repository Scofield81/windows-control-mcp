param(
    [ValidateSet('SAFE','NORMAL','ADMIN')][string]$Mode = 'SAFE',
    [switch]$AutoApprove,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $root 'scripts\run_windows_control_mcp.cmd'
$entrypoint = Join-Path $root 'src\windows_control_mcp\server.py'
$checkScript = Join-Path $root 'scripts\check_installation.ps1'

if (-not (Test-Path $launcher) -or -not (Test-Path $entrypoint)) {
    throw 'A projekt forrása vagy indítófájlja hiányzik.'
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'A Python nem található a PATH-ban.' }

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $checkScript -Json | Write-Output
if ($CheckOnly) {
    Write-Output 'CHECK_ONLY_OK'
    exit 0
}

$config = [ordered]@{
    mcpServers = [ordered]@{
        'windows-control-mcp' = [ordered]@{
            command = $launcher
            args = @()
            env = [ordered]@{
                WINDOWS_CONTROL_MODE = $Mode
                WINDOWS_CONTROL_AUTO_APPROVE = if ($AutoApprove) { '1' } else { '0' }
            }
        }
    }
}
$destination = Join-Path $root 'config.local.json'
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $destination -Encoding UTF8
Write-Output ('LOCAL_CONFIG=' + $destination)
Write-Output ('MODE=' + $Mode)
Write-Output ('AUTO_APPROVE=' + [bool]$AutoApprove)
Write-Output 'INSTALL_LOCAL_OK'
