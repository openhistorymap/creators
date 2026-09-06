#!/usr/bin/env python3
"""List a channel's videos tab, beyond the 15 the RSS feed exposes.

    python3 tools/channel_videos.py @handle
    python3 tools/channel_videos.py UCxxxxxxxxxxxxxxxxxxxxxx --tab shorts

The Atom feed at /feeds/videos.xml only carries the latest 15 uploads, so a
back catalogue is invisible to tools/refresh_feeds.py. This reads the channel
page's embedded ytInitialData instead.

YouTube now renders each entry as a `lockupViewModel`: the id is `contentId`,
not `videoId`, and the duration is a thumbnail badge. Both shapes are handled.
Output is TSV: video_id, duration, title.
"""
import argparse
import json
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def initial_data(html):
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not m:
        m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", html, re.S)
    if not m:
        raise SystemExit("could not find ytInitialData on the page")
    return json.loads(m.group(1))


def text_of(node):
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    if "content" in node and isinstance(node["content"], str):
        return node["content"]
    return "".join(r.get("text", "") for r in node.get("runs", [])
                   if isinstance(r, dict))


DUR = re.compile(r'"text":\s*"(\d{1,3}:\d{2}(?::\d{2})?)"')


def harvest(data):
    out = {}

    def walk(o):
        if isinstance(o, dict):
            lv = o.get("lockupViewModel")
            if isinstance(lv, dict):
                vid = lv.get("contentId")
                meta = (lv.get("metadata") or {}).get("lockupMetadataViewModel", {})
                title = text_of(meta.get("title") or {})
                m = DUR.search(json.dumps(lv))
                if vid and title and vid not in out:
                    out[vid] = (m.group(1) if m else "", title)
            # older shape
            vid = o.get("videoId")
            if isinstance(vid, str) and len(vid) == 11 and vid not in out:
                title = text_of(o.get("title") or {})
                if title:
                    out[vid] = (text_of(o.get("lengthText") or {}), title)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("channel", help="@handle, UC... id, or a full channel URL")
    ap.add_argument("--tab", default="videos", choices=["videos", "shorts", "streams"])
    ap.add_argument("--min-seconds", type=int, default=0,
                    help="only list entries at least this long (needs a duration)")
    args = ap.parse_args()

    c = args.channel
    if c.startswith("http"):
        base = c.rstrip("/")
    elif c.startswith("UC") and len(c) == 24:
        base = "https://www.youtube.com/channel/" + c
    else:
        base = "https://www.youtube.com/@" + c.lstrip("@")

    items = harvest(initial_data(fetch(base + "/" + args.tab)))

    def secs(d):
        if not d:
            return 0
        p = [int(x) for x in d.split(":")]
        return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1]

    n = 0
    for vid, (dur, title) in items.items():
        if args.min_seconds and secs(dur) < args.min_seconds:
            continue
        sys.stdout.write("%s\t%s\t%s\n" % (vid, dur or "-", title))
        n += 1
    print("# %d entries from %s/%s" % (n, base, args.tab), file=sys.stderr)


if __name__ == "__main__":
    main()
