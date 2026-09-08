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
import urllib.request
import xml.etree.ElementTree as ET

NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HEAD = ["influencer_id", "video_id", "title", "published", "url", "thumbnail"]
PER_CREATOR = 8          # keep the panel a summary, not a second index


def main():
    creators = list(csv.DictReader(open(os.path.join(DATA, "influencers.csv"),
                                        encoding="utf-8")))
    videos = list(csv.DictReader(open(os.path.join(DATA, "videos.csv"),
                                      encoding="utf-8")))
    known = {v["url"].rsplit("v=", 1)[-1] for v in videos}

    out = []
    for c in creators:
        cid = (c.get("youtube_channel_id") or "").strip()
        if not cid:
            continue
        try:
            raw = urllib.request.urlopen(FEED % cid, timeout=25).read()
            root = ET.fromstring(raw)
        except Exception as e:
            print("-- %s: feed error %s" % (c["id"], e), file=sys.stderr)
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

    out.sort(key=lambda r: (r["influencer_id"], r["published"]), reverse=False)
    with io.open(os.path.join(DATA, "pending.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print("pending.csv: %d uploads across %d creators"
          % (len(out), len({r["influencer_id"] for r in out})), file=sys.stderr)


if __name__ == "__main__":
    main()
