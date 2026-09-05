#!/usr/bin/env python3
"""Build directory.db from the CSVs, for querying / joining from other OHM tools.

The CSVs stay the source of truth; this database is a disposable derived artifact.

Usage:  python3 tools/build_sqlite.py [--data DIR] [--out directory.db]
"""
import argparse
import csv
import os
import sqlite3

SCHEMA = """
DROP TABLE IF EXISTS influencers;
DROP TABLE IF EXISTS places;
DROP TABLE IF EXISTS videos;
DROP TABLE IF EXISTS video_places;
DROP TABLE IF EXISTS video_tags;
DROP VIEW  IF EXISTS v_directory;

CREATE TABLE influencers (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, handle TEXT, youtube_channel_id TEXT,
  youtube TEXT, instagram TEXT, tiktok TEXT, facebook TEXT, website TEXT,
  language TEXT, focus TEXT, avatar_url TEXT, verified TEXT, notes TEXT
);

CREATE TABLE places (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  lat REAL NOT NULL, lon REAL NOT NULL, country TEXT, wikidata TEXT
);

CREATE TABLE videos (
  id TEXT PRIMARY KEY,
  influencer_id TEXT NOT NULL REFERENCES influencers(id),
  title TEXT NOT NULL, platform TEXT, url TEXT, thumbnail TEXT, published TEXT,
  year_start INTEGER, year_end INTEGER, era TEXT, verified TEXT, notes TEXT
);

CREATE TABLE video_places (
  video_id TEXT NOT NULL REFERENCES videos(id),
  place_id TEXT NOT NULL REFERENCES places(id),
  PRIMARY KEY (video_id, place_id)
);

CREATE TABLE video_tags (
  video_id TEXT NOT NULL REFERENCES videos(id),
  tag TEXT NOT NULL,
  PRIMARY KEY (video_id, tag)
);

CREATE INDEX idx_videos_years ON videos(year_start, year_end);
CREATE INDEX idx_videos_creator ON videos(influencer_id);
CREATE INDEX idx_vp_place ON video_places(place_id);
CREATE INDEX idx_vt_tag ON video_tags(tag);

CREATE VIEW v_directory AS
SELECT v.id, v.title, v.platform, v.url,
       v.year_start, v.year_end, v.era,
       i.name AS creator, i.handle,
       group_concat(p.name, ' | ') AS places,
       (SELECT group_concat(tag, ';') FROM video_tags t WHERE t.video_id = v.id) AS tags
FROM videos v
JOIN influencers i ON i.id = v.influencer_id
LEFT JOIN video_places vp ON vp.video_id = v.id
LEFT JOIN places p ON p.id = vp.place_id
GROUP BY v.id
ORDER BY v.year_start;
"""


def rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def split(value):
    return [x.strip() for x in (value or "").split(";") if x.strip()]


def as_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(root, "data"))
    ap.add_argument("--out", default=os.path.join(root, "directory.db"))
    args = ap.parse_args()

    creators = rows(os.path.join(args.data, "influencers.csv"))
    places = rows(os.path.join(args.data, "places.csv"))
    videos = rows(os.path.join(args.data, "videos.csv"))

    if os.path.exists(args.out):
        os.remove(args.out)
    con = sqlite3.connect(args.out)
    con.executescript(SCHEMA)

    con.executemany(
        "INSERT INTO influencers VALUES (:id,:name,:handle,:youtube_channel_id,:youtube,"
        ":instagram,:tiktok,:facebook,:website,:language,:focus,:avatar_url,:verified,:notes)",
        [{k: c.get(k, "") for k in
          ("id", "name", "handle", "youtube_channel_id", "youtube", "instagram", "tiktok",
           "facebook", "website", "language", "focus", "avatar_url", "verified",
           "notes")} for c in creators])

    con.executemany(
        "INSERT INTO places VALUES (?,?,?,?,?,?)",
        [(p["id"], p["name"], float(p["lat"]), float(p["lon"]),
          p.get("country", ""), p.get("wikidata", "")) for p in places])

    con.executemany(
        "INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [(v["id"], v["influencer_id"], v["title"], v.get("platform", ""), v.get("url", ""),
          v.get("thumbnail", ""), v.get("published", ""),
          as_int(v.get("year_start")), as_int(v.get("year_end")),
          v.get("era", ""), v.get("verified", ""), v.get("notes", "")) for v in videos])

    con.executemany("INSERT OR IGNORE INTO video_places VALUES (?,?)",
                    [(v["id"], pid) for v in videos for pid in split(v.get("places"))])
    con.executemany("INSERT OR IGNORE INTO video_tags VALUES (?,?)",
                    [(v["id"], tag) for v in videos for tag in split(v.get("tags"))])

    con.commit()
    counts = {t: con.execute("SELECT count(*) FROM " + t).fetchone()[0]
              for t in ("influencers", "places", "videos", "video_places", "video_tags")}
    con.close()
    print("wrote %s" % args.out)
    print("  " + " · ".join("%s=%d" % kv for kv in counts.items()))


if __name__ == "__main__":
    main()
