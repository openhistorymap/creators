#!/usr/bin/env python3
"""Turn place names into data/places.csv rows using OpenStreetMap's Nominatim.

    python3 tools/geocode.py "Codnor Castle, Derbyshire, UK"
    python3 tools/geocode.py --file queries.txt        # one "id|query" per line

Guessing coordinates from memory puts a site in the wrong field or the wrong
valley; this looks them up instead. Output is ready to append to
data/places.csv — always eyeball it before you do.

Nominatim's usage policy requires an identifying User-Agent and at most one
request per second. Both are respected here, so a long list takes a while.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

UA = "ohm-creators-directory/1.0 (https://github.com/openhistorymap/creators)"
ENDPOINT = "https://nominatim.openstreetmap.org/search?"


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:40]


def lookup(query):
    url = ENDPOINT + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "addressdetails": 1,
         "accept-language": "en"})
    # accept-language=en, or the country comes back as 中国 / مصر and the
    # gazetteer stops being consistently English.
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = json.load(r)
    if not data:
        return None
    hit = data[0]
    addr = hit.get("address", {})
    country = addr.get("country", "")
    return float(hit["lat"]), float(hit["lon"]), hit.get("display_name", ""), country


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*", help='one or more "query" strings')
    ap.add_argument("--file", help='file of "id|query" lines (id optional)')
    args = ap.parse_args()

    jobs = []
    if args.file:
        for line in open(args.file, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pid, _, q = line.partition("|")
            jobs.append((pid.strip() if q else "", (q or pid).strip()))
    jobs += [("", q) for q in args.query]
    if not jobs:
        ap.error("give a query or --file")

    ok = miss = 0
    for pid, q in jobs:
        try:
            hit = lookup(q)
        except Exception as e:
            print("# ERROR  %s -> %s" % (q, e), file=sys.stderr)
            miss += 1
            time.sleep(1.1)
            continue
        if not hit:
            print("# NO RESULT  %s" % q, file=sys.stderr)
            miss += 1
            time.sleep(1.1)
            continue
        lat, lon, display, country = hit
        name = q.split(",")[0].strip()
        sys.stdout.write("%s,%s,%.4f,%.4f,%s,\n"
                         % (pid or slugify(name), name, lat, lon, country))
        print("# %-34s %s" % (pid or slugify(name), display[:80]), file=sys.stderr)
        ok += 1
        time.sleep(1.1)          # Nominatim: one request per second, max
    print("# %d resolved, %d unresolved" % (ok, miss), file=sys.stderr)


if __name__ == "__main__":
    main()
