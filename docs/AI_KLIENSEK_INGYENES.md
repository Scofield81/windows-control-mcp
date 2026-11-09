# Ingyenes AI-kliensek és MCP-kompatibilitás

Ez a dokumentum a támogatott helyi MCP-kapcsolati lehetőségeket és azok korlátait
foglalja össze. A jelenlegi Windows MCP
helyi stdio-kapcsolata technikailag ellenőrzött, de minden AI-kliensnél külön
felhasználói integrációs teszt szükséges.

Az AI-kliens az a mesterséges intelligenciát használó alkalmazás, amely a helyi
szerver eszközeit meghívja. A `stdio` helyi adatkapcsolatot jelent: az üzenetek
a program bemenetén és kimenetén keresztül közlekednek. Az MCP (Model Context
Protocol) az AI-alkalmazás és a szerver közötti szabványos kapcsolati felület.
A „helyi” azt jelenti, hogy a szerver ugyanazon a számítógépen fut.

| Környezet | Helyi MCP útvonal | Ingyenes állapot | Jelenlegi státusz |
|---|---|---|---|
| Codex CLI / IDE / ChatGPT desktop Codex mód | helyi stdio | Codex a Free csomagban is elérhető | hivatalosan támogatott útvonal, helyi kézi teszt még külön szükséges |
| ChatGPT webes Free beszélgetés | helyi kapcsolat közvetlenül nem olvasható | egyedi MCP-kapcsolatok a hivatalos oldal szerint Business/Enterprise/Edu webes munkaterülethez kötöttek | nem támogatott helyi telepítési cél |
| Claude Desktop | helyi MCP vagy `.mcpb` bővítménycsomag | a helyi mechanizmus elérhető; a fiók és alkalmazás korlátait ellenőrizni kell | konfiguráció-előkészítő és kézi útmutató készült |
| Claude web / Cowork | távoli MCP-kapcsoló | Free felhasználónak legfeljebb egy távoli egyedi kapcsoló | nem használható csak helyi gépen futó szerverrel |
| Google Antigravity Individual | helyi stdio | hivatalosan $0/hó, alap heti limitekkel | elsődleges Google-alapú cél, konfiguráció-előkészítő készült |
| Gemini webes Custom Apps | nyilvános MCP-URL | jelenleg USA, angol nyelv és személyes Google-fiók szükséges | magyarországi helyi telepítéshez nem megfelelő |

## Források

- [OpenAI – Codex a ChatGPT-csomagokban](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [OpenAI – Codex MCP-konfiguráció](https://developers.openai.com/codex/mcp)
- [OpenAI – custom MCP a ChatGPT webben](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt)
- [Anthropic – helyi MCP Claude Desktopban](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Anthropic – remote custom connector Free csomaggal](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [Google Antigravity – MCP](https://antigravity.google/docs/mcp)
- [Google Antigravity – árak](https://antigravity.google/pricing)
- [Google – Gemini Custom Apps korlátozások](https://support.google.com/gemini/answer/17209137)
- [Google – Gemini Code Assist/CLI kivezetés és Antigravity-migráció](https://developers.google.com/gemini-code-assist/docs/deprecations/code-assist-individuals)

## Fontos korlát

A projekt nyilvános GitHub-adattára elérhető:
https://github.com/Scofield81/windows-control-mcp
A telepítési promptokban kizárólag ezt a tényleges repository-URL-t szabad használni;
nem szabad kitalált release- vagy letöltési URL-t megadni.
