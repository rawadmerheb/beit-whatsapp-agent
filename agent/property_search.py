# -*- coding: utf-8 -*-
"""
Generic Lebanese real estate search: every listing site/agency this code
can reach gets searched and merged into ONE flat pool of results. No single
site is treated as a priority source, labeled specially, or shown first --
that includes Arkan Estate, which is just one more site being scraped here,
same as OLX or anything else. (See agent/system_prompt.py for the matching
instruction: never name Arkan by name in a reply unless the client asks.)

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
filters buy/rent/property-type/price client-side by reading each card's own
text (titles consistently say "for Sale" / "for Rent", rentals are priced
".../month"). Individual listing pages are at
https://arkanestate.com/properties/<slug>/ -- confirmed via Google-indexed
Arkan pages and the user's own screenshot.

BEDROOM COUNT NEEDS A SECOND LOOK, AND A REAL FALLBACK, NOT JUST "NOTHING"
(confirmed 2026-08-24, updated 2026-08-24 after a second real bug report)
---------------------------------------------------------------------------
The user found real 3-bedroom Jbeil listings on Arkan (among a real batch
of 34) that a teaser-card-only regex was reporting as "not found" -- Arkan's
search-results card doesn't reliably spell out bedroom count in an easy,
consistent way; it's often only stated properly in the full listing's own
page/description. So: a card's own teaser text is used to confirm/reject a
bedroom count for free when it's actually stated there, and a card with NO
bedroom info at all gets its own individual listing page fetched to check
the real description (capped at a modest number of pages, run concurrently,
so this doesn't blow up response time). See _resolve_bedrooms() /
_extract_bedroom_count().

Second, related bug the user then hit: even with that fix, a strict
"exactly N bedrooms or nothing" filter can leave a reply with almost no
individual listings to show -- especially on OLX, whose own on-site keyword
search (baking "3-bedroom" into the URL as a literal search term) misses
any real listing that phrases it differently ("3 BR", "3 Bedrooms", a
separate "Rooms" attribute never rendered as that literal phrase, etc.), so
scraping that keyword-filtered URL directly often came back with nothing to
show even when the area genuinely has matching listings. The reply then
degraded into "couldn't find anything, want to broaden the search?" with
just a bare search-portal link -- which the user correctly called out as
useless: the whole point of this bot is to hand over real listing links
directly instead of making someone go search a portal themselves.

Fixed by no longer keyword-filtering the page that actually gets scraped:
OLX's plain (unfiltered) area/category page is scraped for real candidate
listings, then bedroom count is confirmed exactly the same way as Arkan
(card teaser first, individual listing page as a fallback) via the shared
_resolve_bedrooms() helper. And _resolve_bedrooms() itself no longer
discards non-matching candidates outright -- it now returns
(matched, close_matches): confirmed exact matches, AND a second, real,
still-linkable pool of the next-closest listings (a different confirmed
bedroom count, or one whose count couldn't be confirmed even after
checking its own page). search_properties() tops the results list up with
close_matches (from either source) whenever confirmed exact matches alone
don't fill out a full page, so a reply almost always has real listings to
show. Every item keeps an honest "bedrooms" field whenever a count was
ever confirmed, whether or not it matches what was asked, so a reply can
say "this one's 2BR, closest to the 3BR you wanted" instead of either
hiding the mismatch or showing nothing at all. OLX's own keyword-filtered
search URL is still built and handed back as "olx_search_url" -- it's a
perfectly good link for someone to keep browsing themselves, just not
relied on as the only way individual listings get found.

Third: the user then pointed at a specific live Arkan listing
(a 210 sqm Amchit apartment) as proof of the underlying principle -- its
own page plainly states "3 Bedrooms" / "Bedrooms: 3" in the description,
exactly the kind of detail a compact search-card teaser or a search
engine's result snippet routinely leaves out, and said the same applies
"on all websites." That's exactly right, and it was only half-generalized:
Arkan and OLX candidates both already got their own detail page read when
their teaser said nothing, but results from the "other portals/open web"
DuckDuckGo queries in search_market() did NOT -- they only got an
opportunistic, best-effort check of the search engine's own snippet text,
which is short and usually doesn't mention bedroom count at all. Fixed by
applying the same _resolve_bedrooms() detail-page confirmation to those
DDG-sourced candidates too (capped lower than Arkan/OLX's, via
DDG_BEDROOM_DETAIL_FETCH_CAP, since these are arbitrary third-party sites
rather than two known, previously-profiled ones) -- so a bedroom count now
gets confirmed by reading the actual listing wherever it's hosted, not
just on the two sites this code knows the layout of.

ON "ALL AGENCIES AND BROKERS IN LEBANON" (AND "GOOGLE")
--------------------------------------------------------
There is no single directory or API covering every Lebanese real estate
agency and broker -- there are hundreds, each with their own website (if
any). There's also no free, ongoing "search Google" API for a new project:
Google closed its Custom Search JSON API to new sign-ups, and the paid
proxies that front real Google results (Serper, SerpAPI, etc.) only offer a
one-time free trial before they require a paid plan.

OLX (olx.com.lb, Lebanon's biggest classifieds/property portal) gets
scraped DIRECTLY -- fetching OLX's own category page (confirmed URL
scheme: olx.com.lb/properties/<category>/<area>/) and reading individual
listing links straight off it (confirmed pattern: href containing "/ad/"
and ending "-ID<code>.html"), instead of hoping a search engine happens to
have indexed individual OLX listing pages -- it generally hasn't; OLX's own
indexed pages are almost all category pages, not individual ads, confirmed
by testing. It's fine to name OLX specifically when presenting a result
found there.

For everything beyond OLX and Arkan -- the long tail of other agencies,
brokers, and portals -- `search_market()` also runs two DuckDuckGo queries
(no API key, no signup, no cost): one for the other curated portals
(OTHER_KNOWN_PORTALS), one fully open (no site filter) so whichever
agency/broker/portal is indexed for that search shows up regardless of any
curated list. Both run concurrently with the direct OLX scrape.
OTHER_KNOWN_PORTALS was expanded 2026-08-24 with a batch of specific
Lebanese sites the user pulled from their own Google search (Confidence
Real Estate, JSK Real Estate, Trust Lebanon Agency, Century 21 Lebanon,
3akarat.net, BluSky Properties) -- each gets the same site: filtered
DuckDuckGo query treatment as the original four, and (since that's already
generalized -- see the bedroom-count section above) the same
detail-page bedroom/price confirmation as everything else DDG turns up.

If you ever want genuine Google-branded results badly enough to accept a
paid API down the line, see README "Optional: real Google search results"
for how to wire in a service like Serper.dev.

RANKING: "TOP 10" MEANS BEST-FIRST, NOT JUST FIRST-FOUND (added 2026-08-24)
----------------------------------------------------------------------------
Originally, search_properties() just interleaved Arkan's and the market's
results round-robin -- fine for "don't favor one source," but it meant the
first 10 results were whichever 10 happened to come back first, not
necessarily the best 10. The user asked for the top 10 to actually be
ranked by newly listed, pricing, features, and how well each one matches
the request. _score_result() scores every candidate on exactly those four
things (see its own docstring for the detail), and _rank_and_fill() sorts
the combined pool by that score before taking the top `limit` -- still
completely blind to which site a result came from, so this doesn't
reintroduce source favoritism, it just stops treating "arrived first" as
"best."

A "NO RESULTS" REPLY WITH REAL LISTINGS ON THE ACTUAL SITE (found + fixed
2026-08-25)
---------------------------------------------------------------------------
The user hit a case where a live search ("3 bedrooms in Jbeil") came back
completely empty -- the reply fell back to "couldn't find anything, here's
a bare OLX search link" even though a manual check of the exact same pages
this code scrapes (arkanestate.com/city/jbeil/ and olx.com.lb's Jbeil
for-sale page) showed both were, at that exact moment, fully live and full
of real individual listings with URLs matching this code's own parsing
patterns. That rules out "the sites changed their markup" or "there's
nothing there" -- the pages were reachable and correctly structured; this
code just wasn't getting through to them from wherever it's actually
deployed. The most likely cause is the deployed server's own outbound
requests being blocked/challenged by one or more of these sites as
"automated traffic" (very common for shared-hosting IP ranges, especially
against a classifieds site like OLX) -- and every previous version of this
code made that completely invisible: every failed fetch was silently
swallowed into an empty list with zero trace of why, anywhere.

This didn't get fixed by throwing more logic at the ranking/fallback
layer (there was already plenty of that -- close_matches, best-first
ranking, etc.) -- none of it matters if the underlying fetches never
succeed at all in the first place. Fixed by making failure visible and a
little more resilient instead of just quieter:
  - _fetch() now sends a fuller, more realistic set of browser-like
    headers (Accept, Accept-Language, Accept-Encoding, etc., not just
    User-Agent), and retries once on a connection-level failure (a
    genuine HTTP error status like 403/503 is NOT retried -- that's a
    real rejection, not a network blip, and retrying it identically
    would just waste time).
  - Every failed fetch (Arkan, OLX, both DuckDuckGo queries) is now
    logged via Python's standard `logging` module -- this shows up in
    Render's own log viewer, so if this happens again, the actual reason
    (blocked/403, timed out, DNS failure, connection reset, etc.) is
    right there instead of requiring more guesswork from a black box.
  - search_arkan(), search_market(), and search_properties() all now
    track whether ANYTHING was actually reachable, separately from
    whether anything matched -- surfaced as a top-level
    "search_unavailable" flag in search_properties()'s return value, so
    the agent can tell the person the truth: "couldn't reach listing
    sites right now, try again shortly" instead of implying an area has
    no matching properties when the search never actually completed at
    all. See agent/system_prompt.py for the matching reply guidance.

If Render's logs (once this is deployed) show a real HTTP error like 403
or 429 from OLX or Arkan specifically, that confirms IP-based bot-blocking
rather than a code bug -- at that point the real fix is routing requests
through a paid residential/rotating-IP proxy service (several exist
specifically for this), not another tweak to this file. Worth knowing
going in, so it isn't a surprise.

DDG RESULTS THAT LAND ON A SEARCH/CATEGORY PAGE, NOT AN ACTUAL LISTING
(fixed 2026-08-25)
---------------------------------------------------------------------------
The user was explicit: results need to land directly on the property, not
on a site's own search page -- exactly the point of scraping real listing
links instead of just handing back a portal search URL. Arkan and OLX
already only ever produce direct listing-page URLs (that's what their own
scrapers parse for). But the DuckDuckGo-sourced "other portals/open web"
results are whatever a search engine happened to index for a given site,
which occasionally is that site's own category/search page rather than one
specific listing. _looks_like_listing_page() filters those out (a bare
domain root, or a path containing an obvious non-listing marker like
"/search", "/category/", "/tag/", or a search-style query string) before a
DDG candidate is ever added to the pool -- a cheap, conservative check, not
a guarantee, since there's no universal way to know a random third-party
site's URL conventions for certain, but it catches the obvious cases.
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# A fuller, more realistic browser header set than just User-Agent -- some
# sites' basic bot-checks look at whether a request "looks like" a normal
# browser navigation at all (Accept/Accept-Language/Accept-Encoding
# present, etc.), not only the User-Agent string. This can't do anything
# about a real IP-based block or a JS challenge (no amount of headers fixes
# that -- see the module docstring's 2026-08-25 section), but it's a cheap,
# real improvement against simpler checks.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
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
# you find ones worth including. Expanded 2026-08-24 with a batch the user
# pulled straight from their own Google search for real estate sites in
# Lebanon -- these are indexed, live sites the same way the original four
# were confirmed, just checked via the site: filter below rather than a
# bespoke scraper each (see module docstring). Left out: yelleb.com, which
# in that same search is itself a directory/"top 10 lists" site rather than
# a portal with its own individual listings -- nothing to search inside.
OTHER_KNOWN_PORTALS = [
    "realestate.com.lb",
    "byootna.com",
    "lebanon.dubizzle.com",
    "lebanon.realigro.com",
    "confidencerealestate.com",
    "jskre.com",
    "trustlebanonagency.com",
    "century21.com.lb",
    "3akarat.net",
    "blusky-properties.com",
]

# Per-request timeout for Arkan and the DuckDuckGo queries. Kept modest
# since several of these run concurrently, and a slow/unreachable site
# shouldn't make the whole reply hang.
REQUEST_TIMEOUT = 10
# OLX's own pages have historically been slower/heavier to load than a
# plain WordPress page -- give it a bit more rope before giving up, since
# it's one of the two explicitly-requested sources.
OLX_TIMEOUT = 14
# Cap on how many "no bedroom info on the card" candidates get their own
# individual page fetched to confirm bedroom count -- bounds worst-case
# latency (these run concurrently, but still cost real time). Applied
# separately per source (Arkan, OLX).
BEDROOM_DETAIL_FETCH_CAP = 12
# Same idea, applied to results from the long-tail "other portals/open web"
# DuckDuckGo search -- kept lower than the Arkan/OLX cap since these are
# arbitrary third-party sites (slower/less predictable to fetch) and this
# pass runs on top of, not instead of, Arkan+OLX's own checks.
DDG_BEDROOM_DETAIL_FETCH_CAP = 6


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


def _extract_bedroom_count(text):
    """Looks for a bedroom count in free text, in whichever order it's
    written ("3 Bedrooms", "Bedrooms: 3", "3 BR"). Returns None if no
    bedroom count is mentioned at all -- that's a real, common case on a
    compact search-card teaser, and callers should NOT treat "not found
    here" as "this listing has no matching bedrooms" (see
    _resolve_bedrooms)."""
    if not text:
        return None
    lower = text.lower()
    m = re.search(r"(\d+)\s*(?:bed\s?rooms?|br\b)", lower)
    if m:
        return int(m.group(1))
    m = re.search(r"bed\s?rooms?\s*[:\-]?\s*(\d+)", lower)
    if m:
        return int(m.group(1))
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
                        min_price, max_price, limit):
    """Parses Arkan's location-archive card grid. Does NOT filter by
    bedroom count here -- that's handled afterward in _resolve_bedrooms(),
    since a card's teaser text often doesn't mention bedrooms at all even
    when the listing itself has them (see module docstring)."""
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

        results.append({
            "title": title,
            "url": href if href.startswith("http") else ARKAN_BASE + href,
            "price_usd": price,
            "snippet": text_block[:220],
            "bedrooms_hint": _extract_bedroom_count(text_block),
        })
        if len(results) >= limit:
            break

    return results


def _fetch(url, timeout=REQUEST_TIMEOUT, retries=1):
    """GETs a URL and returns its HTML text, or None on failure.

    Retries once (no backoff -- the failed attempt already spent the full
    timeout waiting) on a connection-level failure (timeout, DNS, connection
    reset), since those are often transient on shared hosting. Does NOT
    retry an HTTP-level error status (403/429/503, etc.) -- that's a real
    server response actively rejecting the request, and an identical retry
    won't change that, just waste time.

    Every failure is logged via the standard `logging` module (so it shows
    up in Render's own log viewer) instead of vanishing silently -- see the
    module docstring's 2026-08-25 section for why this matters: a fetch
    failing here with zero trace of why is exactly what made a real
    production bug (real listings confirmed live on-site, zero results
    coming back from this code) impossible to diagnose from the outside."""
    attempts = retries + 1
    for attempt in range(attempts):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError as e:
            logger.info("Fetch got an HTTP error for %s: %s", url, e)
            return None
        except requests.RequestException as e:
            if attempt + 1 < attempts:
                continue
            logger.warning(
                "Fetch failed for %s after %d attempt(s): %s", url, attempts, e
            )
            return None


def _resolve_bedrooms(candidates, bedrooms, cap=BEDROOM_DETAIL_FETCH_CAP):
    """Confirms/rejects a requested bedroom count across a list of candidate
    listings, returning (matched, close_matches) -- NEITHER list discards a
    real listing outright.

    `matched` are candidates confirmed (from the card's own teaser, or --
    when the teaser says nothing -- from the listing's own detail page,
    capped at `cap` concurrent fetches to bound latency) to have exactly
    `bedrooms` bedrooms.

    `close_matches` is everything else: a different confirmed bedroom
    count, or a bedroom count that's still unknown even after checking the
    detail page (the page didn't load, or genuinely doesn't state it
    anywhere). Every item that ever gets a confirmed count keeps it in a
    "bedrooms" field (regardless of which list it ends up in); an item
    whose count never got confirmed simply has no "bedrooms" key.

    Callers use `close_matches` to top a reply up with real, honestly
    labeled listings when `matched` alone is too thin to be useful -- the
    fix for a real bug where an exact-match-only filter (especially on
    OLX, whose own keyword search misses listings that phrase bedroom
    count differently) could leave a reply with nothing to show at all,
    even though the area clearly has real listings close to what was
    asked."""
    matched = []
    close_matches = []
    ambiguous = []
    for item in candidates:
        hint = item.pop("bedrooms_hint", None)
        if hint is None:
            ambiguous.append(item)
            continue
        item["bedrooms"] = hint
        (matched if hint == bedrooms else close_matches).append(item)

    to_check = ambiguous[:cap]
    close_matches.extend(ambiguous[cap:])
    if to_check:
        with ThreadPoolExecutor(max_workers=min(8, len(to_check))) as pool:
            detail_htmls = list(pool.map(lambda it: _fetch(it["url"]), to_check))
        for item, html in zip(to_check, detail_htmls):
            confirmed = None
            if html:
                page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                confirmed = _extract_bedroom_count(page_text)
                # Free bonus while the page is already open: fill in price
                # too if this candidate didn't have one yet (common for
                # DuckDuckGo-sourced items, whose search snippet rarely
                # states it) -- used for ranking (see _score_result).
                if not item.get("price_usd"):
                    detail_price = _clean_price(page_text)
                    if detail_price:
                        item["price_usd"] = detail_price
            if confirmed is not None:
                item["bedrooms"] = confirmed
            (matched if confirmed == bedrooms else close_matches).append(item)

    return matched, close_matches


def search_arkan(area, transaction_type="sale", property_type=None,
                  min_price=None, max_price=None, bedrooms=None, limit=10):
    """Scrapes arkanestate.com's own location pages directly (see module
    docstring for the confirmed URL scheme). Tries the matched area/city
    page (plus its page 2, for more to filter from) first, then falls back
    to Arkan's own sitewide search if the area doesn't match a known page.
    When a bedroom count is requested, candidates are split into confirmed
    "results" and a real, honestly-labeled "close_matches" fallback pool
    (see _resolve_bedrooms) instead of silently discarding anything that
    isn't an exact match. Always returns a working "url" -- even with zero
    scraped results, it's a live, correctly-targeted link.
    """
    location_url = _arkan_location_url(area)
    candidates = []
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
                min_price, max_price, limit * 3,
            ):
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                candidates.append(item)

    if not candidates:
        fallback_url = f"{ARKAN_BASE}/?s={area}"
        html = _fetch(fallback_url)
        if html:
            fetched_any = True
            for item in _parse_arkan_cards(
                html, transaction_type, property_type,
                min_price, max_price, limit * 3,
            ):
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                candidates.append(item)
        if not candidates:
            location_url = location_url or fallback_url

    close_matches = []
    if bedrooms:
        candidates, close_matches = _resolve_bedrooms(candidates, bedrooms)
    else:
        for item in candidates:
            hint = item.pop("bedrooms_hint", None)
            if hint is not None:
                item["bedrooms"] = hint

    output = {
        "url": location_url or f"{ARKAN_BASE}/?s={area}",
        "results": candidates[:limit],
        "close_matches": close_matches[:limit],
        "reached": fetched_any,
    }
    if not fetched_any:
        output["error"] = "Could not reach Arkan Estate's site just now."
        logger.warning("Arkan: could not reach any page for area=%r", area)
    return output


def _olx_search_url(area, transaction_type, property_type, bedrooms):
    """Builds OLX's own category/area/keyword search URL directly --
    confirmed URL scheme (2026-08-24): olx.com.lb/properties/<category>/
    <area-slug>/[q-<keywords>/]. Handed back as "olx_search_url" so
    someone can keep browsing on OLX itself -- a genuinely useful, always-
    live link, even though (see _olx_category_url below) it's no longer
    the URL actually scraped for individual listings, since OLX's own
    keyword search misses real listings that phrase bedroom count
    differently than the literal keyword."""
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


def _olx_category_url(area, transaction_type):
    """The plain (no keyword filter) OLX category+area page -- this is what
    actually gets scraped for individual listing links. Kept separate from
    _olx_search_url() (which bakes a bedroom-count keyword into the URL)
    because OLX's own free-text search only matches a listing if it
    happens to contain that literal phrase ("3-bedroom") -- many real
    listings phrase it differently ("3 BR", "3 Bedrooms", a separate
    "Rooms" attribute that never renders as that exact phrase, etc.) and
    would be silently missed by a keyword-filtered fetch. Scraping the
    plain, unfiltered page instead and confirming bedroom count the same
    way Arkan's listings are confirmed (via _resolve_bedrooms) surfaces
    real matches a keyword search alone would miss."""
    category = (
        "apartments-villas-for-rent" if transaction_type == "rent"
        else "apartments-villas-for-sale"
    )
    area_slug = _slugify(area) or "lebanon"
    return f"{OLX_BASE}/properties/{category}/{area_slug}/"


def _parse_olx_cards(html, property_type, limit):
    """Parses an OLX category page's card grid. Mirrors
    _parse_arkan_cards(): does NOT filter by bedroom count here -- that's
    handled afterward, the same way, by _resolve_bedrooms()."""
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
        lower = text_block.lower()
        if property_type and property_type.lower() not in lower:
            continue

        results.append({
            "title": title,
            "url": full_url,
            "price_usd": _clean_price(text_block),
            "snippet": text_block[:220],
            "bedrooms_hint": _extract_bedroom_count(text_block),
        })
        if len(results) >= limit:
            break
    return results


def _scrape_olx_cards(url, property_type, limit):
    """Fetches and parses one OLX category page. Never raises -- returns
    ([], False) on any failure (timeout, block, markup change) so a
    slow/blocked page degrades gracefully instead of breaking the whole
    reply. OLX's pages are heavier than a plain WordPress page and
    occasionally slow or anti-bot-guarded, so an empty result here doesn't
    necessarily mean no listings exist -- that's exactly why
    "olx_search_url" is always handed back to the user regardless.

    Returns (results, reached) -- `reached` is True as soon as the page
    itself was actually fetched, even if 0 cards matched the requested
    property_type filter, so callers can tell "OLX has nothing like that"
    apart from "OLX couldn't be reached at all" (see search_market /
    search_properties's "search_unavailable")."""
    html = _fetch(url, timeout=OLX_TIMEOUT)
    if not html:
        logger.warning("OLX: could not reach %s", url)
        return [], False
    return _parse_olx_cards(html, property_type, limit), True


NON_LISTING_PATH_MARKERS = (
    "/search", "/category/", "/categories/", "/tag/", "/tags/", "/page/",
)


def _looks_like_listing_page(url):
    """Conservative check that a URL looks like it lands on one specific
    listing rather than a site's own search/category/directory page. Not a
    guarantee (there's no universal way to know a random third-party site's
    URL conventions for certain) -- just enough to catch the obvious cases
    a search engine occasionally indexes instead of an individual listing
    (a bare homepage, an obvious "/search"/"/category/"/"/tag/" path, or a
    query string that's clearly a search box, e.g. "?s=" or "?q="). Added
    2026-08-25 per explicit feedback: a result needs to land directly on
    the property, not on a site's own search page -- the entire point of
    scraping real listing links instead of handing back a portal search
    URL."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    if not path:
        return False
    if any(marker in path for marker in NON_LISTING_PATH_MARKERS):
        return False
    query = parsed.query.lower()
    if query and ("s=" in query or "search=" in query or "q=" in query):
        return False
    return True


def _ddg_search(query, limit):
    """One query against DuckDuckGo's no-JS HTML endpoint. Returns
    (results, reached) -- `results` is a list of {title, url, snippet}
    dicts (empty if nothing matched or the request failed), and `reached`
    is True only if the request itself actually succeeded (never raises --
    a slow/blocked search engine should degrade gracefully, not break the
    whole reply, but a failure here is now logged rather than silently
    swallowed -- see module docstring's 2026-08-25 section). Bedroom count
    is opportunistically read from the search engine's own title/snippet
    text when it happens to be there for free; when it isn't,
    search_market() fetches the listing's own page to check (see
    DDG_BEDROOM_DETAIL_FETCH_CAP) the same way Arkan/OLX listings are
    confirmed -- a search engine snippet is usually too short/truncated to
    mention bedroom count even when the real listing page states it
    clearly (confirmed against a real Arkan listing the user linked
    directly: its own page plainly says "3 Bedrooms" / "Bedrooms: 3", the
    kind of detail a card teaser or search snippet routinely omits)."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.info("DuckDuckGo search failed for query %r: %s", query, e)
        return [], False

    soup = BeautifulSoup(resp.text, "html.parser")
    out = []
    for res in soup.select(".result")[:limit]:
        link_tag = res.select_one(".result__a")
        snippet_tag = res.select_one(".result__snippet")
        if not link_tag or not link_tag.get("href"):
            continue
        title = link_tag.get_text(strip=True)
        snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
        item = {"title": title, "url": link_tag.get("href"), "snippet": snippet}
        combined_text = f"{title} {snippet}"
        bedrooms_hint = _extract_bedroom_count(combined_text)
        if bedrooms_hint is not None:
            item["bedrooms"] = bedrooms_hint
        price = _clean_price(combined_text)
        if price is not None:
            item["price_usd"] = price
        out.append(item)
    return out, True


def search_market(area, transaction_type="sale", property_type=None,
                   bedrooms=None, limit=10):
    """Search the Lebanese market beyond Arkan: OLX scraped directly, the
    other known major portals, and an unrestricted search with no site
    filter, so agencies/brokers not on the curated list still surface too.
    All three run concurrently and are merged, deduped by domain+path.
    Always includes "olx_search_url" -- a live, correctly filtered OLX
    link -- even when nothing was scraped. When a bedroom count is
    requested, EVERY candidate -- OLX and the other-portals/open-web
    DuckDuckGo results alike -- gets the same real confirmation Arkan's
    listings get: a card/snippet that already states it is resolved for
    free, and anything else has its own listing page fetched and read (see
    _resolve_bedrooms, and DDG_BEDROOM_DETAIL_FETCH_CAP for the smaller cap
    used on these arbitrary third-party sites), split into "results" and a
    "close_matches" fallback pool. This is what "read inside the property"
    means applied to every source, not just Arkan's own site -- a search
    engine snippet or a portal's summary card mentioning a bedroom count is
    the exception, not the rule. (Arkan itself is searched separately by
    search_arkan() and merged in by search_properties() -- this function
    is everything else.)"""
    kind = "for sale" if transaction_type != "rent" else "for rent"
    ptype = f" {property_type}" if property_type else ""

    olx_search_url = _olx_search_url(area, transaction_type, property_type, bedrooms)
    olx_scrape_url = _olx_category_url(area, transaction_type)
    other_site_filter = " OR ".join(f"site:{d}" for d in OTHER_KNOWN_PORTALS)
    other_portals_query = f"{area}{ptype} {kind} Lebanon ({other_site_filter})"
    open_query = f"{area}{ptype} {kind} Lebanon real estate agency broker listing"
    ddg_queries = [other_portals_query, open_query]

    with ThreadPoolExecutor(max_workers=len(ddg_queries) + 1) as pool:
        olx_future = pool.submit(_scrape_olx_cards, olx_scrape_url, property_type, limit * 3)
        ddg_futures = {pool.submit(_ddg_search, q, limit * 2): q for q in ddg_queries}

        try:
            olx_results, olx_reached = olx_future.result()
        except Exception:  # noqa: BLE001 - a single source failing shouldn't sink the rest
            olx_results, olx_reached = [], False

        results_by_query = {}
        reached_by_query = {}
        for future in as_completed(ddg_futures):
            q = ddg_futures[future]
            try:
                results_by_query[q], reached_by_query[q] = future.result()
            except Exception:  # noqa: BLE001
                results_by_query[q], reached_by_query[q] = [], False

    # Flatten + dedupe the DDG-sourced candidates across both queries
    # (excluding Arkan/OLX -- those have their own dedicated scrapers)
    # before any bedroom confirmation, so the same listing's page never
    # gets fetched twice. Also drops anything that looks like a
    # search/category page rather than one specific listing (see
    # _looks_like_listing_page) -- a result must land directly on the
    # property, not on a site's own search page.
    ddg_candidates = []
    seen_ddg_urls = set()
    for query in ddg_queries:
        for item in results_by_query.get(query, []):
            domain = urlparse(item["url"]).netloc.lower()
            if "arkanestate.com" in domain or "olx.com.lb" in domain:
                continue
            if item["url"] in seen_ddg_urls:
                continue
            if not _looks_like_listing_page(item["url"]):
                continue
            seen_ddg_urls.add(item["url"])
            ddg_candidates.append(item)

    any_reached = olx_reached or any(reached_by_query.values())

    olx_close = []
    ddg_close = []
    if bedrooms:
        # A DDG item may already carry an opportunistic "bedrooms" field
        # from its own snippet text (see _ddg_search) -- treat that the
        # same as a card teaser hint so it's resolved for free instead of
        # re-fetched. OLX and DDG are resolved concurrently with each
        # other (each still fetches its own ambiguous candidates'
        # detail pages concurrently internally).
        for item in ddg_candidates:
            item["bedrooms_hint"] = item.pop("bedrooms", None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            olx_future = pool.submit(_resolve_bedrooms, olx_results, bedrooms)
            ddg_future = pool.submit(
                _resolve_bedrooms, ddg_candidates, bedrooms, DDG_BEDROOM_DETAIL_FETCH_CAP,
            )
            olx_results, olx_close = olx_future.result()
            ddg_candidates, ddg_close = ddg_future.result()
    else:
        for item in olx_results:
            hint = item.pop("bedrooms_hint", None)
            if hint is not None:
                item["bedrooms"] = hint

    merged = []
    close_matches = []
    seen_keys = set()

    def _dedupe_key(item):
        parsed = urlparse(item["url"])
        domain = parsed.netloc.lower()
        return domain, parsed.path.rstrip("/")

    def _add(item, bucket):
        key = _dedupe_key(item)
        if key in seen_keys:
            return
        seen_keys.add(key)
        item["domain"] = key[0]
        bucket.append(item)

    for item in olx_results:
        _add(item, merged)

    for item in ddg_candidates:
        if len(merged) >= limit:
            break
        # Dedupe by the URL itself (ignoring query string/fragment and a
        # trailing slash) -- the same listing can turn up more than once,
        # and a URL match is a more reliable "same listing" signal than
        # title text, which repeats across many listings.
        _add(item, merged)

    for item in olx_close:
        _add(item, close_matches)
    for item in ddg_close:
        _add(item, close_matches)

    if not any_reached:
        logger.warning(
            "search_market: could not reach OLX or either DuckDuckGo query "
            "for area=%r", area,
        )

    return {
        "olx_search_url": olx_search_url,
        "queries": ddg_queries,
        "results": merged[:limit],
        "close_matches": close_matches[:limit],
        "reached": any_reached,
    }


# Keywords that make a listing more attractive/informative when they show
# up in its own title/snippet -- a lightweight, transparent stand-in for
# "features" as a ranking input. Deliberately generic (not tied to any one
# site's markup), so it works the same for Arkan, OLX, or any other portal.
FEATURE_KEYWORDS = [
    "garden", "parking", "maid room", "sea view", "mountain view", "view",
    "furnished", "renovated", "new building", "balcony", "terrace", "pool",
    "elevator", "generator", "storage", "duplex", "rooftop", "open view",
]


def _feature_score(item):
    text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
    return sum(1 for kw in FEATURE_KEYWORDS if kw in text)


def _score_result(item, index_in_source, bedrooms, min_price, max_price):
    """Ranks a single result on the 4 things that actually make one listing
    a better answer than another -- never on which site it came from (no
    site, including Arkan, gets a boost just for being itself):

    - matching request: an exact bedroom match outranks a different
      confirmed count, which outranks one that's still unconfirmed (see
      _resolve_bedrooms's "bedrooms" field); price inside the requested
      budget is rewarded, price confirmed to be outside it is penalized.
    - newly listed: each source's own results already come back in that
      source's newest-first order (Arkan/OLX's own archive pages, in
      particular, are natively newest-first -- see module docstring), so a
      candidate's position within its own source's list is used as a
      recency proxy. No site here exposes a reliably parseable exact
      listing date across the board, so this is an honest proxy, not a
      fabricated timestamp.
    - pricing: a listing with a confirmed price outranks one where price
      is simply unknown -- "unknown" isn't "cheap", it's missing data.
    - features: a richer, more informative description (see
      FEATURE_KEYWORDS) edges out a bare-bones one when everything else
      about two listings is equal.
    """
    score = 0.0

    if bedrooms:
        if item.get("bedrooms") == bedrooms:
            score += 100.0  # matching request: exact bedroom match
        elif "bedrooms" in item:
            score += 40.0   # a different, but confirmed, bedroom count
        else:
            score += 20.0   # bedroom count never got confirmed
    else:
        score += 60.0

    score += max(0.0, 20.0 - index_in_source)  # newly listed (proxy)

    price = item.get("price_usd")
    if price:
        score += 10.0  # pricing: known beats unknown
        if min_price and price < min_price:
            score -= 15.0
        if max_price and price > max_price:
            score -= 15.0

    score += min(_feature_score(item), 5)  # features

    return score


def _rank_and_fill(pool, arkan_items, market_items, bedrooms, min_price,
                    max_price, limit, add_fn):
    """Scores a combined Arkan+market candidate pool by _score_result() and
    adds the best ones to `pool` (via add_fn, which also dedupes) until it
    reaches `limit`. Interleaves Arkan/market before scoring (rather than
    concatenating one after the other) purely so that an exact score tie
    breaks evenly between sources instead of one side consistently winning
    ties -- the actual order is driven by score, not by source."""
    interleaved = []
    for i in range(max(len(arkan_items), len(market_items))):
        if i < len(market_items):
            interleaved.append((market_items[i], i))
        if i < len(arkan_items):
            interleaved.append((arkan_items[i], i))

    scored = [
        (_score_result(item, idx, bedrooms, min_price, max_price), item)
        for item, idx in interleaved
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)

    for _score, item in scored:
        if len(pool) >= limit:
            break
        add_fn(item, pool)


def search_properties(area, transaction_type="sale", property_type=None,
                       min_price=None, max_price=None, bedrooms=None,
                       include_public_sources=True, limit=10):
    """Tool entry point called by the Gemini agent. Searches the Lebanese
    market as ONE generic pool: Arkan Estate's site and the wider market
    (OLX, other portals, open web) all run concurrently and get merged into
    a single flat "results" list, ranked best-first by how well each result
    actually matches the request, how recently it was listed, how complete
    its price is, and how many useful features its description mentions
    (see _score_result) -- never by which site found it, so no single site
    (including Arkan) is ever favored in that ranking. Each result item's
    own "url" naturally reveals which site it's on; nothing here names
    Arkan explicitly (see agent/system_prompt.py for how results should be
    described in a reply).

    When a bedroom count is requested and confirmed exact matches alone
    don't fill out a full page of `limit` results, the list is topped up
    with the closest real listings found instead (a different confirmed
    bedroom count, or one that couldn't be confirmed) -- every item keeps
    an honest "bedrooms" field whenever a count is known, so an approximate
    match is never indistinguishable from an exact one. This is what makes
    a reply show real listings directly far more often, instead of falling
    back to "couldn't find anything" whenever an exact match is thin.

    Pass include_public_sources=False to search Arkan's site alone.
    """
    with ThreadPoolExecutor(max_workers=2) as pool:
        arkan_future = pool.submit(
            search_arkan, area, transaction_type, property_type,
            min_price, max_price, bedrooms, limit,
        )
        market_future = None
        if include_public_sources:
            market_future = pool.submit(
                search_market, area, transaction_type, property_type,
                bedrooms, limit,
            )

        arkan_out = arkan_future.result()
        market_out = market_future.result() if market_future is not None else {
            "results": [], "olx_search_url": None, "close_matches": [],
            "reached": False,
        }

    seen_keys = set()

    def _dedupe_key(item):
        parsed = urlparse(item["url"])
        domain = parsed.netloc.lower()
        return domain, parsed.path.rstrip("/")

    def _add(item, bucket):
        key = _dedupe_key(item)
        if key in seen_keys:
            return False
        seen_keys.add(key)
        item.setdefault("domain", key[0])
        bucket.append(item)
        return True

    merged = []
    _rank_and_fill(
        merged, arkan_out.get("results", []), market_out.get("results", []),
        bedrooms, min_price, max_price, limit, _add,
    )

    # A bedroom count was requested but confirmed exact matches alone are
    # thin -- top the list up with the best of the real, honestly-labeled
    # close matches (see search_arkan/search_market/_resolve_bedrooms),
    # ranked the same way, rather than leaving the reply with little or
    # nothing to actually show.
    if bedrooms and len(merged) < limit:
        _rank_and_fill(
            merged, arkan_out.get("close_matches", []),
            market_out.get("close_matches", []),
            bedrooms, min_price, max_price, limit, _add,
        )

    # True only if EVERY source this call actually tried (Arkan, and OLX +
    # both DuckDuckGo queries when include_public_sources is on) failed to
    # even be reached -- a completely different situation from a
    # successful search that genuinely found nothing (see module
    # docstring's 2026-08-25 section, and agent/system_prompt.py for the
    # matching reply guidance). Never confuse the two: this flag being
    # true means the search never actually completed, so there is no
    # basis to say "no matching properties" -- we simply don't know yet.
    search_unavailable = not (
        arkan_out.get("reached", False) or market_out.get("reached", False)
    )

    output = {
        "results": merged,
        "olx_search_url": market_out.get("olx_search_url"),
        "search_unavailable": search_unavailable,
    }
    if search_unavailable:
        logger.warning(
            "search_properties: every source failed for area=%r -- "
            "search_unavailable=True", area,
        )
        output["note"] = (
            "Could not reach any listing sites just now -- this is almost "
            "always a temporary network issue, not proof the area has no "
            "properties. Say so honestly and suggest trying again shortly; "
            "do not say or imply that no matching properties exist."
        )
    return output


if __name__ == "__main__":
    import json
    import sys
    area_arg = sys.argv[1] if len(sys.argv) > 1 else "Achrafieh"
    print(json.dumps(search_properties(area_arg), indent=2, ensure_ascii=False))
