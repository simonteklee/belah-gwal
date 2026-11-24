#!/usr/bin/env python3
"""Hämtar veckans kampanjer från Matpriskollen och skriver om data.json.

Matpriskollens butikssidor är byggda med Next.js. Erbjudandena ligger som
JSON i sidans så kallade RSC-payload (rader som börjar med self.__next_f.push)
i stället för som text i HTML:en. Vi plockar ut listan "initialDeals" därifrån.
Det är stabilare än att tolka textrader, som går sönder när sidan byter layout.

Körning:   python scraper.py            (vanlig körning)
           python scraper.py --debug    (sparar rå HTML och visar exempel)

Lägg till fler butiker i PAGES: öppna butikens sida på matpriskollen.se och
kopiera adressen. Kör inte oftare än en gång i veckan.
"""
import datetime
import json
import re
import sys
import time
import urllib.request

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Europe/Stockholm")
except Exception:  # saknas tzdata: kör lokal tid
    TZ = None


def local_date(ts=None):
    """Datum i svensk tid. GitHub kör i UTC, annars blir veckan fel dagen före bytet."""
    if ts is None:
        return datetime.datetime.now(TZ).date()
    return datetime.datetime.fromtimestamp(ts, TZ).date()

PAGES = [
    # Willys Mariahallen, Hornsgatan 74
    "https://matpriskollen.se/butiker/willys-mariahallen--537051f9-9354-4758-8d6e-293b1ee06d12",
    # ICA Supermarket Aptiten, Torkel Knutssonsg 16
    "https://matpriskollen.se/butiker/aptiten--27bc426c-0e75-4f77-9713-736dcfedcf45",
    # ICA Nära Banér, Banérgatan
    "https://matpriskollen.se/butiker/ica-nara-baner--d433f430-d5e9-44a5-a7e6-ac81ee1a1f0c",
    # ICA Supermarket Esplanad, Stockholm
    "https://matpriskollen.se/butiker/ica-supermarket-esplanad-stockholm--11efff3a-fae3-4093-b92e-afdd473dbff0",
    # ICA Nära Sergels Torg, Stockholm
    "https://matpriskollen.se/butiker/ica-nara-sergels-torg--befc72b5-8a15-4323-9129-7021dd6cfd9d",
    # Lidl Liljeholmen, Liljeholmstorget 44 (närmast Mariatorget)
    "https://matpriskollen.se/butiker/lidl-liljeholmen--eceea6ed-bf7b-4538-b4c6-5ccd57c6d3e2",
]
UA = "Kampanjkollen/0.2 (privat hobbyprojekt, hämtar en gång i veckan)"
OUT = "data.json"

DEAL_COUNT = re.compile(r"^(\d+) för (\d+(?:,\d+)?)$")
PER_UNIT = re.compile(r"^(\d+(?:,\d+)?)(?:-\d+(?:,\d+)?)?/([A-Za-zåäöÅÄÖ]+)$")

# Butiksnamn som sidan skriver med ortssuffix men appen visar utan.
STORE_ALIAS = {
    "ICA Supermarket Esplanad Stockholm": "ICA Supermarket Esplanad",
    "Lidl Liljeholmen": "Lidl",
}

# Kortare kategorinamn som ibland förekommer i äldre data. Appen har emoji per fullt namn.
CATEGORY_MAP = {
    "Bröd": "Bröd & kakor",
    "Chark": "Chark/Delikatess",
    "Dessert": "Dessert/Mellanmål",
    "Fisk": "Fisk & skaldjur",
    "Frukt": "Frukt & bär",
    "Hem": "Hem & Hushåll",
    "Korv": "Korv & Pålägg",
    "Snacks": "Snacks & Godis",
    "Kropp": "Kroppsvård",
}


def store_name(name):
    name = (name or "").strip()
    return STORE_ALIAS.get(name, name)


def category(name):
    name = (name or "Övrigt").strip()
    return CATEGORY_MAP.get(name, name)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def rsc_payload(html):
    """Sätter ihop alla JSON-bitar som Next.js skickar med sidan."""
    parts = []
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html, re.S):
        try:
            parts.append(json.loads(chunk))
        except ValueError:
            continue
    return "\n".join(parts)


def find_array(payload, key):
    """Hittar "key":[ ... ] i payloaden och tolkar arrayen."""
    i = payload.find('"%s":' % key)
    if i < 0:
        return None
    start = payload.find("[", i)
    if start < 0:
        return None
    depth = 0
    for j in range(start, len(payload)):
        c = payload[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                raw = payload[start:j + 1].replace('"$undefined"', "null")
                try:
                    return json.loads(raw)
                except ValueError:
                    return None
    return None


def price_text(label):
    """'99,00/frp' -> '99,00 kr/frp', '2 för 35,00' -> '2 för 35,00 kr'."""
    if not label:
        return ""
    if "kr" in label:
        return label
    m = PER_UNIT.match(label)
    if m:
        return "%s kr/%s" % (m.group(1), m.group(2))
    return label + " kr"


def price_value(label):
    """Pris per enhet, så att listan kan sorteras på pris."""
    if not label:
        return 0.0
    m = DEAL_COUNT.match(label)
    if m:
        return round(float(m.group(2).replace(",", ".")) / int(m.group(1)), 2)
    m = re.match(r"(\d+(?:,\d+)?)", label)
    return round(float(m.group(1).replace(",", ".")), 2) if m else 0.0


def comprice(label):
    """'198,00/kg' -> (198.0, 'kr/kg'). Tar första siffran i ett intervall."""
    if not label:
        return 0.0, ""
    m = PER_UNIT.match(label)
    if not m:
        return 0.0, ""
    unit = m.group(2).lower()
    return round(float(m.group(1).replace(",", ".")), 2), "kr/" + unit


def week_of(deals):
    """Veckan de flesta erbjudandena börjar gälla."""
    stamps = [d.get("validFrom") or 0 for d in deals]
    newest = max(stamps) if stamps else time.time()
    return local_date(newest).isocalendar()[1]


def to_items(deals, week, today):
    now = int(time.time())
    items = []
    for d in deals:
        if d.get("validTo") and d["validTo"] < now:
            continue  # redan utgången
        price = d.get("priceLabel") or ""
        jm, ju = comprice(d.get("comprice"))
        title = (d.get("title") or "").strip()
        value = price_value(price)
        if not title or not value:
            continue  # utan pris går varan inte att sortera eller jämföra
        item = {
            "s": store_name(d.get("store")),
            "n": title,
            "d": (d.get("subtitle") or d.get("volume") or "").strip(),
            "p": price_text(price),
            "v": value,
            "c": category(d.get("category")),
            "w": week,
            "f": today,
        }
        if jm:
            item["jm"] = jm
            item["ju"] = ju
            item["g"] = title.split(",")[0].strip()
        items.append(item)
    return items


def main():
    debug = "--debug" in sys.argv
    today = local_date().isoformat()
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except Exception:
        old = {"week": 0, "fetched": "", "items": []}

    fresh, refreshed_stores, week = [], set(), None
    for n, url in enumerate(PAGES):
        try:
            html = fetch(url)
        except Exception as e:
            print("FEL: kunde inte hämta %s: %s" % (url, e))
            continue
        if debug:
            open("debug_%d.html" % n, "w", encoding="utf-8").write(html)
        deals = find_array(rsc_payload(html), "initialDeals") or []
        week = week or week_of(deals)
        items = to_items(deals, week, today)
        print("%s\n  -> %d varor (%d rå)" % (url, len(items), len(deals)))
        if debug:
            for it in items[:8]:
                print("    ", it)
        if not items:
            print("  Inga varor hittades. Behåller gamla data för den här butiken. Kör med --debug och titta i debug_*.html.")
            continue
        fresh += items
        refreshed_stores |= {it["s"] for it in items}

    if not fresh:
        print("Ingenting uppdaterades. data.json är oförändrad.")
        sys.exit(1)

    # Behåll varor från butiker som inte kunde hämtas. Appen märker dem "Gammal" efter 8 dagar.
    kept = []
    seen = {(it["s"], it["n"], it.get("d", "")) for it in fresh}
    for it in old.get("items", []):
        it["s"] = store_name(it.get("s"))
        it["c"] = category(it.get("c"))
        if it["s"] in refreshed_stores:
            continue
        key = (it["s"], it["n"], it.get("d", ""))
        if key in seen:
            continue
        seen.add(key)
        kept.append(it)
    data = {"week": week, "fetched": today, "items": fresh + kept}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print("Klart: %d nya och %d behållna varor i %s (vecka %d)." % (len(fresh), len(kept), OUT, week))


if __name__ == "__main__":
    main()
