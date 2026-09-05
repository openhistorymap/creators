# History & Archaeology Creator Directory

**Live: https://openhistorymap.github.io/creators/**

A directory of history / archaeology creators where every reel and video is
indexed by **the time period it talks about** and **the places it talks about** —
so you can ask "what has anyone made about the Aegean between 1300 and 1100 BCE?"
rather than "what did this channel upload last month".

211 items from 29 creators in five languages, across 154 places in 41 countries,
spanning 43 000 BCE to 2023.

The whole thing is three CSV files and a static page. There is no server-side
code, no framework, and no build step.

**Want your channel listed?** See [CONTRIBUTING.md](CONTRIBUTING.md) — open an
issue and a bot opens the pull request for you.

```
data/influencers.csv   who the creators are
data/places.csv        the gazetteer (id, name, lat, lon, wikidata)
data/videos.csv        the index: one row per reel / video
index.html app.js style.css   the browser UI (Leaflet + a warped timeline)
tools/validate.py      referential-integrity check over the CSVs
tools/build_sqlite.py  optional: derive directory.db for SQL querying
tools/refresh_feeds.py poll the channels for uploads not yet indexed
tools/issue_to_row.py  turn a submission issue into validated CSV rows
```

## Run it

```bash
./serve.sh            # http://localhost:8088/
```

The page `fetch()`es the CSVs, so opening `index.html` over `file://` will not
work — it needs to be served over HTTP. Any static server does; `serve.sh` is
just `python3 -m http.server`.

## The data model

**`influencers.csv`** — one row per creator.

| column | meaning |
| --- | --- |
| `id` | slug, referenced by `videos.influencer_id` |
| `youtube_channel_id` | canonical `UC...` id — the key `tools/refresh_feeds.py` polls |
| `name`, `handle` | display name and primary @handle |
| `youtube`, `instagram`, `tiktok`, `facebook`, `website` | profile URLs, any may be blank |
| `language` | ISO code of the main language |
| `focus` | free text — what they cover |
| `avatar_url` | optional image URL |
| `verified` | `yes` once the links have been machine-checked |
| `notes` | free text |

**`places.csv`** — the gazetteer. Each place is entered **once** and referenced
by id, so coordinates stay in one place when twenty videos mention Pompeii.
`wikidata` is the Q-number, for later reconciliation against OHM.

**`videos.csv`** — the actual index. One row per item.

| column | meaning |
| --- | --- |
| `id` | slug/serial |
| `influencer_id` | → `influencers.id` |
| `title` | as published |
| `platform` | `youtube`, `reel`, `short`, `tiktok`, `instagram`, `facebook`, `podcast`, `article` |
| `url` | direct link to the item |
| `thumbnail` | optional image URL |
| `published` | upload date, `YYYY-MM-DD`, optional |
| `year_start`, `year_end` | **the period the content is about**, not the upload date. Integers; negative = BCE. Equal values mean a single year. |
| `era` | human label for that span, e.g. `Late Bronze Age` |
| `places` | `;`-separated `places.id` values |
| `tags` | `;`-separated free tags |
| `verified` | `yes` once the URL, title and creator are confirmed (see Provenance) |
| `notes` | free text |

`year_start` / `year_end` are the join key to the rest of OHM: they are plain
years on the same axis the tileservers use, so this directory can later be
overlaid on OHM map layers without a conversion step.

## Adding an entry

1. If the creator is new, add a row to `data/influencers.csv`.
2. If a place is new, add a row to `data/places.csv` (get lat/lon and the
   Q-number from Wikidata).
3. Add a row to `data/videos.csv` referencing both.
4. `python3 tools/validate.py`

The validator checks for duplicate ids, dangling `influencer_id` / place
references, reversed or non-numeric year spans, out-of-range coordinates,
relative URLs, and unknown platform values. It exits non-zero on errors;
warnings (a video with no place, an unused gazetteer entry) do not fail.

## Optional SQLite view

```bash
python3 tools/build_sqlite.py     # → directory.db
sqlite3 -header -column directory.db \
  "SELECT title, creator, year_start, year_end, places FROM v_directory
   WHERE year_start < -1000;"
```

`directory.db` is a **derived, disposable artifact** — the CSVs remain the source
of truth. The schema normalises `places` and `tags` into `video_places` and
`video_tags` join tables and exposes a flattened `v_directory` view.

## The timeline

The year axis is cube-root warped: a linear axis from the Palaeolithic to now
would compress everything after 3000 BCE into the last few percent of the bar.
The warp gives recorded history a third of the bar while still reaching −50 000,
which is where the oldest indexed item (the Aurignacian) sits. The
histogram behind the slider counts items whose span overlaps each bucket, and
responds to every filter except the year range itself.

## Provenance of the data

The 211 items are **real videos, verified end to end**, from 29 creators in five
languages (English, French, German, Italian, Spanish):

* Each creator's YouTube handle was resolved to a canonical `youtube_channel_id`
  by reading the `rel="canonical"` link on the channel page. Three of the handles
  first guessed from memory were wrong and were corrected this way
  (`@miniminuteman` is a different person; Metatron's history channel is
  `@Metatronrealhistory`; `@Premodernist` does not exist, it is
  `@premodernist_history`).
* Titles, video ids and publication dates come from each channel's own Atom feed
  (`youtube.com/feeds/videos.xml?channel_id=...`), so nothing is transcribed by
  hand and no item can be attributed to the wrong creator.
* Every row was then re-checked against YouTube's oEmbed endpoint: 210 of 211
  URLs resolve, each title matches the feed exactly, and each `author_name`
  matches the creator the row is attributed to. The one exception (`v138`,
  Time Team Classics) has embedding disabled, which makes oEmbed return 401; it
  was confirmed live on its watch page instead and its `notes` say so.
* `platform` is set from whether the id resolves under `/shorts/` — 69 of the
  items are Shorts or reels, 142 long-form.

**What `verified=yes` does and does not mean.** It means the *link, title,
creator and publication date* are confirmed. It does **not** mean someone watched
the video to confirm the period and place: `year_start`, `year_end`, `era` and
`places` are editorial readings of the subject, and where the reading is loose or
a place stands in for a region, the `notes` column says so. Twenty items are
deliberately left with no place — a survey video, or a subject with no single
site — and those simply do not appear on the map.

Archaeosoup is listed as a creator but has no items: the channel resolves, but
its feed returns no recent uploads.

**Language coverage.** 17 anglophone creators (140 items), 5 French (30),
3 German (17), 2 Italian (13), 2 Spanish (11). `influencers.csv` carries the
`language` code and the UI filters on it. The non-English creators are indexed
with their **original titles**, untranslated — the title is what you would search
for on the platform, so translating it would make the row harder to find, not
easier. The `era` and `tags` columns stay in English so they remain a shared
index across languages.

Note that reach is uneven by design of the sources, not of the field: French
archaeology is well served by Inrap, the national preventive-archaeology
institute, whose films are site-by-site and so map unusually cleanly. A few
Inrap entries are `Version LSF` — French sign-language versions of a site film —
which is recorded in `notes`.

**Platforms other than YouTube.** A creator row can carry `instagram`, `tiktok`
and `facebook` links, but only YouTube exposes a public per-channel feed. Meta
and TikTok put individual reel permalinks behind a login wall, so for a
reel-first creator the profile is recorded on the creator row while the indexed
*items* are whatever is publicly enumerable — usually their YouTube Shorts.
Facebook and TikTok reels can still be added by hand, one row at a time, with a
permalink copied from the app.

## Keeping it current

```bash
python3 tools/refresh_feeds.py          # list uploads not yet indexed
python3 tools/refresh_feeds.py --csv    # same, as skeleton rows to paste in
```

It only reports; it never edits the CSVs, because deciding the period and place
of a new video is a judgement call. It also re-checks that each feed is still
titled what `influencers.csv` expects, which is what caught the wrong channel ids
in the first place.

## Automation

Four workflows, in `.github/workflows/`:

| Workflow | Trigger | What it does |
| --- | --- | --- |
| `validate.yml` | every push and PR | runs `tools/validate.py` and the SQLite build |
| `pages.yml` | push to `main` | validates, assembles `_site/`, deploys to GitHub Pages |
| `submission.yml` | issue labelled `add-channel` / `add-item` | runs `tools/issue_to_row.py`, opens a PR, or comments the error back on the issue |
| `refresh.yml` | Mondays 06:17 UTC | sweeps every channel feed and files one issue listing uploads that are not indexed |

The submission bot **prepares**, a human **merges**. It resolves the channel id,
reads the real title and upload date, works out whether the item is a Short, and
refuses anything it cannot verify — but the period and place it writes are the
submitter's claim, and that is what a reviewer is there to check.

The issue body is untrusted input: it is passed to the script through an
environment variable and a file, never interpolated into a shell command. The
parser is stdlib-only, so there is no third-party action in the path that writes
to the data.
