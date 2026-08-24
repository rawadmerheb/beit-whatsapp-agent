# -*- coding: utf-8 -*-
"""
Property search: Arkan Estate first (priority inventory), then the rest of
the Lebanese market -- every agency, broker, and portal Claude's search can
surface, not a fixed shortlist.

HOW ARKAN'S SITE ACTUALLY WORKS (confirmed 2026-08-24 against the live
site -- this replaces an earlier, untested "best guess" version of this
scraper that was returning zero results)
---------------------------------------------------------------------------
Arkan Estate runs on the WPEstate WordPress plugin/theme. It organizes
listings using two location taxonomies, confirmed via arkanestate.com's own
XML sitemaps (property_area-sitemap.xml and property_city-sitemap.xml) and
a real "Advanced Search" results screenshot the user sent for Jbeil:
  - a fine-grained "area" (neighborhood/town), archive at
    https://arkanestate.com/area/<slug>/ -- e.g. /area/achrafieh/,
    /area/verdun/, /area/blat/ (~100 of these, confirmed by fetching the
    sitemap -- see ARKAN_AREA_SLUGS below)
  - a coarser "city" (caza/district), archive at
    https://arkanestate.com/city/<slug>/ -- only 10 of these (see
    ARKAN_CITY_SLUGS)
Both archive pages list ALL of that location's properties mixed together
(buy + rent + land), newest first, paginated (.../page/2/, etc. -- standard
WordPress pagination). There's no confirmed URL parameter that also filters
by buy vs. rent server-side, so this code fetches the location page(s) and
filters buy/rent/property-type/bedrooms client-side by reading each card's
own text (titles consistently say "for Sale" / "for Rent", rentals are
priced ".../month"). Individual listing pages are at
https://arkanestate.com/properties/<slug>/ -- confirmed via Google-indexed
Arkan pages and the user's own screenshot.

If an area doesn't match a known area/city slug (e.g. it's misspelled, or
somewhere Arkan genuinely doesn't cover -- they have nothing indexed for
Bekaa or South Lebanon at time of writing), this falls back to Arkan's own
sitewide WordPress search (?s=<area>) as a last resort.

If Arkan reorganizes their site later and this stops matching, the fastest
fix: open a location's page on arkanestate.com yourself (e.g.
arkanestate.com/area/achrafieh/), view page source, and check whether
listing links still contain "/properties/" -- if not, that selector in
_parse_arkan_cards() needs updating.

ON "ALL AGENCIES AND BROKERS IN LEBANON" (AND "GOOGLE")
--------------------------------------------------------
There is no single directory or API covering every Lebanese real estate
agency and broker -- there are hundreds, each with their own website (if
any). There's also no free, ongoing "search Google" API for a new project:
Google closed its Custom Search JSON API to new sign-ups, and the paid
proxies that front real Google results (Serper, SerpAPI, etc.) only offer a
one-time free trial before they require a paid plan.

OLX (olx.com.lb, Lebanon's biggest classifieds/property portal, explicitly
requested) gets scraped DIRECTLY -- fetching OLX's own category page
(confirmed URL scheme: olx.com.lb/properties/<category>/<area>/[q-<kw>/])
and reading individual listing links straight off it (confirmed pattern:
href containing "/ad/" and ending "-ID<code>.html"), instead of hoping a
search engine happens to have indexed individual OLX listing pages -- it
generally hasn't; OLX's own indexed pages are almost all category pages,
not individual ads, confirmed by testing.

For everything beyond OLX and Arkan -- the long tail of other agencies,
brokers, and portals -- `search_market()` also runs two DuckDuckGo queries
(no API key, no signup, no cost): one for the other curated portals
(OTHER_KNOWN_PORTALS), one fully open (no site filter) so whichever
agency/broker/portal is indexed for that search shows up regardless of any
curated list. Both run concurrently with the direct OLX scrape.

If you ever want genuine Google-branded results badly enough to accept a
paid API down the line, see README "Optional: real Google search results"
for how to wire in a service like Serper.dev.
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

ARKAN_BASE = "https://arkanestate.com"

# Confirmed by fetching https://arkanestate.com/property_area-sitemap.xml
# on 2026-08-24 -- Arkan's fine-grained neighborhood/town archive pages
# (https://arkanestate.com/area/<slug>/). Prefer these when a user's area
# matches one directly, EXCEPT for the handful of names that are also a
# broader "city" (see ARKAN_CITY_SLUGS, checked first in
# _arkan_location_url) -- someone saying just "Jbeil" almost always means
# the whole district, not only Jbeil town itself.
ARKAN_AREA_SLUGS = {
    "aanaya", "achrafieh", "adma", "adonis", "ain-el-rihaneh", "ain-saadeh",
    "ajaltoun", "alali", "alita", "amchit", "antelias", "aoukar", "azra",
    "baabda", "ballouneh", "baouchriyeh", "batrakieh", "batroun", "beeneya",
    "berbara", "betchay", "blat", "bouar", "bourj-hammoud", "breij",
    "bsalim", "bsharri", "chabtine", "chahtoul", "chamlan", "chiyah",
    "choueifat", "damour", "dbayeh", "debbieh", "dekwaneh", "dohat-aramoun",
    "dora", "edde", "ein-jrein", "faitroun", "fanar", "faqra", "faraya",
    "fayadieh", "fkarkedah", "gharfine", "ghbaleh", "halat", "haret-sakher",
    "hazmieh", "hboub", "horsh-tabet", "hosrayel", "hrajel", "jamhour",
    "jbeil", "jdeideh", "jeita", "jisr-el-basha", "jounieh",
    "jouret-el-ballout", "jouret-el-qattine", "kartaba", "kfaraabida",
    "kfarabida", "koubba", "laklouk", "maarab", "mansourieh",
    "marah-al-hajj", "mastita", "mazraat-yachouh", "mechmech", "monsef",
    "mradieh", "mtaileb", "nabay", "naccache", "qaaqour", "qalamoun",
    "qlayaat", "rachana", "ramlet-al-baida", "raoucheh", "ras-beirut",
    "safra", "sah-el-alma", "sahel-alma", "sarba", "sehaileh", "sehayleh",
    "shayleh", "sin-el-fil", "sodeco", "tabarja", "verdun", "yahchouch",
    "zalka", "zekrit", "zouk-mikael", "zouk-mosbeh",
}

# Confirmed by fetching https://arkanestate.com/property_city-sitemap.xml
# on 2026-08-24 -- Arkan's broader caza/district archive pages
# (https://arkanestate.com/city/<slug>/). Checked BEFORE ARKAN_AREA_SLUGS
# in _arkan_location_url so a bare district name (e.g. "Jbeil", "Batroun")
# resolves to the wider page, matching how people actually say it.
ARKAN_CITY_SLUGS = {
    "aley", "batroun", "beirut", "bsharri", "chouf", "jbeil", "keserwan",
    "matn", "mount-lebanon", "tripoli",
}

# Common names/spellings people actually type that don't match a slug
# above directly. Extend this if real usage turns up more.
ARKAN_AREA_ALIASES = {
    "hamra": "ras-beirut",
    "gemmayzeh": "achrafieh",       # no dedicated slug; nearest served area
    "mar mikhael": "achrafieh",     # no dedicated slug; nearest served area
    "mar mikhayel": "achrafieh",
    "downtown": "beirut",
    "downtown beirut": "beirut",
    "solidere": "beirut",
    "byblos": "jbeil",
    "kesrouan": "keserwan",
    "kaslik": "jounieh",
    "beit mery": "mansourieh",      # no dedicated slug; nearest served area
    "beit meri": "mansourieh",
    "broumana": "mansourieh",       # no dedicated slug; nearest served area
}

# OLX gets scraped directly (see module docstring) rather than routed
# through a search engine.
OLX_BASE = "https://www.olx.com.lb"
# Confirmed listing-detail URL shape, e.g.
# "/en/ad/hot-deal-deluxe-apartment-with-terace-at-byblos-city-ID7A1HB.html"
OLX_LISTING_HREF_RE = re.compile(r"/ad/[^/\s\"'?]+-ID[0-9A-Za-z]+\.html")

# The rest of the curated Lebanese listing portals worth always checking
# explicitly, in addition to the unrestricted search below. Add more here as
# you find ones worth including.
OTHER_KNOWN_PORTALS = [
    "realestate.com.lb",
    "byootna.com",
    "lebanon.dubizzle.com",
    "lebanon.realigro.com",
]

# Per-request timeout for Arkan and the DuckDuckGo queries. Kept modest
# since several of these run concurrently, and a slow/unreachable site
# shouldn't make the whole reply hang.
REQUEST_TIMEOUT = 10
# OLX's own pages have historically been slower/heavier to load than a
# plain WordPress page -- give it a bit more rope before giving up, since
# it's one of the two explicitly-requested sources.
OLX_TIMEOUT = 14


def _slugify(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


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


def _arkan_location_url(area):
    """Best-matching Arkan taxonomy archive URL for a free-text area name,
    or None if nothing matches (caller falls back to a sitewide search)."""
    if not area:
        return None
    slug = _slugify(area)
    if slug in ARKAN_CITY_SLUGS:
        return f"{ARKAN_BASE}/city/{slug}/"
    if slug in ARKAN_AREA_SLUGS:
        return f"{ARKAN_BASE}/area/{slug}/"
    alias = ARKAN_AREA_ALIASES.get(area.strip().lower())
    if alias:
        if alias in ARKAN_CITY_SLUGS:
            return f"{ARKAN_BASE}/city/{alias}/"
        if alias in ARKAN_AREA_SLUGS:
            return f"{ARKAN_BASE}/area/{alias}/"
    return None


def _dedupe_hrefs_prefer_text(anchors):
    """Given a list of <a> tags, some of which may point at the same href
    (e.g. one wrapping a thumbnail image, another wrapping the title text --
    very common in real listing-card markup), return one (href, anchor,
    title) tuple per unique href, preferring whichever anchor actually has
    visible text (or an image alt) as the title source. Anchors are often
    encountered in image-first document order, and without this, the
    image-wrapping anchor (no text) would "claim" the href first and the
    real title-bearing anchor for that same listing would get skipped as a
    duplicate -- silently losing the result entirely."""
    best = {}
    order = []
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        text = a.get_text(strip=True)
        if not text and a.img is not None:
            text = a.img.get("alt", "") or ""
        if href not in best:
            best[href] = [a, text]
            order.append(href)
        elif text and not best[href][1]:
            best[href] = [a, text]
    return [(href, best[href][0], best[href][1]) for href in order]


def _parse_arkan_cards(html, transaction_type, property_type,
                        min_price, max_price, bedrooms, limit):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    anchors = soup.select('a[href*="/properties/"]')
    for href, a, title in _dedupe_hrefs_prefer_text(anchors):
        if not title:
            continue

        card = a.find_parent(["article", "div", "li"]) or a
        text_block = card.get_text(" ", strip=True)

        lower = text_block.lower()
        # Arkan's location archive pages mix buy/rent/land together --
        # filter by the card's own text since there's no confirmed URL
        # parameter for this.
        is_rent = "/month" in lower or "for rent" in lower
        if transaction_type == "rent" and not is_rent:
            continue
        if transaction_type != "rent" and is_rent:
            continue
        if property_type and property_type.lower() not in lower:
            continue

        price = _clean_price(text_block)
        if min_price and price and price < min_price:
            continue
        if max_price and price and price > max_price:
            continue
        if bedrooms:
            # Require an explicit, matching bedroom count when the user
            # asked for a specific number -- a listing with no bedroom
            # info at all (land, an office, a parsing gap) is more likely
            # a false positive than a real match, so exclude it rather
            # than including it just because we can't rule it out.
            bd_match = re.search(r"(\d+)\s*(?:bed|br\b)", lower)
            if not bd_match or int(bd_match.group(1)) != bedrooms:
                continue

        results.append({
            "title": title,
            "url": href if href.startswith("http") else ARKAN_BASE + href,
            "price_usd": price,
            "snippet": text_block[:220],
        })
        if len(results) >= limit:
            break

    return results


def _fetch(url, timeout=REQUEST_TIMEOUT):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException:
        return None


def search_arkan(area, transaction_type="sale", property_type=None,
                  min_price=None, max_price=None, bedrooms=None, limit=10):
    """Scrapes arkanestate.com's own location pages directly (see module
    docstring for the confirmed URL scheme). Tries the matched area/city
    page (plus its page 2, for more to filter from) first, then falls back
    to Arkan's own sitewide search if the area doesn't match a known page.
    Always returns a working "url" -- even with zero scraped results, it's
    a live, correctly-targeted link the user can open themselves.
    """
    location_url = _arkan_location_url(area)
    all_results = []
    seen_urls = set()
    fetched_any = False

    if location_url:
        pages = [location_url, location_url.rstrip("/") + "/page/2/"]
        with ThreadPoolExecutor(max_workers=len(pages)) as pool:
            htmls = list(pool.map(_fetch, pages))
        for html in htmls:
            if not html:
                continue
            fetched_any = True
            for item in _parse_arkan_cards(
                html, transaction_type, property_type,
                min_price, max_price, bedrooms, limit * 2,
            ):
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                all_results.append(item)

    if not all_results:
        fallback_url = f"{ARKAN_BASE}/?s={area}"
        html = _fetch(fallback_url)
        if html:
            fetched_any = True
            for item in _parse_arkan_cards(
                html, transaction_type, property_type,
                min_price, max_price, bedrooms, limit,
            ):
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                all_results.append(item)
        if not all_results:
            location_url = location_url or fallback_url

    output = {
        "source": "Arkan Estate",
        "url": location_url or f"{ARKAN_BASE}/?s={area}",
        "results": all_results[:limit],
    }
    if not fetched_any:
        output["error"] = "Could not reach Arkan Estate's site just now."
    return output


def _olx_search_url(area, transaction_type, property_type, bedrooms):
    """Builds OLX's own category/area/keyword search URL directly --
    confirmed URL scheme (2026-08-24): olx.com.lb/properties/<category>/
    <area-slug>/[q-<keywords>/]. This is always a valid, live, correctly
    filtered search page even before any scraping is attempted."""
    category = (
        "apartments-villas-for-rent" if transaction_type == "rent"
        else "apartments-villas-for-sale"
    )
    area_slug = _slugify(area) or "lebanon"
    keyword_parts = []
    if bedrooms:
        keyword_parts.append(f"{bedrooms}-bedroom")
    if property_type and property_type.lower() not in ("apartment", "apartments", "villa", "villas"):
        keyword_parts.append(property_type)
    q_segment = ""
    if keyword_parts:
        q_segment = "q-" + "-".join(_slugify(p) for p in keyword_parts) + "/"
    return f"{OLX_BASE}/properties/{category}/{area_slug}/{q_segment}"


def _scrape_olx_cards(url, limit):
    """Scrapes OLX's own category page directly. Never raises -- returns
    [] on any failure (timeout, block, markup change) so a slow/blocked
    page degrades gracefully instead of breaking the whole reply. OLX's
    pages are heavier than a plain WordPress page and occasionally slow or
    anti-bot-guarded, so an empty result here doesn't necessarily mean no
    listings exist -- that's exactly why `url` above is always handed back
    to the user regardless."""
    html = _fetch(url, timeout=OLX_TIMEOUT)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_urls = set()

    matching_anchors = [
        a for a in soup.find_all("a", href=True)
        if OLX_LISTING_HREF_RE.search(a["href"])
    ]
    for href, a, title in _dedupe_hrefs_prefer_text(matching_anchors):
        if not title:
            continue
        full_url = href if href.startswith("http") else OLX_BASE + href
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        card = a.find_parent(["li", "article", "div"]) or a
        text_block = card.get_text(" ", strip=True)

        results.append({
            "title": title,
            "url": full_url,
            "price_usd": _clean_price(text_block),
            "snippet": text_block[:220],
        })
        if len(results) >= limit:
            break
    return results


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


def search_market(area, transaction_type="sale", property_type=None,
                   bedrooms=None, limit=8):
    """Search the rest of the Lebanese market beyond Arkan: OLX scraped
    directly, the other known major portals, and an unrestricted search
    with no site filter, so agencies/brokers not on the curated list still
    surface too. All three run concurrently and are merged, deduped by
    domain+path. Always includes "olx_search_url" -- a live, correctly
    filtered OLX link -- even when nothing was scraped."""
    kind = "for sale" if transaction_type != "rent" else "for rent"
    ptype = f" {property_type}" if property_type else ""

    olx_url = _olx_search_url(area, transaction_type, property_type, bedrooms)
    other_site_filter = " OR ".join(f"site:{d}" for d in OTHER_KNOWN_PORTALS)
    other_portals_query = f"{area}{ptype} {kind} Lebanon ({other_site_filter})"
    open_query = f"{area}{ptype} {kind} Lebanon real estate agency broker listing"
    ddg_queries = [other_portals_query, open_query]

    with ThreadPoolExecutor(max_workers=len(ddg_queries) + 1) as pool:
        olx_future = pool.submit(_scrape_olx_cards, olx_url, limit)
        ddg_futures = {pool.submit(_ddg_search, q, limit): q for q in ddg_queries}

        try:
            olx_results = olx_future.result()
        except Exception:  # noqa: BLE001 - a single source failing shouldn't sink the rest
            olx_results = []

        results_by_query = {}
        for future in as_completed(ddg_futures):
            q = ddg_futures[future]
            try:
                results_by_query[q] = future.result()
            except Exception:  # noqa: BLE001
                results_by_query[q] = []

    merged = []
    seen_keys = set()

    # OLX's own direct scrape goes first -- it's the named priority public
    # source, and unlike the DDG-routed queries below, these results come
    # straight off OLX's page itself.
    for item in olx_results:
        parsed = urlparse(item["url"])
        domain = parsed.netloc.lower()
        key = (domain, parsed.path.rstrip("/"))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        item["domain"] = domain
        merged.append(item)

    for query in ddg_queries:
        for item in results_by_query.get(query, []):
            parsed = urlparse(item["url"])
            domain = parsed.netloc.lower()
            if "arkanestate.com" in domain or "olx.com.lb" in domain:
                continue
            # Dedupe by the URL itself (ignoring query string/fragment and a
            # trailing slash) -- the same listing can turn up more than
            # once, and a URL match is a more reliable "same listing"
            # signal than title text, which repeats across many listings.
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
        "olx_search_url": olx_url,
        "queries": ddg_queries,
        "results": merged[:limit],
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
                search_market, area, transaction_type, property_type, bedrooms,
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
