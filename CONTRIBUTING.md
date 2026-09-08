# Getting a channel listed

This directory indexes history and archaeology creators by **the period and the
place their videos are about** — not by upload date. That is the whole point of
it, and it shapes what can go in.

There are three ways to contribute, in increasing order of effort.

## 1. Open an issue (easiest)

Use one of the two forms:

* **[Add a creator](../../issues/new?template=add-channel.yml)** — you give a
  channel URL or `@handle`, a language and a one-line focus.
* **[Add a video or reel](../../issues/new?template=add-video.yml)** — you give a
  video URL plus the period and place it covers.

A bot picks the issue up, checks it against the platform, and **opens a pull
request** for a human to review. If it cannot verify something it comments on the
issue explaining exactly what went wrong, and you can edit the issue to retry.

What the bot fills in for you, so you never have to type it:

| | |
| --- | --- |
| Channel id | resolved from the handle via the channel's own canonical link |
| Creator name | read from the channel's Atom feed |
| Video title | read from YouTube's oEmbed endpoint |
| Upload date | read from the channel feed |
| Format (`youtube` / `reel`) | resolved by checking whether the id lives under `/shorts/` |
| Thumbnail | derived from the video id |

What **you** have to supply, because no machine can read it off the platform:

* `year_start` and `year_end` — the years the *content* is about. Negative is BCE.
* `era` — a human label for that span, e.g. `Late Bronze Age Collapse`.
* `places` — ids from [`data/places.csv`](data/places.csv), or a new place with
  coordinates.

## 2. Send a pull request

Edit the CSVs directly and run the validator before you push:

```bash
python3 tools/validate.py
```

CI runs the same check on every pull request, and the site will not deploy if it
fails.

## 3. Promote something from "Latest uploads"

Open any creator's profile panel on the site. If the weekly sweep has found
uploads that nobody has indexed, they appear under **Latest uploads** — real
videos with no period or place attached yet. Picking one off that list and
giving it a `year_start`, `year_end`, `era` and `places` is the single most
useful thing you can do here.

## 4. Add a whole channel's back catalogue

Add the creator first (issue or PR), then let the weekly sweep list their
uploads:

```bash
python3 tools/refresh_feeds.py --deep --csv >> data/videos.csv
```

`--deep` reads the channel's videos and shorts tabs. Without it you only see the
latest 15 uploads, which is how a back catalogue stays invisible.

That writes skeleton rows with the period and place columns blank and
`verified=no`. Fill them in, then run the validator. Do not leave blank rows in a
pull request.

---

## What gets listed

**Yes:**

* Creators whose subject is the human past and who talk about identifiable
  periods and places.
* Any language. The directory is not English-only, and non-English creators are
  actively wanted — titles stay in the original language, because that is what
  you would search for.
* Any format. Reels and Shorts are first-class here, not an afterthought.
* Institutional channels (a museum, a national archaeology body) as well as
  individuals.

**No:**

* Channels with no datable subject — pure commentary, reaction, or news about the
  present.
* Content presenting pseudo-archaeology as fact. Debunking *of* it is welcome and
  well represented.

**Judgement calls** get recorded rather than hidden. If a period is your reading
rather than something the video states, say so in `notes`. If a place stands in
for a whole region, say that too. Roughly a tenth of the index has no place at
all, because the subject genuinely has no single site — those items filter by
time but never appear on the map, and that is correct behaviour, not a gap.

## What `verified` means

`verified=yes` means the **link, title, creator and upload date** are confirmed
against the platform. It does **not** mean anyone watched the video to check the
period and place. Those stay editorial, which is exactly why a human reviews
every bot-opened pull request.

## Adding a place

Places live once in [`data/places.csv`](data/places.csv) and are referenced by id,
so coordinates are not repeated across twenty videos about Pompeii.

```csv
id,name,lat,lon,country,wikidata
lerna,Lerna,37.5583,22.7167,Greece,Q1362321
```

Do not type coordinates from memory — that is how a marker ends up in the wrong
county. Look them up:

```bash
python3 tools/geocode.py "Lerna, Argolis, Greece"
```

`wikidata` is optional — leave it blank rather than guessing a Q-number.

## Removing yourself

If you are a creator and would rather not be listed, open an issue saying so and
we will remove the rows. No justification needed.
