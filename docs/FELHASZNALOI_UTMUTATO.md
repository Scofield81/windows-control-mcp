# Windows Control MCP felhasználói útmutató

## Mire való

Ez a helyi MCP-szerver a Windows számítógép biztonságosan korlátozott
megfigyelésére és vezérlésére szolgál. Az MCP (Model Context Protocol) olyan
szabványos kapcsolati felület, amelyen egy AI-ügynök, vagyis mesterséges
intelligenciát használó program, helyi eszközöket kérdezhet le és használhat.
Az eszközök jogosultsági kategóriáinak jelentése:

| Technikai azonosító | Kezdőbarát megnevezés | Jelentés |
|---|---|---|
| `SAFE` | Csak olvasás és lekérdezés | Adatokat kérdez le és információkat jelenít meg, de nem módosítja a gép állapotát. Az olvasott adat ettől még lehet bizalmas. |
| `NORMAL` | Engedélyköteles műveletek | Egér-, billentyűzet-, fájl- és más módosító műveletek, amelyekhez felhasználói engedély szükséges. |
| `ADMIN` | Rendszergazdai vagy kiemelten védett műveletek | Érzékeny rendszer- és szolgáltatásműveletek, amelyek magasabb szintű ellenőrzéshez kötöttek. |

## Mit tud

- rendszer-, memória-, tárhely- és hálózati állapotot lekérdezni;
- monitorokat, a képernyő nagyítási beállítását (DPI), ablakokat és folyamatokat megmutatni;
- képernyőképet vagy kijelölt képernyőrészletet készíteni;
- egérrel, billentyűzettel és ablakkal dolgozni engedély után;
- helyi fájlokat olvasni és keresni, illetve engedély után módosítani;
- telepített alkalmazásokat, verziókat és becsült vagy mért méreteket összesíteni;
- a Windows csomagkezelőjéből (WinGet) elérhető frissítéseket megmutatni;
- pontos csomagazonosítóval, külön engedéllyel frissíteni vagy eltávolítani;
- összetett, feltételes munkafolyamatokat végrehajtani;
- előre konfigurált, jóváhagyott helyi automatizálásokat meghívni brokerprofillal.

A programablakok gombjainak, szövegmezőinek és más kezelőelemeinek felismeréséhez
a Windows UI Automation technológiáját használja. A UI a felhasználói felület
angol rövidítése. A képen lévő szöveg felismerését OCR-nek nevezik; ez a
képfelismerés szöveges része.

## Fogalmak röviden

- **MCP-kliens:** az AI-alkalmazás, amely a szerver eszközeit meghívja.
- **API:** programok közötti szabályozott kapcsolódási felület.
- **Munkafolyamat:** több egymás utáni, feltételekhez kötött művelet.
- **Broker:** védett programindító szolgáltatás, amely csak előre engedélyezett
  programot indít.
- **Hash és SHA-256:** ellenőrző digitális lenyomat, amellyel észrevehető a
  fájl vagy szabály megváltozása.
- **PowerShell és CMD:** Windows-parancsértelmezők; a belőlük indított művelet
  nagy hatókörű lehet.
- **Named Pipe:** Windows-helyi kommunikációs csatorna két program között.
- **SID:** a Windows felhasználó- vagy szolgáltatásfiókjának egyedi azonosítója.
- **ACL:** hozzáférési szabálylista, amely megmondja, ki férhet hozzá egy fájlhoz
  vagy beállításhoz.

## Engedélykérések

### Mit lát a felhasználó?

A jóváhagyási ablak először egyszerű magyar nyelven mondja el, milyen művelet
indulna, miért kér engedélyt, várhatóan meddig tart, és módosít-e bármit. Ha
elutasítod, a művelet nem indul el. A profilazonosító, az argumentumok és az
időkorlát csak a külön megnyitható technikai részletekben látható.

A jóváhagyó ablak világos vagy sötét Windows-témához igazodik, kontrasztos,
és nem ad hangjelzést. A döntésgombok jelentése egyértelmű: engedélyezés,
elutasítás vagy visszavonás.

Normál böngésző- és asztali vezérléshez egy központi engedélykör használható:
**A számítógép vezérlésének engedélyezése az AI-ügynök számára**. Ez a munkamenet
alatt lefedi a képernyő-, ablak-, egér-, billentyűzet- és böngészővezérlést,
így nem kér új engedélyt minden kattintáshoz. Fájl-, terminál-, kamera-, broker-
és rendszergazdai műveletekre ez az engedély nem terjed ki.

Egy módosító művelet előtt az MCP megmutatja a műveletet, célt, kérő klienst,
kockázatot és az időtartamot. A választható döntések:

| Döntés | Jelentés |
|---|---|
| Egyszer engedélyezem | Egyetlen konkrét műveletre használható |
| Munkamenetre engedélyezem | A munkamenet végéig a megjelölt pontos műveletre vagy korlátozott képességcsoportra |
| Mindig engedélyezem | Pontosan meghatározott műveletre vagy korlátozott képességcsoportra, lejárattal is |
| Egyszer elutasítom | Az aktuális művelet nem fut le |
| Mindig elutasítom | A célzott műveleti kör blokkolva marad |
| Engedély visszavonása | Korábbi engedélyek eltávolítása |

Az engedélyek állapota a `permission_status` lekérdezéssel tekinthető meg:
aktív, munkameneti, elutasított, függőben lévő, lejárt, visszavont és korábbi
események szerint.

## Alkalmazások kezelése

Az alkalmazások listája és frissítéseinek keresése nem telepít automatikusan
semmit. Frissítés vagy eltávolítás előtt meg kell jeleníteni és jóvá kell hagyni
az érintett pontos csomagot. Nem minden program kezelhető WinGetből, ezért a
hiányzó frissítés nem bizonyítja, hogy a program naprakész.

Az alkalmazás mérete lehet megbízhatóan mért vagy becsült érték. Az eltávolítást
ne engedélyezd általános, korlátlan „mindig” szabállyal.

## Fontos biztonsági korlát

Az általános PowerShell/CMD terminál nagy hatókörű eszköz. A biztonságos,
korlátozott alapértelmezett mód (`restricted`) védett programindító nélkül nem
indítja el. A helyi, közvetlen fejlesztői módot (`direct`) úgy kezeld,
mintha a jóváhagyott parancs teljes Windows-hozzáférését engednéd: obfuszkált vagy
közvetett parancsokat a rendszer nem tud teljes bizonyossággal elemezni.

A biztonságos alternatíva a külön, korlátozott Windows-szolgáltatásfiókban
(LocalService) futó, Named Pipe-on elérhető
védett programindító szolgáltatás (execution broker). A szolgáltatás ellenőrzi
a hívó felhasználói SID-jét, a profil SHA-256 digitális lenyomatát és a külön
jóváhagyó segédprogram folyamatazonosságát. A szolgáltatás telepítése és a
profilok ACL-védett kezelése rendszergazdai művelet.

## Gyakori használati sorrend

1. `SAFE` (csak olvasás és lekérdezés) eszközzel kérdezd le az állapotot.
2. Ellenőrizd a célprogramot, fájlt vagy csomagazonosítót.
3. Várd meg és olvasd el az engedélykérést.
4. Csak a szükséges időtartamra engedélyezz.
5. Módosítás után ellenőrizd az eredményt és az előzményt.

## Kiadási állapot

A helyi fejlesztői és tesztkörnyezet 67 eszközt és 57/57 sikeres automatikus
tesztet tartalmaz. Az ACL-védett broker-szolgáltatás és a Named Pipe élő,
izolált próbája sikeresen lefutott. A nyilvános kiadási repository:
https://github.com/Scofield81/windows-control-mcp

Az ingyenes használat kizárólag saját, személyes, nem üzleti célra engedélyezett.
Üzleti használathoz és egyedi szolgáltatásokhoz külön írásos, fizetős megállapodás
szükséges. A teljes feltételeket a kiadott `LICENSE` tartalmazza.

