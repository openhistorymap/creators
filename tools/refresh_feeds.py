#!/usr/bin/env python3
"""List uploads that are not yet in videos.csv.

Usage:  python3 tools/refresh_feeds.py [--csv] [--deep]

By default this reads each creator's Atom feed, which is fast but only carries
their latest 15 uploads — a back catalogue is invisible to it. --deep reads the
videos and shorts tabs instead (via tools/channel_videos.py), which is slower
but sees everything the channel lists.

Prints candidates only; it never edits the CSVs. Adding a row is a judgement call
(what period? what place?) so it stays manual. With --csv it prints skeleton rows
you can paste into data/videos.csv and fill in the year/place columns.
"""
import argparse
import csv
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

NS = {'a': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id=%s"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def deep_list(channel_id):
    """Every video the channel lists, via tools/channel_videos.py."""
    import subprocess
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


def emit(creator, vid, title, pub, args, next_n):
    if args.csv:
        row = ["v%03d" % next_n, creator["id"], title, "youtube",
               "https://www.youtube.com/watch?v=" + vid,
               "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid,
               pub, "", "", "", "", "", "no", "NEEDS period/place"]
        csv.writer(sys.stdout, lineterminator="\n").writerow(row)
    else:
        print("  %s  %s  %s" % (vid, pub or "----------", title))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", action="store_true", help="emit skeleton CSV rows")
    ap.add_argument("--deep", action="store_true",
                    help="read the videos and shorts tabs, not just the 15-entry feed")
    args = ap.parse_args()

    data = os.path.join(ROOT, "data")
    creators = list(csv.DictReader(open(os.path.join(data, "influencers.csv"), encoding="utf-8")))
    videos = list(csv.DictReader(open(os.path.join(data, "videos.csv"), encoding="utf-8")))
    known = {r["url"].rsplit("v=", 1)[-1] for r in videos}
    next_n = max([int(r["id"][1:]) for r in videos] or [0]) + 1

    total = 0
    for c in creators:
        cid = (c.get("youtube_channel_id") or "").strip()
        if not cid:
            print("-- %s: no youtube_channel_id, skipped" % c["id"], file=sys.stderr)
            continue
        if args.deep:
            for vid, title in deep_list(cid):
                if vid in known:
                    continue
                total += 1
                emit(c, vid, title, "", args, next_n)
                next_n += 1
            continue

        try:
            raw = urllib.request.urlopen(FEED % cid, timeout=25).read()
            root = ET.fromstring(raw)
        except Exception as e:
            print("-- %s: feed error %s" % (c["id"], e), file=sys.stderr)
            continue

        feed_name = (root.find('a:title', NS).text or "").strip()
        if feed_name.lower() != c["name"].lower() and c["name"].split("(")[0].strip().lower() not in feed_name.lower():
            print("-- %s: WARNING feed is titled %r, expected %r"
                  % (c["id"], feed_name, c["name"]), file=sys.stderr)

        new = [e for e in root.findall('a:entry', NS)
               if e.find('yt:videoId', NS).text not in known]
        if not new:
            continue
        if not args.csv:
            print("\n### %s (%d new)" % (c["id"], len(new)))
        for e in new:
            vid = e.find('yt:videoId', NS).text
            title = e.find('a:title', NS).text
            pub = e.find('a:published', NS).text[:10]
            total += 1
            if args.csv:
                row = ["v%03d" % next_n, c["id"], title, "youtube",
                       "https://www.youtube.com/watch?v=" + vid,
                       "https://i.ytimg.com/vi/%s/hqdefault.jpg" % vid,
                       pub, "", "", "", "", "", "no", "NEEDS period/place"]
                csv.writer(sys.stdout, lineterminator="\n").writerow(row)
                next_n += 1
            else:
                print("  %s  %s  %s" % (vid, pub, title))

    print("\n%d upload(s) not yet indexed." % total, file=sys.stderr)


if __name__ == "__main__":
    main()
