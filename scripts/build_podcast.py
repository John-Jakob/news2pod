#!/usr/bin/env python3
"""Baut die heutige Podcast-Folge für ein Topic und aktualisiert den RSS-Feed.

Beispiel:
    PODCAST_BASE_URL=https://<user>.github.io/news2pod \
    ANTHROPIC_API_KEY=... ELEVENLABS_API_KEY=... \
    python scripts/build_podcast.py ai
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_config import (
    EPISODES_DIR,
    FEEDS_DIR,
    DOCS_DIR,
    ROOT,
    load_topic,
    list_topics,
    site_base_url,
)
from lib_research import research_and_write_script
from lib_audio import synthesize_episode
from lib_feed import build_feed, build_index, mp3_duration_seconds


def _recent_episode_summaries(episodes_dir: Path, n: int = 3) -> list[dict]:
    """Liest die letzten n Sidecar-JSONs für Dedup-Kontext."""
    out: list[dict] = []
    for sidecar in sorted(episodes_dir.glob("*.json"), reverse=True)[:n]:
        try:
            m = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "date": sidecar.stem,
            "title": m.get("title", ""),
            "headlines": [s.get("headline", "") for s in (m.get("sources") or [])],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Tagesfolge bauen.")
    ap.add_argument("slug", help="Topic-Slug (z.B. 'ai')")
    ap.add_argument("--force", action="store_true", help="bestehende Folge überschreiben")
    ap.add_argument("--feed-only", action="store_true", help="kein neues Audio – nur Feed neu bauen")
    args = ap.parse_args()

    topic = load_topic(args.slug)
    tz = ZoneInfo("Europe/Berlin")
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    today_human = now.strftime("%A, %-d. %B %Y")

    episodes_dir = EPISODES_DIR / args.slug
    episodes_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = episodes_dir / f"{date_str}.mp3"
    meta_path = episodes_dir / f"{date_str}.json"

    if args.feed_only:
        print("Modus: nur Feed neu bauen.")
    elif mp3_path.exists() and not args.force:
        print(f"Folge existiert bereits: {mp3_path.relative_to(ROOT)} (nutze --force).")
    else:
        target_words = int(topic["target_minutes"]) * 150
        recent = _recent_episode_summaries(episodes_dir, n=3)
        if recent:
            print(f"[1/3] Recherche & Skript ({args.slug}, ~{target_words} Wörter, Dedup gegen {len(recent)} letzte Folge(n))…")
        else:
            print(f"[1/3] Recherche & Skript ({args.slug}, ~{target_words} Wörter)…")
        result = research_and_write_script(topic, target_words=target_words,
                                           today_human=today_human,
                                           recent_episodes=recent)
        word_count = len(result["script"].split())
        chunk_count = result["script"].count("===") + 1
        print(f"      Skript: {word_count} Wörter, {chunk_count} Blöcke, {len(result['sources'])} Quellen.")

        if not result["script"].strip():
            print("FEHLER: Leeres Skript erhalten. Abbruch.", file=sys.stderr)
            return 2

        provider = topic.get("tts_provider", "elevenlabs" if topic.get("voice_id") else "openai")
        voice_label = topic.get("voice") or topic.get("voice_id") or "default"
        print(f"[2/3] TTS via {provider} (voice {voice_label}) + Concat + Loudnorm…")
        synthesize_episode(script=result["script"], topic=topic, out_path=mp3_path)

        duration_sec = mp3_duration_seconds(mp3_path)
        pub_iso = now.replace(hour=6, minute=0, second=0, microsecond=0).isoformat()
        meta = {
            "title": result["title"],
            "teaser": result["teaser"],
            "pubDate": pub_iso,
            "duration_seconds": duration_sec,
            "model": result["model"],
            "sources": result["sources"],
            "script": result["script"],
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        size_kb = mp3_path.stat().st_size // 1024
        print(f"      Audio: {mp3_path.relative_to(ROOT)} ({duration_sec}s, {size_kb} KB)")

    base = site_base_url()
    if not base:
        print("HINWEIS: PODCAST_BASE_URL nicht gesetzt – Feed-URLs werden relativ. Für Podcatcher absolute URL setzen.", file=sys.stderr)

    print("[3/3] RSS-Feed & Index aktualisieren…")
    feed_path = FEEDS_DIR / f"{args.slug}.xml"
    build_feed(topic, base, episodes_dir, feed_path)
    all_topics = [load_topic(s) for s in list_topics()]
    build_index(all_topics, base, DOCS_DIR / "index.html")
    print(f"      Feed:  {feed_path.relative_to(ROOT)}")
    print(f"      Index: {(DOCS_DIR / 'index.html').relative_to(ROOT)}")
    print("Fertig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
