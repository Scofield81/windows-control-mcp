param([switch]$RemoveData)
$ErrorActionPreference = 'Stop'
$serviceName = 'WindowsControlMCPBroker'
& sc.exe stop $serviceName | Out-Null
Start-Sleep -Milliseconds 700
& sc.exe delete $serviceName | Out-Null
if ($RemoveData) {
    $root = Join-Path $env:ProgramData 'WindowsControlMCP'
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
Write-Output "Removed service $serviceName. Policy data removed only with -RemoveData."
