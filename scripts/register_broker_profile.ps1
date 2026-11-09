param(
    [Parameter(Mandatory=$true)][string]$ProfileId,
    [Parameter(Mandatory=$true)][string]$Executable,
    [string[]]$FixedArguments = @(),
    [switch]$AllowArguments,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'
$root = Join-Path $env:ProgramData 'WindowsControlMCP'
$policyPath = Join-Path $root 'broker-policy.json'
if (-not (Test-Path -LiteralPath $policyPath -PathType Leaf)) { throw 'Broker policy does not exist.' }
$executableFullPath = [IO.Path]::GetFullPath($Executable)
if (-not [IO.Path]::IsPathRooted($Executable) -or $executableFullPath -ne $Executable) { throw 'Executable path must be absolute.' }
$file = Get-Item -LiteralPath $Executable -ErrorAction Stop
if ($file.PSIsContainer -or $file.LinkType) { throw 'Profile target cannot be a directory or link.' }
$blocked = @('cmd.exe','powershell.exe','pwsh.exe','python.exe','py.exe','wscript.exe','cscript.exe','mshta.exe','rundll32.exe','regsvr32.exe','installutil.exe','msiexec.exe')
if ($blocked -contains $file.Name.ToLowerInvariant()) { throw 'Shells and installers cannot be registered as broker profiles.' }
if ($ProfileId -notmatch '^[A-Za-z0-9._-]{1,64}$') { throw 'Profile ID contains invalid characters.' }
$policy = Get-Content -LiteralPath $policyPath -Raw | ConvertFrom-Json
if ($policy.version -ne 1 -or -not $policy.allowed_user_sid) { throw 'Invalid broker policy.' }
$hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$profile = [ordered]@{ kind = 'process'; executable = $file.FullName; sha256 = $hash; fixed_arguments = @($FixedArguments); allow_arguments = [bool]$AllowArguments }
if ($WhatIf) { $profile | ConvertTo-Json -Depth 5; exit 0 }
if (-not $policy.profiles) { $policy | Add-Member -NotePropertyName profiles -NotePropertyValue ([pscustomobject]@{}) }
$policy.profiles | Add-Member -NotePropertyName $ProfileId -NotePropertyValue ([pscustomobject]$profile) -Force
$backup = "$policyPath.bak"
Copy-Item -LiteralPath $policyPath -Destination $backup -Force
$policy | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $policyPath -Encoding UTF8
& icacls.exe $policyPath /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' '*S-1-5-19:(R)' | Out-Null
Write-Output "Registered broker profile $ProfileId ($($file.FullName)); SHA256 pinned."
