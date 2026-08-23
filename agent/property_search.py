# -*- coding: utf-8 -*-
"""
Property search: Arkan Estate first (priority inventory), then the rest of
the Lebanese market -- every agency, broker, and portal Claude's search can
surface, not a fixed shortlist.

IMPORTANT / HONESTY NOTE
-------------------------
This was built inside a sandboxed session with no outbound access to
arkanestate.com or any other live website, so the Arkan scraper below is
*best-effort*, based on a structural description of the site (repeating
listing cards with a title link to /properties/<slug>/, a price line, and a
beds/baths/size line -- no JSON-LD, no public API). It has NOT been run
against the live site.

The very first time you run this for real, test it with a known area (e.g.
"Achrafieh") and check the `results` list looks right. If Arkan's markup
doesn't match, open properties-for-sale/ in a browser, use "Inspect
Element" on a listing card, and adjust the CSS selectors marked TODO below.
See README "Fixing the Arkan scraper" for a step-by-step.

ON "ALL AGENCIES AND BROKERS IN LEBANON" (AND "GOOGLE")
--------------------------------------------------------
There is no single directory or API covering every Lebanese real estate
agency and broker -- there are hundreds, each with their own website (if
any). There's also no free, ongoing "search Google" API for a new project:
Google closed its Custom Search JSON API to new sign-ups, and the paid
proxies that front real Google results (Serper, SerpAPI, etc.) only offer a
one-time free trial before they require a paid plan.

Instead, `search_market()` below runs THREE queries in parallel and merges
the results:
  1. A DEDICATED query for OLX (olx.com.lb) -- always run on its own, not
     bundled into a combined OR filter, so it can't get crowded out by the
     other portals.
  2. A combined query for the rest of the curated portal list
     (OTHER_KNOWN_PORTALS) -- high-confidence, high-volume sources.
  3. An *unrestricted* open web search (no site filter) for the area/type/
     transaction -- this is what reaches "everywhere else, including
     whatever a Google search would surface": whichever agency, broker, or
     portal has a page indexed for that search shows up here, curated list
     or not.
All three go through DuckDuckGo's HTML endpoint (no API key, no signup, no
cost, no rate-limit surprises for a small pilot). Running them concurrently
(rather than one after another) keeps the total wait roughly equal to the
SLOWEST single request instead of the sum of all of them -- important,
since Arkan's own scrape happens at the same time too.

If you ever want genuine Google-branded results badly enough to accept a
paid API down the line, see README "Optional: real Google search results"
for how to wire in a service like Serper.dev -- the merge/dedupe logic
below doesn't need to change, you'd just add one more query to the list.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

ARKAN_BASE = "https://arkanestate.com"

# OLX gets its own guaranteed query (see module docstring) rather than being
# folded into the combined-portal query below.
OLX_DOMAIN = "olx.com.lb"

# The rest of the curated Lebanese listing portals worth always checking
# explicitly, in addition to the unrestricted search below. Add more here as
# you find ones worth including.
OTHER_KNOWN_PORTALS = [
    "realestate.com.lb",
    "byootna.com",
    "lebanon.dubizzle.com",
    "lebanon.realigro.com",
]

# Per-request timeout. Kept modest because up to 4 of these (Arkan + 3
# market queries) run concurrently, and a slow/unreachable site shouldn't
# make the whole reply hang -- better to come back a little short than to
# leave someone staring at "typing..." for a minute.
REQUEST_TIMEOUT = 10


def _clean_price(text):
    if not text:
        return None
    m = re.search(r"\$?\s?([\d][\d,]{2,})", text)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


def search_arkan(area, transaction_type="sale", property_type=None,
                  min_price=None, max_price=None, bedrooms=None, limit=6):
    """Best-effort scraper for arkanestate.com listing pages."""
    path = "properties-for-rent" if transaction_type == "rent" else "properties-for-sale"
    url = f"{ARKAN_BASE}/{path}/"

    try:
        # WordPress's built-in search param; Arkan's own filter widget may
        # use different param names -- if you find them (view page source
        # on a filtered search), swap this out for the real ones.
        resp = requests.get(url, headers=HEADERS, params={"s": area}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        return {"source": "Arkan Estate", "url": url, "error": str(e), "results": []}

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    seen_urls = set()

    # TODO if this stops matching: inspect a real listing card and update
    # the selector below (currently: any link whose href contains
    # "/properties/", which was the confirmed URL pattern for listing
    # detail pages).
    for a in soup.select('a[href*="/properties/"]'):
        href = a.get("href")
        if not href or href in seen_urls:
            continue
        seen_urls.add(href)

        card = a.find_parent(["article", "div", "li"]) or a
        text_block = card.get_text(" ", strip=True)
        title = a.get_text(strip=True)
        if not title and a.img is not None:
            title = a.img.get("alt", "")
        if not title:
            continue

        price = _clean_price(text_block)
        haystack = (text_block + " " + href).lower()
        if area and area.lower() not in haystack:
            continue
        if min_price and price and price < min_price:
            continue
        if max_price and price and price > max_price:
            continue
        if bedrooms:
            bd_match = re.search(r"(\d+)\s*bed", text_block.lower())
            if bd_match and int(bd_match.group(1)) != bedrooms:
                continue

        results.append({
            "title": title,
            "url": href if href.startswith("http") else ARKAN_BASE + href,
            "price_usd": price,
            "snippet": text_block[:220],
        })
        if len(results) >= limit:
            break

    return {"source": "Arkan Estate", "url": url, "results": results}


def _ddg_search(query, limit):
    """One query against DuckDuckGo's no-JS HTML endpoint. Returns a list of
    {title, url, snippet} dicts, or an empty list on failure (never raises --
    a slow/blocked search engine should degrade gracefully, not break the
    whole reply)."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for res in soup.select(".result")[:limit]:
        link_tag = res.select_one(".result__a")
        snippet_tag = res.select_one(".result__snippet")
        if not link_tag or not link_tag.get("href"):
            continue
        out.append({
            "title": link_tag.get_text(strip=True),
            "url": link_tag.get("href"),
            "snippet": snippet_tag.get_text(strip=True) if snippet_tag else "",
        })
    return out


def search_market(area, transaction_type="sale", property_type=None, limit=8):
    """Search the rest of the Lebanese market beyond Arkan: a guaranteed OLX
    query, the other known major portals, and an unrestricted search with no
    site filter, so agencies/brokers not on the curated list still surface
    too. All three run concurrently and are merged, deduped by
    domain+title."""
    kind = "for sale" if transaction_type != "rent" else "for rent"
    ptype = f" {property_type}" if property_type else ""

    olx_query = f"site:{OLX_DOMAIN} {area}{ptype} {kind} Lebanon"
    other_site_filter = " OR ".join(f"site:{d}" for d in OTHER_KNOWN_PORTALS)
    other_portals_query = f"{area}{ptype} {kind} Lebanon ({other_site_filter})"
    open_query = f"{area}{ptype} {kind} Lebanon real estate agency broker listing"

    queries = [olx_query, other_portals_query, open_query]

    # Run all three DuckDuckGo queries at once instead of one after another --
    # keeps the wait roughly equal to the slowest single query instead of
    # their sum.
    results_by_query = {}
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        future_to_query = {
            pool.submit(_ddg_search, q, limit): q for q in queries
        }
        for future in as_completed(future_to_query):
            q = future_to_query[future]
            try:
                results_by_query[q] = future.result()
            except Exception:  # noqa: BLE001 - a single query failing shouldn't sink the rest
                results_by_query[q] = []

    merged = []
    seen_keys = set()
    for query in queries:
        for item in results_by_query.get(query, []):
            parsed = urlparse(item["url"])
            domain = parsed.netloc.lower()
            if "arkanestate.com" in domain:
                continue
            # Dedupe by the URL itself (ignoring query string/fragment and a
            # trailing slash) -- the same listing can turn up from more than
            # one of the three queries above, and a URL match is a much more
            # reliable "same listing" signal than title text, which can be a
            # generic phrase repeated across many different listings on the
            # same site.
            key = (domain, parsed.path.rstrip("/"))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            item["domain"] = domain
            merged.append(item)
            if len(merged) >= limit:
                break
        if len(merged) >= limit:
            break

    return {
        "source": "Lebanese market (OLX, other portals, and the open web)",
        "queries": queries,
        "results": merged,
    }


def search_properties(area, transaction_type="sale", property_type=None,
                       min_price=None, max_price=None, bedrooms=None,
                       include_public_sources=True):
    """Tool entry point called by the Gemini agent.

    Arkan Estate is always checked first and, when it has matches, they
    should be presented first (that's the priority inventory). By default
    this ALSO searches the wider Lebanese market -- OLX, the other curated
    portals, and the open web -- so coverage is comprehensive, not limited
    to a fixed shortlist. Pass include_public_sources=False to check Arkan
    only.

    Arkan's scrape and the market search run concurrently (not one after
    the other), so asking for both doesn't roughly double the wait.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        arkan_future = pool.submit(
            search_arkan, area, transaction_type, property_type,
            min_price, max_price, bedrooms,
        )
        market_future = None
        if include_public_sources:
            market_future = pool.submit(
                search_market, area, transaction_type, property_type,
            )

        output = {"arkan_estate": arkan_future.result()}
        if market_future is not None:
            output["lebanon_market"] = market_future.result()

    return output


if __name__ == "__main__":
    import json
    import sys
    area_arg = sys.argv[1] if len(sys.argv) > 1 else "Achrafieh"
    print(json.dumps(search_properties(area_arg), indent=2, ensure_ascii=False))
