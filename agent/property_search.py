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
brokers, and portals -- `search_market()` also runs several DuckDuckGo/
Serper queries: OTHER_KNOWN_PORTALS chunked into small site: groups (see
OTHER_PORTALS_CHUNK_SIZE and the module docstring's 2026-08-29 "WHY DO I
ONLY EVER GET JSK FIRST?" section for why it's chunked rather than one
single query), plus one fully open query (no site filter) so whichever
agency/broker/portal is indexed for that search shows up regardless of any
curated list. All run concurrently with each other and with the direct
OLX scrape.
OTHER_KNOWN_PORTALS was expanded 2026-08-24 with a batch of specific
Lebanese sites the user pulled from their own Google search (Confidence
Real Estate, JSK Real Estate, Trust Lebanon Agency, Century 21 Lebanon,
3akarat.net, BluSky Properties) -- each gets the same site: filtered
DuckDuckGo query treatment as the original four, and (since that's already
generalized -- see the bedroom-count section above) the same
detail-page bedroom/price confirmation as everything else DDG turns up.
Expanded again 2026-08-27 after the user flagged that known premium
brokers (Ray White specifically) were missing and results felt thin:
added Ray White International Lebanon (raywhite.com.lb) plus a
researched batch of other well-known, verified-active Lebanese brokers
(Phoenicia Property, RAMCO Real Estate Advisers, AtaBuild, PBM Real
Estate) -- each one's homepage was actually fetched and confirmed to have
real individual listing detail pages (not just a corporate/info page)
before being added, same bar as the original batch.

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

FOLLOW-UP, SAME DAY: A "SUCCESSFUL" FETCH THAT'S ACTUALLY A BOT CHECK
---------------------------------------------------------------------------
After the fix above went live, the very next real test ("3 bedrooms in
Jbeil") still came back with the generic "didn't find anything" reply --
but Render's logs showed ZERO lines about OLX at all, success or failure.
That's the tell: it means _fetch() got an HTTP 200 back from OLX (nothing
"failed" in the eyes of requests.raise_for_status(), so nothing got
logged), yet _parse_olx_cards() still pulled out 0 listings from whatever
that 200 response actually contained. A manual check of the identical page
moments before had shown it full of real listings -- so the most likely
explanation is that OLX served a "prove you're not a robot" interstitial
page instead of the real one, which is itself a normal HTTP 200 response,
not an error status -- completely invisible to the previous round of
logging, which only watched for outright request failures.

Fixed by no longer trusting "got a 200" as "got the real page":
_looks_like_bot_challenge() checks the fetched text itself for common
bot-check phrasing (Cloudflare's challenge page, a generic "prove you're
human" wall, etc.) -- when it matches, that fetch is now treated as NOT
reached (same as a real network failure) instead of quietly producing
"0 listings, nothing to log". And for the still-possible case where a
fetch looks completely legitimate but still yields 0 parsed listings
(a real, if less likely, sign that this code's own parsing selectors no
longer match the site's current markup), the first ~300 characters of
whatever was actually fetched now get logged too -- so the next time this
happens, the logs show, in plain text, exactly what the server sent back,
rather than requiring yet another guess.

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

THE REAL CAUSE, CONFIRMED FOR CERTAIN (2026-08-26): THREE DIFFERENT WALLS,
NONE OF THEM FIXABLE BY BETTER PARSING
---------------------------------------------------------------------------
Everything above (headers, retries, bot-challenge detection, snippet
logging) was aimed at making a failure visible -- and it worked: deployed
logs finally showed, in plain text, exactly what each source was actually
returning. That confirmed three separate, real walls, none of them a bug
in this file:
  - Arkan: every fetch "succeeds" (HTTP 200) but the body is just
    `<script>setTimeout(()=>location.reload(), 5000)</script>` -- a
    JS-only check with no human-readable text at all, so it didn't match
    _looks_like_bot_challenge()'s phrase list either. A plain HTTP client
    can't run that script or see whatever it's waiting for.
  - OLX: the fetched HTML is a legitimate, complete Next.js page shell --
    but the actual listing cards are added afterward by client-side
    JavaScript. There is nothing to parse in the raw HTML because the real
    content doesn't exist yet at fetch time.
  - DuckDuckGo: not a content problem at all -- Render's own outbound
    connection to html.duckduckgo.com times out at the TCP level. DDG
    blocks/throttles connections from cloud-hosting IP ranges outright.

Fixed by adding two optional, paid services that solve each kind of wall
(both fully optional -- everything works exactly as before if neither is
configured; see SCRAPER_API_KEY / SERPER_API_KEY below):
  - ScraperAPI fetches a URL through a real rendering browser (when
    `render=True` -- see _needs_render()) plus a non-datacenter IP, which
    handles both Arkan's JS reload-and-wait check and OLX's client-side
    rendering, since the browser actually waits for the real content.
  - Serper.dev returns real Google search results as plain JSON, replacing
    the DuckDuckGo scrape entirely -- sidesteps the connection block
    completely rather than trying to out-clever it.

FIRST REAL TEST OF THE ABOVE (2026-08-26): TWO SEPARATE MISTAKES, NEITHER
ONE A REASON TO DOUBT THE APPROACH
---------------------------------------------------------------------------
The very first deployed test with both keys set still failed end to end --
but for two very mundane, very fixable reasons, confirmed directly from
Render's logs, not a sign that ScraperAPI/Serper themselves don't work:
  - Serper's own error was "Invalid ... character(s) in header value",
    and the header value in the error was an entire Node.js/axios code
    sample (`const axios = require('axios'); ...`) -- meaning
    SERPER_API_KEY had been set to the "copy as code" snippet shown on
    Serper's dashboard, not the bare API key alone. An easy mistake: many
    API dashboards show both the raw key AND a sample snippet using it,
    right next to each other.
  - Every Arkan fetch timed out and OLX got back an HTTP 499 -- both
    pointing at the same root cause: SCRAPER_API_RENDER_TIMEOUT was set to
    30s, but ScraperAPI's own docs say to allow 70s for a render=true
    request to get a good success rate. 30s was an untested guess; 70s is
    their own documented number. Bumped accordingly, and `premium=true`
    (real residential proxies, not just a rendering browser) added
    alongside render=true specifically for Arkan/OLX -- confirmed to be
    two sites that actively challenge/block plain requests, so worth the
    extra credits on just those two. NOT ultra_premium: that one is
    paid-plan-only per ScraperAPI's docs, so it would silently do nothing
    useful during a free trial.
Gunicorn's own worker timeout (Dockerfile) was bumped from 120s to 200s to
keep real headroom above the new 70s render timeout, since a single chat
reply can involve two render fetches effectively stacking back-to-back
(the initial archive-page fetch, then a detail-page fetch to confirm
bedroom count) -- see BEDROOM_DETAIL_FETCH_CAP, also tightened to 8 so
that second stage can't stack into two sequential batches worst-case.

SECOND REAL TEST (2026-08-27): TWO MORE CONCRETE FINDINGS FROM LOGS,
STILL NOT A REASON TO DOUBT THE APPROACH
---------------------------------------------------------------------------
After the 70s timeout fix above, a fresh test still failed end to end.
Render's logs (searched for "Serper" and "ScraperAPI" right after a live
test) showed two distinct, unrelated problems:
  - Serper: the very first log line still showed SERPER_API_KEY set to
    literal Dockerfile text ("# Docker build so ffmpeg...") -- the same
    kind of copy/paste mix-up as agent/property_search.py getting the
    Dockerfile's content earlier, just landing in an environment variable
    box this time instead of a file. A later test (after presumably
    re-pasting the key) instead got a 403 Forbidden straight back from
    google.serper.dev -- a real response from Serper's own server, not a
    malformed-request error like before, meaning whatever value is
    currently in SERPER_API_KEY still isn't a key Serper accepts. This is
    a configuration problem in Render's Environment tab, not a code bug --
    nothing here can fix a wrong value sitting in that box.
  - ScraperAPI: every single Arkan/OLX fetch got a 500 Internal Server
    Error back from api.scraperapi.com itself (not the target site) while
    render=true and premium=true were both set. ScraperAPI's own status-
    code docs list only one documented cause for a 500: "Extraction
    failed." Their premium-proxy-pools doc page separately says premium
    pools are "available to all paid users" -- suggesting a free trial
    might not qualify as "paid" for that specific feature, which would
    explain every request failing the same way instead of just some.
    premium=true has been removed below (render=true alone stays) to
    isolate this; see _fetch()'s comment for the reasoning and what to
    watch for next.

FOUR MORE REAL ISSUES, ALL CONFIRMED DIRECTLY (2026-08-28)
---------------------------------------------------------------------------
With the ScraperAPI/Serper fix finally live and returning real listings,
the user raised four separate, concrete follow-ups -- each checked against
a real URL before writing any fix, not guessed at:
  - jskre.com: asked for results to land on the actual property page
    (gave a real one: /properties/furnished-duplex-...-l21285). Confirmed
    via a real fetch that this URL IS a proper individual listing page
    with its own og:image -- so the underlying scrape/rank pipeline is
    already right for a site like this; see the og:image work below for
    what was actually missing (a thumbnail, not the link itself).
  - confidencerealestate.com/property-location/jbeil/: confirmed via a
    real fetch to be an essentially blank page -- full <head>/meta tags,
    zero real body content, a normal HTTP 200 the whole way. Neither an
    obvious "/search"/"/category/" path nor a bot-challenge page, so
    nothing in this file caught it before. "/property-location/" is
    WPEstate's own location-taxonomy archive path (the same WordPress
    theme Arkan itself runs on -- see the 2026-08-24 section above) --
    several OTHER_KNOWN_PORTALS entries likely share it. Fixed two ways:
    added to NON_LISTING_PATH_MARKERS as a cheap static filter, AND (the
    real, general fix, since no fixed marker list can catch every site's
    own broken/empty page) _looks_dead_page() now actually reads a
    fetched page's real body text and drops anything suspiciously short
    or containing obvious "not found"/"no longer available" phrasing --
    see _finalize_and_enrich() for where this runs on every result that
    hasn't already been read once for another reason.
  - Facebook/Instagram: asked to land on the actual post, not the page/
    profile. _looks_like_listing_page() now checks those two domains
    specifically -- a bare facebook.com/<name>/ or instagram.com/<name>/
    is rejected the same as a search/category page; only a real post-
    shaped path (facebook.com/.../posts/..., /permalink..., Marketplace
    item URLs; instagram.com/p/<code>/ or /reel/<code>/) passes through.
  - The two real, confirmed-live Arkan listings that never showed up for
    "3 bedrooms in Jbeil" (a 210 sqm Amchit garden apartment, and a Jbeil/
    Byblos development) -- see search_arkan()'s 2026-08-28 comment: a real
    fetch of the city archive page showed 4 total pages, and neither
    listing was among the ~10 on page 1. Fixed by fetching more pages
    (ARKAN_PAGES_PER_SEARCH) in the same single concurrent batch as
    before, not a guarantee for every district but a real, evidence-based
    improvement in coverage.

THUMBNAILS (added 2026-08-28, same round -- the user asked for images
alongside each property, not just a link)
---------------------------------------------------------------------------
Two sources for a thumbnail, used in order of how cheap they are:
  - Arkan/OLX cards already carry their own thumbnail <img> right there on
    the archive page this code already fetches to find them in the first
    place -- _parse_arkan_cards()/_parse_olx_cards() now pull that image
    straight out of the card (preferring a lazy-load data-src/data-lazy-
    src attribute over a possibly-placeholder src), at zero extra cost:
    no additional fetch, no additional latency.
  - Everything else (other portals, open web) gets its image from the
    Open Graph/Twitter Card <meta> tags on the listing's own page --
    confirmed (via a real fetch of jskre.com's listing page) to be how
    virtually any real estate site already exposes a representative photo
    for link-preview purposes, site-markup-agnostic by design. This reuses
    a detail-page fetch that was often already happening anyway (bedroom
    confirmation via _resolve_bedrooms); _finalize_and_enrich() covers the
    remaining candidates (no bedroom count was requested, or a card's own
    teaser already stated it, so no detail fetch had happened yet) with a
    final short, plain (never render=True -- these are never Arkan/OLX)
    pass, which is also where _looks_dead_page() gets applied to catch a
    broken link before it ever reaches the person, pulling in the next-
    best real candidate from a slightly oversized ranked pool
    (RESULT_RESERVOIR_BUFFER) instead of just running a result short.

A DEAD PAGE THAT'S "TOO LONG TO LOOK DEAD" (found + fixed 2026-08-29)
---------------------------------------------------------------------------
The user hit https://www.jskre.com/listings/edde-jbeil -- a real, confirmed
error (a live fetch of it returns HTTP 410 Gone directly), yet it still
reached them as a result. Two things converged:
  - "/listings/<slug>" turns out to be jskre.com's own CATEGORY/archive
    path (confirmed via a real fetch of jskre.com's homepage nav: real
    individual listings are at "/properties/<slug>-l<ID>"; "/listings/"
    is used for pages like "/listings/for-sale", "/listings/for-rent",
    "/listings/for-sale-in-france") -- this one slipped past
    _looks_like_listing_page() because "/listings/" isn't one of the
    denylisted NON_LISTING_PATH_MARKERS. It's deliberately NOT being added
    there, though: this codebase has no reliable way to know whether some
    other curated site's "/listings/" means "category page" (like jskre)
    or "individual listing" (a real, common convention on other sites) --
    guessing wrong would silently drop good results elsewhere. See below
    for the real, general fix instead.
  - The real gap: when this URL is fetched (whether directly, or proxied
    through ScraperAPI when SCRAPER_API_KEY is set), ScraperAPI's own
    documented status-code behavior only explicitly covers 200 and 404 --
    what happens to a 410 specifically when proxied isn't documented, and
    a full WordPress theme's nav/footer/cookie-banner chrome alone can
    easily clear _looks_dead_page()'s old 250-character floor even when
    the actual page has zero real listing content. So the length check
    alone wasn't enough here. Fixed by giving _looks_dead_page() a second,
    positive-evidence check: does this page's text mention an actual price
    ($ or USD/L.L. next to digits) OR a basic property attribute (bedroom,
    bathroom, sqm/m², square feet, etc.) ANYWHERE? A real listing page -- on
    any site this code scrapes -- always states at least one of those;
    chrome-only/error content never does, regardless of its URL shape or
    however its HTTP status came through the proxy. Deliberately does NOT
    treat "for sale"/"for rent" as attribute evidence -- confirmed by
    testing that those exact phrases routinely live in a site's own
    persistent nav menu (a link literally labeled "For Sale"), which would
    appear on every page including a dead one and defeat the check.

"WHY DO I ONLY EVER GET JSK FIRST?" -- A REAL RANKING-CONCENTRATION BUG
(found + fixed 2026-08-29)
---------------------------------------------------------------------------
search_market() used to build exactly ONE Serper/Google query for ALL of
OTHER_KNOWN_PORTALS at once, OR-ing every curated domain's site: filter
together into a single query. That's a real problem: Google (via Serper)
ranks the results of that one query by its own relevance/authority
signals across the whole OR clause, and there's no reason to expect it to
spread hits evenly across a dozen-plus sites of very different SEO
strength -- in practice it consistently surfaced only jskre.com, crowding
out every other curated portal even though several of them have real,
matching listings. Fixed by chunking OTHER_KNOWN_PORTALS into small groups
(OTHER_PORTALS_CHUNK_SIZE) and running one query PER CHUNK, concurrently,
instead of one giant query for the whole list -- every chunk's small OR
clause gives its member sites a real, independent shot at surfacing,
rather than competing against every other curated site at once. Costs a
few more concurrent Serper calls per search (still fast, non-render
requests -- see SCRAPER_API_RENDER_TIMEOUT's docstring for why render
fetches are the only slow ones), not a meaningful latency hit against
Arkan's own up-to-70s render stage running concurrently alongside it.

"CHECK THE LAST PROPERTIES POSTED... LAST 120 DAYS" (added 2026-08-29)
---------------------------------------------------------------------------
The user asked for freshness to actually be checked, not just assumed via
each source's own newest-first list order (see _score_result's existing
"newly listed" proxy). There's no reliable API-level "posted in the last
120 days" filter available here: Serper's own tbs date-range parameter
only documents whole-hour/day/week/month buckets (no arbitrary day count,
and Google's own indexing-freshness isn't the same thing as a property's
actual posting date anyway), so that's not used for a hard cutoff. Instead
_extract_days_old() reads a REAL, explicit "X days/weeks/months ago" (or
"today"/"yesterday") straight from a card's own teaser text, a search
snippet, or the listing's own detail page -- exactly the same "read the
real page, don't guess" principle already used for bedroom count and
price. When a real age is confirmed, _score_result() rewards anything
within the requested 120-day window and mildly deprioritizes (never
excludes) anything confirmed older -- consistent with this file's
established rule (see the bedroom-count sections above) that a real,
matching listing never gets silently dropped just because one signal
about it looks worse; an unconfirmed age (most sites don't expose a date
at all) is treated exactly as it was before this existed, no bonus or
penalty.

EXPANDING PAST "A FEW WEBSITES" (2026-08-29)
---------------------------------------------------------------------------
The user asked for at least 30 credible sites, correctly pointing out that
15 curated portals plus Arkan/OLX was still thin next to how many real
agencies actually operate in Lebanon. OTHER_KNOWN_PORTALS was expanded from
15 to 32 entries -- each one individually verified the same way every prior
addition was (a real fetch of its homepage AND at least one individual
listing page showing a genuine price/description, not just a corporate
site with nothing to scrape). Several strong-looking candidates were
checked and deliberately left OUT after failing that bar: OpenSooq's
Lebanon section is real, but every individual listing page fetched came
back HTTP 403 (bot-blocked) -- nothing to scrape even though the site
itself is legitimate; propertyfinder.com.lb's SSL is currently broken
(hostname mismatch on every attempt); Bayut and Aqarmap have no genuine
Lebanon-country coverage at all (their "Lebanon" hits turned out to be a
Dubai artificial-island development and a Cairo street, respectively); and
none of the major international franchise brands searched (Keller
Williams, Sotheby's International Realty, Engel & Volkers, Coldwell
Banker, Cushman & Wakefield, Savills, Knight Frank, JLL) turned up a real,
working Lebanon-specific website -- only RE/MAX did, via its Tripoli
franchise site. Better to under-promise here than add a domain that turns
out to be dead weight the moment it's queried.

"A LOGO ISN'T A THUMBNAIL" AND "WHY STILL SO FEW RESULTS?" (2026-08-30)
---------------------------------------------------------------------------
Two real bugs the user's next test surfaced, both confirmed live rather
than guessed at:

1. A "JSK BROKERAGE" logo graphic rendered as a listing's thumbnail. Fetched
   two real jskre.com pages to find out why: the homepage's own og:image is
   literally that logo (jskre.com/images/og-image.png), and even a genuine
   individual listing page can carry a generic stand-in image -- one real
   listing's og:image was ".../RES%20SALE.jpg", the CRM's (Propertybase, an
   S3-hosted real estate CRM several agencies here run on) own generic
   "Residential Sale" placeholder for a listing that never had a real photo
   uploaded, not a photo of that unit. A different listing on the same site,
   fetched the same way, had a genuinely listing-specific opaque filename
   instead. og:image was never a safe universal signal -- it can be site
   branding or a shared placeholder as easily as a real photo. Fixed with a
   GENERIC_IMAGE_MARKERS deny-list (_looks_generic_image) that rejects an
   og:image/twitter:image value that looks like branding or a shared
   placeholder rather than a specific listing's own photo, plus a second-
   chance fallback (_extract_body_image) that scans the page's own body
   content (header/nav/footer stripped out first) for a real-looking <img>
   when the meta tags come up empty or all rejected. Both are wrapped in one
   entry point, _extract_thumbnail(), which both call sites now use. A
   missing thumbnail is a much smaller problem than a wrong one, so nothing
   here ever guesses -- it returns None rather than fall back to something
   generic.

2. Results still felt "very limited" despite the 32-site expansion. Two
   compounding causes, found by reading the actual request/response path
   rather than assuming the portal list was still the bottleneck:
   - _serper_search() was building its request body as just {"q": query} --
     it never actually told Serper's API how many results to return. Serper
     silently defaults to ~10 organic results per query when "num" isn't
     sent, so the `[:limit]` slice immediately after looked like it
     controlled result count but never did anything past the first ~10 --
     there was nothing more in the response for it to slice, no matter how
     big a `limit` this code asked for internally. Every one of
     search_market()'s chunked queries was quietly capped at ~10 raw hits
     this way. Fixed by explicitly sending "num" (confirmed via Serper's own
     documented credit rule: up to 10 results costs 1 credit, 11-100 costs a
     flat 2 credits -- not per-result -- so once a query needs more than 10,
     there's no reason to ask for fewer than 100, Serper's own max).
   - search_properties() computed `reservoir_limit` (limit +
     RESULT_RESERVOIR_BUFFER, meant to give _finalize_and_enrich() real
     spare candidates to backfill from when some get dropped as dead pages)
     but then called search_arkan() and search_market() with the bare
     `limit` instead -- and both of those functions truncate their OWN
     "results"/"close_matches" to whatever limit they're handed before ever
     returning. So the reservoir buffer's "spares" never existed in the
     first place: the two sources feeding it were already capped at the
     final count before ranking even began. Fixed by computing
     `reservoir_limit` before calling either function and passing that
     instead of the bare `limit`.
   Together: previously, a search's real candidate ceiling was roughly
   "~10 per source, some of which get dropped as dead links" -- now each
   source can return up to `limit + RESULT_RESERVOIR_BUFFER` real
   candidates, and Serper-backed queries actually retrieve up to 100
   results instead of a silent ~10. This roughly doubles the Serper credit
   cost per search (queries that fell in the 1-credit bracket now use the
   2-credit bracket) -- still a few thousandths of a cent per search on
   Serper's published per-1,000-query pricing, and well within the 2,500
   free queries the account starts with.

A REAL SALE LISTING WRONGLY READ AS A RENTAL (found + fixed 2026-08-30)
---------------------------------------------------------------------------
The user asked why a real, live Arkan listing
(arkanestate.com/properties/luxury-apartment-for-sale-in-jamhour/ --
confirmed via a direct fetch to be a genuine $670,000 SALE, 5 bed/6 bath)
never showed up searching Jamhour. Fetched arkanestate.com/area/jamhour/
directly to see why: Jamhour has exactly ONE real listing, and Arkan
renders it as a special "Featured" hero widget rather than a normal grid
card -- with no dedicated <article>/<li> wrapper of its own, sitting in
the same broad layout container as an unrelated "Latest Listings" sidebar
that includes a genuine rental ("Apartment for Rent in New Shayleh",
"$650/month"). _parse_arkan_cards()'s old card-boundary logic (a plain
find_parent(["article", "div", "li"])) matched whatever <div> was closest
to the listing's own anchor -- which turned out to be that same wide
wrapper enclosing the sidebar too. That sidebar's "for rent"/"$650/month"
text leaked straight into this listing's own rent-vs-sale detection text,
so a genuine sale listing got flagged is_rent=True and silently excluded
from every "buy" search for Jamhour -- not a bug in the rent/sale check
itself, but the text it was reading was scoped far too broadly. This
wasn't caught earlier because every previously-tested area (Jbeil,
Achrafieh, Amchit, etc.) has enough real listings to fill a normal grid,
so the single-listing "Featured hero, no sidebar contamination risk
tested" case never came up before.

Fixed with _card_and_detection_text() (used by both _parse_arkan_cards()
and _parse_olx_cards()): tries a tight <article>/<li> ancestor FIRST --
a far more reliable "this is exactly one card" boundary than a bare
<div>, which can just as easily be a wide multi-column wrapper holding
several unrelated things side by side -- and only falls back to a div
if neither exists. Either way, the text actually used to decide rent-vs-
sale and extract price/bedrooms/age is capped at CARD_DETECTION_TEXT_CAP
(600 characters): a genuine single card's own teaser is always
comfortably under that, so a match far longer than that is itself a
sign the boundary was too broad, and text past the cap isn't trusted.
Verified against a reconstruction of the actual Jamhour page structure
(a shared wide div holding both the featured listing and the
contaminating sidebar rental) plus a regression check that normal,
properly-wrapped grid cards (the common case on every other page this
code has been tested against) still parse exactly as before.

"STILL VERY LIMITED, NEED AT LEAST 10, LOOK BACK 6 MONTHS" (2026-08-31)
---------------------------------------------------------------------------
Two changes made per the user's direct request, plus one real bug found
while looking into why a thin area's Arkan results stayed thin even after
every earlier fix this file already has:

1. A real, confirmed bug in search_arkan()'s own fallback logic: after
   fetching the area/city's own dedicated archive page(s), this function
   was only willing to ALSO try Arkan's sitewide search (?s=<area>) as a
   backup when the dedicated page(s) came back with ZERO listings
   ("if not candidates:"). Re-fetched arkanestate.com/area/jamhour/ live
   to confirm the exact scenario: that page renders exactly ONE real
   listing (still true, same as the previous section), so `candidates`
   already had 1 item in it and the sitewide-search backup was being
   skipped entirely -- even though Arkan's own broader search might
   genuinely have more to offer for that name. A location page that's
   merely thin (a handful of results, not enough to fill a reply) was
   being treated exactly like a location page that came back completely
   empty. Confirmed via a live fetch that this isn't an ARKAN_PAGES_PER_
   SEARCH problem instead: arkanestate.com/city/beirut/ has only 3 real
   pagination pages total (page 4 is a genuine 404) and
   arkanestate.com/city/mount-lebanon/ has only 1 page, period -- so the
   existing page count (4) already covers every city page in full; the
   real gap was purely the fallback's trigger condition. Fixed by
   changing the trigger from "the dedicated page found nothing at all" to
   "the dedicated page didn't find enough" (len(candidates) < limit) --
   still fully additive (existing seen_urls dedup prevents duplicates
   between the two passes) and still skipped once enough real candidates
   already exist, so this never runs pointless extra fetches when a page
   is already well-stocked (e.g. Beirut, Jbeil).

2. RECENCY_WINDOW_DAYS raised from 120 to 180 (6 months) per the user's
   explicit ask to widen how far back this code looks before treating a
   listing as anything other than fully fresh. To be precise about what
   this constant actually controls (it's the same rule as the 2026-08-29
   "last 120 days" section above, just with a wider window now): it is
   purely a _score_result() ranking nudge, never an exclusion filter --
   this file has never dropped a real listing just for being old, and
   still doesn't. Raising it to 180 means a real listing confirmed posted
   between 4 and 6 months ago now gets the same small freshness bonus a
   listing posted last week gets, instead of the small penalty it used to
   get in that 120-180 day range -- so more real, slightly-older listings
   can now rank into the top results instead of being nudged down.

One honest limit worth stating plainly: neither change manufactures
listings that don't exist. "At least 10 options" is now genuinely more
achievable wherever 10 real matching listings exist somewhere across
Arkan/OLX/the curated portals/the open web -- the Jamhour-style fallback
fix in particular closes a real gap that was silently capping some areas
below what Arkan itself actually has to offer. But an area that
genuinely, verifiably has only 2 or 3 real listings anywhere right now
will still only ever show 2 or 3 -- this code has never fabricated a
result and still won't.

"ONLY ONE SITE SHOWS UP, AND ARKAN/CONFIDENCE ARE MISSING" (2026-09-01)
---------------------------------------------------------------------------
The user reported the previous round's fixes weren't enough: results were
still dominated by a single site (this time a well-indexed newer app,
DoorEast -- confirmed real via a live search, not this file's own scraper)
with nothing from Arkan or Confidence Real Estate even though the user had
personally checked both and found real matching listings there. Two
separate, confirmed root causes -- neither guessed at:

1. A real, confirmed bug: confidencerealestate.com is entirely
   client-side-JS-rendered, the same wall OLX had (see the 2026-08-26
   section above), just never diagnosed for this specific site until now.
   Confirmed by directly fetching THREE different pages on it -- the
   homepage, a /property-location/batroun/ archive, AND a real individual
   listing page (confidencerealestate.com/property/an-ideal-120-sqm-
   apartment-with-a-360-sqm-roof-for-sale/, found via a live Google
   search) -- every single one came back as nothing but a bare <head>
   full of meta tags, zero real body content. That means every time this
   code ever found a real Confidence listing (via a Serper/DuckDuckGo
   site: query -- Confidence isn't scraped directly the way Arkan is),
   the very next step (_finalize_and_enrich's dead-page check, or
   _resolve_bedrooms's detail-page confirmation) fetched that candidate's
   own page PLAIN (no rendering), saw the same blank shell, and dropped
   it as "dead" -- discarding a real, live listing every single time,
   with zero exceptions. Fixed by adding confidencerealestate.com to
   RENDER_REQUIRED_DOMAINS, and splitting that set into two: Arkan/OLX
   (DIRECTLY_SCRAPED_DOMAINS -- their own dedicated scraper already
   fetched this exact page fresh, with render=True, moments earlier in
   the same request, so _finalize_and_enrich can safely skip re-checking
   them) versus everything else needing render (Confidence, currently) --
   which DOES still need an active check here, just with render=True
   instead of being skipped or wrongly plain-fetched. See
   DIRECTLY_SCRAPED_DOMAINS and _finalize_and_enrich()'s own docstring.

2. A real, confirmed design gap: nothing anywhere in this file capped how
   many of the FINAL results could come from one single domain. Confirmed
   by reading the merge/ranking code directly -- _rank_and_fill() scored
   every candidate purely on match quality/freshness/price/features (see
   _score_result), with no notion of "which site is this" at all, so
   whichever single site happened to be best-indexed by Google for a
   given area/query (JSK before, DoorEast this time -- there is nothing
   special about either site itself; it's purely a function of that
   site's own SEO strength for that particular query) could end up
   filling most or all of the final list on its own, silently crowding
   out real candidates from Arkan, Confidence, or any other source even
   when they genuinely had matching listings too. Fixed with
   MAX_RESULTS_PER_DOMAIN: a cap of 3, applied identically to every
   domain including Arkan itself (no site is ever exempted from it,
   consistent with this file's existing "no site is ever favored" rule),
   enforced in _rank_and_fill()'s per-domain-aware add_fn calls. Paired
   with a deliberate "overflow" fallback pass (see _rank_and_fill()'s own
   docstring) so the cap only ever enforces diversity that's actually
   available -- it never trims the final list down below what real
   candidates exist just to make room for sources that have nothing to
   offer for that specific query.

Also, per the user's explicit "10-15 properties" ask: search_properties()'s
own default `limit` was raised from 10 to 12 (landed in the middle of that
range, not the top of it, to keep the extra concurrent detail-page/
dead-page checks this now routes through _finalize_and_enrich -- more real
candidates now survive to that stage -- from stacking too much additional
latency on top of the render-heavy Arkan/OLX/Confidence fetches already
happening in the same request). The two matching "show up to 10" lines in
agent/system_prompt.py, and the tool description string in
agent/claude_client.py, were updated to say 12 too -- otherwise the model
would keep truncating its own reply to 10 regardless of how many the tool
actually returns.

Same honest limit as every round before this one: these fixes make real
site diversity and a fuller count achievable wherever multiple real
sources genuinely have matching listings for a given query. They do not
fabricate a 4th, 5th, or 6th source out of nothing when a specific area
truly only has real listings on one or two sites right now.

EVERY SINGLE SEARCH QUERY FAILED WITH AN IDENTICAL 400 (2026-09-02)
---------------------------------------------------------------------------
The user tested a live search and, this time, pulled the actual Render
logs rather than just describing the symptom -- and every single Serper
query in that test failed with the identical error: "400 Client Error:
Bad Request for url: https://google.serper.dev/search". Not some queries,
not one flaky domain -- every chunk of OTHER_KNOWN_PORTALS, and (almost
certainly, though cut off in the visible log) the final open query too.
That single fact explains a lot at once: if the entire "search everything
beyond OLX/Arkan" path is failing outright, no curated portal reachable
only through it (Chidiac Real Estate included, which the user separately
confirmed has real live Jbeil-area listings via its own site) could ever
appear, no matter how correct the ranking/dedup/domain-cap logic is.

Two real possibilities were checked before writing any fix, not guessed
at, given this project's history of exactly one of them (a wrong value
pasted into Render's SERPER_API_KEY box) happening twice already (see the
2026-08-26 and 2026-08-27 sections above):
  - Wrong/misconfigured API key: RULED OUT with real evidence this time --
    the user checked Render's Environment tab and Serper's own dashboard
    side by side, and the key matches exactly
    (c1de70bcdc18583989c781550607bf2425ea4e87 in both places). Not a
    repeat of the earlier mistake.
  - A real logic bug in how many results this code asks Serper for: found
    by rereading _serper_search() against its own documented intent. The
    2026-08-30 section directly above this one says, in its own words,
    "once a query needs more than 10, there's no reason to ask for fewer
    than 100 (Serper's own max)" -- but the code that shipped was
    `payload["num"] = min(limit, 100)`, which returns the SMALLER of the
    two numbers, not a flat 100. For a typical call in this app (limit=44,
    from search_market()'s `limit * 2` sizing), that evaluates to 44 --
    an arbitrary, non-round number sent on every single query, which is
    new behavior introduced by that exact 2026-08-30 change and which
    lines up with when this "every query fails" symptom would first have
    become possible. This is a real, provable mismatch between the code
    and its own stated intent, independent of whatever Serper's exact
    validation rules turn out to be.

Fixed three ways, not just one guessed value, precisely because the first
part above couldn't be confirmed with total certainty without a live test
this sandbox has no way to run against Serper's real endpoint:
  1. The actual bug: `num` is now set to a flat 100 (matching the
     documented intent) whenever more than 10 results are needed, instead
     of `min(limit, 100)`.
  2. _serper_request() (split out of _serper_search() so both the normal
     call and a retry can share it) now captures and logs Serper's own
     response BODY text on an HTTP error, not just the generic exception
     message. Before this, a failure only ever logged "400 Client Error:
     Bad Request for url: ..." -- never Serper's own explanation of WHY,
     which is exactly where an API states its own reason for rejecting a
     request. That gap is what made this incident hard to pin down beyond
     "something about the request is invalid" in the first place.
  3. _serper_search() now retries once, automatically, with no "num"
     field at all (Serper's own implicit default of ~10 results) whenever
     a request that asked for more than that fails. This means that even
     if the `num=100` fix above turns out not to be the whole story, one
     query can never again silently return zero results the way every
     single one did on 2026-09-02 -- worst case, it falls back to
     Serper's original, always-worked default instead of failing outright.

Same honest caveat as always: this makes the "everything beyond OLX/Arkan"
search resilient to a bad `num` value again, and fixes the specific logic
bug that didn't match its own documented intent. It can't guarantee
Serper's API has no OTHER, still-undiscovered rejection reason -- that's
exactly why point 2 above exists: so the next failure, if there is one,
shows its real cause in the logs instead of requiring another guess.

WIDER FRESHNESS WINDOW, AND A REAL GUARANTEE FOR ARKAN/CONFIDENCE
(2026-09-03)
---------------------------------------------------------------------------
With the Serper fix above live and results flowing again, the user asked
for two further, explicit changes:

1. Widen how far back this code looks before treating a listing as
   anything other than fully fresh, from 6 months to a full 12.
   RECENCY_WINDOW_DAYS raised from 180 to 365 -- same rule as every prior
   change to this constant (see the 2026-08-29 and 2026-08-31 sections
   above): a ranking nudge in _score_result() only, never an exclusion
   filter. This file has never dropped a real listing just for being old,
   and still doesn't -- a listing confirmed posted anywhere in the last
   12 months now gets the same small freshness bonus a listing posted
   last week gets, instead of the small penalty it used to get past the
   6-month mark.

2. "Always bring an option from Arkan Estate and Confidence." This is a
   real, deliberate change to how results get chosen, not just a bigger
   number: up to this point, Arkan and Confidence were searched for
   exactly the same as every other site and then subjected to the same
   score-based ranking and MAX_RESULTS_PER_DOMAIN cap as everything else
   (see the 2026-09-01 section above) -- which means it was always
   possible, by design, for either one to be out-scored entirely by other
   sites' results and not appear in a reply at all, even when it had a
   real, live, matching listing. That's exactly what "no site is ever
   favored" was built to allow, and it was working as intended -- the
   user is now explicitly asking for a narrow, named exception to that
   rule for these two specific sources.

   Implemented as a guarantee step that runs AFTER ranking and dead-page
   filtering, not as a ranking boost baked into _score_result() -- a
   ranking boost would just shuffle these two higher in the score order,
   which doesn't guarantee anything if enough other real candidates still
   out-score them. _ensure_priority_domains() instead looks at the final,
   already-ranked, already-dead-page-filtered candidate pool directly: if
   the top `limit` results don't already include a live Arkan and/or
   Confidence result, and one exists ANYWHERE further down that same
   pool (i.e. it was found and confirmed alive, just ranked below the
   cutoff), it gets promoted into the reply, swapping out the
   currently-lowest-ranked result to make room. This only ever costs one
   slot per missing priority domain, and only when that domain actually
   has zero live results in the pool the user would otherwise have seen.

   Deliberately does NOT touch _finalize_and_enrich()'s dead-page
   filtering or _rank_and_fill()'s scoring/domain-cap logic at all --
   those still run exactly as before, for every site including these two.
   _finalize_and_enrich() itself was changed only to stop trimming its
   own output to `limit` (it now returns the full, alive-filtered,
   best-first reservoir) so the guarantee step below it has real spare
   candidates to promote from; the actual trim to `limit` now happens in
   search_properties() after the guarantee step runs.

   Same honest limit as this file has always held to: this guarantees
   representation only when a real, live listing genuinely exists
   somewhere in the ranked pool. If Arkan's site couldn't be reached at
   all for this search, or Confidence genuinely has nothing matching,
   nothing gets fabricated to fill that slot -- the reply simply won't
   have one, the same as it wouldn't for any other source with nothing
   real to offer.

"STILL NOT SHOWING ARKAN" -- THE GUARANTEE HAD NOTHING TO PROMOTE FROM
(found + fixed 2026-09-04)
---------------------------------------------------------------------------
The user reported the 2026-09-03 guarantee wasn't working: Arkan still
wasn't showing up. Reproduced this directly (not guessed at) by rebuilding
_rank_and_fill()'s actual candidate-selection logic with realistic inputs
in a throwaway script, run before writing any fix: a bedroom count
requested (by far the most common real query shape in this whole
project's history -- "3 bedrooms in Jbeil," etc.), Arkan's own candidates
with an UNCONFIRMED bedroom count (a real, common case -- see the
2026-08-24 section above on why Arkan's card teaser often doesn't state
bedroom count clearly), and enough market-side candidates (OLX/other
portals) with a CONFIRMED exact bedroom match to fill the entire
`reservoir_limit`-sized pool on their own. The reproduction confirmed the
worst case exactly: after the first _rank_and_fill() pass (confirmed
matches only), the reservoir was already completely full -- so the SECOND
pass, the one that even looks at close_matches (where Arkan's
unconfirmed-bedroom candidates actually live), never ran at all. See
search_properties()'s own "if bedrooms and len(merged) < reservoir_limit"
guard -- that condition was false, so the whole close_matches pass was
skipped outright.

That is a real, confirmed gap in the 2026-09-03 fix, not a deployment
problem: _ensure_priority_domains() was built to promote a real Arkan/
Confidence candidate that ranked below the top `limit` but was still
SOMEWHERE in the already-ranked reservoir. It had no way to help when the
candidate was never scored or added to that reservoir in the first place
-- which is exactly what happens whenever Arkan's own candidates all land
in close_matches and the market side alone has enough confirmed matches to
fill every slot before close_matches ever gets considered. In that
situation, "alive_candidates" handed to _ensure_priority_domains() never
contained an Arkan item at all, so it correctly (by its own rules) did
nothing -- but "correctly did nothing" here meant a real, live Arkan
listing that did exist for this search still never reached the reply.

Fixed by giving _ensure_priority_domains() a second, deeper fallback,
_rescue_priority_domain(): when a priority domain has nothing in the
ranked reservoir at all, this reads directly from that domain's OWN raw
search output -- arkan_out's "results"/"close_matches" for Arkan,
market_out's for Confidence -- completely independent of whether
_rank_and_fill() ever got around to scoring or ranking it. This is the
same real data search_arkan()/search_market() already returned earlier in
this exact request; nothing here re-searches or invents anything. A
rescued Arkan candidate needs no extra check (search_arkan() already
fetched that exact archive page fresh, with render=True, moments earlier
-- see DIRECTLY_SCRAPED_DOMAINS); a rescued Confidence candidate still
gets the same real dead-page check _finalize_and_enrich() would have run,
before ever being trusted. If a priority domain genuinely has nothing at
all in EITHER the ranked reservoir OR its own raw output, this still does
nothing for it -- same honest limit as always, just now checking in the
right place before giving up.
"""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, unquote

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
# See search_arkan()'s 2026-08-28 comment for why this is 4, not 2.
ARKAN_PAGES_PER_SEARCH = 4

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
    # Ray White International Lebanon -- confirmed real domain
    # (raywhite.com.lb) 2026-08-27, added per the user naming it
    # specifically as a premium broker missing from results.
    "raywhite.com.lb",
    # Batch added 2026-08-27 per the user's "premium brokers" ask -- each
    # one confirmed (via a real fetch of its homepage, not just a search
    # result) to be an active site with individual property listing pages,
    # not just a corporate/info page with nothing to actually scrape:
    "phoeniciaproperty.com",   # Beirut-focused, individual listing pages
                                # confirmed (e.g. Property-R1240.html)
    "ramcolb.com",             # RAMCO Real Estate Advisers, Beirut, est.
                                # 1973 -- "Featured Properties" + /listings
    "atabuild.com",            # self-described luxury/high-end Lebanese
                                # real estate agency, confirmed listing pages
    "pbm-leb.com",             # Lebanon brokerage since 2007, confirmed
                                # individual /property/<id> listing pages
    # Batch added 2026-08-29 per the user's "find at least 30 credible
    # websites" ask -- each one confirmed via a real fetch of its own
    # homepage AND at least one individual listing page showing a real
    # price/description (not just a corporate page with nothing to
    # scrape), same verification bar as every entry above. See module
    # docstring's 2026-08-29 section for what was checked and deliberately
    # left out (OpenSooq, propertyfinder.com.lb, Bayut, Aqarmap, and the
    # major international franchise brands beyond RE/MAX).
    "remax-tripoli.com",       # RE/MAX Lebanon's actual franchise site
                                # (Tripoli office) -- confirmed individual
                                # listings (e.g. a priced Koura villa) and
                                # a dedicated Batroun archive
    "localsrealestatelb.com",  # Beirut-area licensed broker (Elissar
                                # office), confirmed priced listing pages
    "dealers-group.com",       # Beirut (Hamra) brokerage, confirmed
                                # listings across Achrafieh and a dedicated
                                # Jbeil/Byblos page
    "reflb.com",               # Real Estate Finder Lebanon -- multi-agency
                                # portal, confirmed listings across Beirut,
                                # Mount Lebanon, North, and Bekaa
    "chidiac-realestate.com",  # Keserwan/Metn brokerage (CHRE), confirmed
                                # listings covering Adma, Jbeil, and Jounieh
    "whiterealestategroup.com",  # Achrafieh-based luxury brokerage,
                                # confirmed high-end priced listings
    "s-gestion.realestate",    # Beirut agency portal (est. 1996), confirmed
                                # listings across Metn, Batroun, Keserwan
    "arezrealestate.com",      # Beirut/Mount Lebanon brokerage, confirmed
                                # ~19 active priced listings
    "lebanonmls.com.lb",       # "Lebanon MLS" nationwide listings
                                # aggregator, confirmed individual listings
    "lebaqar.com",             # LebAqar -- peer-to-peer Lebanese listing
                                # platform, confirmed real priced listings
    "realtylebanon.com",       # Realty Lebanon, confirmed active listings
                                # across Mount Lebanon/Beirut
    "rizkproperties.net",      # Rizk Properties (Dbayeh), confirmed
                                # listings across Batroun, Jbeil, Keserwan,
                                # Metn
    "isold-realestate.com",    # iSOLD Real Estate, Lebanese Real Estate
                                # Syndicate member, confirmed listings
                                # across Metn, Keserwan, Jbeil, Batroun
    "icarwakim.com",           # ICAR Wakim, Beit Mery agency since 2002,
                                # confirmed listings incl. a dedicated
                                # Batroun page
    "elegant-realestate.com",  # Elegant Real Estate, confirmed active
                                # sale/rent listings across Lebanon
    "byblosestate.com",        # Jbeil/Byblos-based agency office (Blat-
                                # Jbeil), confirmed listings across Jbeil,
                                # Batroun, Kesrouan
    "lpirealestate.com",       # Keserwan-specific brokerage (Sahel Alma,
                                # Faqra), confirmed priced listings
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
# separately per source (Arkan, OLX). Kept at 8 (matching _resolve_bedrooms's
# own max_workers=min(8, ...)) so this stage always finishes in a single
# concurrent batch rather than two sequential ones -- with a 70s render
# timeout on Arkan/OLX candidates (see SCRAPER_API_RENDER_TIMEOUT), two
# sequential batches could approach gunicorn's own worker timeout.
BEDROOM_DETAIL_FETCH_CAP = 8
# Same idea, applied to results from the long-tail "other portals/open web"
# DuckDuckGo search -- kept lower than the Arkan/OLX cap since these are
# arbitrary third-party sites (slower/less predictable to fetch) and this
# pass runs on top of, not instead of, Arkan+OLX's own checks.
DDG_BEDROOM_DETAIL_FETCH_CAP = 6
# _finalize_and_enrich()'s final pass (dead-page check + thumbnail
# backfill, see module docstring's 2026-08-28 "THUMBNAILS" section) can
# drop a handful of candidates that turn out to be broken/blank pages --
# without some spare candidates already ranked and waiting, that would
# just make a reply come back short instead of full. So _rank_and_fill()
# is asked for `limit + RESULT_RESERVOIR_BUFFER` candidates (still ranked
# best-first, so the extras are only ever used to backfill a dropped
# slot, never to bump a genuinely worse result ahead of a better one).
RESULT_RESERVOIR_BUFFER = 10
# Added 2026-09-01: no site (see _rank_and_fill()) was ever explicitly
# favored in ranking, but nothing capped how many of the FINAL results
# could come from one single domain either -- so whichever one site
# happened to be best-indexed by Google for a given area/query (JSK
# before, a newer app called DoorEast this time -- see module docstring)
# could fill most or all of the list on its own, crowding out real
# candidates from Arkan, Confidence, or anywhere else. Applied identically
# to every domain, Arkan included -- see _rank_and_fill()'s docstring for
# the "overflow" pass that keeps this from ever trimming the list below
# what real candidates genuinely exist.
MAX_RESULTS_PER_DOMAIN = 3
# See module docstring's 2026-08-29 "WHY DO I ONLY EVER GET JSK FIRST?"
# section -- one giant OR-of-all-curated-portals query let Google's own
# ranking crowd out every site but the strongest one. Splitting
# OTHER_KNOWN_PORTALS into chunks this small and querying each separately
# gives every curated site a real, independent shot at surfacing.
OTHER_PORTALS_CHUNK_SIZE = 5
# See module docstring's 2026-08-29 "last 120 days" section -- a real,
# confirmed listing age within this window is rewarded in _score_result();
# an age confirmed OLDER than this is deprioritized, never excluded
# outright (a listing with no confirmed age at all is neither -- most
# sites this code scrapes don't expose a date, and that's not evidence of
# anything). Bumped from 120 to 180 (2026-08-31), then to 365 (2026-09-03)
# per the user's explicit request to widen this to a full 12 months -- see
# module docstring's 2026-09-03 section. Still never an exclusion filter,
# only a ranking nudge.
RECENCY_WINDOW_DAYS = 365

# Added 2026-09-03 per the user's explicit request that Arkan Estate and
# Confidence Real Estate always be represented in a reply, not merely
# subject to the same score-based ranking and MAX_RESULTS_PER_DOMAIN cap
# as every other site -- see module docstring's 2026-09-03 section and
# _ensure_priority_domains() for the guarantee logic itself. This is a
# deliberate, narrow exception to this file's long-standing "no site is
# ever favored" rule (see MAX_RESULTS_PER_DOMAIN and _score_result above),
# made only because the user explicitly asked for it, and scoped to
# "guarantee presence when a real one exists" -- it never fabricates a
# result for a domain that genuinely has none.
PRIORITY_DOMAINS = ("arkanestate.com", "confidencerealestate.com")


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


# See module docstring's 2026-08-29 "last 120 days" section.
_RELATIVE_AGE_RE = re.compile(
    r"\b(\d+)\s*(hour|hours|day|days|week|weeks|month|months|year|years)\s*ago\b",
    re.IGNORECASE,
)
_TODAY_AGE_MARKERS = ("today", "just now", "a few minutes ago", "a moment ago")
_YESTERDAY_AGE_MARKERS = ("yesterday",)


def _extract_days_old(text):
    """Best-effort real "how long ago was this posted" estimate, read
    directly from the listing's own text (a card teaser, a search
    snippet, or its full detail page) -- e.g. OLX and several portals
    show "3 days ago" / "2 weeks ago" right on the card. Returns an
    integer number of days, or None when nothing like this is stated
    anywhere (a very common case -- most sites this code scrapes don't
    expose a posting date at all). Never guessed or fabricated: only ever
    a real, explicitly-parsed number from the page's own text (see
    _score_result for how this is used -- a real but old date is
    deprioritized, never a reason to drop an otherwise-good listing, and
    an unparseable date is treated exactly as it was before this existed,
    with no bonus or penalty either way)."""
    if not text:
        return None
    lower = text.lower()
    for marker in _TODAY_AGE_MARKERS:
        if marker in lower:
            return 0
    for marker in _YESTERDAY_AGE_MARKERS:
        if marker in lower:
            return 1
    m = _RELATIVE_AGE_RE.search(lower)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit.startswith("hour"):
        return 0
    if unit.startswith("day"):
        return n
    if unit.startswith("week"):
        return n * 7
    if unit.startswith("month"):
        return n * 30
    if unit.startswith("year"):
        return n * 365
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


def _extract_card_image(card, base_url):
    """Pulls a thumbnail straight out of a search-results card's own <img>
    tag -- zero extra cost, since the archive page these cards live on is
    already being fetched anyway to find the listings in the first place
    (added 2026-08-28 per the user's "add thumbnails" request). Prefers a
    lazy-load attribute (data-src/data-lazy-src/data-original) over a plain
    src, since many WordPress/Next.js card grids ship a tiny shared
    placeholder in src and only swap in the real photo once JavaScript/
    scroll-triggered lazy-loading actually fires -- something a plain
    fetch never triggers, so reading src literally would often hand back
    the same placeholder graphic for every single card. Returns an
    absolute URL, or None if the card has no usable image at all."""
    img = card.find("img")
    if img is None:
        return None
    for attr in ("data-src", "data-lazy-src", "data-original", "src"):
        value = img.get(attr)
        if value and not value.strip().lower().startswith("data:"):
            return urljoin(base_url, value.strip())
    return None


# Added 2026-08-30: confirmed live on arkanestate.com/area/jamhour/ -- an
# area with exactly ONE real listing, shown as a special "Featured" hero
# widget rather than a normal grid card, with no dedicated <article>/<li>
# wrapper of its own. The old plain find_parent(["article", "div", "li"])
# matched whatever <div> happened to be closest, which on this page turned
# out to be a wide layout wrapper that ALSO contains an unrelated "Latest
# Listings" sidebar -- including a genuine rental ("Apartment for Rent in
# New Shayleh", "$650/month"). That sidebar text leaked straight into this
# listing's own rent-vs-sale detection text, so a real, live $670,000 SALE
# listing (5 bed/6 bath, confirmed via a direct fetch) got wrongly flagged
# as a rental and silently excluded from every "buy"/sale search for
# Jamhour -- not because of a bug in the rent/sale logic itself, but
# because the text it was reading was scoped too broadly. <article> and
# <li> are far more reliable "this is exactly one card" boundaries than a
# bare <div>, which can just as easily be a multi-column layout wrapper
# holding several unrelated things side by side -- so those are tried
# FIRST now, falling back to a bare div only if neither exists.
# CARD_DETECTION_TEXT_CAP is a second, cheaper safety net for that
# fallback case: a genuine single card's own teaser text is always
# comfortably under this; text far longer than that is itself a sign the
# match was too broad, so anything past the cap isn't trusted for
# deciding rent-vs-sale or extracting price/bedrooms/age.
CARD_DETECTION_TEXT_CAP = 600


def _card_and_detection_text(a, fallback_tags=("article", "div", "li")):
    """Given a listing's own anchor tag, returns (card, detection_text):
    `card` is the best-guess element representing just this one listing
    (used for e.g. pulling its own <img> via _extract_card_image), and
    `detection_text` is the safely-bounded text actually used to decide
    rent-vs-sale and extract price/bedrooms/age for THIS card specifically
    -- see CARD_DETECTION_TEXT_CAP above for why this exists."""
    tight = a.find_parent(["article", "li"])
    card = tight or a.find_parent(list(fallback_tags)) or a
    text = card.get_text(" ", strip=True)
    return card, text[:CARD_DETECTION_TEXT_CAP]


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

        card, text_block = _card_and_detection_text(a)

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

        days_old = _extract_days_old(text_block)
        results.append({
            "title": title,
            "url": href if href.startswith("http") else ARKAN_BASE + href,
            "price_usd": price,
            "snippet": text_block[:220],
            "bedrooms_hint": _extract_bedroom_count(text_block),
            "image_url": _extract_card_image(card, ARKAN_BASE),
            **({"days_old": days_old} if days_old is not None else {}),
        })
        if len(results) >= limit:
            break

    return results


# Phrases that show up in a bot-check/verification interstitial page
# (Cloudflare's challenge page, a generic "prove you're human" wall, etc.)
# rather than the real page. These almost always come back as a normal
# HTTP 200 -- _fetch()'s error handling never sees anything wrong, since
# nothing actually "failed" from an HTTP-status point of view -- which is
# exactly how a real production bug hid from every log line until this was
# added: a technically-successful fetch that silently contains zero real
# listings, logged nowhere, indistinguishable from "this site really has
# nothing" without literally reading what came back. Added 2026-08-25 after
# a live OLX search test parsed 0 listings with zero errors of any kind
# logged, while a manual check of the exact same page moments earlier
# (via a different fetch path) showed it full of real listings.
BOT_CHALLENGE_MARKERS = (
    "captcha", "checking your browser", "cf-browser-verification",
    "cf-chl", "access denied", "are you a human", "just a moment",
    "enable javascript and cookies", "unusual traffic", "verify you are human",
    "attention required", "please verify you are a human",
    "pardon our interruption", "request unsuccessful",
)


def _looks_like_bot_challenge(html):
    """Cheap heuristic, not a guarantee: does this fetched page look like a
    bot-check/verification wall rather than the real content? Not
    exhaustive, but catches the common Cloudflare/anti-bot phrasing. Does
    NOT catch a pure-JS reload-and-wait check with no human-readable text
    at all (that's what Arkan turned out to actually do -- see module
    docstring, 2026-08-26) -- there's no text to match in that case; the
    real fix for that is ScraperAPI's render=True, not a smarter phrase
    list."""
    if not html:
        return False
    lower = html.lower()
    return any(marker in lower for marker in BOT_CHALLENGE_MARKERS)


# --- Optional paid fallbacks for the two confirmed hard walls above ------
# Both fully optional: unset SCRAPER_API_KEY/SERPER_API_KEY and everything
# behaves exactly as before (plain direct fetches, DuckDuckGo scraping).
# Set either one to switch that specific piece over. See module docstring's
# 2026-08-26 section for exactly what each one fixes and why a code-only
# fix isn't possible for either wall.
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "").strip()
SCRAPER_API_ENDPOINT = "https://api.scraperapi.com/"
# A rendered fetch (a real headless browser) takes much longer than a
# plain one -- give it real room instead of timing out on exactly the
# requests that need it most. 70s matches ScraperAPI's own documented
# guidance ("set a 70 second timeout in your application to get the best
# possible success rates") -- confirmed necessary in practice, not just
# theory: a first real test at 30s timed out on every single Arkan/OLX
# fetch (see module docstring's next dated section). Dockerfile's gunicorn
# --timeout is set to 200 specifically to leave real headroom above this,
# even with two render fetches effectively stacking back-to-back within
# the same chat reply (the initial archive-page fetch, then a detail-page
# fetch to confirm bedroom count -- see BEDROOM_DETAIL_FETCH_CAP below).
SCRAPER_API_RENDER_TIMEOUT = 70
# Confirmed to need a real rendering browser (see _needs_render()) --
# every other fetch still goes through ScraperAPI's proxy when the key is
# set (for its non-datacenter IP alone), just without paying render's
# extra cost/latency. confidencerealestate.com added 2026-09-01 -- a live
# fetch of THREE different pages on that site (homepage, a
# /property-location/batroun/ archive, and a real individual
# /property/<slug>/ listing page found via a live Google search) each
# came back as nothing but a bare <head> full of meta tags -- the same
# client-side-JS-only wall OLX has (see the 2026-08-26 section above),
# just never diagnosed for this specific site until now. See
# DIRECTLY_SCRAPED_DOMAINS below and _finalize_and_enrich() for why this
# one still needs an active check (unlike Arkan/OLX) rather than being
# skipped outright.
RENDER_REQUIRED_DOMAINS = (
    "arkanestate.com", "olx.com.lb", "confidencerealestate.com",
)

# Of the domains above, these two already get a guaranteed-FRESH
# render=True fetch of the exact page a candidate came from, moments
# earlier in this same request, via their own dedicated scraper
# (search_arkan() / _scrape_olx_cards()) -- so _finalize_and_enrich() can
# safely skip re-checking them (see its own docstring). Confidence is
# deliberately NOT in this set: its candidates are only ever discovered
# secondhand, via a Serper/DuckDuckGo search hit -- this code has never
# actually fetched that specific listing page itself before that point,
# so it genuinely needs the check (with render=True, not skipped and not
# plain-fetched) to tell a real live listing apart from a genuinely dead
# one.
DIRECTLY_SCRAPED_DOMAINS = ("arkanestate.com", "olx.com.lb")

# Serper.dev returns real Google search results as plain JSON -- replaces
# the DuckDuckGo HTML scrape entirely when set, since DuckDuckGo's own
# endpoint outright refuses the TCP connection from Render's IP range
# (confirmed via a real connection timeout in production -- see module
# docstring). 2,500 free queries to start, then roughly $0.30/1,000.
SERPER_API_KEY = os.getenv("SERPER_API_KEY", "").strip()
SERPER_ENDPOINT = "https://google.serper.dev/search"


def _needs_render(url):
    """Does this URL need a real rendering browser (see
    RENDER_REQUIRED_DOMAINS), rather than a plain proxied fetch?"""
    domain = urlparse(url).netloc.lower()
    return any(d in domain for d in RENDER_REQUIRED_DOMAINS)


def _is_directly_scraped(url):
    """Does this URL belong to a site whose own dedicated scraper
    (search_arkan() / _scrape_olx_cards()) already fetched THIS exact
    page, fresh, with render=True, earlier in this same request? See
    DIRECTLY_SCRAPED_DOMAINS above -- _finalize_and_enrich() uses this to
    skip a pointless re-check for those two, while still actively
    checking a RENDER_REQUIRED_DOMAINS site that ISN'T in this set (e.g.
    Confidence Real Estate), whose candidates only ever arrive secondhand
    via a search hit and have never actually been fetched by this code
    before that point."""
    domain = urlparse(url).netloc.lower()
    return any(d in domain for d in DIRECTLY_SCRAPED_DOMAINS)


def _fetch(url, timeout=REQUEST_TIMEOUT, retries=1, render=False):
    """GETs a URL and returns its HTML text, or None on failure.

    Retries once (no backoff -- the failed attempt already spent the full
    timeout waiting) on a connection-level failure (timeout, DNS, connection
    reset), since those are often transient on shared hosting. Does NOT
    retry an HTTP-level error status (403/429/503, etc.) -- that's a real
    server response actively rejecting the request, and an identical retry
    won't change that, just waste time.

    When SCRAPER_API_KEY is set, the request is routed through ScraperAPI's
    proxy (a non-datacenter IP) instead of a direct requests.get(). Pass
    render=True to additionally ask ScraperAPI to load the page in a real
    headless browser and wait for it to finish -- needed for Arkan's JS
    reload-and-wait check and OLX's client-rendered listings (see
    _needs_render() and the module docstring's 2026-08-26 section); it
    costs more credits and takes longer, so callers only set it for fetches
    that actually need it. With no SCRAPER_API_KEY set, `render` is ignored
    and this behaves exactly as before (a plain direct fetch).

    Every failure is logged via the standard `logging` module (so it shows
    up in Render's own log viewer) instead of vanishing silently -- see the
    module docstring's 2026-08-25 section for why this matters: a fetch
    failing here with zero trace of why is exactly what made a real
    production bug (real listings confirmed live on-site, zero results
    coming back from this code) impossible to diagnose from the outside."""
    if SCRAPER_API_KEY:
        request_url = SCRAPER_API_ENDPOINT
        params = {"api_key": SCRAPER_API_KEY, "url": url}
        if render:
            params["render"] = "true"
            # premium=true REMOVED (see module docstring's next dated
            # section) -- every single Arkan/OLX fetch came back as a 500
            # "Extraction failed" straight from ScraperAPI's own server
            # while this was set, confirmed directly from Render's logs.
            # ScraperAPI's premium-proxy docs page says premium pools are
            # "available to all paid users" -- a free trial may not count
            # as "paid" even though it needs no card, which would explain a
            # blanket failure on every request rather than just some. Only
            # render=True (a real rendering browser, no special proxy pool)
            # is requested now, to isolate whether that alone clears
            # Arkan's JS reload-and-wait check and OLX's client-side
            # rendering without the premium add-on. If Render's logs still
            # show real listings failing after this, premium proxies (i.e.
            # upgrading past the trial) may be the next thing to try --
            # but don't re-add premium=true speculatively before that's
            # actually confirmed necessary.
            timeout = max(timeout, SCRAPER_API_RENDER_TIMEOUT)
        request_kwargs = {"params": params}
    else:
        request_url = url
        request_kwargs = {"headers": HEADERS}

    attempts = retries + 1
    for attempt in range(attempts):
        try:
            resp = requests.get(request_url, timeout=timeout, **request_kwargs)
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError as e:
            logger.warning("Fetch got an HTTP error for %s: %s", url, e)
            return None
        except requests.RequestException as e:
            if attempt + 1 < attempts:
                continue
            logger.warning(
                "Fetch failed for %s after %d attempt(s): %s", url, attempts, e
            )
            return None


# Added 2026-08-30: og:image is NOT reliably a photo of the specific
# listing it's read from -- confirmed against two real, live jskre.com
# pages the user's own screenshot led back to. The site's homepage sets
# og:image to its own logo (jskre.com/images/og-image.png -- literally
# the "JSK BROKERAGE" graphic the user spotted standing in for a
# thumbnail). And even a genuine individual listing page can carry a
# generic stand-in image: one real JSK listing's og:image was
# ".../RES%20SALE.jpg" -- "RES SALE" being the CRM's (Propertybase, an
# S3-hosted real estate CRM several agencies here run on) own generic
# "Residential Sale" placeholder, used whenever that specific listing
# never had a real photo uploaded to it -- not a photo of that unit.
# A genuinely listing-specific photo, confirmed on a different JSK
# listing fetched the same way, instead has an opaque per-upload
# filename (c7c7545d-0d03-4137-b425-7acfe38e684d.jpeg) with no generic
# wording anywhere in it. GENERIC_IMAGE_MARKERS is a deny-list of
# path/filename substrings that flag an image URL as site-wide branding
# or a shared placeholder rather than a specific listing's own photo.
# Checked against the URL percent-decoded and lowercased, so
# "RES%20SALE" and "res-sale" both match the same "res sale" entry.
GENERIC_IMAGE_MARKERS = (
    "og-image", "og_image", "og image",
    "logo",
    "brand", "branding",
    "placeholder",
    "no-image", "no_image", "no image", "noimage",
    "no-photo", "no_photo", "no photo", "nophoto",
    "coming-soon", "coming_soon", "coming soon",
    "default-image", "default_image", "default photo",
    "share-image", "share_image", "share image",
    "social-image", "social_image", "social image",
    "res-sale", "res_sale", "res sale", "ressale",
    "res-rent", "res_rent", "res rent", "resrent",
    "watermark",
)


def _looks_generic_image(url):
    """Is this image URL site-wide branding or a shared CRM/category
    placeholder rather than an actual listing photo? See
    GENERIC_IMAGE_MARKERS above -- confirmed against real fetched pages,
    not guessed. A hit here means the image gets dropped rather than
    shown: a missing thumbnail is a much smaller problem for a real
    estate app than an agency's logo standing in for a listing photo."""
    if not url:
        return False
    decoded = unquote(url).lower()
    return any(marker in decoded for marker in GENERIC_IMAGE_MARKERS)


def _extract_og_image(html, base_url):
    """Pulls a thumbnail image URL out of a fetched page's Open Graph /
    Twitter Card meta tags. Confirmed 2026-08-28 via a real fetch of a
    jskre.com listing page to be how virtually every real estate site
    (including ones this code has no custom parser for) already exposes a
    representative photo -- built for link-preview purposes, but works
    just as well here, and is far more reliable than guessing each site's
    own card-image markup. Skips (rather than returns) a tag whose value
    looks generic -- see _looks_generic_image -- since a shared logo/
    placeholder is worse than no thumbnail at all. Returns an absolute
    URL, or None if no real, listing-specific tag is present."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for attrs in (
        {"property": "og:image"},
        {"name": "og:image"},
        {"property": "twitter:image"},
        {"name": "twitter:image"},
    ):
        tag = soup.find("meta", attrs=attrs)
        content = tag.get("content") if tag else None
        if content and content.strip() and not _looks_generic_image(content):
            return urljoin(base_url, content.strip())
    return None


def _extract_body_image(html, base_url):
    """Second-chance thumbnail extraction for when a page's own og:image/
    twitter:image tags are missing or every one of them looked generic
    (see _extract_og_image/_looks_generic_image) -- scans the page's own
    body content, with <header>/<nav>/<footer> stripped out first (that's
    where a site's logo and nav icons live, not a listing's own photos),
    for the first real-looking <img>. Prefers lazy-load attributes
    (data-src etc, same reasoning as _extract_card_image) over a plain
    src, since many sites only populate src with a placeholder until JS
    runs. Returns None rather than guess when nothing clean turns up."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag_name in ("header", "nav", "footer"):
        for tag in soup.find_all(tag_name):
            tag.decompose()
    for img in soup.find_all("img"):
        for attr in ("data-src", "data-lazy-src", "data-original", "src"):
            value = img.get(attr)
            if not value or not value.strip():
                continue
            value = value.strip()
            if value.startswith("data:"):
                continue
            if _looks_generic_image(value):
                continue
            if not re.search(r"\.(jpe?g|png|webp)(\?|$)", value, re.IGNORECASE):
                continue
            return urljoin(base_url, value)
    return None


def _extract_thumbnail(html, base_url):
    """Single entry point callers should use to get a listing's thumbnail
    from a fetched detail page: tries the reliable, cross-site og:image/
    twitter:image route first (_extract_og_image, itself already
    filtering out generic/branding images), then falls back to scanning
    the page's own body content directly (_extract_body_image) when that
    comes up empty -- no extra fetch either way, since `html` is already
    in hand. Returns None (never a guess) if neither turns up a real,
    listing-specific photo."""
    return _extract_og_image(html, base_url) or _extract_body_image(html, base_url)


# A real listing page always has a meaningful amount of actual body text
# (price, description, specs, location) -- a blank/broken page does not,
# even though it can still return a normal HTTP 200 with a fully-formed
# <head> (meta tags, title) and no real <body> content at all. Confirmed
# 2026-08-28 against a real broken URL the user hit
# (confidencerealestate.com/property-location/jbeil/ -- a real 200 with a
# complete set of meta tags but nothing else). 250 characters is a
# conservative floor: comfortably below even a terse real listing's own
# description, comfortably above the stray nav/footer text an empty
# template page still renders.
DEAD_PAGE_TEXT_MARKERS = (
    "page not found", "404 not found", "no longer available",
    "listing has been removed", "this ad is no longer", "property not found",
)
DEAD_PAGE_MIN_TEXT_LENGTH = 250

# Added 2026-08-29: a real, confirmed dead page the user hit
# (https://www.jskre.com/listings/edde-jbeil, an actual HTTP 410 Gone)
# still cleared the length floor above -- a full WordPress theme's own
# nav/footer/cookie-banner chrome alone is often well over 250 characters
# even when the page underneath has zero real listing content, and
# ScraperAPI's own documented status-code behavior doesn't clearly cover
# what happens to a non-200/404 target status like 410 when proxied. See
# module docstring's 2026-08-29 "too long to look dead" section. A real
# listing page -- on literally any site this code scrapes -- always
# states an actual price and/or a basic property attribute somewhere in
# its own text; chrome-only/error content never does.
PRICE_LIKE_RE = re.compile(r"\$\s?\d|\busd\s*\d|\bl\.?l\.?\s*\d", re.IGNORECASE)
# Deliberately does NOT include "for sale"/"for rent" -- those are exactly
# the kind of phrase that lives in a site's own persistent nav menu (a
# link literally labeled "For Sale") and shows up on EVERY page, including
# a broken/dead one, which would defeat the whole point of this check.
# Confirmed by testing against a realistic simulated dead page: nav chrome
# routinely contains "For Sale"/"For Rent" as menu items regardless of
# whether the actual page underneath is alive.
LISTING_ATTRIBUTE_MARKERS = (
    "bedroom", "bathroom", "sqm", "sq m", "sq. m", "m²", "square meter",
    "square feet", "sq ft",
)


def _looks_dead_page(html):
    """Is this fetched page essentially blank/broken rather than a real,
    live listing? See _finalize_and_enrich() for where this actually keeps
    a broken link from ever reaching the person, instead of just being
    informational."""
    if not html:
        return True
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    lower = text.lower()
    if any(marker in lower for marker in DEAD_PAGE_TEXT_MARKERS):
        return True
    if len(text) < DEAD_PAGE_MIN_TEXT_LENGTH:
        return True
    has_price = bool(PRICE_LIKE_RE.search(lower))
    has_attribute = any(marker in lower for marker in LISTING_ATTRIBUTE_MARKERS)
    if not has_price and not has_attribute:
        return True
    return False


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
        def _fetch_detail(it):
            # Arkan/OLX individual listing pages sit behind the same wall
            # as their archive pages (see module docstring, 2026-08-26) --
            # render=True there too, or this would "succeed" while quietly
            # fetching a reload-stub/empty shell instead of the real page.
            needs_render = _needs_render(it["url"])
            return _fetch(it["url"], render=needs_render, retries=0 if needs_render else 1)

        with ThreadPoolExecutor(max_workers=min(8, len(to_check))) as pool:
            detail_htmls = list(pool.map(_fetch_detail, to_check))
        for item, html in zip(to_check, detail_htmls):
            # Added 2026-08-28: this candidate's own page is already being
            # fetched right here anyway (to confirm bedroom count) -- a
            # free, zero-extra-cost place to also check it isn't a broken/
            # blank page (see _looks_dead_page, and the module docstring's
            # 2026-08-28 section for the real confidencerealestate.com
            # example that motivated this) and to grab a thumbnail image
            # (see _extract_thumbnail) while the HTML is already in hand.
            # A dead-looking page is dropped entirely, not just marked
            # unconfirmed -- a fetch that failed outright, or a page this
            # broken, isn't something to ever hand to the person as a real
            # result. "_verified" tells _finalize_and_enrich() this
            # candidate has already been checked once here, so it doesn't
            # get fetched a second time later.
            if _looks_dead_page(html):
                logger.warning(
                    "Dropping candidate whose own page looks dead/broken "
                    "(empty, 404, or fetch failed): %s", item["url"],
                )
                continue
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
            if not item.get("image_url"):
                thumbnail = _extract_thumbnail(html, item["url"])
                if thumbnail:
                    item["image_url"] = thumbnail
            if item.get("days_old") is None:
                detail_days_old = _extract_days_old(page_text)
                if detail_days_old is not None:
                    item["days_old"] = detail_days_old
            item["_verified"] = True
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
        # Bumped from 2 pages to ARKAN_PAGES_PER_SEARCH (2026-08-28) -- the
        # user asked why two real, confirmed-live listings (a 210 sqm
        # Amchit garden apartment, and a Jbeil/Byblos development) never
        # showed up for "3 bedrooms in Jbeil". A real fetch of
        # arkanestate.com/city/jbeil/ showed pagination reading "1 2 3 4"
        # -- 4 total pages for this one district -- and neither listing
        # was among the ~10 on page 1. Fetching more pages concurrently
        # (still one single batch, so worst-case latency stays bounded by
        # the slowest individual page, not the sum) covers a district's
        # full inventory far more often. Not a guarantee for every area --
        # a bigger city could have more than ARKAN_PAGES_PER_SEARCH pages
        # -- but this trades a bounded, modest increase in ScraperAPI
        # credits/concurrent connections for meaningfully better coverage.
        pages = [
            location_url if i == 0 else location_url.rstrip("/") + f"/page/{i + 1}/"
            for i in range(ARKAN_PAGES_PER_SEARCH)
        ]
        with ThreadPoolExecutor(max_workers=len(pages)) as pool:
            # render=True: Arkan sends every plain fetch a blank
            # "wait 5 seconds and reload" page instead of real listings --
            # see module docstring, 2026-08-26. retries=0 since a rendered
            # fetch already takes a while; a second full-length retry
            # risks the reply itself timing out for no real benefit.
            htmls = list(pool.map(lambda u: _fetch(u, render=True, retries=0), pages))
        for page_url, html in zip(pages, htmls):
            if not html:
                continue
            if _looks_like_bot_challenge(html):
                logger.warning(
                    "Arkan: got a response for %s but it looks like a bot "
                    "check/verification page, not real listings. First 300 "
                    "chars: %r", page_url, html[:300],
                )
                continue
            fetched_any = True
            page_items = _parse_arkan_cards(
                html, transaction_type, property_type,
                min_price, max_price, limit * 3,
            )
            if not page_items:
                logger.warning(
                    "Arkan: fetched %s successfully but parsed 0 listings "
                    "from it. First 300 chars: %r", page_url, html[:300],
                )
            for item in page_items:
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                candidates.append(item)

    # Changed 2026-08-31 from "if not candidates:" (only ran when the
    # location page(s) above found ZERO listings at all) to "thin, not
    # just empty" -- confirmed live on arkanestate.com/area/jamhour/:
    # that page has exactly ONE real listing, so `candidates` already had
    # 1 item in it and the sitewide-search backup was being skipped
    # entirely -- even though Arkan's own broader search might genuinely
    # have more to offer for that name. A location page that's merely thin
    # (a handful of results, not enough to fill a reply) was being treated
    # exactly like a location page that came back completely empty. The
    # user asked for at least 10 real options whenever they exist -- a
    # location page that's merely thin (1-9 results) is exactly the case
    # this fallback needs to run for, not just a location page that came
    # back fully empty. Still fully additive (seen_urls below prevents
    # duplicates) and still skipped once `candidates` already has enough.
    if len(candidates) < limit:
        fallback_url = f"{ARKAN_BASE}/?s={area}"
        html = _fetch(fallback_url, render=True, retries=0)
        if html and _looks_like_bot_challenge(html):
            logger.warning(
                "Arkan: got a response for %s but it looks like a bot "
                "check/verification page, not real listings. First 300 "
                "chars: %r", fallback_url, html[:300],
            )
            html = None
        if html:
            fetched_any = True
            fallback_items = _parse_arkan_cards(
                html, transaction_type, property_type,
                min_price, max_price, limit * 3,
            )
            if not fallback_items:
                logger.warning(
                    "Arkan: fetched %s successfully but parsed 0 listings "
                    "from it. First 300 chars: %r", fallback_url, html[:300],
                )
            for item in fallback_items:
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

        # Same reasoning as _parse_arkan_cards()'s 2026-08-30 fix -- see
        # _card_and_detection_text()'s docstring: prefer a tight
        # <article>/<li> card boundary over a bare <div>, and cap the
        # text actually used for price/bedroom/age extraction, so this
        # card's own data can't get contaminated by an unrelated
        # sibling card/widget sharing the same broad wrapping div.
        card, text_block = _card_and_detection_text(a)
        lower = text_block.lower()
        if property_type and property_type.lower() not in lower:
            continue

        days_old = _extract_days_old(text_block)
        results.append({
            "title": title,
            "url": full_url,
            "price_usd": _clean_price(text_block),
            "snippet": text_block[:220],
            "bedrooms_hint": _extract_bedroom_count(text_block),
            "image_url": _extract_card_image(card, OLX_BASE),
            **({"days_old": days_old} if days_old is not None else {}),
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
    # render=True: OLX's category pages are a Next.js app whose listing
    # cards are added by client-side JavaScript after the initial load --
    # see module docstring, 2026-08-26. retries=0 for the same reason as
    # Arkan's fetch above.
    html = _fetch(url, timeout=OLX_TIMEOUT, render=True, retries=0)
    if not html:
        logger.warning("OLX: could not reach %s", url)
        return [], False
    if _looks_like_bot_challenge(html):
        logger.warning(
            "OLX: got a response for %s but it looks like a bot "
            "check/verification page, not real listings. First 300 "
            "chars: %r", url, html[:300],
        )
        return [], False
    results = _parse_olx_cards(html, property_type, limit)
    if not results:
        logger.warning(
            "OLX: fetched %s successfully but parsed 0 listings from it. "
            "First 300 chars: %r", url, html[:300],
        )
    return results, True


NON_LISTING_PATH_MARKERS = (
    "/search", "/category/", "/categories/", "/tag/", "/tags/", "/page/",
    # "/property-location/" added 2026-08-28: WPEstate's own location-
    # taxonomy archive path (same theme Arkan itself runs -- see the
    # 2026-08-24 section above), confirmed via a real, blank/broken
    # example the user hit on confidencerealestate.com. Several
    # OTHER_KNOWN_PORTALS entries likely share this same WPEstate-based
    # URL scheme, so this one marker covers more than just that one site.
    "/property-location/",
)

# Facebook/Instagram need their own rule, not the generic path-marker list
# above -- added 2026-08-28 per explicit feedback: a result must land on
# the actual post, never a bare page/profile. A post-shaped path is the
# allowlist here (rather than a denylist like NON_LISTING_PATH_MARKERS)
# because a bare facebook.com/<name>/ or instagram.com/<name>/ has no
# distinguishing marker of its own to deny -- it just looks like any other
# short path, so the safe default for these two domains specifically is
# "reject unless it clearly looks like one specific post."
FACEBOOK_POST_PATH_MARKERS = (
    "/posts/", "/permalink", "/photo.php", "/photo/", "/videos/",
    "/watch/", "/marketplace/item/", "/story.php",
)
INSTAGRAM_POST_PATH_RE = re.compile(r"^/(p|reel|tv)/[^/]+")


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
    URL. Extended 2026-08-28 with Facebook/Instagram-specific handling
    (see FACEBOOK_POST_PATH_MARKERS/INSTAGRAM_POST_PATH_RE) -- a page/
    profile is never acceptable there, only an actual post."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.rstrip("/").lower()

    if "facebook.com" in domain:
        return any(marker in path for marker in FACEBOOK_POST_PATH_MARKERS)
    if "instagram.com" in domain:
        return bool(INSTAGRAM_POST_PATH_RE.match(path))

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
        logger.warning("DuckDuckGo search failed for query %r: %s", query, e)
        return [], False

    if _looks_like_bot_challenge(resp.text):
        logger.warning(
            "DuckDuckGo: got a response for query %r but it looks like a "
            "block/anomaly page, not real results. First 300 chars: %r",
            query, resp.text[:300],
        )
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
        days_old = _extract_days_old(combined_text)
        if days_old is not None:
            item["days_old"] = days_old
        out.append(item)
    if not out:
        logger.warning(
            "DuckDuckGo: query %r got a normal-looking response but 0 "
            "results were parsed from it. First 300 chars: %r",
            query, resp.text[:300],
        )
    return out, True


def _serper_request(query, num=None):
    """Makes exactly one POST request to Serper.dev's Search API and
    returns (data, error): `data` is the parsed JSON response (None on any
    failure), `error` is a human-readable description of what went wrong
    (None on success). `num` is omitted from the request body entirely
    when None, letting Serper apply its own implicit default (~10 results)
    -- see _serper_search() for why a caller might deliberately want that.

    Split out of _serper_search() on 2026-09-02 so that function can retry
    once with a different `num` after a failure without duplicating the
    request/error-handling logic, and so a failure's error text includes
    Serper's own response BODY -- not just the generic exception message.
    Before this, a failed request only ever logged something like "400
    Client Error: Bad Request for url: https://google.serper.dev/search",
    which never included Serper's own explanation of why -- exactly where
    an API states its own reason for rejecting a request. That gap is what
    made a real, live 2026-09-02 incident (confirmed via the user's own
    Render logs: EVERY single query failing with this identical error)
    impossible to diagnose beyond "something about the request is
    invalid" -- see module docstring's 2026-09-02 section."""
    payload = {"q": query}
    if num is not None:
        payload["num"] = num
    resp = None
    try:
        resp = requests.post(
            SERPER_ENDPOINT,
            json=payload,
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json(), None
    except requests.HTTPError as e:
        body = ""
        if resp is not None:
            try:
                body = resp.text[:500]
            except Exception:  # noqa: BLE001 - never let logging itself break a search
                pass
        return None, f"{e} -- response body: {body!r}"
    except (requests.RequestException, ValueError) as e:
        return None, str(e)


def _serper_search(query, limit):
    """One query against Serper.dev's Google Search API. Used instead of
    _ddg_search() when SERPER_API_KEY is set -- see module docstring,
    2026-08-26: DuckDuckGo's own endpoint outright refuses the TCP
    connection from Render's IP range (a real connection timeout,
    confirmed in production), which no amount of retrying or better
    headers can fix, since the connection itself never completes. Returns
    (results, reached) in the same shape _ddg_search() returns, so
    search_market() doesn't need to know or care which one actually ran.

    Added 2026-08-30: explicitly sends Serper's own "num" field now.
    Before this, the request body only ever sent {"q": query} -- Serper
    was never told how many results to return, so it quietly defaulted
    to its own standard ~10 organic results per query no matter how big
    a `limit` this function was called with. The `[:limit]` slice below
    looked like it controlled result count, but it never actually did
    anything past the first ~10 -- there was nothing more in `data`
    for it to slice. Since every query this project runs (see
    search_market's chunked OTHER_KNOWN_PORTALS queries) was silently
    capped at ~10 raw hits this way, this was very likely the single
    biggest reason results still felt "very limited" even after the
    30+ -site expansion and the reservoir buffer (RESULT_RESERVOIR_BUFFER)
    -- both of those only ever had ~10 real candidates per query to work
    with, regardless of how much bigger a number was asked for. Confirmed
    via Serper's own documented credit rule (2026-08-30 research): a
    query for up to 10 results costs 1 credit; 11-100 costs a flat 2
    credits -- not a per-result cost -- so once a query needs more than
    10, there's no reason to ask for fewer than 100 (Serper's own max).

    Fixed 2026-09-02: the num value actually sent was `min(limit, 100)` --
    the SMALLER of the two, e.g. 44 for a typical call in this app, not
    the flat 100 the paragraph above says it should be. That mismatch
    between the code and its own documented intent lines up with exactly
    when a real "every single query fails with 400" incident became
    possible (see module docstring's 2026-09-02 section) -- fixed to send
    a flat 100, and now retries once with no `num` at all if that fails,
    so one bad `num` value can never again zero out an entire query's
    results the way it did that day."""
    requested_num = 100 if limit > 10 else None
    data, error = _serper_request(query, requested_num)
    if data is None and requested_num is not None:
        logger.warning(
            "Serper search with num=%s failed for query %r (%s) -- "
            "retrying without num", requested_num, query, error,
        )
        data, error = _serper_request(query, None)
    if data is None:
        logger.warning("Serper search failed for query %r: %s", query, error)
        return [], False

    out = []
    for res in data.get("organic", [])[:limit]:
        link = res.get("link")
        if not link:
            continue
        title = res.get("title", "")
        snippet = res.get("snippet", "")
        item = {"title": title, "url": link, "snippet": snippet}
        combined_text = f"{title} {snippet}"
        bedrooms_hint = _extract_bedroom_count(combined_text)
        if bedrooms_hint is not None:
            item["bedrooms"] = bedrooms_hint
        price = _clean_price(combined_text)
        if price is not None:
            item["price_usd"] = price
        days_old = _extract_days_old(combined_text)
        if days_old is not None:
            item["days_old"] = days_old
        out.append(item)
    if not out:
        logger.warning(
            "Serper: query %r got a normal-looking response but 0 organic "
            "results were in it.", query,
        )
    return out, True


def _web_search(query, limit):
    """Dispatches to Serper.dev when SERPER_API_KEY is configured (a paid,
    reliable Google Search API -- see _serper_search()); otherwise falls
    back to the free, no-key DuckDuckGo scrape (_ddg_search()), exactly as
    before. Both return the same (results, reached) shape, so search_market
    below doesn't need to know which one actually ran."""
    if SERPER_API_KEY:
        return _serper_search(query, limit)
    return _ddg_search(query, limit)


def search_market(area, transaction_type="sale", property_type=None,
                   bedrooms=None, limit=10):
    """Search the Lebanese market beyond Arkan: OLX scraped directly, the
    other known major portals (queried in small chunks -- see
    OTHER_PORTALS_CHUNK_SIZE -- rather than one giant combined query, so no
    single strong site crowds out the rest), and an unrestricted search
    with no site filter, so agencies/brokers not on the curated list still
    surface too. All of these run concurrently and are merged, deduped by
    domain+path. Always includes "olx_search_url" -- a live, correctly filtered OLX
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
    # Chunked into small groups rather than one giant OR-of-everything query
    # -- see module docstring's 2026-08-29 "WHY DO I ONLY EVER GET JSK
    # FIRST?" section. A single query OR-ing all of OTHER_KNOWN_PORTALS
    # together let Google's own ranking crowd out every curated site but
    # the strongest one; querying each small chunk separately gives every
    # site a real, independent chance to surface.
    portal_chunks = [
        OTHER_KNOWN_PORTALS[i:i + OTHER_PORTALS_CHUNK_SIZE]
        for i in range(0, len(OTHER_KNOWN_PORTALS), OTHER_PORTALS_CHUNK_SIZE)
    ]
    other_portals_queries = [
        f"{area}{ptype} {kind} Lebanon (" + " OR ".join(f"site:{d}" for d in chunk) + ")"
        for chunk in portal_chunks
    ]
    open_query = f"{area}{ptype} {kind} Lebanon real estate agency broker listing"
    ddg_queries = other_portals_queries + [open_query]

    with ThreadPoolExecutor(max_workers=len(ddg_queries) + 1) as pool:
        olx_future = pool.submit(_scrape_olx_cards, olx_scrape_url, property_type, limit * 3)
        ddg_futures = {pool.submit(_web_search, q, limit * 2): q for q in ddg_queries}

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
    - real, confirmed posting age (see _extract_days_old): a listing
      confirmed posted within RECENCY_WINDOW_DAYS is rewarded, one
      confirmed OLDER is mildly deprioritized (never excluded outright --
      see module docstring's 2026-08-29 "last 120 days" section). Most
      listings have no confirmed age at all; that's neutral, not a strike
      against them.
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

    days_old = item.get("days_old")
    if days_old is not None:
        if days_old <= RECENCY_WINDOW_DAYS:
            score += 8.0   # confirmed within the requested freshness window
        else:
            score -= 8.0   # confirmed OLDER -- deprioritized, not excluded
    # else: age simply unconfirmed -- no bonus, no penalty

    return score


def _rank_and_fill(pool, arkan_items, market_items, bedrooms, min_price,
                    max_price, limit, add_fn):
    """Scores a combined Arkan+market candidate pool by _score_result() and
    adds the best ones to `pool` (via add_fn, which also dedupes AND, as of
    2026-09-01, enforces MAX_RESULTS_PER_DOMAIN -- see its own docstring)
    until it reaches `limit`. Interleaves Arkan/market before scoring
    (rather than concatenating one after the other) purely so that an
    exact score tie breaks evenly between sources instead of one side
    consistently winning ties -- the actual order is driven by score, not
    by source.

    Added 2026-09-01: a second "overflow" pass runs after the first if the
    per-domain cap left `pool` short of `limit`. add_fn returning False can
    mean either a true duplicate (never retried) or only "this domain is
    already at its cap" (retried here, this time with force=True, which
    bypasses the cap but never the dedupe check). This is deliberate: the
    cap's whole job is to stop one domain from crowding out real
    candidates from OTHER domains -- never to make a reply come back
    shorter than it could genuinely be. When there simply aren't enough
    distinct domains with real matches for this query, the overflow pass
    still fills the list up with the next-best real candidates regardless
    of domain, exactly as this worked before the cap existed."""
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

    deferred = []
    for _score, item in scored:
        if len(pool) >= limit:
            return
        if not add_fn(item, pool):
            deferred.append(item)

    for item in deferred:
        if len(pool) >= limit:
            return
        add_fn(item, pool, force=True)


def _finalize_and_enrich(ranked_candidates):
    """Last stop before a ranked candidate pool becomes the actual reply:
    drops anything that turns out to be a broken/blank page and backfills
    a thumbnail for whatever candidate doesn't already have one -- all
    without ever demoting a better-ranked real result in favor of a worse
    one that merely happened to get checked.

    `ranked_candidates` must already be in best-first order (this never
    re-sorts). Most items arrive already "_verified" -- either their own
    detail page was already fetched once by _resolve_bedrooms() (bedroom
    count was requested and the card's own teaser didn't say), or they're
    an Arkan/OLX card that got its thumbnail straight from the archive
    page's own markup for free (see _extract_card_image) and doesn't need
    a second visit just to double-check it's alive. Only the leftover
    candidates -- no bedroom count was requested, or the card's teaser
    already stated it, so _resolve_bedrooms() never opened this one's
    page -- get fetched here.

    Skipped entirely for DIRECTLY_SCRAPED_DOMAINS (Arkan/OLX) even when
    they aren't "_verified": those two sites need a real 70s-class
    rendering browser to show anything at all (see module docstring's
    2026-08-26 section), and their own dedicated scraper already fetched
    this exact page moments ago with render=True -- re-checking here would
    just cost time for no new information (a plain fetch there wouldn't
    reveal a real dead link either -- it would just misread a normal
    reload-and-wait stub as a dead page and wrongly discard a perfectly
    live listing). Everything else gets an actual fetch here: render=True
    for a RENDER_REQUIRED_DOMAINS site that ISN'T in DIRECTLY_SCRAPED_
    DOMAINS (Confidence Real Estate, as of 2026-09-01 -- see that
    section), otherwise a plain, short, non-rendering one (_fetch()'s
    render=False default, REQUEST_TIMEOUT's ~10s).

    Changed 2026-09-03: no longer trims the result down to a `limit` --
    this now runs its dead-page check/enrichment pass over the WHOLE
    (deliberately oversized, see RESULT_RESERVOIR_BUFFER) reservoir and
    hands back every surviving real, live candidate, still in best-first
    order. Trimming used to happen right here, but that meant a real,
    live Arkan/Confidence candidate ranked just below the cutoff was
    already gone by the time anything downstream could act on it. Now
    search_properties() runs _ensure_priority_domains() on this full,
    already-checked list BEFORE trimming to `limit` -- see that function
    and module docstring's 2026-09-03 section for why."""
    to_check = [
        item for item in ranked_candidates
        if not item.get("_verified") and not _is_directly_scraped(item["url"])
    ]

    if to_check:
        def _check(item):
            return _fetch(item["url"], render=_needs_render(item["url"]), retries=0)

        with ThreadPoolExecutor(max_workers=min(8, len(to_check))) as pool:
            htmls = list(pool.map(_check, to_check))
        for item, html in zip(to_check, htmls):
            if _looks_dead_page(html):
                item["_dead"] = True
                logger.warning(
                    "_finalize_and_enrich: dropping candidate whose own "
                    "page looks dead/broken (empty, 404, or fetch "
                    "failed): %s", item["url"],
                )
                continue
            if not item.get("image_url"):
                thumbnail = _extract_thumbnail(html, item["url"])
                if thumbnail:
                    item["image_url"] = thumbnail
            if item.get("days_old") is None:
                page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                detail_days_old = _extract_days_old(page_text)
                if detail_days_old is not None:
                    item["days_old"] = detail_days_old

    alive = []
    for item in ranked_candidates:
        if item.get("_dead"):
            continue
        item.pop("_verified", None)
        item.pop("_dead", None)
        alive.append(item)
    return alive


def _priority_domain_of(item):
    """Which PRIORITY_DOMAINS entry (if any) does this item's own URL
    belong to? Matches by substring against the URL's actual netloc
    (same robust pattern as _needs_render()/_is_directly_scraped() above)
    rather than the item's own "domain" field, so this still works
    correctly even if that field ever ends up "www."-prefixed or
    otherwise not byte-identical to the bare PRIORITY_DOMAINS string."""
    domain = urlparse(item["url"]).netloc.lower()
    for pd in PRIORITY_DOMAINS:
        if pd in domain:
            return pd
    return None


def _rescue_priority_domain(domain, arkan_out, market_out):
    """The real, deeper fallback added 2026-09-04 -- see module docstring's
    "STILL NOT SHOWING ARKAN" section for the confirmed bug this closes.
    _ensure_priority_domains() can only promote a priority-domain
    candidate that's SOMEWHERE in the already-ranked reservoir it's
    handed. That reservoir can genuinely never contain one at all -- most
    commonly when a bedroom count is requested, Arkan's own candidates
    land in close_matches with an unconfirmed count (a real, common case
    -- see the 2026-08-24 section above), and the market side alone has
    enough CONFIRMED exact matches to fill the whole reservoir before
    close_matches ever gets a second look (see search_properties()'s
    "if bedrooms and len(merged) < reservoir_limit" guard). In that case
    there is nothing wrong to detect in the reservoir -- the candidate
    just was never put there.

    This reads directly from that domain's own raw search output instead:
    arkan_out's "results" then "close_matches" for arkanestate.com (both
    already best-first within their own list), or market_out's for any
    other priority domain (currently just confidencerealestate.com) --
    the exact same real data search_arkan()/search_market() already
    returned earlier in this same request. Nothing here re-searches or
    invents anything.

    An Arkan candidate is trusted without a further check -- search_arkan()
    already fetched that exact archive page fresh, with render=True,
    moments earlier in this same request (see DIRECTLY_SCRAPED_DOMAINS).
    Anything else (Confidence) gets the same real dead-page check
    _finalize_and_enrich() would have run, plus the same thumbnail/
    days_old backfill, before ever being trusted -- this candidate never
    went through that pass, since it never made it into the ranked
    reservoir in the first place.

    Returns the first real, live candidate found, or None if this
    domain genuinely has nothing at all in its own raw output either --
    the same honest limit as everywhere else in this file: never
    fabricates a result that doesn't exist."""
    if domain in DIRECTLY_SCRAPED_DOMAINS:
        raw = list(arkan_out.get("results", [])) + list(arkan_out.get("close_matches", []))
    else:
        raw = list(market_out.get("results", [])) + list(market_out.get("close_matches", []))

    for item in raw:
        if _priority_domain_of(item) != domain:
            continue
        if domain in DIRECTLY_SCRAPED_DOMAINS:
            return item
        html = _fetch(item["url"], render=_needs_render(item["url"]), retries=0)
        if _looks_dead_page(html):
            logger.warning(
                "_rescue_priority_domain: a raw %s candidate (%s) never "
                "made it into the ranked reservoir, and its own page now "
                "looks dead/broken too -- skipping it, not promoting it.",
                domain, item["url"],
            )
            continue
        if not item.get("image_url"):
            thumbnail = _extract_thumbnail(html, item["url"])
            if thumbnail:
                item["image_url"] = thumbnail
        if item.get("days_old") is None:
            page_text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
            detail_days_old = _extract_days_old(page_text)
            if detail_days_old is not None:
                item["days_old"] = detail_days_old
        return item
    return None


def _ensure_priority_domains(alive_candidates, limit, rescue_fn=None):
    """Guarantees that Arkan Estate and Confidence Real Estate each have at
    least one real, live result inside the final `limit`-sized reply
    whenever either one actually has ANY real, live candidate ANYWHERE in
    `alive_candidates` (the full, already dead-page-filtered,
    already best-first-ranked reservoir _finalize_and_enrich() hands
    back) -- even if that candidate ranked below what the top `limit`
    would otherwise have included. See PRIORITY_DOMAINS and module
    docstring's 2026-09-03 section for why this deliberate, narrow
    exception to this file's "no site is ever favored" ranking rule
    exists: the user explicitly asked for these two specific sources to
    always be represented, not just be subject to the same score-based
    ranking/MAX_RESULTS_PER_DOMAIN cap as everything else.

    Only ever costs ONE slot per missing priority domain -- the
    currently-lowest-ranked slot not already spoken for by an earlier
    promotion in this same call -- and only when that domain has zero
    live results in the top `limit` already.

    Added 2026-09-04: when a priority domain has nothing anywhere in
    `alive_candidates` (not even ranked below the cutoff -- it never made
    it into the reservoir at all), this now calls `rescue_fn(domain)`, if
    given one, as a deeper fallback before giving up -- see
    _rescue_priority_domain() and module docstring's 2026-09-04 section
    for the real, confirmed gap this closes (a common case with a
    requested bedroom count, where the market side alone could fill the
    whole reservoir with confirmed matches before Arkan's own
    close_matches ever got considered).

    Never fabricates a result either way: if a priority domain genuinely
    has no real, live candidate in `alive_candidates` NOR (when rescue_fn
    is given) in its own raw search output, this does nothing for that
    domain -- the same "never invent what isn't there" rule as everywhere
    else in this file.

    Returns the full list (still oversized) with priority-domain
    candidates promoted into the first `limit` positions where needed --
    the caller trims to `limit` afterward."""
    top = list(alive_candidates[:limit])
    rest = list(alive_candidates[limit:])
    protected = set()

    for domain in PRIORITY_DOMAINS:
        already_present = False
        for i, item in enumerate(top):
            if _priority_domain_of(item) == domain:
                protected.add(i)
                already_present = True
        if already_present:
            continue

        promoted = None
        for i, item in enumerate(rest):
            if _priority_domain_of(item) == domain:
                promoted = rest.pop(i)
                break

        if promoted is None and rescue_fn is not None:
            promoted = rescue_fn(domain)
            if promoted is not None:
                logger.info(
                    "_ensure_priority_domains: rescued a live %s result "
                    "straight from its own raw search output -- it never "
                    "made it into the ranked reservoir at all (see module "
                    "docstring's 2026-09-04 section).", domain,
                )

        if promoted is None:
            # Genuinely nothing from this domain anywhere in the ranked
            # pool OR its own raw output -- an honest limit, not
            # something to fabricate around.
            continue

        victim_idx = next(
            (i for i in range(len(top) - 1, -1, -1) if i not in protected),
            None,
        )
        if victim_idx is None:
            top.append(promoted)
            protected.add(len(top) - 1)
        else:
            logger.info(
                "_ensure_priority_domains: promoting %s (no live %s result "
                "made the top %d on ranking alone)", promoted["url"], domain, limit,
            )
            top[victim_idx] = promoted
            protected.add(victim_idx)

    return top + rest


def search_properties(area, transaction_type="sale", property_type=None,
                       min_price=None, max_price=None, bedrooms=None,
                       include_public_sources=True, limit=12):
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

    Added 2026-09-03: Arkan Estate and Confidence Real Estate are each
    guaranteed to appear at least once in the returned "results" whenever
    either has a real, live candidate anywhere in the ranked pool -- a
    deliberate, narrow exception to the "no site is ever favored" ranking
    rule above, made only because the user explicitly asked these two
    sources always be represented (see PRIORITY_DOMAINS and
    _ensure_priority_domains()). This never fabricates a result for either
    one -- if a source genuinely has nothing real to offer for this query,
    nothing fills that slot.

    Pass include_public_sources=False to search Arkan's site alone.
    """
    # Added 2026-08-30: computed BEFORE calling search_arkan()/
    # search_market() now (it used to only exist further down, after
    # those calls had already returned), and passed to them below instead
    # of the bare `limit`. This was a real bug: search_arkan() and
    # search_market() each truncate their OWN "results"/"close_matches"
    # to whatever `limit` they were called with (see their own
    # `candidates[:limit]` / `merged[:limit]`) before ever handing
    # anything back here. Calling them with the plain `limit` (10) meant
    # the reservoir buffer below (_rank_and_fill asking for
    # `reservoir_limit` candidates so _finalize_and_enrich has real
    # spares to backfill from -- see RESULT_RESERVOIR_BUFFER) never
    # actually had more than ~`limit` candidates per source to draw
    # from in the first place -- the "spare" pool the whole reservoir
    # design depends on didn't exist yet at the point these two were
    # called. Passing `reservoir_limit` here instead means each source
    # itself returns up to `limit + RESULT_RESERVOIR_BUFFER` candidates,
    # so there are real spares once dead pages get dropped further down.
    reservoir_limit = limit + RESULT_RESERVOIR_BUFFER

    with ThreadPoolExecutor(max_workers=2) as pool:
        arkan_future = pool.submit(
            search_arkan, area, transaction_type, property_type,
            min_price, max_price, bedrooms, reservoir_limit,
        )
        market_future = None
        if include_public_sources:
            market_future = pool.submit(
                search_market, area, transaction_type, property_type,
                bedrooms, reservoir_limit,
            )

        arkan_out = arkan_future.result()
        market_out = market_future.result() if market_future is not None else {
            "results": [], "olx_search_url": None, "close_matches": [],
            "reached": False,
        }

    seen_keys = set()
    domain_counts = {}

    def _dedupe_key(item):
        parsed = urlparse(item["url"])
        domain = parsed.netloc.lower()
        return domain, parsed.path.rstrip("/")

    def _add(item, bucket, force=False):
        key = _dedupe_key(item)
        if key in seen_keys:
            return False
        domain = key[0]
        # See MAX_RESULTS_PER_DOMAIN's 2026-09-01 docstring -- force=True
        # (only ever passed by _rank_and_fill's own overflow pass) bypasses
        # the per-domain cap, never the dedupe check above.
        if not force and domain_counts.get(domain, 0) >= MAX_RESULTS_PER_DOMAIN:
            return False
        seen_keys.add(key)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        item.setdefault("domain", domain)
        bucket.append(item)
        return True

    # `reservoir_limit` was already computed above (before search_arkan()/
    # search_market() were called, so it could be passed to them too) --
    # still exactly what it was before: `limit` plus RESULT_RESERVOIR_BUFFER
    # of real spares for _finalize_and_enrich() below to pull from if a
    # candidate's own page turns out to be broken, without ever bumping a
    # spare ahead of a genuinely better-ranked result.
    merged = []
    _rank_and_fill(
        merged, arkan_out.get("results", []), market_out.get("results", []),
        bedrooms, min_price, max_price, reservoir_limit, _add,
    )

    # A bedroom count was requested but confirmed exact matches alone are
    # thin -- top the list up with the best of the real, honestly-labeled
    # close matches (see search_arkan/search_market/_resolve_bedrooms),
    # ranked the same way, rather than leaving the reply with little or
    # nothing to actually show.
    if bedrooms and len(merged) < reservoir_limit:
        _rank_and_fill(
            merged, arkan_out.get("close_matches", []),
            market_out.get("close_matches", []),
            bedrooms, min_price, max_price, reservoir_limit, _add,
        )

    # Final pass: drop anything that turns out to be a broken/blank page
    # and backfill a thumbnail for whatever candidate doesn't already have
    # one -- see _finalize_and_enrich(). Changed 2026-09-03: this no
    # longer trims to `limit` itself (see that function's own docstring)
    # -- _ensure_priority_domains() below needs the full, still-oversized,
    # already-alive-filtered reservoir to promote from, and the actual
    # trim to `limit` happens after that runs.
    merged = _finalize_and_enrich(merged)

    # Guarantees Arkan Estate and Confidence Real Estate each appear at
    # least once in the reply whenever either has a real, live result
    # anywhere in the ranked pool -- see PRIORITY_DOMAINS and
    # _ensure_priority_domains()'s own docstring, and module docstring's
    # 2026-09-03 section for why this explicit exception to "no site is
    # ever favored" exists (the user asked for it directly). Runs AFTER
    # ranking and dead-page filtering, so it only ever promotes a
    # confirmed-alive candidate, never a fabricated one. Passes
    # _rescue_priority_domain() as a deeper fallback (added 2026-09-04,
    # see module docstring's "STILL NOT SHOWING ARKAN" section) for when a
    # priority domain's real candidates never made it into `merged` at all
    # -- arkan_out/market_out are still the exact raw per-source output
    # from earlier in this same request, so this never re-searches or
    # fabricates anything.
    merged = _ensure_priority_domains(
        merged, limit,
        rescue_fn=lambda domain: _rescue_priority_domain(domain, arkan_out, market_out),
    )
    merged = merged[:limit]

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
