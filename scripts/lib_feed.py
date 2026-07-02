"""RSS-Feed-Generierung (iTunes-Podcast-Format) aus den Episode-Dateien."""
from __future__ import annotations
import json
import re
from datetime import datetime
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

from mutagen.mp3 import MP3

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def mp3_duration_seconds(mp3_path: Path) -> int:
    try:
        return int(MP3(str(mp3_path)).info.length)
    except Exception:
        return 300


def format_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def _shownotes_html(meta: dict) -> str:
    teaser = meta.get("teaser", "") or ""
    parts = []
    if teaser:
        parts.append(f"<p>{escape(teaser)}</p>")
    sources = meta.get("sources") or []
    valid = [s for s in sources if s.get("url") and s.get("headline")]
    if valid:
        items = []
        for s in valid:
            url = escape(s["url"], {'"': "&quot;"})
            head = escape(s["headline"])
            src = escape(s.get("source", "") or "")
            tail = f" <em>({src})</em>" if src else ""
            items.append(f'<li><a href="{url}">{head}</a>{tail}</li>')
        parts.append("<p><strong>Heutige Quellen:</strong></p>\n<ul>\n" + "\n".join(items) + "\n</ul>")
    return "\n".join(parts)


def build_feed(topic_cfg: dict, base_url: str, episodes_dir: Path, feed_path: Path) -> Path:
    slug = topic_cfg["slug"]
    title = topic_cfg["title"]
    description = topic_cfg.get("description", "")
    cover_image = topic_cfg.get("cover_image", "default-cover.png")
    cover_url = f"{base_url}/images/{cover_image}" if base_url else f"images/{cover_image}"
    feed_url = f"{base_url}/feeds/{slug}.xml" if base_url else f"feeds/{slug}.xml"
    link = f"{base_url}/" if base_url else "./"
    owner_email = topic_cfg.get("owner_email", "chat@hh3.info")
    owner_name = topic_cfg.get("owner_name", "news2pod")

    items_xml: list[str] = []
    sidecars = [s for s in sorted(episodes_dir.glob("*.json"), reverse=True)
                if DATE_RE.fullmatch(s.stem)]
    max_episodes = int(topic_cfg.get("feed_max_episodes", 30))
    for sidecar in sidecars[:max_episodes]:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        date = sidecar.stem  # YYYY-MM-DD
        local_mp3 = sidecar.with_suffix(".mp3")
        # Bevorzugt: Release-Asset-URL aus dem Sidecar. Legacy-Fallback: MP3 neben dem JSON.
        mp3_url = meta.get("mp3_url")
        if not mp3_url:
            if not local_mp3.exists():
                continue
            mp3_url = f"{base_url}/episodes/{slug}/{date}.mp3" if base_url else f"episodes/{slug}/{date}.mp3"
        pub_iso = meta.get("pubDate", f"{date}T06:00:00+02:00")
        try:
            pub_dt = datetime.fromisoformat(pub_iso)
        except ValueError:
            pub_dt = datetime.fromisoformat(f"{date}T06:00:00+02:00")
        size = int(meta.get("size_bytes") or (local_mp3.stat().st_size if local_mp3.exists() else 0))
        duration_sec = int(meta.get("duration_seconds")
                           or (mp3_duration_seconds(local_mp3) if local_mp3.exists() else 300))
        ep_title = meta.get("title") or f"{title} – {date}"
        ep_desc = meta.get("teaser") or ""
        shownotes = _shownotes_html(meta)
        guid = f"{slug}-{date}"

        items_xml.append(f"""    <item>
      <title>{escape(ep_title)}</title>
      <description><![CDATA[{shownotes}]]></description>
      <content:encoded><![CDATA[{shownotes}]]></content:encoded>
      <itunes:summary>{escape(ep_desc)}</itunes:summary>
      <pubDate>{format_datetime(pub_dt)}</pubDate>
      <guid isPermaLink="false">{guid}</guid>
      <enclosure url="{escape(mp3_url, {'"': '&quot;'})}" length="{size}" type="audio/mpeg"/>
      <itunes:duration>{format_duration(duration_sec)}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    items_str = "\n".join(items_xml)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(title)}</title>
    <link>{link}</link>
    <atom:link href="{escape(feed_url, {'"': '&quot;'})}" rel="self" type="application/rss+xml"/>
    <description>{escape(description)}</description>
    <language>de-DE</language>
    <itunes:author>{escape(owner_name)}</itunes:author>
    <itunes:summary>{escape(description)}</itunes:summary>
    <itunes:category text="News"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:image href="{escape(cover_url, {'"': '&quot;'})}"/>
    <itunes:owner>
      <itunes:name>{escape(owner_name)}</itunes:name>
      <itunes:email>{escape(owner_email)}</itunes:email>
    </itunes:owner>
{items_str}
  </channel>
</rss>
"""
    feed_path.parent.mkdir(parents=True, exist_ok=True)
    feed_path.write_text(xml, encoding="utf-8")
    return feed_path


def build_index(topic_cfgs: list[dict], base_url: str, out_path: Path) -> Path:
    items = []
    for cfg in topic_cfgs:
        slug = cfg["slug"]
        feed_url = f"{base_url}/feeds/{slug}.xml" if base_url else f"feeds/{slug}.xml"
        items.append(f"""      <li>
        <h2>{escape(cfg['title'])}</h2>
        <p>{escape(cfg.get('description',''))}</p>
        <p><a href="{escape(feed_url)}">Feed-URL kopieren</a></p>
        <p><code>{escape(feed_url)}</code></p>
      </li>""")
    html = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<title>news2pod</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; max-width: 720px; margin: 3rem auto; padding: 0 1rem; color: #111; line-height: 1.55; }}
  h1 {{ font-weight: 600; margin-bottom: .25rem; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ border: 1px solid #e3e3e3; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: .75rem; }}
  li h2 {{ margin: 0 0 .25rem; font-size: 1.15rem; }}
  code {{ background: #f4f4f5; padding: 2px 6px; border-radius: 4px; font-size: .9em; word-break: break-all; }}
  a {{ color: #2050d0; }}
  small {{ color: #666; }}
</style>
</head>
<body>
<h1>news2pod</h1>
<p><small>Tägliche KI-kuratierte 5-Minuten-Podcasts. Abonniere den Feed in deinem Podcatcher.</small></p>
<ul>
{chr(10).join(items)}
</ul>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
