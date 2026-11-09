param(
    [ValidateSet('Antigravity','ClaudeDesktop','CodexSnippet')][string]$Client,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $root 'scripts\run_windows_control_mcp.cmd'
$server = [ordered]@{
    command = 'cmd.exe'
    args = @('/d', '/c', $launcher)
    cwd = $root
    env = [ordered]@{
        WINDOWS_CONTROL_MODE = 'SAFE'
        WINDOWS_CONTROL_AUTO_APPROVE = '0'
    }
}

function Write-JsonConfig([string]$Path) {
    $existing = [ordered]@{}
    if (Test-Path -LiteralPath $Path) {
        $raw = Get-Content -LiteralPath $Path -Raw
        if ($raw.Trim()) { $existing = $raw | ConvertFrom-Json -AsHashtable }
    }
    if ($null -eq $existing['mcpServers']) { $existing['mcpServers'] = [ordered]@{} }
    $existing['mcpServers']['windows-control-mcp'] = $server
    if ($Apply -and (Test-Path -LiteralPath $Path)) {
        Copy-Item -LiteralPath $Path -Destination ($Path + '.bak-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    }
    if ($Apply) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
        $existing | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
        Write-Output ('APPLIED=' + $Path)
    } else {
        Write-Output ('DRY_RUN=' + $Path)
        $existing | ConvertTo-Json -Depth 8
    }
}

switch ($Client) {
    'Antigravity' {
        Write-JsonConfig (Join-Path $env:USERPROFILE '.gemini\config\mcp_config.json')
    }
    'ClaudeDesktop' {
        Write-JsonConfig (Join-Path $env:APPDATA 'Claude\claude_desktop_config.json')
    }
    'CodexSnippet' {
        Write-Output 'A Codex CLI/IDE konfigurációt a hivatalos codex mcp add paranccsal vagy config.toml-ban állítsd be.'
        Write-Output ('codex mcp add windows-control-mcp --env WINDOWS_CONTROL_MODE=SAFE --env WINDOWS_CONTROL_AUTO_APPROVE=0 -- cmd.exe /d /c "' + $launcher + '"')
        Write-Output ('Project cwd: ' + $root)
    }
}
