# Beit — Lebanese Real Estate WhatsApp Agent

A WhatsApp AI agent for the Lebanese real estate market. People text or send
a **voice note** in Arabic/French/English (or a mix — completely normal in
Lebanon), and it:

- searches for properties across the whole Lebanese market in one go —
  Arkan Estate's own listings (surfaced first, as the priority source) plus
  every other agency, broker, and portal reachable via search (OLX/Dubizzle,
  realestate.com.lb, Byootna, and an open web search that catches brokers
  not on that list too — see "On 'all agencies and brokers in Lebanon'" in
  `agent/property_search.py`),
- answers questions on Lebanese real estate law (foreign ownership,
  registration fees, rent law, etc.),
- talks through investment questions (yields, areas, market conditions),
- and knows the character of each area of the country.

It replies by voice if you asked by voice, and by text if you typed —
matching however you reached out.

## Read this first — an honest note on what's verified and what isn't

This was built in a sandboxed cloud session that could not make outbound
requests to arbitrary websites (only package registries and Anthropic's own
API were reachable). That means:

- The **Claude "brain," the tool-calling logic, and the voice pipeline
  logic** were unit-tested with synthetic data and work as designed (see the
  test snippets used during the build — the parsing logic for a listing
  card correctly extracted title/price/link/area from a mock page matching
  Arkan Estate's described structure).
- The **Arkan Estate scraper** (`agent/property_search.py`) is built from a
  structural description of the site (repeating cards linking to
  `/properties/<slug>/`, a price line, a beds/baths/size line — confirmed
  there's no public API or JSON-LD to rely on instead), but it has **not**
  been run against the live site. The very first time you run a real
  search, sanity-check the results — see "Fixing the Arkan scraper" below
  if it comes back empty.
- **faster-whisper** (speech-to-text) and **edge-tts** (text-to-speech) are
  real, widely-used open libraries and the code around them is standard —
  but the actual model download/synthesis couldn't be exercised end-to-end
  here either, for the same networking reason.

None of this should take more than a few minutes to confirm once you run it
somewhere with normal internet access (your laptop, or a cloud host) — it's
just something I can't hand you as "already tested live," so test it before
you lean on it.

## Architecture

```
WhatsApp user  <-->  Twilio (WhatsApp Sandbox or Business API)
                              |
                              v
                     app.py  (Flask webhook)
                        |         |
              voice note?         text
                        v         v
             agent/voice.py   (as-is)
        (faster-whisper STT)
                        \        /
                         v      v
                  agent/claude_client.py
                (Claude + search_properties tool)
                              |
                              v
                agent/property_search.py
        (Arkan Estate scraper -> public portals fallback)
                              |
                              v
                    reply text (+ voice via
                    edge-tts if input was voice)
```

## Get a real, always-on link (no terminal) — recommended

This puts the exact same code permanently online with a real public URL,
using only your browser — no laptop that has to stay open, no terminal.
Everything on the hosting side is already prepared (`Dockerfile`,
`render.yaml` in this folder auto-configure the server). Three accounts are
involved — GitHub, Render, Twilio — and each one has to be created and
owned by *you*, since that's where billing, login, and control over your
own product live. That's the one part that can't be done on your behalf;
everything else is already built.

**A. Put the code on GitHub (~5 min, no git commands needed)**

1. If you don't have one: create a free account at
   https://github.com/signup.
2. Click the **+** (top right) → **New repository**. Name it e.g.
   `beit-whatsapp-agent`. Public or Private, your choice. Don't check
   "add a README" (this project already has one). Click **Create
   repository**.
3. On the new, empty repo's page, click **uploading an existing file**.
4. On your computer, open the unzipped `lebanon-realestate-whatsapp-agent`
   folder, select everything inside it (all the files, and the `agent`
   folder), and drag them onto that GitHub page. Click **Commit changes**.

**B. Deploy it on Render (~5 min)**

1. Create a free account at https://render.com — signing up with your
   GitHub account also connects the two automatically.
2. Dashboard → **New +** → **Blueprint**.
3. Pick the `beit-whatsapp-agent` repo. Render reads this project's
   `render.yaml` and pre-fills almost everything on its own.
4. It'll ask you to type in three values it deliberately left blank (so
   they never sit inside your code): `ANTHROPIC_API_KEY`,
   `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` — get these from Steps 1-2
   just below if you don't have them yet.
5. Click **Apply**/**Deploy**. The first build takes a few minutes (it's
   installing ffmpeg and everything else). When it's done, Render hands
   you a permanent link like `https://beit-whatsapp-agent.onrender.com`.

   Free-tier note: it sleeps after 15 minutes with no traffic, and the
   next message wakes it back up in 30-60 seconds — fine for a pilot;
   upgrade the instance type later if that delay ever matters.

**C. Connect that link to WhatsApp**

Do Step 2 below to get a Twilio Sandbox number and join it from your
phone, then paste `https://beit-whatsapp-agent.onrender.com/whatsapp`
(your actual Render URL + `/whatsapp`) into Twilio's **"when a message
comes in"** field. Done — the link is real and stays live.

---

## Or: run it yourself locally first (developer path)

Useful for testing changes before pushing them live, or if you'd rather
not use a hosting account yet.

### Prerequisites

- Python 3.10+ and `ffmpeg` installed (`ffmpeg -version` to check; install
  via `brew install ffmpeg` on Mac, `apt install ffmpeg` on Linux, or
  https://ffmpeg.org/download.html on Windows).
- A phone with WhatsApp, to test with.

## Step 1 — Get a Claude API key

1. Go to https://console.anthropic.com, sign up/log in.
2. Settings → API Keys → Create Key. Copy it.

This key gets billed per message the agent handles (typically a fraction of
a cent to a couple of cents per reply on Sonnet — see
https://www.anthropic.com/pricing for current rates). Keep it secret.

## Step 2 — Get WhatsApp working via Twilio's free Sandbox

The Sandbox is the fastest way to test today: free, no business
verification, live in minutes. Its limits: only phone numbers that
explicitly "join" your sandbox can talk to it, and each joined session
expires after 3 days (just re-send the join message). That's fine for
testing; see "Going to production" below for the real, public-facing setup.

1. Sign up free at https://www.twilio.com/try-twilio.
2. In the Twilio Console, find **"Try WhatsApp"** / the **WhatsApp Sandbox**
   (Console → Messaging → Try it out → Send a WhatsApp message). It shows
   you a sandbox number (usually **+1 415 523 8886**) and a join code like
   `join <two-words>`.
3. From your own WhatsApp, send that exact `join <code>` message to that
   number. Twilio confirms you're connected.
4. On the same Sandbox page, note your **Account SID** and **Auth Token**
   (also on your Console dashboard homepage).

## Step 3 — Install and configure

```bash
cd lebanon-realestate-whatsapp-agent
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# now edit .env and fill in ANTHROPIC_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
```

Leave `PUBLIC_BASE_URL` for the next step.

## Step 4 — Run it and expose it publicly

In one terminal:

```bash
python app.py
# Flask starts on http://localhost:5000
```

In a second terminal, get a free public HTTPS URL with `cloudflared`
(no account needed):

```bash
# Mac:    brew install cloudflared
# Linux:  see https://pkg.cloudflare.com/ or download the binary from
#         https://github.com/cloudflare/cloudflared/releases
# Windows: download cloudflared.exe from the same releases page

cloudflared tunnel --url http://localhost:5000
```

It prints a URL like `https://random-words.trycloudflare.com`. Copy it.

Now put that URL into your `.env` as `PUBLIC_BASE_URL` (no trailing slash),
and restart `python app.py` so it picks up the change.

## Step 5 — Point Twilio at your webhook

Back in the Twilio Console's WhatsApp Sandbox settings, find **"When a
message comes in"** and set it to:

```
https://random-words.trycloudflare.com/whatsapp
```

Method: `HTTP POST`. Save.

## Step 6 — Test it

From the WhatsApp number you joined the sandbox with:

- Text it: `Looking for a 2 bedroom apartment in Achrafieh, budget 300k`
- Send a voice note asking the same thing in Lebanese Arabic.
- Ask something legal: `Can a foreigner buy an apartment in Beirut?`
- Ask something investment-y: `Is Batroun a good area to invest in right now?`

You should get a reply in the same medium (text→text, voice→voice) and, for
property questions, real search activity against Arkan Estate.

## Fixing the Arkan scraper (if it comes back empty)

1. Open https://arkanestate.com/properties-for-sale/ in a normal browser.
2. Right-click a listing card → "Inspect". Note the actual container
   element and any class names.
3. In `agent/property_search.py`, the scraper currently keys off any link
   containing `/properties/` (confirmed as the detail-page URL pattern) and
   pulls the surrounding card's text for price/beds/baths. If Arkan has
   changed their markup, adjust the `soup.select(...)` line and the
   `_clean_price` regex accordingly.
4. Quick way to test in isolation without WhatsApp at all:
   ```bash
   python -m agent.property_search Achrafieh
   ```

## Notes on scraping responsibly

- Arkan Estate's `robots.txt` only disallows `/wp-includes/` — the listing
  pages this uses are not disallowed. Still, this hits their site
  live on every search; keep request volume reasonable, and if this becomes
  a real product (not just a prototype), it's worth reaching out to Arkan
  Estate directly about a proper data feed or partnership instead of
  scraping indefinitely.
- The public-portal fallback searches via DuckDuckGo's HTML endpoint rather
  than scraping each portal individually — lighter-weight, but it means
  those results are links + snippets, not structured listings. If you want
  real structured data from a specific portal, that portal would need its
  own scraper or an official API/partnership.

## Costs

- **Anthropic (Claude)**: pay-per-use, current rates at
  anthropic.com/pricing.
- **Twilio Sandbox**: free for testing. A real WhatsApp Business number
  through Twilio costs a small monthly number fee plus per-conversation
  fees once you go to production.
- **faster-whisper, edge-tts**: free/open-source, no API key.
- Running on your own laptop: free. Running on a always-on host: see below.

## Going to production (beyond today's demo)

1. **Real WhatsApp access**: either stay on Twilio but move off the Sandbox
   onto a real Twilio WhatsApp Sender (needs Meta Business verification),
   or apply directly for Meta's WhatsApp Cloud API
   (https://developers.facebook.com/docs/whatsapp/cloud-api). Either path
   needs a verified Meta Business account and a dedicated phone number, and
   involves Meta's review process (usually days, not months, but plan for
   it) plus WhatsApp's 24-hour "session window" and pre-approved message
   template rules for anything sent outside that window.
2. **Always-on hosting**: the "Get a real, always-on link" section above
   already covers this (Render, via the included `Dockerfile` +
   `render.yaml`). Upgrade off the free instance type when the 15-minute
   sleep/cold-start becomes annoying, or move to Railway/Fly.io/a VPS if
   you'd rather — the `Dockerfile` works anywhere that runs Docker images.
3. **Persistent conversation history**: swap the in-memory `HISTORY` dict in
   `app.py` for Redis or a small database so context survives restarts and
   scales across multiple server workers.
4. **Your own listings**: if/when you have your own property inventory
   (spreadsheet, CRM, or database), add a `search_own_listings()` function
   alongside `search_arkan()` in `agent/property_search.py` and have the
   agent check it first — the system prompt in `agent/system_prompt.py`
   already assumes a "priority source first, public fallback second"
   pattern, so it's a small change.
5. **Legal review**: the law/tax content in `agent/system_prompt.py` is
   general information for a demo, fact-checked against public sources as
   of August 2026 (see Sources below) — not legal advice, and rates/rules do
   change. Before this goes out to real customers making real decisions,
   have a Lebanese real estate lawyer review the legal content in the
   system prompt.

## Project files

```
app.py                      Flask webhook (entry point)
agent/system_prompt.py      The agent's domain knowledge (law, investment, areas)
agent/property_search.py    Arkan Estate + wider Lebanese market search
agent/voice.py               STT (faster-whisper) + TTS (edge-tts)
agent/claude_client.py       Claude tool-use loop
requirements.txt
Dockerfile                  Container build (Python + ffmpeg) for hosting
render.yaml                 Render Blueprint -- auto-configures the deploy
.dockerignore / .gitignore
.env.example
```

## Sources used while building this

- [Arkan Real Estate Lebanon](https://arkanestate.com/) — listings source
- [Legal Framework for Ownership of Land in Lebanon (investinlebanon.gov.lb)](https://investinlebanon.gov.lb/Content/uploads/Legal_Framework_for_Ownership_of_Land_in_Lebanon.pdf)
- [Foreign Ownership of Real Estate in Lebanon – Green Titles](https://www.greentitles.com/beirut-real-estate-blog/property-laws/foreign-ownership-of-real-estate-in-lebanon/)
- [Real Estate – Law on Foreign Acquisition – Lebanon | Alem & Associates](https://www.alemlaw.com/news-and-insights/real-estate--law-on-foreign-acquisition--lebanon)
- [Lebanese Parliament Votes On New Rent Law | Blog Baladi](https://blogbaladi.com/lebanese-parliament-votes-on-new-rent-law-old-rent-law-abolished-at-last/)
- [Lebanon Real Estate Market 2026 | rm-realestateconsultant.com](https://rm-realestateconsultant.com/2026/06/01/lebanon-real-estate-market-2026/)
- [Twilio WhatsApp Sandbox docs](https://www.twilio.com/docs/whatsapp/sandbox)
- [Claude model overview (platform.claude.com)](https://platform.claude.com/docs/en/about-claude/models/overview)
