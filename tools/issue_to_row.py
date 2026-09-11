#!/usr/bin/env python3
"""Turn a submission issue into CSV rows.

    python3 tools/issue_to_row.py --type channel --body-file body.md
    python3 tools/issue_to_row.py --type item    --body-file body.md

Reads a GitHub issue-form body, checks the submission against the platform
itself, and appends validated rows to data/. Anything it cannot verify is a hard
error — the point is that a human reviews a *correct* pull request, not that the
bot guesses.

No third-party dependencies: stdlib only, so there is no action supply chain to
trust. Network is used only to read public YouTube endpoints.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"


class Fail(Exception):
    """A submission problem worth reporting back to the issue author."""


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en"})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_text(url):
    with get(url) as r:
        return r.read().decode("utf-8", "replace")


# ---------------------------------------------------------------- issue body

def parse_form(body):
    """GitHub issue forms render as '### Label\\n\\nvalue'. Key by squashed label."""
    out, key, buf = {}, None, []
    for line in (body or "").replace("\r\n", "\n").split("\n"):
        if line.startswith("### "):
            if key:
                out[key] = "\n".join(buf).strip()
            key = re.sub(r"[^a-z0-9]", "", line[4:].lower())
            buf = []
        elif key:
            buf.append(line)
    if key:
        out[key] = "\n".join(buf).strip()
    for k, v in list(out.items()):
        if v in ("_No response_", "_No response*_", "None"):
            out[k] = ""
    return out


def field(form, *names, **kw):
    for n in names:
        if form.get(n):
            return form[n].strip()
    if kw.get("required"):
        raise Fail("missing required field: **%s**" % names[0])
    return kw.get("default", "")


# ------------------------------------------------------------------- csv io

def read(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows


def write(name, rows, header):
    with io.open(os.path.join(DATA, name), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:48] or "creator"


# --------------------------------------------------------------- youtube io

def resolve_channel(url_or_handle):
    """A channel URL or @handle -> (channel_id, name). Verified against its feed."""
    s = url_or_handle.strip()
    m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{22})", s)
    if m:
        cid = m.group(1)
    else:
        handle = s
        m = re.search(r"youtube\.com/@([A-Za-z0-9._-]+)", s)
        if m:
            handle = m.group(1)
        handle = handle.lstrip("@").split("/")[0]
        if not handle or not re.match(r"^[A-Za-z0-9._-]+$", handle):
            raise Fail("could not read a channel handle out of `%s`" % s)
        try:
            page = fetch_text("https://www.youtube.com/@" + urllib.parse.quote(handle))
        except urllib.error.HTTPError as e:
            raise Fail("`@%s` does not resolve on YouTube (HTTP %s)" % (handle, e.code))
        # The page links to other channels too, so take the CANONICAL link only.
        m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/channel/'
                      r'(UC[A-Za-z0-9_-]{22})">', page)
        if not m:
            raise Fail("found `@%s` but could not read its canonical channel id" % handle)
        cid = m.group(1)

    feed = fetch_text(FEED % cid)
    m = re.search(r"<title>([^<]*)</title>", feed)
    if not m:
        raise Fail("channel `%s` has no readable feed" % cid)
    return cid, m.group(1).strip()


def oembed(video_url):
    u = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
        {"url": video_url, "format": "json"})
    try:
        with get(u) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise Fail("YouTube will not confirm this video through oEmbed "
                       "(embedding is disabled). Add it by hand in a pull request, "
                       "with a note saying how it was checked.")
        raise Fail("that video does not resolve (HTTP %s)" % e.code)


TIKTOK_OEMBED = "https://www.tiktok.com/oembed?url="


def tiktok_oembed(url):
    """Verify a TikTok permalink. No auth needed, and a fabricated id 400s.

    TikTok has no public per-account feed, so a whole channel cannot be swept
    the way a YouTube one can — but a single permalink a human supplies can be
    checked properly, which is all this pipeline needs.
    """
    try:
        with get(TIKTOK_OEMBED + urllib.parse.quote(url, safe="")) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise Fail("TikTok does not recognise that link. Check the URL is a "
                       "video permalink, not a profile or a short share link.")
        raise Fail("that TikTok link does not resolve (HTTP %s)" % e.code)


def tiktok_id_of(url):
    m = re.search(r"tiktok\.com/@[A-Za-z0-9._-]+/video/(\d{6,25})", url)
    if not m:
        raise Fail("could not read a TikTok video id out of `%s`. A share link "
                   "like vm.tiktok.com/... needs expanding to its full "
                   "/@user/video/... form first." % url)
    return m.group(1)


def is_reel(video_id):
    try:
        with get("https://www.youtube.com/shorts/" + video_id) as r:
            return "/shorts/" in r.geturl()
    except Exception:
        return False


def video_id_of(url):
    m = (re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
         or re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
         or re.search(r"/shorts/([A-Za-z0-9_-]{11})", url))
    if not m:
        raise Fail("could not read a video id out of `%s`" % url)
    return m.group(1)


def published_of(channel_id, video_id):
    try:
        feed = fetch_text(FEED % channel_id)
    except Exception:
        return ""
    m = re.search(r"<yt:videoId>%s</yt:videoId>.*?<published>(\d{4}-\d{2}-\d{2})"
                  % re.escape(video_id), feed, re.S)
    return m.group(1) if m else ""


# ------------------------------------------------------------------ handlers

def add_channel(form):
    creators = read("influencers.csv")
    header = list(creators[0].keys())

    cid, feed_name = resolve_channel(field(form, "channelurlorhandle", required=True))
    if any((c.get("youtube_channel_id") or "") == cid for c in creators):
        existing = next(c for c in creators if c["youtube_channel_id"] == cid)
        raise Fail("already listed as **%s** (`%s`)" % (existing["name"], existing["id"]))

    slug = slugify(feed_name)
    taken = {c["id"] for c in creators}
    base, i = slug, 2
    while slug in taken:
        slug, i = "%s-%d" % (base, i), i + 1

    handle = field(form, "channelurlorhandle")
    m = re.search(r"youtube\.com/@([A-Za-z0-9._-]+)", handle)
    handle = "@" + (m.group(1) if m else handle.lstrip("@").split("/")[0])

    row = {k: "" for k in header}
    row.update({
        "id": slug,
        "name": feed_name,
        "handle": handle,
        "youtube_channel_id": cid,
        "youtube": "https://www.youtube.com/" + handle,
        "instagram": field(form, "instagramurl"),
        "tiktok": field(form, "tiktokurl"),
        "facebook": field(form, "facebookurl"),
        "website": field(form, "website"),
        "language": field(form, "language", required=True).lower()[:5],
        "focus": field(form, "focus", required=True).replace("\n", " "),
        "verified": "yes",
        "notes": field(form, "anythingelse").replace("\n", " "),
    })
    creators.append(row)
    write("influencers.csv", creators, header)
    return ("Added creator **%s** (`%s`)\n\n"
            "- channel id `%s`, confirmed by reading its own feed\n"
            "- language `%s`\n\n"
            "No items were indexed. Open an **Add a video or reel** issue for each "
            "item, or let the weekly feed sweep list their uploads."
            % (row["name"], slug, cid, row["language"]))


def add_item(form):
    creators = read("influencers.csv")
    places = read("places.csv")
    videos = read("videos.csv")
    vheader, pheader = list(videos[0].keys()), list(places[0].keys())

    url = field(form, "videourl", required=True)

    def norm(s):
        return re.sub(r"[^a-z0-9]", "", (s or "").lower())

    if "tiktok.com" in url:
        tid = tiktok_id_of(url)
        if any(tid in v["url"] for v in videos):
            raise Fail("that video is already in the index")
        meta = tiktok_oembed(url)
        handle = (meta.get("author_unique_id") or "").strip()
        canonical = "https://www.tiktok.com/@%s/video/%s" % (handle, tid)
        platform = "tiktok"
        thumb = meta.get("thumbnail_url", "")
        published = ""          # TikTok oEmbed carries no publication date
        # Match on the creator's recorded TikTok handle, not on display name:
        # TikTok display names rarely match the channel name we list.
        creator = next((c for c in creators
                        if handle and handle.lower() in (c.get("tiktok") or "").lower()), None)
        if creator is None:
            raise Fail("this TikTok is by **@%s**, and no listed creator has that "
                       "handle in their `tiktok` column. Open an **Add a creator** "
                       "issue first, or add the handle to the existing creator row."
                       % (handle or "unknown"))
    else:
        vid = video_id_of(url)
        canonical = "https://www.youtube.com/watch?v=" + vid
        if any(v["url"].rsplit("v=", 1)[-1] == vid for v in videos):
            raise Fail("that video is already in the index")
        meta = oembed(canonical)
        platform = "reel" if is_reel(vid) else "youtube"
        thumb = "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid
        author = (meta.get("author_name") or "").strip()
        creator = next((c for c in creators if norm(c["name"]) == norm(author)), None)
        if creator is None:
            creator = next((c for c in creators
                            if norm(author) and norm(author) in norm(c["name"])), None)
        if creator is None:
            raise Fail("this video is by **%s**, who is not listed yet. Open an "
                       "**Add a creator** issue first." % (author or "an unknown channel"))
        published = published_of(creator.get("youtube_channel_id", ""), vid)

    try:
        y0 = int(float(field(form, "periodstartyear", required=True)))
        y1 = int(float(field(form, "periodendyear", required=True)))
    except ValueError:
        raise Fail("the period years must be whole numbers, negative for BCE")
    if y1 < y0:
        raise Fail("the period end (%d) is before the start (%d)" % (y1, y0))

    # new places first, so the ids they define can be referenced below
    added = []
    for line in field(form, "newplaces").split("\n"):
        line = line.strip().strip(",")
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            raise Fail("new place `%s` should be `id,Name,lat,lon,Country`" % line)
        pid, pname, plat, plon = parts[0], parts[1], parts[2], parts[3]
        country = parts[4] if len(parts) > 4 else ""
        if not re.match(r"^[a-z0-9-]+$", pid):
            raise Fail("place id `%s` should be lowercase letters, digits and dashes" % pid)
        if any(p["id"] == pid for p in places):
            raise Fail("place id `%s` already exists" % pid)
        try:
            flat, flon = float(plat), float(plon)
        except ValueError:
            raise Fail("place `%s` has non-numeric coordinates" % pid)
        if not (-90 <= flat <= 90 and -180 <= flon <= 180):
            raise Fail("place `%s` has out-of-range coordinates" % pid)
        prow = {k: "" for k in pheader}
        prow.update({"id": pid, "name": pname, "lat": plat, "lon": plon,
                     "country": country})
        places.append(prow)
        added.append(pid)

    known = {p["id"] for p in places}
    pids = [p.strip() for p in field(form, "placeids").split(";") if p.strip()]
    unknown = [p for p in pids if p not in known]
    if unknown:
        raise Fail("unknown place id(s): %s. Add them in the **New places** field, "
                   "or pick from `data/places.csv`."
                   % ", ".join("`%s`" % u for u in unknown))

    row = {k: "" for k in vheader}
    row.update({
        "id": "",
        "influencer_id": creator["id"],
        "title": meta.get("title", "").strip(),
        "platform": platform,
        "url": canonical,
        "thumbnail": thumb,
        "published": published,
        "year_start": y0,
        "year_end": y1,
        "era": field(form, "eralabel", required=True).replace("\n", " "),
        "places": ";".join(pids),
        "tags": ";".join(t.strip().lower() for t in field(form, "tags").split(";")
                         if t.strip()),
        "verified": "yes",
        "notes": field(form, "notes").replace("\n", " "),
    })
    videos.append(row)
    videos.sort(key=lambda r: (int(r["year_start"]), int(r["year_end"])))
    for i, r in enumerate(videos, 1):
        r["id"] = "v%03d" % i

    if added:
        write("places.csv", places, pheader)
    write("videos.csv", videos, vheader)

    return ("Added **%s**\n\n"
            "- creator: %s\n- format: `%s`\n- period: %s to %s (%s)\n"
            "- places: %s\n%s\n"
            "Title, creator and format were read from the platform, not from the issue."
            % (row["title"], creator["name"], row["platform"], y0, y1, row["era"],
               ", ".join("`%s`" % p for p in pids) or "_none_",
               ("- new places added: %s\n" % ", ".join("`%s`" % p for p in added))
               if added else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", required=True, choices=["channel", "item"])
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--summary-file", default="")
    args = ap.parse_args()

    with open(args.body_file, encoding="utf-8") as fh:
        form = parse_form(fh.read())

    try:
        summary = add_channel(form) if args.type == "channel" else add_item(form)
    except Fail as e:
        msg = "Could not process this submission: %s" % e
        if args.summary_file:
            with io.open(args.summary_file, "w", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        print(msg, file=sys.stderr)
        return 1

    if args.summary_file:
        with io.open(args.summary_file, "w", encoding="utf-8") as fh:
            fh.write(summary + "\n")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
