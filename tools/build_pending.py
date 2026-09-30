#!/usr/bin/env python3
"""Write data/pending.csv: recent uploads that are not indexed yet.

    python3 tools/build_pending.py

Runs weekly in CI. It reads each creator's Atom feed — which carries publication
dates, unlike the videos tab — drops anything already in videos.csv, and writes
what is left.

These rows deliberately carry **no period and no place**. Working those out is a
human judgement, so pending.csv is a "here is what is new" list, not an index.
The site shows it inside a creator's profile panel, clearly separated from the
indexed items, and nothing in it reaches the map or the timeline.
"""
import csv
import io
import os
import re
import sys
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET

NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HEAD = ["influencer_id", "video_id", "title", "published", "url", "thumbnail"]
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
PER_CREATOR = 8          # keep the panel a summary, not a second index


# YouTube's /feeds/videos.xml answered normally on 28 September 2026 and began
# returning 404 and 500 for almost every channel on 30 September, from both a
# home host and GitHub runners. Whether that is a withdrawal, a bug or a very
# wide block is not knowable from here — so the tab fallback now resolves real
# upload dates and is a first-class path rather than a degraded one. The only
# remaining tripwire is producing nothing at all.


def fetch_feed(channel_id, attempts=3):
    """Read a channel's Atom feed, retrying before giving up.

    YouTube will start answering 404 and 500 to a host that has been making a lot
    of requests, for channels whose feeds are perfectly healthy from elsewhere.
    A single failure therefore means very little.
    """
    last = None
    for i in range(attempts):
        try:
            return ET.fromstring(urllib.request.urlopen(FEED % channel_id, timeout=25).read())
        except Exception as e:
            last = e
            if i + 1 < attempts:
                time.sleep(2 * (i + 1))
    raise last


def publish_date(video_id):
    """Exact upload date from the watch page.

    The videos tab gives only a relative time ("3 weeks ago"), which is no use in
    a dataset, so each kept video is resolved individually. Bounded by
    PER_CREATOR, not by the size of the catalogue.
    """
    try:
        req = urllib.request.Request("https://www.youtube.com/watch?v=" + video_id,
                                     headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")
        m = re.search(r'"publishDate":"(\d{4}-\d{2}-\d{2})', html)
        return m.group(1) if m else ""
    except Exception:
        return ""


def from_videos_tab(channel_id):
    """Every video a channel lists, when its Atom feed will not answer."""
    out = []
    for tab in ("videos", "shorts"):
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(ROOT, "tools", "channel_videos.py"),
                 channel_id, "--tab", tab],
                capture_output=True, text=True, timeout=90)
            for line in r.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 3:
                    out.append((parts[0], parts[2]))
        except Exception as e:
            print("-- %s %s: %s" % (channel_id, tab, e), file=sys.stderr)
    return out


def main():
    creators = list(csv.DictReader(open(os.path.join(DATA, "influencers.csv"),
                                        encoding="utf-8")))
    videos = list(csv.DictReader(open(os.path.join(DATA, "videos.csv"),
                                      encoding="utf-8")))
    known = {v["url"].rsplit("v=", 1)[-1] for v in videos}

    out = []
    fell_back = []
    considered = 0
    for c in creators:
        cid = (c.get("youtube_channel_id") or "").strip()
        if not cid:
            continue
        considered += 1
        try:
            root = fetch_feed(cid)
        except Exception as e:
            fell_back.append(c["id"])
            print("-- %s: no Atom feed (%s); reading the videos tab instead"
                  % (c["id"], e), file=sys.stderr)
            n = 0
            for vid, title in from_videos_tab(cid):
                if vid in known or n >= PER_CREATOR:
                    continue
                out.append({
                    "influencer_id": c["id"], "video_id": vid, "title": title,
                    "published": publish_date(vid),
                    "url": "https://www.youtube.com/watch?v=" + vid,
                    "thumbnail": "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid,
                })
                n += 1
            continue

        # Compare on letters and digits only: a curly apostrophe or a dropped
        # space is not a channel mismatch.
        def squash(s):
            return re.sub(r"[^a-z0-9]", "", s.lower())

        feed_name = (root.find('a:title', NS).text or "").strip()
        expected = squash(c["name"].split("(")[0])
        if expected not in squash(feed_name) and squash(feed_name) not in squash(c["name"]):
            print("-- %s: WARNING feed titled %r, expected %r"
                  % (c["id"], feed_name, c["name"]), file=sys.stderr)

        n = 0
        for e in root.findall('a:entry', NS):
            vid = e.find('yt:videoId', NS).text
            if vid in known or n >= PER_CREATOR:
                continue
            out.append({
                "influencer_id": c["id"],
                "video_id": vid,
                "title": e.find('a:title', NS).text or "",
                "published": e.find('a:published', NS).text[:10],
                "url": "https://www.youtube.com/watch?v=" + vid,
                "thumbnail": "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid,
            })
            n += 1

    if considered and not out:
        print("ABORT: %d creators checked and nothing came back from either the "
              "feeds or the videos tabs. Refusing to overwrite data/pending.csv "
              "with an empty file." % considered, file=sys.stderr)
        return 0        # a correct no-op, not a failure

    # The invariant that actually matters, whatever the cause: never trade dated
    # rows for undated ones. A throttled run, a withdrawn endpoint and a YouTube
    # outage all look different in the logs but identical in the data, and this
    # catches all three.
    existing = os.path.join(DATA, "pending.csv")
    if os.path.exists(existing):
        was = list(csv.DictReader(open(existing, encoding="utf-8")))
        if was:
            before = sum(1 for r in was if (r.get("published") or "").strip()) / float(len(was))
            after = sum(1 for r in out if r["published"]) / float(len(out))
            if after < before - 0.05:
                print("ABORT: %.0f%% of the new rows carry an upload date against "
                      "%.0f%% of the rows already committed. Refusing to make the "
                      "data worse; leaving data/pending.csv as it is."
                      % (after * 100, before * 100), file=sys.stderr)
                return 0

    out.sort(key=lambda r: (r["influencer_id"], r["published"]), reverse=False)
    with io.open(os.path.join(DATA, "pending.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print("pending.csv: %d uploads across %d creators%s"
          % (len(out), len({r["influencer_id"] for r in out}),
             " (%d via the videos tab)" % len(fell_back) if fell_back else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
