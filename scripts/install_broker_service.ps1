param(
    [Parameter(Mandatory=$true)][string]$HelperPath,
    [Parameter(Mandatory=$true)][string]$HelperSha256,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$serviceName = 'WindowsControlMCPBroker'
$root = Join-Path $env:ProgramData 'WindowsControlMCP'
$policy = Join-Path $root 'broker-policy.json'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$helperFullPath = [System.IO.Path]::GetFullPath($HelperPath)
if (-not [System.IO.Path]::IsPathRooted($HelperPath) -or $helperFullPath -ne $HelperPath -or -not (Test-Path -LiteralPath $HelperPath -PathType Leaf)) { throw 'Approval helper must be an existing absolute file path.' }
if ($HelperSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Helper SHA-256 must contain 64 hexadecimal characters.' }

$policyObject = [ordered]@{
    version = 1
    allowed_user_sid = $sid
    approval_helper = [ordered]@{ path = $helperFullPath; sha256 = $HelperSha256.ToLowerInvariant() }
    profiles = [ordered]@{}
}
if ($WhatIf) { $policyObject | ConvertTo-Json -Depth 8; exit 0 }

New-Item -ItemType Directory -Path $root -Force | Out-Null
$policyObject | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $policy -Encoding UTF8
& icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)(F)' '*S-1-5-32-544:(OI)(CI)(F)' '*S-1-5-19:(OI)(CI)(RX)' | Out-Null
& icacls.exe $policy /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' '*S-1-5-19:(R)' | Out-Null
& sc.exe query $serviceName *> $null
if ($LASTEXITCODE -eq 0) { & sc.exe stop $serviceName *> $null; & sc.exe delete $serviceName *> $null }
Start-Sleep -Milliseconds 500
$projectRoot = Split-Path -Parent $PSScriptRoot
$oldPythonPath = $env:PYTHONPATH
if ($oldPythonPath) { $env:PYTHONPATH = (Join-Path $projectRoot 'src') + ';' + $oldPythonPath }
else { $env:PYTHONPATH = Join-Path $projectRoot 'src' }
$runtime = Join-Path $root 'service-runtime'
$runtimePackage = Join-Path $runtime 'windows_control_mcp'
New-Item -ItemType Directory -Path $runtimePackage -Force | Out-Null
$win32Dir = (& $python -c "import os,win32service; print(os.path.dirname(win32service.__file__))").Trim()
$pywin32SystemDir = (& $python -c "import os,pywintypes; print(os.path.dirname(os.path.abspath(pywintypes.__file__)))").Trim()
$pythonDll = (& $python -c "import ctypes,sys; k=ctypes.WinDLL('kernel32',use_last_error=True); f=k.GetModuleFileNameW; f.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_uint]; f.restype=ctypes.c_uint; b=ctypes.create_unicode_buffer(1024); f(ctypes.c_void_p(sys.dllhandle),b,len(b)); print(b.value)").Trim()
$pythonHome = Split-Path -Parent $pythonDll
$userSite = (& $python -c "import site; print(site.getusersitepackages())").Trim()
$serviceHost = Join-Path $runtime 'pythonservice.exe'
Copy-Item -LiteralPath (Join-Path $win32Dir 'pythonservice.exe') -Destination $serviceHost -Force
Copy-Item -LiteralPath (Join-Path $pywin32SystemDir 'pywintypes313.dll') -Destination $runtime -Force
Copy-Item -LiteralPath $pythonDll -Destination $runtime -Force
Copy-Item -LiteralPath (Join-Path $pythonHome 'Lib') -Destination $runtime -Recurse -Force
Copy-Item -LiteralPath (Join-Path $userSite 'win32') -Destination (Join-Path $runtime 'Lib\site-packages') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $userSite 'win32com') -Destination (Join-Path $runtime 'Lib\site-packages') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $userSite 'win32comext') -Destination (Join-Path $runtime 'Lib\site-packages') -Recurse -Force
Copy-Item -LiteralPath (Join-Path $userSite 'pythonwin') -Destination (Join-Path $runtime 'Lib\site-packages') -Recurse -Force
Copy-Item -Path (Join-Path $userSite 'pywin32*.py') -Destination (Join-Path $runtime 'Lib\site-packages') -Force
Copy-Item -LiteralPath (Join-Path $userSite 'pywin32.pth') -Destination (Join-Path $runtime 'Lib\site-packages') -Force
Copy-Item -LiteralPath $pywin32SystemDir -Destination $runtime -Recurse -Force
Copy-Item -Path (Join-Path $projectRoot 'src\windows_control_mcp\*.py') -Destination $runtimePackage -Force
$env:WINDOWS_CONTROL_MCP_SERVICE_HOST = $serviceHost
$env:PYTHONPATH = $runtime
& $python -m windows_control_mcp.broker_service --startup manual --username 'NT AUTHORITY\LocalService' install
if ($LASTEXITCODE -ne 0) { throw "pywin32 service registration failed with exit code $LASTEXITCODE." }
Write-Output "Installed service $serviceName through pywin32 ServiceFramework with manual start."
Write-Output "Policy: $policy. The service is not started automatically."
