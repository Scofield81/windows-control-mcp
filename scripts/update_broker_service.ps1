param([Parameter(Mandatory=$true)][string]$PolicyPath)
$ErrorActionPreference = 'Stop'
$serviceName = 'WindowsControlMCPBroker'
$target = Join-Path $env:ProgramData 'WindowsControlMCP\broker-policy.json'
if (-not (Test-Path -LiteralPath $PolicyPath -PathType Leaf)) { throw 'A házirendfájl nem található.' }
$data = Get-Content -LiteralPath $PolicyPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($data.version -ne 1 -or [string]::IsNullOrWhiteSpace($data.allowed_user_sid)) { throw 'Érvénytelen brokerházirend.' }
if ((Get-Service -Name $serviceName -ErrorAction SilentlyContinue).Status -eq 'Running') { & sc.exe stop $serviceName | Out-Null; Start-Sleep -Seconds 1 }
$backup = "$target.bak-$(Get-Date -Format yyyyMMddHHmmss)"
if (Test-Path -LiteralPath $target) { Copy-Item -LiteralPath $target -Destination $backup -Force }
Copy-Item -LiteralPath $PolicyPath -Destination $target -Force
& icacls.exe $target /inheritance:r /grant:r 'SYSTEM:(F)' 'Administrators:(F)' 'NT AUTHORITY\LOCAL SERVICE:(R)' | Out-Null
Write-Output "Updated broker policy; backup: $backup"
