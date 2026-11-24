# በላሕ ጓል (Kampanjkollen)

Mobilvänlig kampanjapp som visar veckans matkampanjer och jämför priser mellan butiker i närheten. Allt är statiskt och gratis att publicera på GitHub Pages.

| Fil | Vad den gör |
|---|---|
| `index.html` | Appen. Läser `data.json` och visar kampanjerna. |
| `data.json` | Kampanjerna. Uppdateras av skrapan. |
| `scraper.py` | Hämtar nya kampanjer från Matpriskollen och skriver om `data.json`. |
| `.github/workflows/update.yml` | Kör `scraper.py` automatiskt varje måndag på GitHub. |

## Så hämtas datan

Matpriskollens butikssidor är byggda med Next.js. Erbjudandena ligger som JSON i sidans RSC-payload (rader som börjar med `self.__next_f.push`), inte som text i HTML:en. `scraper.py` plockar ut listan `initialDeals` därifrån och översätter den till appens format:

| Appens fält | Betydelse | Exempel |
|---|---|---|
| `s` | butik | Willys Mariahallen |
| `n` | vara | Salami |
| `d` | beskrivning/mängd | Välj mellan olika sorter. |
| `p` | pris som text | 2 för 35,00 kr |
| `v` | pris per enhet (för sortering) | 17.5 |
| `c` | kategori | Korv & Pålägg |
| `jm` + `ju` | jämförpris + enhet | 175.0 + kr/kg |
| `g` | gruppnamn för prisjämförelse | Salami |
| `w` / `f` | kampanjvecka / hämtningsdatum | 48 / 2026-11-24 |

Skrapan kräver bara Python 3 – inga extra paket.

## Testa på din egen dator

```
python3 scraper.py --debug
```

Du ska se antal varor per butik och åtta exempel. `--debug` sparar också `debug_0.html` och `debug_1.html` så du kan inspektera rådata.
Stämmer det: kör `python3 scraper.py` utan `--debug`.

## Butiker

Butikerna ligger i listan `PAGES` i `scraper.py`. Öppna butikens sida på matpriskollen.se, kopiera adressen och lägg till den:

- Willys Mariahallen, Hornsgatan 74
- ICA Supermarket Aptiten, Torkel Knutssonsg 16

Har en butik ingen data än visas den som "Ingen data än" i appen. Misslyckas en hämtning behålls butikens gamla varor, så inget försvinner.

## Publicering

Appen ligger på GitHub Pages från `main` och rotmappen:

```
https://simonteklee.github.io/belah-gwal/
```

Öppna adressen i telefonen och välj "Lägg till på hemskärmen" för att få den som app.

- Uppdatera manuellt: fliken **Actions** → *Uppdatera kampanjer* → **Run workflow**.
- Automatiskt: varje måndag 05:00 UTC.
- Workflow-permissions måste vara **Read and write** (Settings → Actions → General), annars kan boten inte committa `data.json`.

## Gamla kampanjer

Varje vara sparas med hämtningsdatum. Är datan äldre än 8 dagar märks varan **Gammal** och hamnar längst ner i listan.

## Att tänka på

- Kontrollera Matpriskollens villkor innan du hämtar data automatiskt, och kör aldrig oftare än en gång i veckan.
- Blir GitHubs servrar blockerade av sidan: kör `python3 scraper.py` lokalt och ladda upp `data.json`.
- Notiser när appen är stängd är inte med än. De kräver en egen server.
