# Másolható magyar telepítési promptok

Az alábbi promptok a projekt jelenlegi állapotára épülnek. Hivatalos kiadási forrás:
https://github.com/Scofield81/windows-control-mcp
Az ingyenes licenc kizárólag saját, személyes, nem üzleti használatra vonatkozik;
üzleti használathoz külön írásos, fizetős licenc szükséges.

Jogosultsági rövidítések: `SAFE` = csak olvasás és lekérdezés, `NORMAL` =
engedélyköteles műveletek, `ADMIN` = rendszergazdai vagy kiemelten védett
műveletek. Ezek a technikai azonosítók a konfigurációban változatlanok maradnak.

Az MCP (Model Context Protocol) az AI-alkalmazás és a helyi szerver közötti
szabványos kapcsolat. A `stdio` helyi adatkapcsolatot jelent, az
`initialize` a kapcsolat indítása, a `tools/list` az elérhető eszközök listája,
a `system_info` pedig a számítógép alapállapotát lekérdező eszköz. A broker
védett programindító szolgáltatás; a `Named Pipe` Windows-helyi kommunikációs
csatorna, a `policy` házirend, a `SID` Windows-azonosító, az `IPC` pedig
programok közötti kommunikáció. A `PASS`, `FAIL` és `BLOCKED` rendre sikeres,
hibás és külső okból nem igazolható állapotot jelent.

## Codex Free / Codex CLI / IDE

```text
Szeretném biztonságosan telepíteni a Windows Számítógép-vezérlő MCP-t a saját Windows gépemre.
Hivatalos forrás: https://github.com/Scofield81/windows-control-mcp

Ellenőrizd a Windows-verziót, a Python-verziót és a lemeztárhelyet. Csak a projekt saját
telepítési útmutatóját kövesd, ne telepíts második Python- vagy Node-környezetet, és ne kérj
rendszergazdai jogosultságot indokolatlanul. A szervert először csak olvasási
(`SAFE`) módban állítsd be,
automatikus jóváhagyás nélkül. Ne kapcsold be automatikusan az egeret, billentyűzetet,
kamerát vagy ADMIN-eszközöket.

Állítsd be helyi stdio MCP-szerverként a Codexben, majd ellenőrizd az initialize, tools/list
és egy csak olvasási (`SAFE`) `system_info` hívást. A végén magyarul írd le, mi sikerült és mihez kell még kézi
engedély. Ne módosíts meglévő kliensbeállítást biztonsági mentés nélkül.
```

## Claude Desktop Free

```text
Szeretném telepíteni a Windows Számítógép-vezérlő MCP-t Claude Desktopban.
Forrás: https://github.com/Scofield81/windows-control-mcp

Ellenőrizd, hogy helyi MCP-szerver használható-e ebben a Claude Desktop-fiókban. Ha van
ellenőrzött `.mcpb` helyi bővítménycsomag, csak azt használd. Ha nincs, a projekt helyi stdio konfigurációját
állítsd be a dokumentáció szerint, előbb készíts biztonsági mentést, és csak olvasási
(`SAFE`) módban indíts.
Ne állíts be nyilvános távoli továbbító szolgáltatást, ne kérj API-kulcsot (titkos
hozzáférési kulcsot), és ne engedélyezz automatikus
kamerát, billentyűzetet vagy ADMIN-műveletet.

Ellenőrizd egy csak olvasási (`SAFE`) `system_info` hívással, majd magyarul jelentsd az eredményt. Ha csak Claude
webes vagy Cowork hozzáférés áll rendelkezésre, mondd ki, hogy a helyi stdio szerver közvetlenül
nem érhető el, és ne próbálj internetes kerülőutat létrehozni.
```

## Google Antigravity Individual

```text
Szeretném telepíteni a Windows Számítógép-vezérlő MCP-t Google Antigravityban.
Ellenőrzött forrás: https://github.com/Scofield81/windows-control-mcp

Ellenőrizd a Windows-környezetet, majd a projekt telepítőjével készíts csak olvasási
(`SAFE`), automatikus
jóváhagyás nélküli helyi stdio konfigurációt a Gemini/Antigravity `mcp_config.json`
beállítási fájlhoz.
A meglévő konfigurációt ne írd felül: készíts biztonsági mentést. Ne telepíts felesleges
függőséget és ne kapcsolj be kamerát, billentyűzetet vagy ADMIN-eszközt.

Indítsd újra az Antigravity MCP-kezelőt, ellenőrizd a kapcsolatot és futtass egy csak
olvasási (`SAFE`) `system_info` tesztet. Magyarul írd le az eredményt és minden szükséges kézi lépést.
```

## Közös biztonsági feltétel

Egyetlen prompt sem jogosít fel hitelesítő adatok, jelszavak, tokenek vagy privát kulcsok
bekérésére. A helyi MCP-t csak a tulajdonos által ellenőrzött forrásból szabad telepíteni.

## Teljes AI-ügynöki telepítési prompt

Az alábbi szöveg önállóan átadható egy kompatibilis AI-ügynöknek.

```text
Feladat: a Windows-automatizálási rendszer MCP-integrációval biztonságos helyi
telepítése és ellenőrzése ezen a Windows-gépen.

Hivatalos forrás: https://github.com/Scofield81/windows-control-mcp
Hivatalos dokumentáció: docs/TELEPITES.md, docs/FELHASZNALOI_UTMUTATO.md,
docs/EXECUTION_BROKER.md és docs/TELEPITESI_PROMPTOK.md.

Telepítés előtt csak olvasható ellenőrzést végezz: Windows-verzió és architektúra,
Python-verziók, a pywin32 csomag, meglévő Windows Control MCP, broker-szolgáltatás,
MCP- és brokerfolyamatok, releváns portok és Named Pipe-végpontok, szabad lemez- és
memória, CPU-/lemezterhelés, hőmérsékletszenzorok, korábbi konfigurációk és engedélyek.
Ne telepíts újra már működő komponenst, ne írd felül más projektek Python-környezetét,
és lehetőség szerint használj elkülönített virtuális környezetet.

Csak a valóban hiányzó összetevőket telepítsd. A telepítési lépések legyenek
ismételt futtatáskor is biztonságosak. A broker korlátozott LocalService-fiókkal,
hozzáférési szabályokkal védett házirenddel, SID-ellenőrzéssel, Named Pipe IPC-vel
és ellenőrzött digitális lenyomatú profilokkal működik. A szolgáltatás telepítése,
frissítése, profilregisztrációja és eltávolítása rendszergazdai művelet: ezek előtt
állj meg, mutasd meg a pontos műveletet, és kérj aktuális felhasználói jóváhagyást.
Ne indíts második brokerpéldányt, ne állítsd le a felhasználó alkalmazásait, és ne
kapcsold be a közvetlen (`direct`) vagy automatikus jóváhagyási fejlesztői utat.

Állítsd be az MCP-klienst helyi stdio módban, csak olvasási (`SAFE`) alapértelmezéssel és automatikus
jóváhagyás nélkül. A meglévő klienskonfigurációról készíts mentést. Ellenőrizd az
initialize, tools/list és egy SAFE system_info hívást. A módosító műveleteknél a
felhasználó lássa a célt, paramétereket, kockázatot és időtartamot; az ügynök saját
magának nem adhat engedélyt.

Telepítés után készíts magyar jelentést PASS/FAIL/BLOCKED (sikeres/hibás/nem
igazolható) állapotokkal. PASS csak akkor
adható, ha a verziók, függőségek, a broker házirendje (policy), a jogosultságmodell,
az MCP-kapcsolat, az eszközlista, egy csak olvasási (`SAFE`) próbahívás és a
jogosulatlan művelet elutasítása igazolható. Jelentsd
a futó folyamatokat és maradt ideiglenes tesztfolyamatokat is. Hiba esetén ne próbálkozz
automatikus ismétléssel, hanem állj meg és írd le a konkrét okot.

Ne kérj, ne tárolj és ne naplózz jelszót, tokent, privát kulcsot vagy más érzékeny adatot.
Az opcionális rendszerfigyelő csak akkor ajánlható, ha a tényleges forrása és URL-je
ellenőrzött; hiányában használd a Windows beépített diagnosztikáját. Az MCP működése
nem függhet ettől az opcionális komponenstől.
```
