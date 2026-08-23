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

ON "ALL AGENCIES AND BROKERS IN LEBANON"
------------------------------------------
There is no single directory or API covering every Lebanese real estate
agency and broker -- there are hundreds, each with their own website (if
any). Hand-writing a scraper per agency doesn't scale and breaks constantly.
Instead, `search_market()` below runs two searches and merges them:
  1. A curated list of the major Lebanese listing portals (KNOWN_PORTALS) --
     high-confidence, high-volume sources.
  2. An *unrestricted* web search (no site filter) for the area/type/
     transaction -- this is what actually reaches "all agencies and
     brokers": whichever agency or broker has a page indexed for that
     search, curated list or not, shows up here.
Both go through DuckDuckGo's HTML endpoint (no API key required). If you
later get a real search API (Google Custom Search, Bing, SerpAPI), swap it
in here for better ranking/coverage -- the merge/dedupe logic stays the
same.
"""

import re
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

# Major Lebanese listing portals worth always checking explicitly, in
# addition to the unrestricted search below. Add more here as you find
# ones worth including.
KNOWN_PORTALS = [
    "olx.com.lb",
    "realestate.com.lb",
    "byootna.com",
    "lebanon.dubizzle.com",
    "lebanon.realigro.com",
]


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
        resp = requests.get(url, headers=HEADERS, params={"s": area}, timeout=12)
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
    {title, url, snippet} dicts, or an empty list on failure."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=12,
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
    """Search the rest of the Lebanese market beyond Arkan: the known major
    portals PLUS an unrestricted search with no site filter, so agencies
    and brokers not on the curated list still surface. Merged and deduped
    by domain+title."""
    kind = "for sale" if transaction_type != "rent" else "for rent"
    ptype = f" {property_type}" if property_type else ""

    site_filter = " OR ".join(f"site:{d}" for d in KNOWN_PORTALS)
    curated_query = f"{area}{ptype} {kind} Lebanon ({site_filter})"
    open_query = f"{area}{ptype} {kind} Lebanon real estate agency broker listing"

    merged = []
    seen_keys = set()
    for query in (curated_query, open_query):
        for item in _ddg_search(query, limit):
            domain = urlparse(item["url"]).netloc.lower()
            key = (domain, item["title"].lower())
            if key in seen_keys or "arkanestate.com" in domain:
                continue
            seen_keys.add(key)
            item["domain"] = domain
            merged.append(item)
            if len(merged) >= limit:
                break
        if len(merged) >= limit:
            break

    return {
        "source": "Lebanese market (all agencies, brokers & portals)",
        "queries": [curated_query, open_query],
        "results": merged,
    }


def search_properties(area, transaction_type="sale", property_type=None,
                       min_price=None, max_price=None, bedrooms=None,
                       include_public_sources=True):
    """Tool entry point called by the Claude agent.

    Arkan Estate is always checked first and, when it has matches, they
    should be presented first (that's the priority inventory). By default
    this ALSO searches the wider Lebanese market -- every agency, broker,
    and portal reachable via search -- so coverage is comprehensive, not
    limited to a fixed shortlist. Pass include_public_sources=False to
    check Arkan only.
    """
    arkan = search_arkan(area, transaction_type, property_type, min_price,
                         max_price, bedrooms)
    output = {"arkan_estate": arkan}
    if include_public_sources:
        output["lebanon_market"] = search_market(area, transaction_type, property_type)
    return output


if __name__ == "__main__":
    import json
    import sys
    area_arg = sys.argv[1] if len(sys.argv) > 1 else "Achrafieh"
    print(json.dumps(search_properties(area_arg), indent=2, ensure_ascii=False))
