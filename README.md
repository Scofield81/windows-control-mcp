# Windows Control MCP

A Windows Control MCP helyi MCP-szerver. Az MCP (Model Context Protocol,
vagyis mesterséges intelligencia és helyi programok közötti szabványos
kapcsolati protokoll) lehetővé teszi, hogy egy AI-ügynök, azaz mesterséges
intelligenciát használó program, ellenőrzött módon használja a Windows gépet.
Lekérdezheti a számítógép állapotát, és a megfelelő felhasználói engedéllyel
végrehajthat jóváhagyott feladatokat.

Azért készült, hogy a rendszerinformációk, ablakok, fájlok, alkalmazások és
ismétlődő munkafolyamatok egy ellenőrizhető, helyi kapcsolaton keresztül legyenek
elérhetők.

Saját gépen futó MCP-szerverként nem kell távoli vezérlőszolgáltatásra bízni a
helyi műveleteket. Az AI-ügynök a lekérdezhető és módosítható műveleteket külön
biztonsági szinteken keresztül használja, a felhasználói jóváhagyás pedig a
kockázatosabb feladatok előtt látható marad.

## Kiknek ajánlott?

- Otthoni felhasználóknak, fejlesztőknek és programozóknak.
- AI-ügynökökkel dolgozóknak és Windows-automatizálást végzőknek.
- Rendszerüzemeltetőknek a tényleges jogosultsági és házirend-korlátokon belül.

## Mire képes?

A program képes lekérdezni a számítógép és a hálózat állapotát, felismerni a
megnyitott programablakokat, valamint azok gombjait, szövegmezőit és egyéb
kezelőelemeit. Képernyőképet készíthet, fájlokat kezelhet, és megfelelő
engedéllyel egér- és billentyűzetműveleteket is végrehajthat. Feltételes,
többlépéses munkafolyamatokat is futtathat.

A programablakok kezelőelemeinek felismeréséhez a Windows UI Automation
technológiáját is használja. A UI (User Interface) a felhasználói felület
angol rövidítése. A kezelőelemek felismerése nem jelenti azt, hogy a program
önállóan megkerüli az alkalmazások vagy a Windows védelmét.

## Fogalmak és rövidítések közérthetően

- **MCP:** szabványos kapcsolati felület, amelyen keresztül egy AI-program
  helyi eszközöket kérdezhet le vagy használhat.
- **AI-ügynök:** mesterséges intelligenciát használó program, amely a felhasználó
  kérését lépésekre bontja és a rendelkezésére álló eszközöket meghívja.
- **UI / UI Automation:** felhasználói felület / Windows-technológia, amely a
  programablakok gombjait, mezőit és egyéb kezelőelemeit azonosítja.
- **OCR:** képen látható szöveg felismerése.
- **API:** programok közötti szabályozott kapcsolódási felület.
- **MCP-kliens:** az a program, például egy AI-alkalmazás, amely az MCP-szerver
  eszközeit meghívja.
- **JSON és JSON-RPC:** gépek közötti adatcsere-formátum és az erre épülő
  kérés-válasz szabályrendszer.
- **stdio:** helyi adatkapcsolat, amely a program bemenetén és kimenetén
  keresztül továbbítja az üzeneteket.
- **Munkafolyamat (workflow):** előre meghatározott, több lépésből álló
  automatizált feladatsor.
- **Védett programindító szolgáltatás (execution broker):** olyan külön
  szolgáltatás, amely csak előre engedélyezett és ellenőrzött programot indít.
- **Ellenőrző digitális lenyomat (hash):** egy fájlból vagy szabályból számított
  érték, amellyel észrevehető, ha a tartalom megváltozott.
- **PowerShell és CMD:** a Windows két parancsértelmezője. A terminálban kiadott
  parancsok nagy hatókörűek lehetnek, ezért külön engedélyhez kötöttek.
- **WinGet:** a Windows csomagkezelője, amely ismert programok frissítését és
  eltávolítását tudja kezelni.
- **CPU:** a számítógép központi processzora.
- **Unicode:** a különböző nyelvek karaktereit egységesen kezelő szövegkódolás.
- **HTTP:** a webes adatátvitel egyik szabványos módja. A projekt ezt nem
  kapcsolja be automatikus távoli vezérlésként.

## Regisztrált MCP-eszközök

A Windows Control MCP 67 eszközt tartalmaz:

- 30 csak olvasási és lekérdezési eszköz (`SAFE`).
- 35 felhasználói engedélyhez kötött eszköz (`NORMAL`).
- 2 kiemelten védett rendszervezérlési eszköz (`ADMIN`).

### Csak olvasás és lekérdezés – 30 eszköz

| Funkció | MCP-eszköz | Mit tud? | Jogosultság |
|---|---|---|---|
| Rendszerinformáció | `system_info` | Windows- és tárhelyadatokat kérdez le. | Csak olvasás és lekérdezés (SAFE) |
| Engedélyállapot | `permission_status` | Aktív és korábbi helyi jóváhagyásokat listáz. | Csak olvasás és lekérdezés (SAFE) |
| Ellenőrzött programprofilok | `execution_broker_profiles` | Megmutatja, mely előre ellenőrzött programok indítását engedélyezheti a rendszer. | Csak olvasás és lekérdezés (SAFE) |
| Védett programindító állapota | `execution_broker_status` | Megmutatja, hogy a védett programindító helyi és szolgáltatásként működő része elérhető-e. | Csak olvasás és lekérdezés (SAFE) |
| Rendszermetrikák | `system_metrics` | Korlátozott CPU-, memória-, üzemidő- és tárhelyadatokat ad. | Csak olvasás és lekérdezés (SAFE) |
| Hálózati adapterek | `network_adapters` | Windows hálózati adaptereket és címeket olvas. | Csak olvasás és lekérdezés (SAFE) |
| Telepített alkalmazások | `installed_applications` | A Windows-alkalmazásbejegyzéseket listázza. | Csak olvasás és lekérdezés (SAFE) |
| Alkalmazás-összesítő | `installed_application_summary` | Az alkalmazások számát és becsült méretét összesíti. | Csak olvasás és lekérdezés (SAFE) |
| Frissítések | `application_updates` | WinGet-frissítéseket telepítés nélkül mutat. | Csak olvasás és lekérdezés (SAFE) |
| Karbantartási előzmények | `application_maintenance_history` | Frissítési és eltávolítási előzményeket olvas. | Csak olvasás és lekérdezés (SAFE) |
| Windows-beállítás olvasása | `registry_read` | Egy Windows-rendszerbeállítási kulcs vagy érték tartalmát olvassa. | Csak olvasás és lekérdezés (SAFE) |
| Kijelzők | `display_list` | A csatlakoztatott kijelzőket listázza. | Csak olvasás és lekérdezés (SAFE) |
| Kurzorpozíció | `cursor_position` | Lekérdezi az egérmutató helyét. | Csak olvasás és lekérdezés (SAFE) |
| Ablaklista | `window_list` | A látható ablakokat listázza. | Csak olvasás és lekérdezés (SAFE) |
| Aktív ablak | `active_window` | Lekérdezi az előtérben lévő ablakot. | Csak olvasás és lekérdezés (SAFE) |
| UI-fa | `ui_tree` | Korlátozott Windows UI Automation-fát olvas. | Csak olvasás és lekérdezés (SAFE) |
| UI-keresés | `ui_find` | Egy pontos UI Automation-elemet keres. | Csak olvasás és lekérdezés (SAFE) |
| UI-tulajdonságok | `ui_properties` | UI Automation-tulajdonságokat és mintákat olvas. | Csak olvasás és lekérdezés (SAFE) |
| UI-szöveg | `ui_get_text` | Egy UI Automation-elem szövegét vagy értékét olvassa. | Csak olvasás és lekérdezés (SAFE) |
| Szöveg felismerése képből | `ocr_image` | Egy helyi képen látható szöveget olvas fel. | Csak olvasás és lekérdezés (SAFE) |
| Kameralista | `camera_list` | A Windows által felismert kamerákat listázza; képet nem készít. | Csak olvasás és lekérdezés (SAFE) |
| Folyamatlista | `process_list` | A futó folyamatokat listázza. | Csak olvasás és lekérdezés (SAFE) |
| Szolgáltatáslista | `service_list` | A Windows-szolgáltatásokat listázza. | Csak olvasás és lekérdezés (SAFE) |
| Könyvtárlista | `file_list` | Egy könyvtár tartalmát listázza. | Csak olvasás és lekérdezés (SAFE) |
| Fájlolvasás | `file_read` | Egy szövegfájl kijelölt részét olvassa. | Csak olvasás és lekérdezés (SAFE) |
| Fájlkeresés | `file_search` | Név alapján keres fájlokat. | Csak olvasás és lekérdezés (SAFE) |
| Fájltulajdonságok | `file_properties` | Fájl vagy könyvtár metaadatait olvassa. | Csak olvasás és lekérdezés (SAFE) |
| Képernyőkép | `screenshot` | Monitorról, asztalról, ablakról vagy régióról képet készít. | Csak olvasás és lekérdezés (SAFE) |
| Képernyő-összehasonlítás | `screen_compare` | Két kép hash-alapú metaadatait hasonlítja össze. | Csak olvasás és lekérdezés (SAFE) |
| Képernyőváltozás várása | `screen_wait_change` | Megvárja egy képernyőrégió változását. | Csak olvasás és lekérdezés (SAFE) |

### Engedélyköteles műveletek – 35 eszköz

| Funkció | MCP-eszköz | Mit tud? | Jogosultság |
|---|---|---|---|
| Egérmozgatás | `mouse_move` | Az egérmutatót a megadott helyre mozgatja. | Engedélyköteles műveletek (NORMAL) |
| Egérkattintás | `mouse_click` | Kattintást küld. | Engedélyköteles műveletek (NORMAL) |
| Egérhúzás | `mouse_drag` | Húzómozdulatot hajt végre. | Engedélyköteles műveletek (NORMAL) |
| Görgetés | `mouse_scroll` | Az egérgörgőt mozgatja. | Engedélyköteles műveletek (NORMAL) |
| Billentyű | `key_press` | Egy virtuális billentyűt lenyom. | Engedélyköteles műveletek (NORMAL) |
| Gyorsbillentyű | `hotkey` | Billentyűkombinációt küld. | Engedélyköteles műveletek (NORMAL) |
| Szövegbevitel | `type_text` | A megadott szöveget beírja az aktív ablakba. | Engedélyköteles műveletek (NORMAL) |
| Vágólap olvasása | `clipboard_read` | A Unicode-vágólap tartalmát olvassa. | Engedélyköteles műveletek (NORMAL) |
| Vágólap írása | `clipboard_write` | Lecseréli a Unicode-vágólap tartalmát. | Engedélyköteles műveletek (NORMAL) |
| Ablakfókusz | `window_focus` | Ablakot fókuszba helyez. | Engedélyköteles műveletek (NORMAL) |
| Ablakállapot | `window_set_state` | Ablakot minimalizál, maximalizál vagy visszaállít. | Engedélyköteles műveletek (NORMAL) |
| Ablak átméretezése | `window_resize` | Ablakot mozgat és átméretez. | Engedélyköteles műveletek (NORMAL) |
| Ablak bezárása | `window_close` | Bezárási kérést küld. | Engedélyköteles műveletek (NORMAL) |
| Kezelőelem aktiválása | `ui_invoke` | Egy pontos ablakelemet, például gombot, aktivál vagy átvált. | Engedélyköteles műveletek (NORMAL) |
| Kezelőelem értékének beállítása | `ui_set_value` | Egy pontos szövegmező vagy más ablakelem értékét állítja. | Engedélyköteles műveletek (NORMAL) |
| Kezelőelem kijelölése | `ui_select` | Egy listából vagy más ablakból kiválaszt egy elemet. | Engedélyköteles műveletek (NORMAL) |
| Kapcsoló átváltása | `ui_toggle` | Egy be-ki kapcsolható ablakelemet átvált. | Engedélyköteles műveletek (NORMAL) |
| Kezelőelem megjelenítése | `ui_scroll` | Egy ablakelemet látható helyre görget. | Engedélyköteles műveletek (NORMAL) |
| Kezelőelem fókusza | `ui_focus` | Egy pontos ablakelemet aktívvá tesz. | Engedélyköteles műveletek (NORMAL) |
| Kamerakép | `camera_snapshot` | Egy képkockát rögzít külön engedélyezett kameráról. | Engedélyköteles műveletek (NORMAL) |
| Alkalmazásindítás | `launch_application` | Helyi alkalmazást indít. | Engedélyköteles műveletek (NORMAL) |
| Fájlírás | `file_write` | UTF-8 szövegfájlt ír. | Engedélyköteles műveletek (NORMAL) |
| Fájlmásolás | `file_copy` | Egy fájlt másol. | Engedélyköteles műveletek (NORMAL) |
| Fájláthelyezés | `file_move` | Egy fájlt áthelyez. | Engedélyköteles műveletek (NORMAL) |
| Fájltörlés | `file_delete` | Egy fájlt töröl jóváhagyás után. | Engedélyköteles műveletek (NORMAL) |
| Korlátozott terminálparancs | `terminal_run` | Korlátozott PowerShell- vagy CMD-parancsot futtat. | Engedélyköteles műveletek (NORMAL) |
| Terminál indítása | `terminal_start` | Memóriában interaktív terminálmunkamenetet indít. | Engedélyköteles műveletek (NORMAL) |
| Terminálbevitel | `terminal_input` | Szöveget küld egy interaktív terminálba. | Engedélyköteles műveletek (NORMAL) |
| Terminál lekérdezése | `terminal_poll` | Korlátozott kimenetet olvas a terminálból. | Engedélyköteles műveletek (NORMAL) |
| Terminál leállítása | `terminal_stop` | Leállít egy interaktív terminálmunkamenetet. | Engedélyköteles műveletek (NORMAL) |
| Munkafolyamat | `workflow_run` | Többlépéses, feltételekhez kötött feladatsort futtat. | Engedélyköteles műveletek (NORMAL) |
| Alkalmazás eltávolítása | `application_uninstall` | Egy pontos WinGet-csomagot távolít el. | Engedélyköteles műveletek (NORMAL) |
| Alkalmazás frissítése | `application_update` | Egy pontos WinGet-csomagot frissít. | Engedélyköteles műveletek (NORMAL) |
| Engedélykérés | `permission_prompt` | Látható felhasználói jóváhagyási ablakot jelenít meg. | Engedélyköteles műveletek (NORMAL) |
| Védett programindítás | `execution_broker_run` | Egy előre ellenőrzött programot indít el, általános parancsértelmező nélkül. | Engedélyköteles műveletek (NORMAL) |

### Kiemelten védett rendszervezérlés – 2 eszköz

| Funkció | MCP-eszköz | Mit tud? | Jogosultság |
|---|---|---|---|
| Folyamat leállítása | `process_stop` | Egy folyamatfát állít le. | Kiemelten védett rendszervezérlés (ADMIN) |
| Szolgáltatásvezérlés | `service_control` | Egy Windows-szolgáltatás indítását vagy leállítását kéri. | Kiemelten védett rendszervezérlés (ADMIN) |

## AI-kliensek, telepítés és integráció

A helyi stdio MCP-kapcsolat Codex CLI/IDE, ChatGPT desktop Codex mód, Claude
Desktop és Google Antigravity helyi konfigurációjához használható. A webes
AI-felületek a helyi szervert közvetlenül nem érik el; köztes távoli továbbító
szolgáltatás és nyilvános HTTP-végpont nincs automatikusan bekapcsolva.

Kézi telepítés: [docs/TELEPITES.md](docs/TELEPITES.md). Felhasználói útmutató:
[docs/FELHASZNALOI_UTMUTATO.md](docs/FELHASZNALOI_UTMUTATO.md). Broker:
[docs/BROKER_TELEPITES_FELHASZNALOKNAK.md](docs/BROKER_TELEPITES_FELHASZNALOKNAK.md).
AI-ügynöki promptok: [docs/TELEPITESI_PROMPTOK.md](docs/TELEPITESI_PROMPTOK.md).

## Jogosultságkezelés

Az egyszeri, munkameneti és tartós engedélyek a művelet hatóköréhez kötődnek.
A normál asztali és böngészővezérlés központi `computer_control` képességcsoporton
keresztül engedélyezhető, de a fájl-, terminál-, kamera-, broker- és ADMIN-
műveletek külön hatókörben maradnak. A Windows UAC és az operációs rendszer
jogosultságai nem kerülhetők meg.

## Tesztelés és ismert korlátok

Az automatikus regressziós csomag 57/57 sikeres tesztet tartalmaz; ez a tesztek
száma, nem az MCP-eszközöké. A kiadási csomagot külön biztonsági ellenőrzés
vizsgálja, hogy ne kerüljenek bele belső fájlok vagy titkok. Folyamatos
képernyő- vagy videórögzítés és távoli HTTP-
vezérlés nincs automatikusan bekapcsolva. A kamera külön engedélyt kér, a
terminál és az alkalmazásindítás alapértelmezett `restricted` házirendben
broker nélkül blokkolt.

## Licenc és kapcsolat

A személyes, nem üzleti használat díjmentes. Üzleti használathoz, egyedi
fejlesztéshez, integrációhoz, karbantartáshoz és támogatáshoz külön írásos
megállapodás szükséges. Részletek: [LICENSE](LICENSE).

Készítő: Vollai Roland · GitHub: [Scofield81](https://github.com/Scofield81) ·
Üzleti kapcsolattartás: `admin@zsebai.hu`
