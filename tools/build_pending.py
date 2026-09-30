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
PER_CREATOR = 8          # keep the panel a summary, not a second index


# If this share of creators falls back, the feed endpoint is not broken for them
# individually — this host is being throttled. Writing that run's output would
# replace good dated rows with dateless ones, so abort instead.
FALLBACK_ABORT_RATIO = 0.25


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


def from_videos_tab(channel_id):
    """Fallback for a channel whose Atom feed will not answer.

    The tab carries no publication dates, so those come back empty — which is why
    this is a fallback and not the default.
    """
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
                    "published": "",
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

    if considered and len(fell_back) > considered * FALLBACK_ABORT_RATIO:
        print("ABORT: %d of %d creators fell back to the videos tab. That is a "
              "throttled host, not %d broken feeds — refusing to overwrite "
              "data/pending.csv with dateless rows."
              % (len(fell_back), considered, len(fell_back)), file=sys.stderr)
        # Not an error: declining to write is the correct outcome. Exiting
        # non-zero here would fail the whole weekly job, including the backlog
        # issue, over a condition that resolves itself.
        return 0

    out.sort(key=lambda r: (r["influencer_id"], r["published"]), reverse=False)
    with io.open(os.path.join(DATA, "pending.csv"), "w",
                 encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print("pending.csv: %d uploads across %d creators%s"
          % (len(out), len({r["influencer_id"] for r in out}),
             " (%d via the videos tab, no dates)" % len(fell_back) if fell_back else ""),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
