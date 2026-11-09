# Broker telepítése felhasználóknak

Ebben az útmutatóban a `SAFE` a csak olvasási és lekérdezési, a `NORMAL` az
engedélyköteles, az `ADMIN` pedig a rendszergazdai vagy kiemelten védett
műveleteket jelöli. A `SAFE` olvasási kategória nem jelenti azt, hogy minden
lekérdezett adat nyilvános vagy bizalmas adatot nem tartalmazhat.

A broker védett programindító szolgáltatás: csak előre ellenőrzött programot
indít, nem általános parancsértelmező. A hash egy ellenőrző digitális lenyomat,
amelyből észrevehető, ha az ellenőrzött fájl megváltozott. A `LocalService` a
Windows korlátozott szolgáltatásfiókja.

Az MCP (Model Context Protocol) az AI-alkalmazás és a Windows Control MCP
szerver közötti szabványos kapcsolat; a broker ennek a kapcsolatnak a védett
programindítási részét kezeli.

A felhasználónak nem kell PyInstallert, Nuitkát, .NET SDK-t vagy más fejlesztői
csomagolót telepítenie.

A végleges Windows-kiadás a szükséges jóváhagyó komponenst előre elkészített,
ellenőrzött `WindowsControlMCPApproval.exe` fájlként tartalmazza. A telepítő ezt
hash alapján ellenőrzi, majd a broker külön `LocalService` Windows-szolgáltatásként
települ. A rendszergazdai lépéseket a telepítő előtt külön felhasználói jóváhagyás
védi.

A helper a kiadási csomag `tools\WindowsControlMCPApproval.exe` fájlja; a
felhasználónak nem kell PyInstallert telepítenie.

A felhasználó általános menete:

1. Töltsd le az ellenőrzött kiadási csomagot.
2. Indítsd el az AI-ügynöki telepítési promptot vagy a dokumentált telepítőt.
3. Hagyd jóvá csak a ténylegesen szükséges rendszergazdai műveletet.
4. A telepítő ellenőrzi a Python-környezetet, az MCP-kapcsolatot és a broker állapotát.
5. A használat csak olvasási (`SAFE`) módban és automatikus jóváhagyás nélkül indul.

PyInstaller csak a kiadási csomag fejlesztői előállításához szükséges; a normál
felhasználónak nem kell telepítenie vagy futtatnia.
