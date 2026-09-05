#!/usr/bin/env python3
"""Integrity check for the CSV directory.

Usage:  python3 tools/validate.py [--data DIR]

Exits non-zero if any error is found. Warnings do not fail the run.
"""
import argparse
import csv
import os
import sys

REQUIRED = {
    "influencers.csv": ["id", "name", "handle", "youtube_channel_id", "youtube",
                        "instagram", "tiktok", "facebook", "website", "language",
                        "focus", "avatar_url", "verified", "notes"],
    "places.csv": ["id", "name", "lat", "lon", "country", "wikidata"],
    "videos.csv": ["id", "influencer_id", "title", "platform", "url", "thumbnail",
                   "published", "year_start", "year_end", "era", "places", "tags",
                   "verified", "notes"],
}
PLATFORMS = {"youtube", "reel", "short", "tiktok", "instagram", "facebook",
             "podcast", "article"}

errors, warnings = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warnings.append(msg)


def read(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return rows


def check_headers(name, path):
    with open(path, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    missing = [c for c in REQUIRED[name] if c not in header]
    if missing:
        err("%s: missing column(s) %s" % (name, ", ".join(missing)))
    extra = [c for c in header if c not in REQUIRED[name]]
    if extra:
        warn("%s: extra column(s) %s (kept, but the UI ignores them)" % (name, ", ".join(extra)))


def unique_ids(name, rows):
    seen, dupes = set(), set()
    for r in rows:
        rid = (r.get("id") or "").strip()
        if not rid:
            err("%s: row with empty id (%s)" % (name, r.get("name") or r.get("title") or "?"))
        elif rid in seen:
            dupes.add(rid)
        seen.add(rid)
    for d in sorted(dupes):
        err("%s: duplicate id '%s'" % (name, d))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    args = ap.parse_args()
    data = os.path.abspath(args.data)

    paths = {}
    for name in REQUIRED:
        p = os.path.join(data, name)
        if not os.path.exists(p):
            err("missing file: %s" % p)
        else:
            paths[name] = p
    if errors:
        report()
        return 1

    for name, p in paths.items():
        check_headers(name, p)

    creators = read(paths["influencers.csv"])
    places = read(paths["places.csv"])
    videos = read(paths["videos.csv"])

    creator_ids = unique_ids("influencers.csv", creators)
    place_ids = unique_ids("places.csv", places)
    unique_ids("videos.csv", videos)

    for p in places:
        for axis, lo, hi in (("lat", -90, 90), ("lon", -180, 180)):
            try:
                v = float(p[axis])
            except (TypeError, ValueError):
                err("places.csv '%s': %s is not a number (%r)" % (p["id"], axis, p.get(axis)))
                continue
            if not lo <= v <= hi:
                err("places.csv '%s': %s out of range (%s)" % (p["id"], axis, v))

    for c in creators:
        if not any((c.get(k) or "").strip()
                   for k in ("youtube", "instagram", "tiktok", "facebook", "website")):
            warn("influencers.csv '%s': no link on any platform" % c["id"])

    used_places = set()
    for v in videos:
        vid = v["id"]
        if v["influencer_id"] not in creator_ids:
            err("videos.csv '%s': unknown influencer_id '%s'" % (vid, v["influencer_id"]))
        for pid in [x.strip() for x in (v.get("places") or "").split(";") if x.strip()]:
            if pid not in place_ids:
                err("videos.csv '%s': unknown place id '%s'" % (vid, pid))
            else:
                used_places.add(pid)
        try:
            y0, y1 = int(float(v["year_start"])), int(float(v["year_end"]))
        except (TypeError, ValueError):
            err("videos.csv '%s': year_start/year_end must be numbers (got %r, %r)"
                % (vid, v.get("year_start"), v.get("year_end")))
        else:
            if y1 < y0:
                err("videos.csv '%s': year_end (%d) before year_start (%d)" % (vid, y1, y0))
            if y1 > 2100:
                warn("videos.csv '%s': year_end %d looks like a typo" % (vid, y1))
        plat = (v.get("platform") or "").lower()
        if plat not in PLATFORMS:
            warn("videos.csv '%s': unusual platform '%s' (known: %s)"
                 % (vid, plat, ", ".join(sorted(PLATFORMS))))
        url = (v.get("url") or "").strip()
        if not url:
            warn("videos.csv '%s': no url" % vid)
        elif not url.startswith(("http://", "https://")):
            err("videos.csv '%s': url is not absolute (%r)" % (vid, url))
        if not (v.get("places") or "").strip():
            warn("videos.csv '%s': no place linked — it will not appear on the map" % vid)

    orphan = sorted(place_ids - used_places)
    if orphan:
        warn("places.csv: %d place(s) referenced by no video: %s"
             % (len(orphan), ", ".join(orphan[:10]) + ("…" if len(orphan) > 10 else "")))

    unverified = sum(1 for v in videos if (v.get("verified") or "").lower() != "yes")
    print("%d creators · %d places · %d videos (%d unverified)"
          % (len(creators), len(places), len(videos), unverified))
    report()
    return 1 if errors else 0


def report():
    for w in warnings:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    print("\n%d error(s), %d warning(s)" % (len(errors), len(warnings)))


if __name__ == "__main__":
    sys.exit(main())
