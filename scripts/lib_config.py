"""Pfad- und Config-Helfer."""
from __future__ import annotations
import os
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "topics"
DOCS_DIR = ROOT / "docs"
EPISODES_DIR = DOCS_DIR / "episodes"
FEEDS_DIR = DOCS_DIR / "feeds"
IMAGES_DIR = DOCS_DIR / "images"
BUILD_DIR = ROOT / "build"   # lokale MP3-Ausgabe (gitignored); Hosting läuft über Releases

SLUG_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")


def validate_slug(slug: str) -> str:
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"Ungültiger Slug (erlaubt: a-z, 0-9, '-', 1-40 Zeichen): {slug!r}")
    return slug


def load_topic(slug: str) -> dict:
    validate_slug(slug)
    path = TOPICS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Topic-Config nicht gefunden: {path}")
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg.setdefault("slug", slug)
    cfg.setdefault("language", "de")
    cfg.setdefault("voice_model", "eleven_multilingual_v2")
    cfg.setdefault("target_minutes", 5)
    cfg.setdefault("cover_image", "default-cover.png")
    cfg.setdefault("feed_max_episodes", 30)
    cfg.setdefault("title", slug.title())
    cfg.setdefault("description", f"Tägliches {cfg['title']}-Briefing.")
    return cfg


def list_topics() -> list[str]:
    return sorted(p.stem for p in TOPICS_DIR.glob("*.yaml"))


def site_base_url() -> str:
    return os.environ.get("PODCAST_BASE_URL", "").rstrip("/")
