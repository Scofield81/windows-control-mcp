# Telepítés és kézi indítás

## Előfeltétel

Nyilvános kiadási repository: https://github.com/Scofield81/windows-control-mcp
Az ingyenes licenc kizárólag személyes, nem üzleti használatra vonatkozik; üzleti
használathoz külön írásos licenc szükséges. Lásd a gyökérben lévő `LICENSE` fájlt.

- Windows 10/11, aktív felhasználói asztali munkamenet.
- Python 3.10 vagy újabb.
- A csak olvasási (`SAFE`) alapműveletek külső MCP SDK nélkül futnak.
- Képernyőképhez a gépen elérhető `pywin32` szükséges.

Az MCP (Model Context Protocol) az AI-alkalmazás és a helyi Windows-szerver
közötti szabványos kapcsolat. A `stdio` azt jelenti, hogy a kapcsolat a program
bemenetén és kimenetén keresztül működik. A JSON-RPC a gépek közötti kérés-válasz
formátuma. A `pywin32` olyan Python-csomag, amelyen keresztül a program egyes
Windows-funkciókat ér el.

## Forrásból történő indítás

PowerShellben a projekt gyökeréből:

```powershell
$env:PYTHONPATH = "src"
python -m windows_control_mcp.server
```

A szerver `stdio` JSON-RPC-n kommunikál, ezért az ablakot az MCP-kliensnek, azaz
az MCP-szervert használó AI-alkalmazásnak kell
elindítania és nyitva tartania. A kézi indítás elsősorban diagnosztikára való.

Windows parancsfájlból is indítható:

```text
scripts\run_windows_control_mcp.cmd
```

## MCP-kliens konfigurációs minta

```json
{
  "mcpServers": {
    "windows-control-mcp": {
      "command": "python",
      "args": ["-m", "windows_control_mcp.server"],
      "cwd": "C:\\WindowsControlMCP",
      "env": {"PYTHONPATH": "src", "WINDOWS_CONTROL_MODE": "SAFE"}
    }
  }
}
```

Ha a kliens `.cmd` (Windows-parancsfájl) indítót támogat, a `command` értéke a teljes
`C:\\WindowsControlMCP\\scripts\\run_windows_control_mcp.cmd`
útvonal lehet, argumentumok nélkül.

Az engedélyköteles (`NORMAL`) vagy a kiemelten védett (`ADMIN`) módot csak külön,
megbízható helyi klienskonfigurációban szabad engedélyezni. Az automatikus jóváhagyás (`WINDOWS_CONTROL_AUTO_APPROVE=1`)
nem alapértelmezett, és csak kontrollált környezetben használható.

## Ellenőrzés

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

Az MCP-kliensnek először `initialize`, majd `tools/list` kérést kell küldenie.

